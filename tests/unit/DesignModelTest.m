classdef (TestTags = {'Design'}) DesignModelTest < matlab.unittest.TestCase
    %DESIGNMODELTEST The design model agrees with the DDL, the graph model
    % and the diagrams, with no database connection.
    %
    % Everything the diagram build checks before it draws is checked here
    % too, so a change to the model, a schema file or a writer that breaks
    % the agreement fails `buildtool test` and not the next diagram build.

    properties
        Root (1,1) string
        Model (1,1) struct
        Graph (1,1) struct
    end

    properties (TestParameter)
        schemaView = {"logical", "postgresql", "mysql"}
        fdView = {"fd_maps", "table_map"}
        graphView = {"graph_logical", "graph_physical"}
        typeCase = struct( ...
            pgDecimal = {{"DECIMAL(24,8)", "postgresql", "NUMERIC(24,8)"}}, ...
            pgTimestamp = {{"TIMESTAMP", "postgresql", "TIMESTAMP (no tz)"}}, ...
            myBoolean = {{"BOOLEAN", "mysql", "TINYINT(1)"}}, ...
            myInteger = {{"INTEGER", "mysql", "INT"}}, ...
            logicalIdentity = {{"DECIMAL(24,8)", "logical", "DECIMAL(24,8)"}}, ...
            caseInsensitive = {{" boolean ", "mysql", "TINYINT(1)"}})
    end

    methods (TestClassSetup)
        function loadModel(testCase)
            import matlab.unittest.fixtures.PathFixture
            testCase.Root = string(fileparts(fileparts(fileparts(mfilename("fullpath")))));
            testCase.applyFixture(PathFixture(fullfile(testCase.Root, "src")));
            testCase.Model = dbdesign.fred_relational_model();
            testCase.Graph = dbdesign.fred_graph_model(testCase.Model);
        end
    end

    methods (Test)

        function modelMatchesPostgresDdl(testCase)
            problems = dbdesign.check_model_against_ddl(testCase.Model, ...
                fullfile(testCase.Root, "sql", "fred_schema.sql"), "postgresql");
            testCase.verifyEmpty(problems, strjoin(problems, newline));
        end

        function modelMatchesMysqlDdl(testCase)
            problems = dbdesign.check_model_against_ddl(testCase.Model, ...
                fullfile(testCase.Root, "sql", "mysql", "fred_schema.sql"), "mysql");
            testCase.verifyEmpty(problems, strjoin(problems, newline));
        end

        function graphCoversRelationalModel(testCase)
            problems = dbdesign.check_graph_model(testCase.Graph, testCase.Model, Live = false);
            testCase.verifyEmpty(problems, strjoin(problems, newline));
        end

        function tableNamesAreUnique(testCase)
            names = [testCase.Model.tables.name];
            testCase.verifyEqual(numel(unique(names)), numel(names), ...
                "Duplicate table name in fred_relational_model.");
        end

        function physicalTypeMapping(testCase, typeCase)
            actual = dbdesign.physical_type(typeCase{1}, typeCase{2});
            testCase.verifyEqual(actual, string(typeCase{3}));
        end

        function physicalTypeRejectsUnknownDialect(testCase)
            testCase.verifyError(@() dbdesign.physical_type("INTEGER", "oracle"), ...
                "MATLAB:validators:mustBeMember");
        end

        function schemaViewNamesEveryTable(testCase, schemaView)
            dotPath = testCase.tempDot();
            dotText = dbdesign.write_schema_dot(testCase.Model, schemaView, dotPath);
            testCase.verifyTrue(isfile(dotPath));
            testCase.verifyNamesPresent(dotText, [testCase.Model.tables.name], "table");
            testCase.verifyDotCompiles(dotPath);
        end

        function fdViewNamesEveryTable(testCase, fdView)
            dotPath = testCase.tempDot();
            dotText = dbdesign.write_fd_dot(testCase.Model, fdView, dotPath);
            testCase.verifyNamesPresent(dotText, [testCase.Model.tables.name], "table");
            testCase.verifyDotCompiles(dotPath);
        end

        function graphViewNamesEveryLabelAndRelationship(testCase, graphView)
            dotPath = testCase.tempDot();
            dotText = dbdesign.write_graph_dot(testCase.Graph, testCase.Model, graphView, dotPath);
            testCase.verifyNamesPresent(dotText, [testCase.Graph.labels.name], "label");
            testCase.verifyNamesPresent(dotText, [testCase.Graph.relationships.type], "relationship");
            testCase.verifyDotCompiles(dotPath);
        end

        function writersRejectUnknownView(testCase)
            dotPath = testCase.tempDot();
            testCase.verifyError(@() dbdesign.write_schema_dot(testCase.Model, "oracle", dotPath), ...
                "MATLAB:validators:mustBeMember");
            testCase.verifyError(@() dbdesign.write_fd_dot(testCase.Model, "logical", dotPath), ...
                "MATLAB:validators:mustBeMember");
        end

        function degreeAuditCoversEveryRelationshipItNames(testCase)
            % The audit file is hand-written Cypher. Keep it tied to the model:
            % fourteen statements, one rule id each, and no relationship type
            % that the graph model does not declare.
            auditPath = fullfile(testCase.Root, "neo4j", "cypher", "fred_degree_audit.cypher");
            text = fileread(auditPath);
            statements = strtrim(split(string(text), newline + ";" + newline));
            statements = statements(strlength(statements) > 0 & ~startsWith(statements, "//") ...
                | contains(statements, "MATCH"));

            testCase.verifyEqual(numel(statements), 14, "Expected 14 audit statements.");

            ruleIds = strings(0, 1);
            for s = statements'
                testCase.verifyTrue(contains(s, "RETURN"), "Statement without RETURN: " + extractBefore(s, 60));
                tok = regexp(s, "'(A\d\d) ", "tokens", "once");
                testCase.assertNotEmpty(tok, "Statement without a rule id: " + extractBefore(s, 60));
                ruleIds(end + 1, 1) = string(tok{1}); %#ok<AGROW>
            end
            testCase.verifyEqual(ruleIds, "A" + compose("%02d", (1:14)'), "Rule ids must be A01..A14 in order.");

            used = unique(string(regexp(text, "\[:([A-Z_]+)\]", "tokens")));
            declared = [testCase.Graph.relationships.type];
            testCase.verifyEmpty(setdiff(used, declared), ...
                "Audit names relationship types the graph model does not declare: " + ...
                strjoin(setdiff(used, declared), ", "));
        end

    end

    methods (Access = private)

        function dotPath = tempDot(testCase)
            import matlab.unittest.fixtures.TemporaryFolderFixture
            f = testCase.applyFixture(TemporaryFolderFixture);
            dotPath = fullfile(f.Folder, "view.dot");
        end

        function verifyNamesPresent(testCase, dotText, names, kind)
            missing = names(~contains(dotText, names));
            testCase.verifyEmpty(missing, sprintf("%s(s) missing from the diagram: %s", ...
                kind, strjoin(missing, ", ")));
        end

        function verifyDotCompiles(testCase, dotPath)
            [status, ~] = system("dot -V");
            testCase.assumeEqual(status, 0, "Graphviz dot is not on the PATH; skipping render check.");
            [status, message] = system("dot -Tsvg """ + dotPath + """ -o /dev/null");
            testCase.verifyEqual(status, 0, "dot rejected the file: " + string(message));
        end

    end

end
