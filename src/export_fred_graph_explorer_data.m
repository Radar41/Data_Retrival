function outFile = export_fred_graph_explorer_data(options)
%EXPORT_FRED_GRAPH_EXPLORER_DATA Snapshot parts of the FRED graph for docs/graph_explorer.
%
% outFile = export_fred_graph_explorer_data()
% outFile = export_fred_graph_explorer_data(SeriesIds=["UNRATE" "GDPC1"])
%
% Queries the live Neo4j database over the HTTP API (resultDataContents =
% "graph", the shape neo4jd3 renders) and writes
% docs/graph_explorer/fred_graph_data.js, a script that sets
% window.FRED_GRAPH. index.html in the same folder loads it, so the page
% works from a local file, a local web server, or a published artifact.
%
% Views written:
%   schema     CALL db.schema.visualization(): one node per label, one
%              edge per relationship pattern
%   <series>   one per SeriesIds entry: the series, its release, source,
%              frequency, units, seasonal adjustment, category chain to the
%              root, tags and tag groups, the catalog snapshots that
%              contain it, the latest press release describing its release
%              with two chunks, and the two latest release dates
%   lineage    the data-list side: Provider, Dataset, StagingRun,
%              RawArtifact, SourceMember, three series with their variants,
%              and the snapshot/raw-response provenance
%
% Chunk embeddings (768 floats) are replaced by embedding_dims.
% The password comes from Password, else NEO4J_PASSWORD, else the MATLAB
% vault secret "neo4j_pw" (same as dbdesign.check_graph_model).

arguments
    options.ProjectRoot (1,1) string = string(fileparts(fileparts(mfilename("fullpath"))))
    options.OutputFile (1,1) string = ""
    options.SeriesIds (1,:) string = ["UNRATE", "PAYEMS", "GDPC1", "CPIAUCSL", "INDPRO"]
    options.Url (1,1) string = "http://localhost:7474"
    options.Database (1,1) string = "neo4j"
    options.Username (1,1) string = "neo4j"
    options.Password (1,1) string = ""
end

outFile = options.OutputFile;

if strlength(outFile) == 0
    outFile = fullfile(options.ProjectRoot, "docs", "graph_explorer", "fred_graph_data.js");
end

password = options.Password;

if strlength(password) == 0
    password = string(getenv("NEO4J_PASSWORD"));
end

if strlength(password) == 0
    password = string(getSecret("neo4j_pw"));
end

conn = struct("Url", options.Url, "Database", options.Database, ...
    "Username", options.Username, "Password", password);

views = {};

views{end + 1} = makeView("schema", "Schema", "schema", ...
    "Every label and relationship pattern in the database (db.schema.visualization). " + ...
    "Hover a label for its constraints.", ...
    "CALL db.schema.visualization()", struct());

seriesStatements = [ ...
    "MATCH p = (s:Series {series_id: $id})-[:IN_RELEASE|HAS_FREQUENCY|MEASURED_IN|ADJUSTED|IN_CATEGORY|TAGGED]->() RETURN p"
    "MATCH p = (s:Series {series_id: $id})-[:TAGGED]->(:Tag)-[:IN_GROUP]->(:TagGroup) RETURN p"
    "MATCH p = (s:Series {series_id: $id})-[:IN_RELEASE]->(:Release)-[:PUBLISHED_BY]->(:Source) RETURN p"
    "MATCH p = (s:Series {series_id: $id})-[:IN_CATEGORY]->(:Category)-[:CHILD_OF*0..10]->(:Category) RETURN p"
    "MATCH p = (:Provider)-[:EXPOSED_IN]->(:CatalogSnapshot)-[:CONTAINS_SERIES]->(s:Series {series_id: $id}) RETURN p"
    "MATCH (s:Series {series_id: $id})-[:IN_RELEASE]->(r:Release) " + ...
        "CALL (r) { MATCH p = (d:Document)-[:DESCRIBES]->(r) RETURN p, d ORDER BY d.release_date DESC LIMIT 1 } " + ...
        "CALL (d) { MATCH q = (d)-[:HAS_CHUNK]->(c:Chunk) RETURN q ORDER BY c.seq LIMIT 2 } " + ...
        "RETURN p, q"
    "MATCH (s:Series {series_id: $id})-[:IN_RELEASE]->(r:Release) " + ...
        "CALL (r) { MATCH p = (r)-[:SCHEDULED_ON]->(rd:ReleaseDate) RETURN p ORDER BY rd.date DESC LIMIT 2 } " + ...
        "RETURN p"];

for id = options.SeriesIds
    views{end + 1} = makeView(id, id, "series", "", seriesStatements, struct("id", id)); %#ok<AGROW>
end

views{end + 1} = makeView("lineage", "Lineage", "lineage", ...
    "The data-list ingestion side and the API provenance: datasets, staging runs, raw files, " + ...
    "source members and series variants, plus the catalog snapshots and their raw responses.", [ ...
    "MATCH p = (:Provider)-[:PUBLISHED]->(:Dataset)-[:HAS_STAGING_RUN|HAS_RAW_ARTIFACT|HAS_SOURCE_MEMBER]->() RETURN p"
    "MATCH p = (:Provider)-[:EXPOSED_IN]->(:CatalogSnapshot)-[:RAW_RESPONSE]->(:ApiResponseArtifact) RETURN p"
    "MATCH (d:Dataset)-[:CONTAINS_SERIES]->(s:Series) WITH d, s ORDER BY s.series_id LIMIT 3 " + ...
        "MATCH p = (d)-[:CONTAINS_SERIES]->(s)-[:HAS_TRANSFORMATION]->(:SeriesVariant)-[:AVAILABLE_IN]->(:SourceMember) RETURN p"], ...
    struct());

