function problems = check_graph_model(graph, relationalModel, options)
%CHECK_GRAPH_MODEL List every difference between the graph model and reality.
%
% problems = dbdesign.check_graph_model(graph, relationalModel)
% problems = dbdesign.check_graph_model(graph, relationalModel, Live=false)
%
% 1. Relational coverage: every table becomes a label, or is a join table
%    that became a relationship, or is listed in graph.excluded; every FK
%    became a relationship, belongs to a join table, or is excluded.
% 2. Live database (unless Live=false), through the Neo4j HTTP API:
%    labels, properties with their stored types and whether every node has
%    them, relationship patterns (from)-[TYPE]->(to), uniqueness
%    constraints, and the indexes not owned by a constraint.
%
% The password comes from the Password option, else the NEO4J_PASSWORD
% environment variable, else the MATLAB vault secret "neo4j_pw".
% Returns a string column of problems; empty means everything agrees.

arguments
    graph (1,1) struct
    relationalModel (1,1) struct
    options.Live (1,1) logical = true
    options.Url (1,1) string = "http://localhost:21004"
    options.Database (1,1) string = "neo4j"
    options.Username (1,1) string = "neo4j"
    options.Password (1,1) string = ""
end

problems = relationalCoverage(graph, relationalModel);

if ~options.Live
    return
end

password = options.Password;

if strlength(password) == 0
    password = string(getenv("NEO4J_PASSWORD"));
end

if strlength(password) == 0
    password = string(getSecret("neo4j_pw"));
end

lines = cypherLines(options, password, [ ...
    "CALL db.labels() YIELD label RETURN label AS line"
    "CALL db.schema.nodeTypeProperties() YIELD nodeLabels, propertyName, propertyTypes, mandatory " + ...
        "WHERE propertyName IS NOT NULL " + ...
        "RETURN nodeLabels[0] + '|' + propertyName + '|' + propertyTypes[0] + '|' + toString(mandatory) AS line"
    "MATCH (a)-[r]->(b) RETURN DISTINCT labels(a)[0] + '|' + type(r) + '|' + labels(b)[0] AS line"
    "CALL db.schema.relTypeProperties() YIELD relType, propertyName WHERE propertyName IS NOT NULL " + ...
        "RETURN relType + '|' + propertyName AS line"
    "SHOW CONSTRAINTS YIELD name, labelsOrTypes, properties, type " + ...
        "RETURN name + '|' + labelsOrTypes[0] + '|' + reduce(s = '', p IN properties | s + ',' + p) + '|' + type AS line"
    "SHOW INDEXES YIELD name, type, labelsOrTypes, properties, owningConstraint " + ...
        "WHERE owningConstraint IS NULL AND type <> 'LOOKUP' " + ...
        "RETURN name + '|' + type + '|' + labelsOrTypes[0] + '|' + reduce(s = '', p IN properties | s + ',' + p) AS line"]);

[liveLabels, liveProps, livePatterns, liveRelProps, liveConstraints, liveIndexes] = lines{:};

labelNames = [graph.labels.name];

for n = setdiff(liveLabels, labelNames)'
    problems(end + 1, 1) = ":" + n + " in database, not in model"; %#ok<AGROW>
end

for n = setdiff(labelNames, liveLabels)
    problems(end + 1, 1) = ":" + n + " in model, not in database"; %#ok<AGROW>
end

propParts = splitLines(liveProps, 4);

