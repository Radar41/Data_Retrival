function model = fred_relational_model()
%FRED_RELATIONAL_MODEL Canonical description of the FRED catalog schema.
%
% model = dbdesign.fred_relational_model()
%
% Single source for every design diagram. The logical view, the PostgreSQL
% physical view and the MySQL/MariaDB physical view are all rendered from
% this one struct by dbdesign.write_schema_dot, so a change made here shows
% up in every diagram. Column types are the declared types in
% sql/fred_schema.sql; dbdesign.physical_type maps them to what each DBMS
% actually stores.
%
% dbdesign.check_model_against_ddl compares this model with both DDL files,
% and dbdesign.check_model_against_postgres compares it with the live
% PostgreSQL catalog. Keep all three in agreement.

model = struct();
model.name = "FRED Metadata Catalog";
model.author = "Adrian Aziza";
model.course = "ADIT2200-01 Database Management, Fall 2026";

% Column rows: {name, declared type, "NN" (NOT NULL) or "", default,
%               "DERIVED" or "", comment}
T = struct([]);

T = addTable(T, "frequency", "FREQUENCY", "strong", "lookup", ...
    "How often a series is observed", "frequency_code", { ...
    "frequency_code", "VARCHAR(4)",  "NN", "", "", "FRED frequency_short: M, Q, A, W, D, BW, SA"
    "frequency_name", "VARCHAR(40)", "NN", "", "", "Monthly, Quarterly, ..."});

T = addTable(T, "units", "UNITS", "strong", "lookup", ...
    "Unit of measure", "units_code", { ...
    "units_code", "VARCHAR(80)",  "NN", "", "", "FRED units_short"
    "units_name", "VARCHAR(120)", "NN", "", "", "Percent, Billions of Dollars, ..."});

T = addTable(T, "seasonal_adjustment", "SEASONAL_ADJUSTMENT", "strong", "lookup", ...
    "SA / NSA / SAAR", "sa_code", { ...
    "sa_code", "VARCHAR(8)",  "NN", "", "", "SA, NSA, SAAR"
    "sa_name", "VARCHAR(80)", "NN", "", "", "Seasonally Adjusted, ..."});

T = addTable(T, "source", "SOURCE", "strong", "provenance", ...
    "Publishing agency", "source_id", { ...
    "source_id",   "INTEGER",      "NN", "", "", "FRED source id (BLS = 22)"
    "source_name", "VARCHAR(200)", "NN", "", "", ""
    "source_link", "VARCHAR(400)", "",   "", "", "May be absent"});

T = addTable(T, "release", "RELEASE", "strong", "provenance", ...
    "Named publication", "release_id", { ...
    "release_id",    "INTEGER",      "NN", "",     "", "FRED release id (Employment Situation = 50)"
    "release_name",  "VARCHAR(200)", "NN", "",     "", ""
    "press_release", "BOOLEAN",      "NN", "TRUE", "", "FRED press_release flag"
    "release_link",  "VARCHAR(400)", "",   "",     "", ""});

T = addTable(T, "release_source", "RELEASE_SOURCE", "associative", "provenance", ...
    "Resolves M:N RELEASE-SOURCE (rule 1)", ["release_id", "source_id"], { ...
    "release_id", "INTEGER", "NN", "", "", ""
    "source_id",  "INTEGER", "NN", "", "", ""});

T = addTable(T, "release_date", "RELEASE_DATE", "weak", "provenance", ...
    "Weak: a date belongs to one release (rule 2)", ["release_id", "release_date"], { ...
    "release_id",   "INTEGER",     "NN", "",            "", ""
    "release_date", "DATE",        "NN", "",            "", ""
    "date_status",  "VARCHAR(10)", "NN", "'scheduled'", "", "scheduled | actual"});

T = addTable(T, "release_table_element", "RELEASE_TABLE_ELEMENT", "strong", "provenance", ...
    "Table tree of a release: section > table > header > series row (rule 12)", "element_id", { ...
    "element_id",    "INTEGER",      "NN", "", "", "FRED element id"
    "release_id",    "INTEGER",      "NN", "", "", ""
    "parent_id",     "INTEGER",      "",   "", "", "NULL for a top-level section (unary 1:M)"
    "element_type",  "VARCHAR(8)",   "NN", "", "", "section | table | header | series"
    "element_name",  "VARCHAR(300)", "NN", "", "", "Section title, table title, row label"
    "element_level", "SMALLINT",     "NN", "", "", "Indentation level within its table"
    "line_no",       "INTEGER",      "",   "", "", "Line number in the published table"
    "series_id",     "VARCHAR(40)",  "",   "", "", "FRED series id on series rows; no FK: the catalog holds a subset of each release's series"});

