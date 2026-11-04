function graph = fred_graph_model(relationalModel)
%FRED_GRAPH_MODEL Canonical description of the FRED catalog graph in Neo4j.
%
% graph = dbdesign.fred_graph_model()
% graph = dbdesign.fred_graph_model(dbdesign.fred_relational_model())
%
% The graph side of the design. Every label and relationship type records
% where it came from in the relational model, following the table-to-graph
% checklist in Neo4j's "Definitive Guide to Graph Databases for the RDBMS
% Developer":
%   - each entity table becomes a node label, each column a property
%   - business keys get uniqueness constraints, lookups get indexes
%   - foreign keys become relationships
%   - join tables become relationships (their columns would become
%     relationship properties; the three here have none)
%
% Labels and relationships with an empty source were added in the graph
% only: the press-release documents (unstructured layer) and the
% provenance/lineage of every load. OBSERVATION is deliberately not in the
% graph: dense vintages stay in SQL (fred_logical_design.md section 7.1).
%
% dbdesign.check_graph_model checks this against the relational model
% (every table and FK accounted for) and against the live Neo4j database.

arguments
    relationalModel (1,1) struct = dbdesign.fred_relational_model()
end

graph = struct();
graph.name = relationalModel.name;
graph.author = relationalModel.author;
graph.course = relationalModel.course;
graph.dbms = "Neo4j Community 2026.07";

graph.layers = struct( ...
    "name", {"catalog"; "documents"; "lineage"}, ...
    "title", {"FRED catalog (from the relational model)"; ...
        "Press releases (unstructured)"; ...
        "Provenance and lineage"}, ...
    "color", {"#e8eef7"; "#eef6ea"; "#f6f0e6"});

% Property rows: {name, Cypher type, mandatory (1/0), source column, note}
% Cypher types: STRING, INTEGER, FLOAT, BOOLEAN, DATE, ZONED DATETIME,
% LIST<FLOAT>. "Mandatory" is observed in the data: Community edition has
% no property-existence constraints, so it is not enforced.
L = struct([]);

L = addLabel(L, "Provider", "lineage", "", "provider_id_unique", "provider_id", { ...
    "provider_id",  "STRING", 1, "", "fred"
    "name",         "STRING", 1, "", ""
    "short_name",   "STRING", 1, "", ""
    "display_name", "STRING", 1, "", ""
    "description",  "STRING", 1, "", ""
    "project",      "STRING", 1, "", ""
    "api_base_url", "STRING", 1, "", ""
    "homepage_url", "STRING", 1, "", ""});

L = addLabel(L, "CatalogSnapshot", "lineage", "", "catalog_snapshot_id_unique", "snapshot_id", { ...
    "snapshot_id",                "STRING",  1, "", "UTC timestamp of the load"
    "provider_id",                "STRING",  1, "", ""
    "endpoint",                   "STRING",  1, "", ""
    "schema_version",             "STRING",  1, "", ""
    "retrieved_at_utc",           "STRING",  0, "", ""
    "request_parameters",         "STRING",  0, "", ""
    "category_count",             "INTEGER", 0, "", ""
    "snapshot_directory",         "STRING",  0, "", ""
    "manifest_file",              "STRING",  0, "", ""
    "normalized_categories_file", "STRING",  0, "", ""
    "neo4j_import_file",          "STRING",  0, "", ""});

L = addLabel(L, "ApiResponseArtifact", "lineage", "", "api_response_artifact_path_unique", "path", { ...
    "path",        "STRING", 1, "", "Raw JSON kept unchanged on disk"
    "provider_id", "STRING", 1, "", ""
    "snapshot_id", "STRING", 1, "", ""
    "endpoint",    "STRING", 1, "", ""
    "format",      "STRING", 1, "", ""
    "kind",        "STRING", 1, "", ""});

