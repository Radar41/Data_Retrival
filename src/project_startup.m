function project_startup()
%PROJECT_STARTUP Runs when the Data_Retrival MATLAB project opens.
%   Secrets come from the MATLAB vault only (setSecret / getSecret); nothing
%   is read from startup.m. Checks PostgreSQL, starts the project's Neo4j
%   container if it is down, and creates the git-ignored working folders.
%
%   Register: Project > Startup and Shutdown > Startup files > add this file.

root = currentProject().RootFolder;

% --- secrets -> process environment (never written to disk) -------------
if isSecret("MyFREDKey") && strlength(getenv("FRED_API_KEY")) == 0
    setenv("FRED_API_KEY", getSecret("MyFREDKey"));
end
setenv("FRED_PAYLOADS", fullfile(root, "payloads"));
setenv("NEO4J_IMPORT",  fullfile(root, "data", "staging", "neo4j-import"));

% --- PostgreSQL: check only; systemd owns the service ---------------------
[s, ~] = system("pg_isready -q -h localhost -p 5432");
pgUp = (s == 0);

% --- Neo4j: start the project container if it is not running --------------
neoUp = containerRunning();
if ~neoUp
    system(sprintf('cd "%s/neo4j" && docker compose up -d', root));
    pause(5);
    neoUp = containerRunning();
end

% --- git-ignored working folders a fresh clone lacks ----------------------
needed = ["payloads", fullfile("data", "staging", "neo4j-import"), ...
          fullfile("data", "raw", "documents"), fullfile("data", "staging", "run_all")];
for d = needed
    p = fullfile(root, d);
    if ~isfolder(p), mkdir(p); end
end

fprintf("Data_Retrival | FRED key: %s | PostgreSQL: %s | Neo4j: %s\n", ...
    onoff(strlength(getenv("FRED_API_KEY")) > 0, "set", "MISSING (setSecret(""MyFREDKey""))"), ...
    onoff(pgUp, "up", "DOWN (sudo systemctl start postgresql)"), ...
    onoff(neoUp, "up", "DOWN (see neo4j/compose.yaml)"));
end

function tf = containerRunning()
[~, out] = system("docker inspect -f '{{.State.Running}}' data_retrival_neo4j 2>/dev/null");
tf = strcmp(strtrim(out), "true");
end

function s = onoff(c, a, b)
if c, s = a; else, s = b; end
end