T = addTable(T, "category", "CATEGORY", "strong", "classification", ...
    "Topic hierarchy (unary 1:M)", "category_id", { ...
    "category_id",   "INTEGER",      "NN", "", "", "Root = 0"
    "category_name", "VARCHAR(200)", "NN", "", "", ""
    "parent_id",     "INTEGER",      "",   "", "", "NULL only for the root"});

T = addTable(T, "tag_group", "TAG_GROUP", "strong", "classification", ...
    "Kind of tag (rule 8)", "group_id", { ...
    "group_id",   "VARCHAR(8)",  "NN", "", "", "freq, gen, geo, geot, rls, seas, src, cc"
    "group_name", "VARCHAR(80)", "NN", "", "", ""});

T = addTable(T, "tag", "TAG", "strong", "classification", ...
    "Keyword label", "tag_name", { ...
    "tag_name",   "VARCHAR(120)", "NN", "", "", ""
    "group_id",   "VARCHAR(8)",   "NN", "", "", ""
    "tag_notes",  "VARCHAR(400)", "",   "", "", ""
    "popularity", "SMALLINT",     "",   "", "", "0-100"});

T = addTable(T, "series", "SERIES", "strong", "series", ...
    "One FRED time series (rules 3, 4)", "series_id", { ...
    "series_id",         "VARCHAR(40)",  "NN", "", "",        "UNRATE, GDPC1, CPIAUCSL"
    "title",             "VARCHAR(300)", "NN", "", "",        ""
    "release_id",        "INTEGER",      "NN", "", "",        ""
    "frequency_code",    "VARCHAR(4)",   "NN", "", "",        ""
    "units_code",        "VARCHAR(80)",  "NN", "", "",        ""
    "sa_code",           "VARCHAR(8)",   "NN", "", "",        ""
    "observation_start", "DATE",         "",   "", "DERIVED", "MIN(observation_date), kept by trigger"
    "observation_end",   "DATE",         "",   "", "DERIVED", "MAX(observation_date), kept by trigger"
    "last_updated",      "TIMESTAMP",    "",   "", "",        "FRED last_updated"
    "popularity",        "SMALLINT",     "",   "", "",        ""
    "notes",             "TEXT",         "",   "", "",        "Agency free text"});

T = addTable(T, "series_category", "SERIES_CATEGORY", "associative", "series", ...
    "Resolves M:N SERIES-CATEGORY (rule 5)", ["series_id", "category_id"], { ...
    "series_id",   "VARCHAR(40)", "NN", "", "", ""
    "category_id", "INTEGER",     "NN", "", "", ""});

T = addTable(T, "series_tag", "SERIES_TAG", "associative", "series", ...
    "Resolves M:N SERIES-TAG (rule 7)", ["series_id", "tag_name"], { ...
    "series_id", "VARCHAR(40)",  "NN", "", "", ""
    "tag_name",  "VARCHAR(120)", "NN", "", "", ""});

T = addTable(T, "observation", "OBSERVATION", "weak", "observation", ...
    "Weak: every vintage of every value (rules 9-11)", ...
    ["series_id", "observation_date", "realtime_start"], { ...
    "series_id",        "VARCHAR(40)",   "NN", "",             "", ""
    "observation_date", "DATE",          "NN", "",             "", "Period the value describes"
    "realtime_start",   "DATE",          "NN", "",             "", "First day published"
    "realtime_end",     "DATE",          "NN", "'9999-12-31'", "", "Last day current"
    "value",            "DECIMAL(24,8)", "",   "",             "", "NULL where FRED reports '.'"});

T = addTable(T, "vintage_date", "VINTAGE_DATE", "weak", "observation", ...
    "Weak: every date on which a series was revised or extended (rule 13)", ...
    ["series_id", "vintage_date"], { ...
    "series_id",    "VARCHAR(40)", "NN", "", "", ""
    "vintage_date", "DATE",        "NN", "", "", "FRED series/vintagedates"});

model.tables = T;