L = addLabel(L, "Dataset", "lineage", "", "dataset_id_unique", "dataset_id", { ...
    "dataset_id",              "STRING",  1, "", "FRED public data list"
    "title",                   "STRING",  1, "", ""
    "source_datalist_id",      "STRING",  1, "", ""
    "source_url",              "STRING",  1, "", ""
    "ingestion_status",        "STRING",  1, "", ""
    "audit_status",            "STRING",  1, "", ""
    "audit_at_utc",            "STRING",  1, "", ""
    "metadata_series_count",   "INTEGER", 1, "", ""
    "normalized_series_count", "INTEGER", 1, "", ""});

L = addLabel(L, "RawArtifact", "lineage", "", "raw_artifact_sha256_unique", "sha256", { ...
    "sha256",             "STRING",  1, "", "Content address of the raw file"
    "provider_id",        "STRING",  1, "", ""
    "original_file_name", "STRING",  1, "", ""
    "raw_file_name",      "STRING",  1, "", ""
    "raw_file_path",      "STRING",  1, "", ""
    "bytes",              "INTEGER", 1, "", ""
    "storage_class",      "STRING",  1, "", ""
    "registered_at_utc",  "STRING",  1, "", ""});

L = addLabel(L, "StagingRun", "lineage", "", "", "staging_key", { ...
    "staging_key",                      "STRING",  1, "", ""
    "staging_path",                     "STRING",  1, "", ""
    "raw_archive_sha256",               "STRING",  1, "", ""
    "normalization_status",             "STRING",  1, "", ""
    "audit_status",                     "STRING",  1, "", ""
    "audit_at_utc",                     "STRING",  1, "", ""
    "metadata_series_count",            "INTEGER", 1, "", ""
    "normalized_union_series_count",    "INTEGER", 1, "", ""
    "weekly_normalized_rows",           "INTEGER", 1, "", ""
    "ending_wednesday_normalized_rows", "INTEGER", 1, "", ""});

L = addLabel(L, "SourceMember", "lineage", "", "source_member_key_unique", "member_key", { ...
    "member_key",             "STRING",  1, "", "File inside the data-list archive"
    "dataset_id",             "STRING",  1, "", ""
    "member_path",            "STRING",  1, "", ""
    "frequency_label",        "STRING",  1, "", ""
    "base_series_count",      "INTEGER", 1, "", ""
    "data_column_count",      "INTEGER", 1, "", ""
    "normalized_row_count",   "INTEGER", 1, "", ""
    "nonmissing_value_count", "INTEGER", 1, "", ""});

L = addLabel(L, "SeriesVariant", "lineage", "", "series_variant_key_unique", "variant_key", { ...
    "variant_key",         "STRING", 1, "", "Series x transformation in one member"
    "series_id",           "STRING", 1, "", ""
    "dataset_id",          "STRING", 1, "", ""
    "transformation_code", "STRING", 1, "", "LEVEL, CHG, PCH, ..."
    "frequency_label",     "STRING", 1, "", ""
    "raw_column_name",     "STRING", 1, "", ""
    "source_member_path",  "STRING", 1, "", ""});

L = addLabel(L, "Source", "catalog", "source", "source_key_unique", "source_key", { ...
    "source_key",  "STRING",  1, "",            "Graph key fred:source:<id>"
    "source_id",   "INTEGER", 1, "source_id",   ""
    "provider_id", "STRING",  1, "",            ""
    "name",        "STRING",  1, "source_name", ""
    "link",        "STRING",  0, "source_link", ""});

L = addLabel(L, "Release", "catalog", "release", "release_key_unique", "release_key", { ...
    "release_key",   "STRING",  1, "",              "Graph key fred:release:<id>"
    "release_id",    "INTEGER", 1, "release_id",    ""
    "provider_id",   "STRING",  1, "",              ""
    "name",          "STRING",  1, "release_name",  ""
    "press_release", "BOOLEAN", 1, "press_release", ""
    "link",          "STRING",  0, "release_link",  ""});