for k = 1:numel(views)

    v = views{k};
    response = runCypher(conn, v.statements, v.parameters, "graph");
    v.graph = mergeGraph(response);

    if v.kind == "series"
        v.title = seriesTitle(v.graph, v.id);
        v.description = "Everything attached to " + v.id + ": release and source, frequency, units, " + ...
            "seasonal adjustment, category path to the root, tags and their groups, the catalog " + ...
            "snapshots that list it, the latest press release with two text chunks, and the next release dates.";
    end

    v = rmfield(v, ["statements", "parameters"]);
    views{k} = v;
    fprintf("  %-10s %4d nodes %4d relationships\n", v.id, numel(v.graph.nodes), numel(v.graph.relationships));

end

meta = struct();
meta.exported_at_utc = string(datetime("now", TimeZone="UTC", Format="yyyy-MM-dd'T'HH:mm:ss'Z'"));
meta.database = options.Database;
meta.url = options.Url;
meta.series_ids = cellstr(options.SeriesIds);

rows = runCypher(conn, [ ...
    "CALL dbms.components() YIELD name, versions RETURN name + ' ' + versions[0] AS line"
    "MATCH (n) WITH labels(n)[0] AS l, count(*) AS c ORDER BY c DESC RETURN l + '|' + toString(c) AS line"
    "MATCH ()-[r]->() WITH type(r) AS t, count(*) AS c ORDER BY c DESC RETURN t + '|' + toString(c) AS line"], struct(), "row");

meta.neo4j_version = rowLines(rows, 1);
meta.neo4j_version = meta.neo4j_version(1);
meta.label_counts = countPairs(rowLines(rows, 2));
meta.relationship_counts = countPairs(rowLines(rows, 3));

out = struct("meta", meta, "views", {views});

folder = fileparts(outFile);

if strlength(folder) > 0 && ~isfolder(folder)
    mkdir(folder);
end

text = "// Generated by src/export_fred_graph_explorer_data.m on " + meta.exported_at_utc + ...
    ". Do not edit; rerun the exporter." + newline + ...
    "window.FRED_GRAPH = " + jsonencode(out, PrettyPrint=true) + ";" + newline;
writelines(text, outFile);
fprintf("Wrote %s\n", outFile);

end


function v = makeView(id, title, kind, description, statements, parameters)

v = struct("id", string(id), "title", string(title), "kind", string(kind), ...
    "description", string(description), "statements", string(statements(:)'), ...
    "parameters", parameters);

end


function response = runCypher(conn, statements, parameters, contents)

stmts = cell(1, numel(statements));

for k = 1:numel(statements)
    stmts{k} = struct("statement", statements(k), "parameters", parameters, ...
        "resultDataContents", {{char(contents)}});
end

body = struct("statements", {stmts});

webOpts = weboptions("Username", conn.Username, "Password", conn.Password, ...
    "MediaType", "application/json", "ContentType", "json", "Timeout", 120);

response = webwrite(conn.Url + "/db/" + conn.Database + "/tx/commit", body, webOpts);

if ~isempty(response.errors)
    error("export_fred_graph_explorer_data:Cypher", "Neo4j error: %s", jsonencode(response.errors));
end

end


function graph = mergeGraph(response)

% Union of every row's graph, deduplicated by id, insertion order kept.
% Cells (not struct arrays) so jsonencode always writes JSON arrays.

nodes = {};
rels = {};
seenNodes = containers.Map("KeyType", "char", "ValueType", "logical");
seenRels = containers.Map("KeyType", "char", "ValueType", "logical");

for result = asCell(response.results)

    for datum = asCell(result{1}.data)

        for n = asCell(datum{1}.graph.nodes)

            node = n{1};

            if isKey(seenNodes, node.id)
                continue
            end

            seenNodes(node.id) = true;
            nodes{end + 1} = struct("id", string(node.id), "labels", {cellstr(node.labels)}, ...
                "properties", trimProperties(node.properties)); %#ok<AGROW>

        end

        for r = asCell(datum{1}.graph.relationships)

            rel = r{1};

            if isKey(seenRels, rel.id)
                continue
            end

            seenRels(rel.id) = true;
            rels{end + 1} = struct("id", string(rel.id), "type", string(rel.type), ...
                "startNode", string(rel.startNode), "endNode", string(rel.endNode), ...
                "properties", rel.properties); %#ok<AGROW>

        end

    end

end

graph = struct("nodes", {nodes}, "relationships", {rels});

end


function p = trimProperties(p)

if isfield(p, "embedding")
    n = numel(p.embedding);
    p = rmfield(p, "embedding");
    p.embedding_dims = n;
end

end


function c = asCell(x)

if iscell(x)
    c = reshape(x, 1, []);
elseif isempty(x)
    c = {};
else
    c = reshape(num2cell(x), 1, []);
end

end


function title = seriesTitle(graph, id)

title = id;

for n = graph.nodes

    node = n{1};

    if any(string(node.labels) == "Series") && isfield(node.properties, "series_id") && ...
            string(node.properties.series_id) == id
        title = id + " · " + string(node.properties.title);
        return
    end

end

end


function lines = rowLines(response, k)

results = asCell(response.results);
data = asCell(results{k}.data);
lines = strings(1, numel(data));

for j = 1:numel(data)
    lines(j) = string(data{j}.row);
end

end


function pairs = countPairs(lines)

pairs = cell(1, numel(lines));

for j = 1:numel(lines)
    parts = split(lines(j), "|");
    pairs{j} = struct("name", parts(1), "count", double(parts(2)));
end

end
