function problems = check_model_against_ddl(model, ddlPath, dialect)
%CHECK_MODEL_AGAINST_DDL List every difference between the model and a DDL file.
%
% problems = dbdesign.check_model_against_ddl(model, "sql/fred_schema.sql", "postgresql")
% problems = dbdesign.check_model_against_ddl(model, "sql/mysql/fred_schema.sql", "mysql")
%
% Parses CREATE TABLE and CREATE INDEX statements and compares tables,
% column order, declared types, NOT NULL, defaults, primary keys, foreign
% keys (columns, referenced table, ON DELETE), CHECK constraint names and
% expressions, and the secondary indexes declared for that dialect.
% Returns a string column of problems; empty means the file and the model
% agree. Needs no database connection.

arguments
    model (1,1) struct
    ddlPath (1,1) string {mustBeFile}
    dialect (1,1) string {mustBeMember(dialect, ["postgresql", "mysql"])}
end

problems = strings(0, 1);

sqlText = strjoin(readlines(ddlPath), newline);
sqlText = regexprep(sqlText, "--[^\n]*", "");   % drop line comments

tableBlocks = regexp(sqlText, ...
    "CREATE\s+TABLE\s+`?(\w+)`?\s*\((.*?)\)\s*(?:ENGINE[^;]*)?;", ...
    "tokens");

ddlTables = strings(0, 1);