L = addLabel(L, "ReleaseDate", "catalog", "release_date", "release_date_key", "rd_key", { ...
    "rd_key",      "STRING", 1, "",             "<release_key>:<date>; NODE KEY is Enterprise-only"
    "release_key", "STRING", 1, "release_id",   "FK value kept: part of rd_key"
    "date",        "DATE",   1, "release_date", ""
    "status",      "STRING", 1, "date_status",  "scheduled | actual"});

L = addLabel(L, "Frequency", "catalog", "frequency", "frequency_code_unique", "code", { ...
    "code", "STRING", 1, "frequency_code", ""
    "name", "STRING", 1, "frequency_name", ""});

L = addLabel(L, "Units", "catalog", "units", "units_code_unique", "code", { ...
    "code", "STRING", 1, "units_code", ""
    "name", "STRING", 1, "units_name", ""});

L = addLabel(L, "SeasonalAdjustment", "catalog", "seasonal_adjustment", "sa_code_unique", "code", { ...
    "code", "STRING", 1, "sa_code", ""
    "name", "STRING", 1, "sa_name", ""});

L = addLabel(L, "Category", "catalog", "category", "category_key_unique", ["provider_id", "category_id"], { ...
    "provider_id",    "STRING",  1, "",              ""
    "category_id",    "STRING",  1, "category_id",   "STRING here, INTEGER in SQL"
    "category_key",   "STRING",  1, "",              ""
    "name",           "STRING",  1, "category_name", ""
    "parent_id",      "STRING",  1, "parent_id",     "FK value kept; '' for the root"
    "is_root",        "BOOLEAN", 1, "",              ""
    "catalog_source", "STRING",  0, "",              ""
    "import_file",    "STRING",  0, "",              ""});

L = addLabel(L, "TagGroup", "catalog", "tag_group", "tag_group_id_unique", "group_id", { ...
    "group_id", "STRING", 1, "group_id",   ""
    "name",     "STRING", 1, "group_name", ""});

L = addLabel(L, "Tag", "catalog", "tag", "tag_name_unique", "tag_name", { ...
    "tag_name",   "STRING",  1, "tag_name",   ""
    "notes",      "STRING",  0, "tag_notes",  ""
    "popularity", "INTEGER", 1, "popularity", ""});

L = addLabel(L, "Series", "catalog", "series", "fred_series_catalog_key_unique", "catalog_key", { ...
    "catalog_key",         "STRING",         1, "",                  "Graph key fred:<series_id>, shared with the data-list graph"
    "series_id",           "STRING",         1, "series_id",         "Indexed, not constrained"
    "title",               "STRING",         1, "title",             ""
    "observation_start",   "DATE",           0, "observation_start", "Derived"
    "observation_end",     "DATE",           0, "observation_end",   "Derived"
    "last_updated",        "ZONED DATETIME", 0, "last_updated",      ""
    "popularity",          "INTEGER",        0, "popularity",        ""
    "notes",               "STRING",         0, "notes",             ""
    "series_catalog_key",  "STRING",         0, "",                  ""
    "provider_id",         "STRING",         0, "",                  ""
    "dataset_id",          "STRING",         0, "",                  "Data-list series only (41)"
    "source_datalist_id",  "STRING",         0, "",                  "Data-list series only"
    "raw_archive_sha256",  "STRING",         0, "",                  "Data-list series only"
    "frequency",           "STRING",         0, "",                  "Data-list text copy"
    "seasonal_adjustment", "STRING",         0, "",                  "Data-list text copy"
    "units_level",         "STRING",         0, "",                  "Data-list text copy"
    "release",             "STRING",         0, "",                  "Data-list text copy"
    "source",              "STRING",         0, "",                  "Data-list text copy"
    "real_time_start",     "STRING",         0, "",                  "Data-list text copy"
    "period_end",          "STRING",         0, "",                  "Data-list text copy"});

