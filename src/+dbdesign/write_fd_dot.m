function dotText = write_fd_dot(model, view, dotPath)
%WRITE_FD_DOT Functional-dependency map or table map of a relational model.
%
% dotText = dbdesign.write_fd_dot(model, view, dotPath)
%
%   view = "fd_maps"    one dependency map per relation, in the course
%                       notation: the primary key as one underlined box,
%                       an arrow to every non-key attribute. All-key
%                       relations have nothing to depend, so they are
%                       listed in a note.
%   view = "table_map"  the relations as records: PK underlined, FK
%                       columns tagged, an arrow from each FK column to the
%                       key it references.
%
% Both come from the same model as the logical and physical designs
% (dbdesign.fred_relational_model), so they can never disagree with the
% DDL that build_fred_design_diagrams checks the model against.

arguments
    model (1,1) struct
    view (1,1) string {mustBeMember(view, ["fd_maps", "table_map"])}
    dotPath (1,1) string = ""
end

navy = "#1f3557";
red = "#8a1c22";
keyFill = "#e8eef7";
derivedFill = "#fbefdc";
noteFill = "#f8f0dc";

titles = struct( ...
    "fd_maps", "Functional dependency maps (every determinant is the whole primary key: 3NF)", ...
    "table_map", "Table map: underline = primary key, FK = foreign key, arrows point to the referenced key");

g = strings(0, 1);
g(end + 1) = "digraph " + view + " {";
g(end + 1) = "graph [rankdir=LR, pad=0.4, fontname=""Helvetica"", labelloc=t, fontsize=20, " + ...
    "label=<<B>" + esc(model.name + ": " + titles.(view)) + "</B><BR/>" + ...
    "<FONT POINT-SIZE=""11"">" + esc(model.author + " · " + model.course) + "</FONT>>, " + ...
    rankOptions(view) + "];";

% g(end + 1) on a string array grows it as a row, so flatten before joining.
switch view
    case "fd_maps"
        body = fdMapBody(model, navy, keyFill, derivedFill, noteFill);
    case "table_map"
        body = tableMapBody(model, navy, red);
end

g = [g(:); body(:)];

g(end + 1) = "}";

dotText = strjoin(g, newline);

if strlength(dotPath) > 0

    folder = fileparts(dotPath);

    if strlength(folder) > 0 && ~isfolder(folder)
        mkdir(folder);
    end

    writelines(dotText, dotPath);

end

end


function opts = rankOptions(view)

if view == "fd_maps"
    opts = "nodesep=0.25, ranksep=0.5, compound=true";
else
    opts = "nodesep=0.35, ranksep=0.9, splines=true";
end

end


function g = fdMapBody(model, navy, keyFill, derivedFill, noteFill)

g = strings(0, 1);
g(end + 1) = "node [fontname=""Helvetica"", fontsize=10, shape=box, style=""rounded,filled"", " + ...
    "fillcolor=""white"", color=""" + navy + """];";
g(end + 1) = "edge [color=""" + navy + """, arrowsize=0.7];";

allKey = strings(0, 1);
derivedSeen = false;

for i = 1:numel(model.tables)

    t = model.tables(i);
    fkColumns = foreignKeyColumns(model, t.name);
    nonKey = t.columns(~ismember([t.columns.name], t.primary_key));

    if isempty(nonKey)
        allKey(end + 1) = t.entity; %#ok<AGROW>
        continue
    end

    g(end + 1) = sprintf("subgraph cluster_%d { label=""%s""; style=""rounded""; color=""%s""; " + ...
        "fontname=""Helvetica-Bold""; fontsize=11;", i, t.entity, navy); %#ok<AGROW>

    keyNode = sprintf("k%d", i);
    g(end + 1) = keyNode + " [label=<<U>" + strjoin(esc(t.primary_key), "<BR/>") + ...
        "</U>>, fillcolor=""" + keyFill + """];"; %#ok<AGROW>

    for j = 1:numel(nonKey)

        c = nonKey(j);
        attrNode = sprintf("a%d_%d", i, j);
        label = c.name;
        fill = "white";

        if c.derived
            label = "[" + label + "]";
            fill = derivedFill;
            derivedSeen = true;
        end

        if ismember(c.name, fkColumns)
            label = label + " (FK)";
        end

        g(end + 1) = attrNode + " [label=""" + label + """, fillcolor=""" + fill + """];"; %#ok<AGROW>
        g(end + 1) = keyNode + " -> " + attrNode + ";"; %#ok<AGROW>

    end

    g(end + 1) = "}"; %#ok<AGROW>

end

noteLines = "All-key relations (no non-key attributes, nothing to depend):\n" + strjoin(allKey, ", ");

if derivedSeen
    noteLines = noteLines + "\n\nDerived attributes in [brackets] are controlled denormalization,\n" + ...
        "kept consistent by trigger (see the physical designs).";
end

g(end + 1) = "note [shape=note, fillcolor=""" + noteFill + """, label=""" + noteLines + """];";

end


function g = tableMapBody(model, navy, red)

g = strings(0, 1);
g(end + 1) = "node [fontname=""Helvetica"", fontsize=10, shape=plain];";
g(end + 1) = "edge [color=""" + red + """, arrowsize=0.7, penwidth=1.1];";

for t = model.tables'

    fkColumns = foreignKeyColumns(model, t.name);

    rows = "<TR><TD BGCOLOR=""" + navy + """ COLSPAN=""2""><FONT COLOR=""white""><B>" + ...
        esc(t.entity) + "</B></FONT></TD></TR>";

    for c = t.columns'

        isKey = ismember(c.name, t.primary_key);
        nameText = esc(c.name);

        if c.derived
            nameText = "[" + nameText + "]";
        end

        if isKey
            nameText = "<U>" + nameText + "</U>";
        end

        if ismember(c.name, fkColumns)
            tag = "FK";
        elseif isKey
            tag = "PK";
        else
            tag = "";
        end

        rows = rows + "<TR><TD PORT=""" + c.name + """ ALIGN=""LEFT"">" + nameText + ...
            "</TD><TD>" + tag + "</TD></TR>";

    end

    g(end + 1) = """" + t.entity + """ [label=<<TABLE BORDER=""1"" CELLBORDER=""0"" CELLSPACING=""0"" " + ...
        "CELLPADDING=""3"" COLOR=""" + navy + """>" + rows + "</TABLE>>];"; %#ok<AGROW>

end

for fk = model.foreign_keys'

    child = model.tables([model.tables.name] == fk.child);
    parent = model.tables([model.tables.name] == fk.parent);

    for k = 1:numel(fk.child_columns)
        g(end + 1) = sprintf("""%s"":""%s"":e -> ""%s"":""%s"":w;", ...
            child.entity, fk.child_columns(k), parent.entity, fk.parent_columns(k)); %#ok<AGROW>
    end

end

lookups = model.tables([model.tables.group] == "lookup");

if ~isempty(lookups)
    g(end + 1) = "{rank=same; " + strjoin([lookups.entity], "; ") + ";}";
end

end


function columns = foreignKeyColumns(model, tableName)

fks = model.foreign_keys([model.foreign_keys.child] == tableName);
columns = strings(0, 1);

for fk = fks'
    columns = [columns; fk.child_columns(:)]; %#ok<AGROW>
end

end


function s = esc(s)

s = string(s);
s = replace(s, "&", "&amp;");
s = replace(s, "<", "&lt;");
s = replace(s, ">", "&gt;");
s = replace(s, """", "&quot;");

end