for lbl = graph.labels'

    live = propParts(propParts(:, 1) == lbl.name, :);

    for n = setdiff(live(:, 2), [lbl.properties.name]')'
        problems(end + 1, 1) = ":" + lbl.name + "." + n + " in database, not in model"; %#ok<AGROW>
    end

    for p = lbl.properties'

        row = live(live(:, 2) == p.name, :);
        where = ":" + lbl.name + "." + p.name;

        if isempty(row)
            problems(end + 1, 1) = where + " in model, not in database"; %#ok<AGROW>
            continue
        end

        if row(3) ~= schemaTypeName(p.type)
            problems(end + 1, 1) = where + ": stored " + row(3) + ", model " + p.type; %#ok<AGROW>
        end

        if (row(4) == "true") ~= p.mandatory
            problems(end + 1, 1) = where + ": on every node = " + row(4) + ", model says " + ...
                string(p.mandatory); %#ok<AGROW>
        end

    end

end

modelPatterns = arrayfun(@(r) r.from + "|" + r.type + "|" + r.to, graph.relationships);

for n = setdiff(livePatterns, modelPatterns)'
    problems(end + 1, 1) = "pattern " + n + " in database, not in model"; %#ok<AGROW>
end

for n = setdiff(modelPatterns, livePatterns)'
    problems(end + 1, 1) = "pattern " + n + " in model, not in database"; %#ok<AGROW>
end

for n = liveRelProps'
    problems(end + 1, 1) = "relationship property " + n + " in database; model has none"; %#ok<AGROW>
end

constraintParts = splitLines(liveConstraints, 4);
keyed = graph.labels(strlength([graph.labels.key_constraint]) > 0);

for lbl = keyed'

    row = constraintParts(constraintParts(:, 1) == lbl.key_constraint, :);

    if isempty(row)
        problems(end + 1, 1) = "constraint " + lbl.key_constraint + " missing"; %#ok<AGROW>
    elseif row(2) ~= lbl.name || row(3) ~= "," + strjoin(lbl.key, ",") || row(4) ~= "UNIQUENESS"
        problems(end + 1, 1) = "constraint " + lbl.key_constraint + " differs: " + ...
            strjoin(row, " "); %#ok<AGROW>
    end

end

for n = setdiff(constraintParts(:, 1), [keyed.key_constraint]')'
    problems(end + 1, 1) = "constraint " + n + " in database, not in model"; %#ok<AGROW>
end

indexParts = splitLines(liveIndexes, 4);

for ix = graph.indexes'

    row = indexParts(indexParts(:, 1) == ix.name, :);

    if isempty(row)
        problems(end + 1, 1) = "index " + ix.name + " missing"; %#ok<AGROW>
    elseif row(2) ~= ix.type || row(3) ~= ix.label || row(4) ~= "," + ix.properties
        problems(end + 1, 1) = "index " + ix.name + " differs: " + strjoin(row, " "); %#ok<AGROW>
    end

end

for n = setdiff(indexParts(:, 1), [graph.indexes.name]')'
    problems(end + 1, 1) = "index " + n + " in database, not in model"; %#ok<AGROW>
end

end


function problems = relationalCoverage(graph, relationalModel)

problems = strings(0, 1);

sources = [graph.relationships.source];
joinTables = extractAfter(sources(startsWith(sources, "table:")), "table:");
mappedFks = extractAfter(sources(startsWith(sources, "fk:")), "fk:");
labelTables = [graph.labels.source_table];
excluded = [graph.excluded.name];

for t = relationalModel.tables'

    if ~ismember(t.name, [labelTables, joinTables, excluded])
        problems(end + 1, 1) = "table " + t.name + " has no label or relationship in the graph"; %#ok<AGROW>
    end

end

for fk = relationalModel.foreign_keys'

    if ~ismember(fk.name, [mappedFks, excluded]) && ~ismember(fk.child, joinTables)
        problems(end + 1, 1) = "FK " + fk.name + " has no relationship in the graph"; %#ok<AGROW>
    end

end

for n = setdiff(joinTables, [relationalModel.tables.name])
    problems(end + 1, 1) = "relationship maps missing join table " + n; %#ok<AGROW>
end

for n = setdiff(mappedFks, [relationalModel.foreign_keys.name])
    problems(end + 1, 1) = "relationship maps missing FK " + n; %#ok<AGROW>
end

end


function results = cypherLines(options, password, statements)

body = struct("statements", {num2cell(struct("statement", cellstr(statements)))'});

webOpts = weboptions( ...
    "Username", options.Username, ...
    "Password", password, ...
    "MediaType", "application/json", ...
    "ContentType", "json", ...
    "Timeout", 60);

url = options.Url + "/db/" + options.Database + "/tx/commit";
response = webwrite(url, body, webOpts);

if ~isempty(response.errors)
    error("dbdesign:check_graph_model:Cypher", "Neo4j error: %s", ...
        jsonencode(response.errors));
end

results = cell(numel(statements), 1);

for k = 1:numel(statements)

    if iscell(response.results)
        result = response.results{k};
    else
        result = response.results(k);
    end

    if isempty(result.data)
        results{k} = strings(0, 1);
        continue
    end

    if iscell(result.data)
        rows = cellfun(@(d) d.row, result.data, "UniformOutput", false);
    else
        rows = {result.data.row};
    end

    results{k} = string(cellfun(@(r) string(r), rows))';
    results{k} = results{k}(:);

end

end


function parts = splitLines(lines, n)

if isempty(lines)
    parts = strings(0, n);
    return
end

parts = split(lines, "|", 2);

end


function name = schemaTypeName(cypherType)

switch cypherType
    case "STRING",         name = "String";
    case "INTEGER",        name = "Long";
    case "FLOAT",          name = "Double";
    case "BOOLEAN",        name = "Boolean";
    case "DATE",           name = "Date";
    case "ZONED DATETIME", name = "DateTime";
    case "LIST<FLOAT>",    name = "FloatArray";
    otherwise,             name = cypherType;
end

end
