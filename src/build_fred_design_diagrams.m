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
%      fred_physical_postgresql PostgreSQL 16
%      fred_physical_mysql      MySQL 8 / MariaDB (InnoDB)
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

if options.CheckLiveDatabase
    problems = [problems; prefix("live " + options.Database, ...
        dbdesign.check_model_against_postgres(model, options.Database))];
end

if ~isempty(problems)
    error("build_fred_design_diagrams:ModelMismatch", ...
        "Model disagrees with the schema:\n  %s", strjoin(problems, newline + "  "));
end

fprintf("Model matches both DDL files%s.\n", ...
    repmat(" and the live " + options.Database + " database", 1, options.CheckLiveDatabase));

views = ["logical", "postgresql", "mysql"];
stems = ["fred_logical_design", "fred_physical_postgresql", "fred_physical_mysql"];

if ~isfolder(outputFolder)
    mkdir(outputFolder);
end

outputs = strings(0, 1);

for k = 1:numel(views)

    dotPath = fullfile(outputFolder, stems(k) + ".dot");
    dbdesign.write_schema_dot(model, views(k), dotPath);

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
