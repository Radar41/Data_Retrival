function T = fred_pg_query(sql, options)
%FRED_PG_QUERY Run one SQL statement against the FRED catalog in PostgreSQL.
%   T = FRED_PG_QUERY(SQL) returns the result set as a table. Dates arrive as
%   datetime, numerics as double and text as string, whichever way in is used.
%
%   Two ways in, chosen automatically (Backend="auto"):
%     "toolbox"  Database Toolbox native PostgreSQL interface over TCP. Used
%                when a password is available: the environment variable
%                FRED_PG_PASSWORD or the MATLAB vault secret fred_pg_pw
%                (setSecret("fred_pg_pw")). User from PGUSER or the OS user,
%                server from PGHOST (localhost), port from PGPORT (5432).
%     "psql"     psql over the local socket with peer authentication, no
%                password, the same path src/+dbdesign/check_model_against_postgres.m
%                uses. Needs psql on the PATH.
%   The database is FRED_DB, default "fred".
%
%   The password is never printed, logged or stored by this function.
%
%   See also fred_series, fred_panel, fred_series_sql.
arguments
    sql (1,1) string
    options.Database (1,1) string = defaultDatabase()
    options.Backend (1,1) string {mustBeMember(options.Backend, ["auto", "toolbox", "psql"])} = "auto"
end

backend = options.Backend;
if backend == "auto"
    if strlength(pgPassword()) > 0 && license("test", "Database_Toolbox")
        backend = "toolbox";
    else
        backend = "psql";
    end
end
switch backend
    case "toolbox"
        T = viaToolbox(sql, options.Database);
    case "psql"
        T = viaPsql(sql, options.Database);
end
T = normalizeText(T);
end


function db = defaultDatabase()
db = string(getenv("FRED_DB"));
if strlength(db) == 0, db = "fred"; end
end


function pw = pgPassword()
pw = string(getenv("FRED_PG_PASSWORD"));
if strlength(pw) == 0 && isSecret("fred_pg_pw")
    pw = string(getSecret("fred_pg_pw"));
end
end


function T = viaToolbox(sql, database)
user = string(getenv("PGUSER"));
if strlength(user) == 0, user = string(getenv("USER")); end
host = string(getenv("PGHOST"));
if strlength(host) == 0, host = "localhost"; end
port = str2double(getenv("PGPORT"));
if isnan(port), port = 5432; end
conn = postgresql(user, pgPassword(), "Server", host, "PortNumber", port, "DatabaseName", database);
cleanup = onCleanup(@() close(conn)); %#ok<NASGU>
assert(isopen(conn), "fred_pg_query:connect", "PostgreSQL connection failed: %s", conn.Message);
T = fetch(conn, sql);
end


function T = viaPsql(sql, database)
sqlFile = tempname + ".sql";
csvFile = tempname + ".csv";
cleanup = onCleanup(@() cellfun(@(f) deleteIfPresent(f), {sqlFile, csvFile})); %#ok<NASGU>
writelines(sql, sqlFile);
% MATLAB's bundled libraries shadow the system's for psql; drop them for the call.
command = "env -u LD_LIBRARY_PATH psql -X -q -v ON_ERROR_STOP=1 --csv -d " + database + ...
    " -f """ + sqlFile + """ -o """ + csvFile + """ </dev/null 2>&1";
[status, output] = system(command);
assert(status == 0, "fred_pg_query:psql", "psql failed: %s", strtrim(string(output)));
lines = readlines(csvFile);
lines(strlength(lines) == 0) = [];
if numel(lines) <= 1
    names = split(lines(1), ",");
    T = table('Size', [0, numel(names)], 'VariableTypes', repmat("string", 1, numel(names)), ...
        'VariableNames', cellstr(names));
    return
end
opts = detectImportOptions(csvFile, "TextType", "string", "Delimiter", ",", ...
    "VariableNamingRule", "preserve", "FileType", "delimitedtext");
T = readtable(csvFile, opts);
end


function deleteIfPresent(f)
if isfile(f), delete(f); end
end


function T = normalizeText(T)
for name = string(T.Properties.VariableNames)
    if iscellstr(T.(name)) || ischar(T.(name))
        T.(name) = string(T.(name));
    end
end
end