% Foreign keys double as the logical relationships.
% {name, child, child cols, parent, parent cols, ON DELETE,
%  verb, parent end, child end}
% Ends: "one", "zero_one", "one_many", "zero_many" (crow's foot).
fkRows = {
    "fk_release_source_release",   "release_source",  "release_id",     "release",             "release_id",     "CASCADE",  "published by",  "one",      "one_many"
    "fk_release_source_source",    "release_source",  "source_id",      "source",              "source_id",      "RESTRICT", "publishes",     "one",      "one_many"
    "fk_release_date_release",     "release_date",    "release_id",     "release",             "release_id",     "CASCADE",  "is scheduled",  "one",      "one_many"
    "fk_rte_release",              "release_table_element", "release_id", "release",           "release_id",     "RESTRICT", "structures",    "one",      "zero_many"
    "fk_rte_parent",               "release_table_element", "parent_id",  "release_table_element", "element_id", "RESTRICT", "contains",      "zero_one", "zero_many"
    "fk_category_parent",          "category",        "parent_id",      "category",            "category_id",    "RESTRICT", "parent of",     "zero_one", "zero_many"
    "fk_tag_tag_group",            "tag",             "group_id",       "tag_group",           "group_id",       "RESTRICT", "groups",        "one",      "one_many"
    "fk_series_release",           "series",          "release_id",     "release",             "release_id",     "RESTRICT", "contains",      "one",      "one_many"
    "fk_series_frequency",         "series",          "frequency_code", "frequency",           "frequency_code", "RESTRICT", "describes",     "one",      "zero_many"
    "fk_series_units",             "series",          "units_code",     "units",               "units_code",     "RESTRICT", "measures",      "one",      "zero_many"
    "fk_series_sa",                "series",          "sa_code",        "seasonal_adjustment", "sa_code",        "RESTRICT", "adjusts",       "one",      "zero_many"
    "fk_series_category_series",   "series_category", "series_id",      "series",              "series_id",      "CASCADE",  "classified in", "one",      "one_many"
    "fk_series_category_category", "series_category", "category_id",    "category",            "category_id",    "RESTRICT", "holds",         "one",      "zero_many"
    "fk_series_tag_series",        "series_tag",      "series_id",      "series",              "series_id",      "CASCADE",  "carries",       "one",      "zero_many"
    "fk_series_tag_tag",           "series_tag",      "tag_name",       "tag",                 "tag_name",       "RESTRICT", "applied as",    "one",      "one_many"
    "fk_observation_series",       "observation",     "series_id",      "series",              "series_id",      "CASCADE",  "has",           "one",      "zero_many"
    "fk_vintage_date_series",      "vintage_date",    "series_id",      "series",              "series_id",      "CASCADE",  "revised on",    "one",      "zero_many"};

FK = struct([]);

for i = 1:size(fkRows, 1)

    r = fkRows(i, :);

    fk = struct();
    fk.name = string(r{1});
    fk.child = string(r{2});
    fk.child_columns = string(r{3});
    fk.parent = string(r{4});
    fk.parent_columns = string(r{5});
    fk.on_delete = string(r{6});
    fk.verb = string(r{7});
    fk.parent_end = string(r{8});
    fk.child_end = string(r{9});

    % Identifying when the migrated key is part of the child's primary key
    % (weak and associative entities).
    childTable = T([T.name] == fk.child);
    fk.identifying = all(ismember(fk.child_columns, childTable.primary_key));

    FK = [FK; fk]; %#ok<AGROW>

end

model.foreign_keys = FK;

model.checks = struct( ...
    "name", { ...
    "ck_release_date_status", ...
    "ck_rte_type", ...
    "ck_series_obs_range", ...
    "ck_observation_realtime"}, ...
    "table", {"release_date", "release_table_element", "series", "observation"}, ...
    "expression", { ...
    "date_status IN ('scheduled', 'actual')", ...
    "element_type IN ('section', 'table', 'header', 'series')", ...
    "observation_end IS NULL OR observation_start IS NULL OR observation_end >= observation_start", ...
    "realtime_end >= realtime_start"});

% Column vector like every other struct array in the model, so that
% "for x = array'" iterates element by element.
model.checks = stringifyStruct(model.checks(:));

% Secondary indexes. "dialects" lists where the DDL declares the index.
% MySQL/MariaDB omits the ones InnoDB already creates for an FK column.
both = ["postgresql", "mysql"];
pgOnly = "postgresql";

idx = {
    "ix_series_release",      "series",          "release_id",                                   pgOnly, "Which series does release X update"
    "ix_series_frequency_sa", "series",          ["frequency_code", "sa_code"],                  both,   "Monthly SA series"
    "ix_series_last_updated", "series",          "last_updated",                                 both,   "What changed this week"
    "ix_release_date_date",   "release_date",    "release_date",                                 both,   "Releases scheduled in week W"
    "ix_rte_release",         "release_table_element", "release_id",                             pgOnly, "Table tree of release X"
    "ix_rte_parent",          "release_table_element", "parent_id",                              pgOnly, "Children of an element"
    "ix_rte_series",          "release_table_element", "series_id",                              both,   "Where does series X appear in the published tables"
    "ix_category_parent",     "category",        "parent_id",                                    pgOnly, "Hierarchy walk"
    "ix_series_category_cat", "series_category", "category_id",                                  pgOnly, "Reverse lookup of the M:N"
    "ix_series_tag_tag",      "series_tag",      "tag_name",                                     pgOnly, "Reverse lookup of the M:N"
    "ix_tag_group",           "tag",             "group_id",                                     pgOnly, "Tags in a group"
    "ix_observation_current", "observation",     ["series_id", "realtime_end", "observation_date"], both, "Current value as of"
    "ix_observation_vintage", "observation",     ["series_id", "observation_date", "realtime_end"], both, "How many revisions"
    "ix_vintage_date_date",   "vintage_date",    "vintage_date",                                 both,   "What was revised on day D"};

IX = struct([]);

for i = 1:size(idx, 1)

    ix = struct();
    ix.name = string(idx{i, 1});
    ix.table = string(idx{i, 2});
    ix.columns = string(idx{i, 3});
    ix.dialects = string(idx{i, 4});
    ix.purpose = string(idx{i, 5});

    IX = [IX; ix]; %#ok<AGROW>

end

model.indexes = IX;

% Procedural objects (sql/fred_triggers.sql, sql/mysql/fred_triggers.sql).
rt = {
    "close_prior_vintage",  "trigger",   "BEFORE INSERT ON observation", pgOnly,  "Rule 11: close the open vintage before a new one is added"
    "add_vintage",          "procedure", "CALL instead of INSERT",       "mysql", "Rule 11 in MySQL: a trigger may not update its own table (error 1442)"
    "refresh_series_range", "trigger",   "AFTER INSERT ON observation",  both,    "Keeps series.observation_start/end consistent; per statement (transition table) in PostgreSQL, per row in MySQL"
    "value_as_of",          "function",  "(series, obs_date, as_of)",    both,    "Value of a series as it was known on a date"
    "post_release",         "procedure", "(release_id, date)",           both,    "Marks a release date actual"};

RT = struct([]);

for i = 1:size(rt, 1)

    r = struct();
    r.name = string(rt{i, 1});
    r.kind = string(rt{i, 2});
    r.signature = string(rt{i, 3});
    r.dialects = string(rt{i, 4});
    r.purpose = string(rt{i, 5});

    RT = [RT; r]; %#ok<AGROW>

end

model.routines = RT;

validateModel(model);

end


function T = addTable(T, name, entity, kind, group, purpose, primaryKey, columnRows)

columns = struct([]);

for i = 1:size(columnRows, 1)

    c = struct();
    c.name = string(columnRows{i, 1});
    c.type = string(columnRows{i, 2});
    c.not_null = string(columnRows{i, 3}) == "NN";
    c.default = string(columnRows{i, 4});
    c.derived = string(columnRows{i, 5}) == "DERIVED";
    c.comment = string(columnRows{i, 6});

    columns = [columns; c]; %#ok<AGROW>

end

t = struct();
t.name = string(name);
t.entity = string(entity);
t.kind = string(kind);
t.group = string(group);
t.purpose = string(purpose);
t.primary_key = string(primaryKey);
t.primary_key_name = "pk_" + string(name);
t.columns = columns;

T = [T; t];

end


function s = stringifyStruct(s)

f = fieldnames(s);

for i = 1:numel(s)
    for j = 1:numel(f)
        s(i).(f{j}) = string(s(i).(f{j}));
    end
end

end


function validateModel(model)

tableNames = [model.tables.name];

assert(numel(unique(tableNames)) == numel(tableNames), ...
    "Duplicate table names in model.");

for t = model.tables'

    columnNames = [t.columns.name];

    assert(all(ismember(t.primary_key, columnNames)), ...
        "Primary key of %s names a missing column.", t.name);

    assert(all([t.columns(ismember(columnNames, t.primary_key)).not_null]), ...
        "Primary-key column of %s must be NOT NULL.", t.name);

end

for fk = model.foreign_keys'

    child = model.tables(tableNames == fk.child);
    parent = model.tables(tableNames == fk.parent);

    assert(~isempty(child) && ~isempty(parent), ...
        "%s references a missing table.", fk.name);

    assert(isequal(sort(fk.parent_columns), sort(parent.primary_key)), ...
        "%s must reference the primary key of %s.", fk.name, fk.parent);

    childTypes = arrayfun(@(c) child.columns([child.columns.name] == c).type, ...
        fk.child_columns);
    parentTypes = arrayfun(@(c) parent.columns([parent.columns.name] == c).type, ...
        fk.parent_columns);

    assert(isequal(childTypes, parentTypes), ...
        "%s column types differ from the referenced key.", fk.name);

end

for ix = model.indexes'

    t = model.tables(tableNames == ix.table);

    assert(~isempty(t) && all(ismember(ix.columns, [t.columns.name])), ...
        "Index %s names a missing table or column.", ix.name);

end

end