L = addLabel(L, "Document", "documents", "", "document_id_unique", "doc_id", { ...
    "doc_id",      "STRING", 1, "", "<release_key>:<date>"
    "release_key", "STRING", 1, "", "Links to Release and to SQL release_id"
    "release_date","DATE",   1, "", "Matches a release_date row"
    "title",       "STRING", 1, "", ""
    "source_name", "STRING", 1, "", "Agency"
    "file_type",   "STRING", 1, "", ""
    "path",        "STRING", 1, "", "data/raw/documents/<release_id>/<date>.pdf"
    "sha256",      "STRING", 1, "", ""});

L = addLabel(L, "Chunk", "documents", "", "chunk_key", "chunk_key", { ...
    "chunk_key", "STRING",      1, "", "<doc_id>:<seq>"
    "doc_id",    "STRING",      1, "", "FK value kept: part of chunk_key"
    "seq",       "INTEGER",     1, "", ""
    "text",      "STRING",      1, "", "~800 characters"
    "embedding", "LIST<FLOAT>", 1, "", "768-d, all-mpnet-base-v2"});

graph.labels = L;

% Relationship rows: {type, from, to, layer, source, note}
% source: "fk:<constraint>" (a foreign key), "table:<join table>", or ""
% (graph only). Direction follows the sentence the edge reads as; where
% that reverses the FK direction the note says so.
relRows = {
    "IN_RELEASE",        "Series",          "Release",             "catalog",   "fk:fk_series_release",          ""
    "HAS_FREQUENCY",     "Series",          "Frequency",           "catalog",   "fk:fk_series_frequency",        ""
    "MEASURED_IN",       "Series",          "Units",               "catalog",   "fk:fk_series_units",            ""
    "ADJUSTED",          "Series",          "SeasonalAdjustment",  "catalog",   "fk:fk_series_sa",               ""
    "IN_CATEGORY",       "Series",          "Category",            "catalog",   "table:series_category",         ""
    "TAGGED",            "Series",          "Tag",                 "catalog",   "table:series_tag",              ""
    "PUBLISHED_BY",      "Release",         "Source",              "catalog",   "table:release_source",          ""
    "SCHEDULED_ON",      "Release",         "ReleaseDate",         "catalog",   "fk:fk_release_date_release",    "Reversed: owner points to weak entity"
    "CHILD_OF",          "Category",        "Category",            "catalog",   "fk:fk_category_parent",         ""
    "IN_GROUP",          "Tag",             "TagGroup",            "catalog",   "fk:fk_tag_tag_group",           ""
    "DESCRIBES",         "Document",        "Release",             "documents", "",                              ""
    "HAS_CHUNK",         "Document",        "Chunk",               "documents", "",                              ""
    "EXPOSED_IN",        "Provider",        "CatalogSnapshot",     "lineage",   "",                              ""
    "PUBLISHED",         "Provider",        "Dataset",             "lineage",   "",                              ""
    "CONTAINS_CATEGORY", "CatalogSnapshot", "Category",            "lineage",   "",                              ""
    "CONTAINS_SERIES",   "CatalogSnapshot", "Series",              "lineage",   "",                              ""
    "RAW_RESPONSE",      "CatalogSnapshot", "ApiResponseArtifact", "lineage",   "",                              ""
    "CONTAINS_SERIES",   "Dataset",         "Series",              "lineage",   "",                              ""
    "HAS_RAW_ARTIFACT",  "Dataset",         "RawArtifact",         "lineage",   "",                              ""
    "HAS_SOURCE_MEMBER", "Dataset",         "SourceMember",        "lineage",   "",                              ""
    "HAS_STAGING_RUN",   "Dataset",         "StagingRun",          "lineage",   "",                              ""
    "HAS_TRANSFORMATION","Series",          "SeriesVariant",       "lineage",   "",                              ""
    "AVAILABLE_IN",      "SeriesVariant",   "SourceMember",        "lineage",   "",                              ""};