for b = 1:numel(tableBlocks)

    tableName = string(tableBlocks{b}{1});
    ddlTables(end + 1, 1) = tableName; %#ok<AGROW>

    mt = model.tables([model.tables.name] == tableName);

    if isempty(mt)
        problems(end + 1, 1) = tableName + ": in DDL, not in model"; %#ok<AGROW>
        continue
    end

    items = splitTopLevel(string(tableBlocks{b}{2}));

    ddlColumns = strings(0, 1);

    for item = items'

        if startsWith(item, "CONSTRAINT", "IgnoreCase", true)
            problems = [problems; checkConstraint(model, mt, item)]; %#ok<AGROW>
            continue
        end

        tok = regexp(item, "^(\w+)\s+(\w+(?:\s*\(\s*\d+(?:\s*,\s*\d+)?\s*\))?)(.*)$", ...
            "tokens", "once");

        if isempty(tok)
            problems(end + 1, 1) = tableName + ": cannot parse """ + item + """"; %#ok<AGROW>
            continue
        end

        columnName = tok(1);
        ddlColumns(end + 1, 1) = columnName; %#ok<AGROW>

        mc = mt.columns([mt.columns.name] == columnName);

        if isempty(mc)
            problems(end + 1, 1) = tableName + "." + columnName + ": in DDL, not in model"; %#ok<AGROW>
            continue
        end

        declared = upper(regexprep(tok(2), "\s+", ""));

        if declared ~= upper(mc.type)
            problems(end + 1, 1) = tableName + "." + columnName + ": type " + ...
                declared + " in DDL, " + mc.type + " in model"; %#ok<AGROW>
        end

        rest = tok(3);
        notNull = contains(rest, "NOT NULL", "IgnoreCase", true);

        if notNull ~= mc.not_null
            problems(end + 1, 1) = tableName + "." + columnName + ": NOT NULL differs"; %#ok<AGROW>
        end

        defTok = regexp(rest, "DEFAULT\s+(.+?)\s*$", "tokens", "once", "ignorecase");
        ddlDefault = "";

        if ~isempty(defTok)
            ddlDefault = regexprep(defTok(1), "^DATE\s+", "", "ignorecase");
        end

        if ddlDefault ~= mc.default
            problems(end + 1, 1) = tableName + "." + columnName + ": default " + ...
                ddlDefault + " in DDL, " + mc.default + " in model"; %#ok<AGROW>
        end

    end

    if ~isequal(ddlColumns, [mt.columns.name]')
        problems(end + 1, 1) = tableName + ": column order differs from model"; %#ok<AGROW>
    end

    % Every model constraint on this table must appear in the DDL.
    expectedNames = [mt.primary_key_name, ...
        model.foreign_keys([model.foreign_keys.child] == tableName).name, ...
        model.checks([model.checks.table] == tableName).name];

    ddlNames = string(regexp(strjoin(items, newline), "CONSTRAINT\s+(\w+)", ...
        "tokens"));

    for n = setdiff(expectedNames, ddlNames)
        problems(end + 1, 1) = tableName + ": constraint " + n + " missing from DDL"; %#ok<AGROW>
    end

end

for n = setdiff([model.tables.name], ddlTables)
    problems(end + 1, 1) = n + ": in model, not in DDL"; %#ok<AGROW>
end

% Secondary indexes declared for this dialect.
indexTok = regexp(sqlText, ...
    "CREATE\s+INDEX\s+(\w+)\s+ON\s+`?(\w+)`?\s*\(([^)]*)\)", "tokens");

ddlIndexes = strings(0, 1);

for k = 1:numel(indexTok)

    ixName = string(indexTok{k}{1});
    ddlIndexes(end + 1, 1) = ixName; %#ok<AGROW>

    mi = model.indexes([model.indexes.name] == ixName);

    if isempty(mi)
        problems(end + 1, 1) = "index " + ixName + ": in DDL, not in model"; %#ok<AGROW>
        continue
    end

    cols = strtrim(split(string(indexTok{k}{3}), ","))';

    if string(indexTok{k}{2}) ~= mi.table || ~isequal(cols, mi.columns)
        problems(end + 1, 1) = "index " + ixName + ": table or columns differ"; %#ok<AGROW>
    end

    if ~ismember(dialect, mi.dialects)
        problems(end + 1, 1) = "index " + ixName + ": in " + dialect + ...
            " DDL but model says it is not declared there"; %#ok<AGROW>
    end

end

expected = model.indexes(arrayfun(@(ix) ismember(dialect, ix.dialects), model.indexes));

for n = setdiff([expected.name], ddlIndexes)
    problems(end + 1, 1) = "index " + n + ": in model for " + dialect + ", not in DDL"; %#ok<AGROW>
end

end


function problems = checkConstraint(model, mt, item)

problems = strings(0, 1);
item = regexprep(item, "\s+", " ");
name = string(regexp(item, "CONSTRAINT (\w+)", "tokens", "once"));

if contains(item, "PRIMARY KEY", "IgnoreCase", true)

    cols = parseColumns(regexp(item, "PRIMARY KEY \(([^)]*)\)", "tokens", "once"));

    if name ~= mt.primary_key_name || ~isequal(cols, mt.primary_key)
        problems(end + 1, 1) = mt.name + ": primary key " + name + " differs from model";
    end

elseif contains(item, "FOREIGN KEY", "IgnoreCase", true)

    fk = model.foreign_keys([model.foreign_keys.name] == name);

    tok = regexp(item, ...
        "FOREIGN KEY \(([^)]*)\) REFERENCES `?(\w+)`? \(([^)]*)\)", ...
        "tokens", "once");

    if isempty(fk)
        problems(end + 1, 1) = mt.name + ": " + name + " in DDL, not in model";
        return
    end

    onDelete = "NO ACTION";

    onDeleteTok = regexp(item, "ON DELETE (\w+( \w+)?)", "tokens", "once");

    if ~isempty(onDeleteTok)
        onDelete = upper(onDeleteTok(1));
    end

    if fk.child ~= mt.name || ...
            ~isequal(parseColumns(tok(1)), fk.child_columns) || ...
            tok(2) ~= fk.parent || ...
            ~isequal(parseColumns(tok(3)), fk.parent_columns) || ...
            onDelete ~= fk.on_delete
        problems(end + 1, 1) = mt.name + ": " + name + " differs from model";
    end

elseif contains(item, "CHECK", "IgnoreCase", true)

    ck = model.checks([model.checks.name] == name);
    expr = regexp(item, "CHECK \((.*)\)$", "tokens", "once");

    if isempty(ck)
        problems(end + 1, 1) = mt.name + ": " + name + " in DDL, not in model";
    elseif strtrim(expr) ~= ck.expression
        problems(end + 1, 1) = mt.name + ": " + name + " expression differs from model";
    end

end

end


function cols = parseColumns(text)

cols = strtrim(split(string(text), ","))';

end


function items = splitTopLevel(body)

chars = char(body);
items = strings(0, 1);
depth = 0;
inQuote = false;
start = 1;

for k = 1:numel(chars)

    ch = chars(k);

    if ch == ''''
        inQuote = ~inQuote;
    elseif ~inQuote && ch == '('
        depth = depth + 1;
    elseif ~inQuote && ch == ')'
        depth = depth - 1;
    elseif ~inQuote && ch == ',' && depth == 0
        items(end + 1, 1) = strtrim(string(chars(start:k - 1))); %#ok<AGROW>
        start = k + 1;
    end

end

items(end + 1, 1) = strtrim(string(chars(start:end)));
items = regexprep(items, "\s+", " ");
items = items(strlength(items) > 0);

end
