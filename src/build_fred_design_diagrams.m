function outputs = build_fred_design_diagrams(options)
%BUILD_FRED_DESIGN_DIAGRAMS Logical and physical design diagrams for the FRED catalog.
%
% outputs = build_fred_design_diagrams()
% outputs = build_fred_design_diagrams(CheckLiveDatabase=false)
%
% 1. Builds the canonical model (dbdesign.fred_relational_model).
% 2. Checks it against sql/fred_schema.sql and sql/mysql/fred_schema.sql,
%    and against the live PostgreSQL database unless CheckLiveDatabase is
%    false. Any difference stops the build, so a diagram never disagrees
%    with the code it documents.
% 3. Writes .dot, .png and .svg for each view into docs/design/:
%      fred_logical_design      DBMS-independent relational model
%      fred_fd_maps             functional dependency map per relation (course notation)
%      fred_table_map           relations as records with FK arrows
%      fred_physical_postgresql PostgreSQL 16
%      fred_physical_mysql      MySQL 8 / MariaDB (InnoDB)
%      fred_neo4j_logical       property graph model (dbdesign.fred_graph_model)
%      fred_neo4j_physical      Neo4j Community: types, constraints, indexes
%
% Needs Graphviz (dot) on the PATH.

arguments
    options.ProjectRoot (1,1) string = string(fileparts(fileparts(mfilename("fullpath"))))
    options.OutputFolder (1,1) string = ""
    options.CheckLiveDatabase (1,1) logical = true
    options.Database (1,1) string = "fred"
end

root = options.ProjectRoot;
outputFolder = options.OutputFolder;

if strlength(outputFolder) == 0
    outputFolder = fullfile(root, "docs", "design");
end

model = dbdesign.fred_relational_model();

problems = [ ...
    prefix("postgresql DDL", dbdesign.check_model_against_ddl(model, ...
        fullfile(root, "sql", "fred_schema.sql"), "postgresql"))
    prefix("mysql DDL", dbdesign.check_model_against_ddl(model, ...
        fullfile(root, "sql", "mysql", "fred_schema.sql"), "mysql"))];

graph = dbdesign.fred_graph_model(model);

if options.CheckLiveDatabase
    problems = [problems
        prefix("live " + options.Database, ...
            dbdesign.check_model_against_postgres(model, options.Database))
        prefix("graph", dbdesign.check_graph_model(graph, model))];
else
    problems = [problems
        prefix("graph", dbdesign.check_graph_model(graph, model, Live=false))];
end

if ~isempty(problems)
    error("build_fred_design_diagrams:ModelMismatch", ...
        "Model disagrees with the schema:\n  %s", strjoin(problems, newline + "  "));
end

fprintf("Model matches both DDL files%s.\n", ...
    repmat(" and the live " + options.Database + " and Neo4j databases", 1, options.CheckLiveDatabase));

views = ["logical", "fd_maps", "table_map", "postgresql", "mysql", "graph_logical", "graph_physical"];
stems = ["fred_logical_design", "fred_fd_maps", "fred_table_map", "fred_physical_postgresql", ...
    "fred_physical_mysql", "fred_neo4j_logical", "fred_neo4j_physical"];

if ~isfolder(outputFolder)
    mkdir(outputFolder);
end

outputs = strings(0, 1);

for k = 1:numel(views)

    dotPath = fullfile(outputFolder, stems(k) + ".dot");
    if startsWith(views(k), "graph_")
        dbdesign.write_graph_dot(graph, model, views(k), dotPath);
    elseif ismember(views(k), ["fd_maps", "table_map"])
        dbdesign.write_fd_dot(model, views(k), dotPath);
    else
        dbdesign.write_schema_dot(model, views(k), dotPath);
    end

    for fmt = ["png", "svg"]

        outPath = fullfile(outputFolder, stems(k) + "." + fmt);
        dpi = "";

        if fmt == "png"
            dpi = " -Gdpi=150";
        end

        [status, message] = system("dot" + dpi + " -T" + fmt + " """ + dotPath + ...
            """ -o """ + outPath + """");

        assert(status == 0, "build_fred_design_diagrams:Graphviz", ...
            "dot failed for %s: %s", dotPath, message);

        outputs(end + 1, 1) = outPath; %#ok<AGROW>

    end

    fprintf("  %s\n", fullfile(outputFolder, stems(k) + ".png"));

end

end


function problems = prefix(label, problems)

problems = label + ": " + problems;

end