R = struct([]);

for i = 1:size(relRows, 1)

    r = struct();
    r.type = string(relRows{i, 1});
    r.from = string(relRows{i, 2});
    r.to = string(relRows{i, 3});
    r.layer = string(relRows{i, 4});
    r.source = string(relRows{i, 5});
    r.note = string(relRows{i, 6});

    R = [R; r]; %#ok<AGROW>

end

graph.relationships = R;

% Indexes that are not backing a uniqueness constraint.
graph.indexes = struct( ...
    "name", {"series_id_lookup"; "series_last_updated"; "release_date_date"; "chunk_text"; "chunk_embedding"}, ...
    "type", {"RANGE"; "RANGE"; "RANGE"; "FULLTEXT"; "VECTOR"}, ...
    "label", {"Series"; "Series"; "ReleaseDate"; "Chunk"; "Chunk"}, ...
    "properties", {"series_id"; "last_updated"; "date"; "text"; "embedding"}, ...
    "options", {""; ""; ""; "analyzer standard-no-stop-words"; "768 dims, COSINE, HNSW m=16"});

graph.indexes = stringifyStruct(graph.indexes);

% Tables and FKs the graph leaves out on purpose.
graph.excluded = struct( ...
    "name", {"observation"; "fk_observation_series"}, ...
    "reason", {"Dense vintages stay in SQL; the graph holds the catalog and lineage"; ...
        "Goes with OBSERVATION"});

graph.excluded = stringifyStruct(graph.excluded);

validateGraph(graph, relationalModel);

end


function L = addLabel(L, name, layer, sourceTable, constraintName, keyProperties, rows)

props = struct([]);

for i = 1:size(rows, 1)

    p = struct();
    p.name = string(rows{i, 1});
    p.type = string(rows{i, 2});
    p.mandatory = logical(rows{i, 3});
    p.source_column = string(rows{i, 4});
    p.note = string(rows{i, 5});

    props = [props; p]; %#ok<AGROW>

end

lbl = struct();
lbl.name = string(name);
lbl.layer = string(layer);
lbl.source_table = string(sourceTable);
lbl.key_constraint = string(constraintName);
lbl.key = string(keyProperties);
lbl.properties = props;

L = [L; lbl];

end


function s = stringifyStruct(s)

f = fieldnames(s);

for i = 1:numel(s)
    for j = 1:numel(f)
        s(i).(f{j}) = string(s(i).(f{j}));
    end
end

end


function validateGraph(graph, relationalModel)

labelNames = [graph.labels.name];

assert(numel(unique(labelNames)) == numel(labelNames), "Duplicate labels.");

for lbl = graph.labels'

    names = [lbl.properties.name];

    assert(numel(unique(names)) == numel(names), ...
        "Duplicate property on :%s.", lbl.name);

    assert(all(ismember(lbl.key, names)), ...
        "Key of :%s names a missing property.", lbl.name);

    if strlength(lbl.source_table) > 0

        t = relationalModel.tables([relationalModel.tables.name] == lbl.source_table);

        assert(~isempty(t), ":%s maps a missing table.", lbl.name);

        mapped = [lbl.properties.source_column];
        mapped = mapped(strlength(mapped) > 0);

        assert(all(ismember(mapped, [t.columns.name])), ...
            ":%s maps a column that %s does not have.", lbl.name, t.name);

    end

end

for r = graph.relationships'

    assert(all(ismember([r.from, r.to], labelNames)), ...
        "%s connects a missing label.", r.type);

end

for ix = graph.indexes'

    lbl = graph.labels(labelNames == ix.label);

    assert(~isempty(lbl) && ismember(ix.properties, [lbl.properties.name]), ...
        "Index %s names a missing label or property.", ix.name);

end

end
