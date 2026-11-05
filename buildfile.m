function plan = buildfile
%BUILDFILE MATLAB build plan for the Data_Retrival project.
%
%   buildtool            runs the default tasks: check, then test
%   buildtool check      Code Analyzer on src/, tests/ and this file; any
%                        warning fails the build (errors always do)
%   buildtool test       every test under tests/ (unit and integration);
%                        integration tests skip themselves when PostgreSQL
%                        or Neo4j is not reachable. JUnit results and
%                        Cobertura coverage of src/ go to derived/quality/
%   buildtool compat     Code Compatibility Analyzer report for src/;
%                        fails on any Error-severity recommendation
%   buildtool diagrams   docs/design/*.{dot,png,svg} from the checked model
%                        (DDL and graph-model checks only; no live database).
%                        Incremental: skipped while the model and writers
%                        are older than the outputs.
%   buildtool requirements
%                        requirements/fred_catalog.slreqx and the per-test
%                        link sets (tests/**/*~m.slmx) from
%                        src/build_fred_requirements.m (Requirements Toolbox)
%
%   From a shell:  matlab -batch "buildtool"      or  ./run_all.sh check

import matlab.buildtool.tasks.CodeIssuesTask
import matlab.buildtool.tasks.TestTask

plan = buildplan(localfunctions);

plan("check") = CodeIssuesTask(["src", "tests", "buildfile.m"], ...
    IncludeSubfolders = true, ...
    WarningThreshold = 0);

plan("test") = TestTask("tests", ...
    IncludeSubfolders = true, ...
    SourceFiles = "src", ...
    TestResults = fullfile("derived", "quality", "test-results.xml"), ...
    CodeCoverageResults = fullfile("derived", "quality", "coverage.xml"));
plan("test").Dependencies = "check";

plan("compat").Outputs = fullfile("derived", "quality", "code_compatibility.csv");

plan("diagrams").Inputs = [ ...
    files(plan, fullfile("src", "+dbdesign", "*.m")), ...
    files(plan, fullfile("src", "build_fred_design_diagrams.m")), ...
    files(plan, fullfile("sql", "**", "fred_schema.sql"))];
plan("diagrams").Outputs = files(plan, fullfile("docs", "design", "fred_*.*"));

plan("requirements").Inputs = [ ...
    files(plan, fullfile("src", "build_fred_requirements.m")), ...
    files(plan, fullfile("neo4j", "cypher", "fred_degree_audit.cypher")), ...
    files(plan, fullfile("tests", "**", "*Test.m"))];
plan("requirements").Outputs = [ ...
    files(plan, fullfile("requirements", "fred_catalog.slreqx")), ...
    files(plan, fullfile("tests", "**", "*~m.slmx"))];

plan.DefaultTasks = ["check", "test"];

end


function compatTask(context)
% Code Compatibility Analyzer over src/; the report is a CSV under derived/.

results = analyzeCodeCompatibility(fullfile(context.Plan.RootFolder, "src"));
recs = results.Recommendations;

outFile = context.Task.Outputs.paths;
if ~isfolder(fileparts(outFile)), mkdir(fileparts(outFile)); end
writetable(recs, outFile);

counts = groupcounts(recs, "Severity");
disp(counts);

nErrors = sum(recs.Severity == "Error");
assert(nErrors == 0, "buildfile:compat", ...
    "%d Error-severity compatibility recommendation(s); see %s", nErrors, outFile);

end


function requirementsTask(context)
% Requirement set + Verify links from the test methods (Requirements Toolbox).

addpath(fullfile(context.Plan.RootFolder, "src"));
build_fred_requirements(ProjectRoot = context.Plan.RootFolder);

end


function diagramsTask(context)
% Regenerate the design diagrams without touching a live database.

addpath(fullfile(context.Plan.RootFolder, "src"));
build_fred_design_diagrams(ProjectRoot = context.Plan.RootFolder, CheckLiveDatabase = false);

end
