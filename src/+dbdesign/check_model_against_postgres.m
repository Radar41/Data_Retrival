function problems = check_model_against_postgres(model, database)
%CHECK_MODEL_AGAINST_POSTGRES Compare the model with a live PostgreSQL catalog.
%
% problems = dbdesign.check_model_against_postgres(model)          % database "fred"
% problems = dbdesign.check_model_against_postgres(model, "fred_check")
%
% Reads information_schema and pg_catalog through psql over the local
% socket (no password needed for the owning role) and compares tables,
% columns, stored types, NOT NULL, defaults, constraint names, foreign-key
% targets and ON DELETE actions, secondary indexes, and the triggers,
% functions and procedures the PostgreSQL design declares. Returns a string
% column of problems; empty means the database matches the model.

arguments
    model (1,1) struct
    database (1,1) string = "fred"
end

problems = strings(0, 1);

columnRows = psqlRows(database, ...
    "SELECT table_name, column_name, data_type, " + ...
    "coalesce(character_maximum_length::text, ''), " + ...
    "coalesce(numeric_precision::text, ''), coalesce(numeric_scale::text, ''), " + ...
    "is_nullable, coalesce(column_default, '') " + ...
    "FROM information_schema.columns WHERE table_schema = 'public' " + ...
    "ORDER BY table_name, ordinal_position");

constraintRows = psqlRows(database, ...
    "SELECT conrelid::regclass::text, conname, contype::text, pg_get_constraintdef(oid) " + ...
    "FROM pg_constraint WHERE connamespace = 'public'::regnamespace");

indexRows = psqlRows(database, ...
    "SELECT indexname, tablename, indexdef FROM pg_indexes WHERE schemaname = 'public'");

routineRows = psqlRows(database, ...
    "SELECT proname FROM pg_proc WHERE pronamespace = 'public'::regnamespace " + ...
    "UNION SELECT tgname FROM pg_trigger WHERE NOT tgisinternal");

liveTables = unique(columnRows(:, 1));

for n = setdiff(liveTables, [model.tables.name]')'
    problems(end + 1, 1) = n + ": in database, not in model"; %#ok<AGROW>
end

for t = model.tables'

    rows = columnRows(columnRows(:, 1) == t.name, :);

    if isempty(rows)
        problems(end + 1, 1) = t.name + ": in model, not in database"; %#ok<AGROW>
        continue
    end

    if ~isequal(rows(:, 2), [t.columns.name]')
        problems(end + 1, 1) = t.name + ": columns or order differ"; %#ok<AGROW>
        continue
    end

    for k = 1:numel(t.columns)

        c = t.columns(k);
        r = rows(k, :);
        where = t.name + "." + c.name;

        if storedType(r) ~= upper(c.type)
            problems(end + 1, 1) = where + ": stored " + storedType(r) + ", model " + c.type; %#ok<AGROW>
        end

        if (r(7) == "NO") ~= c.not_null
            problems(end + 1, 1) = where + ": NOT NULL differs"; %#ok<AGROW>
        end

        liveDefault = lower(regexprep(r(8), "::[\w ]+$", ""));

        if liveDefault ~= lower(c.default)
            problems(end + 1, 1) = where + ": default " + r(8) + " in database, " + ...
                c.default + " in model"; %#ok<AGROW>
        end

    end

    live = constraintRows(constraintRows(:, 1) == t.name, :);

    if ~any(live(:, 2) == t.primary_key_name & live(:, 3) == "p")
        problems(end + 1, 1) = t.name + ": primary key " + t.primary_key_name + " missing"; %#ok<AGROW>
    end

    for fk = model.foreign_keys([model.foreign_keys.child] == t.name)'

        def = live(live(:, 2) == fk.name & live(:, 3) == "f", 4);

        if isempty(def)
            problems(end + 1, 1) = t.name + ": " + fk.name + " missing"; %#ok<AGROW>
            continue
        end

        tok = regexp(def, "FOREIGN KEY \(([^)]*)\) REFERENCES (\w+)\(([^)]*)\)", ...
            "tokens", "once");

        onDelete = "NO ACTION";

        onDeleteTok = regexp(def, "ON DELETE (\w+( \w+)?)", "tokens", "once");

        if ~isempty(onDeleteTok)
            onDelete = upper(onDeleteTok(1));
        end

        if tok(1) ~= strjoin(fk.child_columns, ", ") || tok(2) ~= fk.parent || ...
                tok(3) ~= strjoin(fk.parent_columns, ", ") || onDelete ~= fk.on_delete
            problems(end + 1, 1) = t.name + ": " + fk.name + " differs: " + def; %#ok<AGROW>
        end

    end

    for ck = model.checks([model.checks.table] == t.name)'
        if ~any(live(:, 2) == ck.name & live(:, 3) == "c")
            problems(end + 1, 1) = t.name + ": " + ck.name + " missing"; %#ok<AGROW>
        end
    end

end

secondary = indexRows(~startsWith(indexRows(:, 1), "pk_"), :);
expected = model.indexes(arrayfun(@(ix) ismember("postgresql", ix.dialects), model.indexes));

for ix = expected'

    row = secondary(secondary(:, 1) == ix.name, :);

    if isempty(row)
        problems(end + 1, 1) = "index " + ix.name + " missing"; %#ok<AGROW>
        continue
    end

    cols = regexp(row(3), "\(([^)]*)\)\s*$", "tokens", "once");

    if row(2) ~= ix.table || cols ~= strjoin(ix.columns, ", ")
        problems(end + 1, 1) = "index " + ix.name + " differs: " + row(3); %#ok<AGROW>
    end

end

for n = setdiff(secondary(:, 1), [expected.name]')'
    problems(end + 1, 1) = "index " + n + ": in database, not in model"; %#ok<AGROW>
end

expectedRoutines = model.routines(arrayfun(@(r) ismember("postgresql", r.dialects), model.routines));

for n = setdiff([expectedRoutines.name], routineRows(:, 1)')
    problems(end + 1, 1) = "routine " + n + " missing"; %#ok<AGROW>
end

end


function t = storedType(r)

switch r(3)
    case "character varying"
        t = "VARCHAR(" + r(4) + ")";
    case "numeric"
        t = "DECIMAL(" + r(5) + "," + r(6) + ")";
    case "timestamp without time zone"
        t = "TIMESTAMP";
    otherwise
        t = upper(r(3));
end

end


function rows = psqlRows(database, query)

command = "env -u LD_LIBRARY_PATH psql -X -A -t -q -v ON_ERROR_STOP=1 -F '|' -d " + database + " </dev/null" + ...
    " -c """ + query + """";

[status, output] = system(command);

assert(status == 0, "dbdesign:check_model_against_postgres:psql", ...
    "psql failed: %s", strtrim(output));

lines = splitlines(string(strtrim(output)));
lines = lines(strlength(lines) > 0);

if isempty(lines)
    rows = strings(0, 1);
    return
end

parts = arrayfun(@(l) split(l, "|")', lines, "UniformOutput", false);
rows = vertcat(parts{:});

end
