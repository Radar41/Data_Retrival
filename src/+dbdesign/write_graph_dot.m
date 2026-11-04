function dotText = write_graph_dot(graph, relationalModel, view, dotPath)
%WRITE_GRAPH_DOT Render the Neo4j logical or physical design as Graphviz.
%
% dotText = dbdesign.write_graph_dot(graph, relationalModel, view, dotPath)
%
%   view = "graph_logical"   labels, properties (key underlined), directed
%                            relationship types, grouped by layer; each
%                            label and edge names the table or FK it came
%                            from, and a legend lists the full
%                            relational-to-graph conversion
%   view = "graph_physical"  stored Cypher types, required/optional,
%                            uniqueness constraints, RANGE / FULLTEXT /
%                            VECTOR indexes, Community-edition limits and
%                            every type difference from the SQL schema

arguments
    graph (1,1) struct
    relationalModel (1,1) struct
    view (1,1) string {mustBeMember(view, ["graph_logical", "graph_physical"])}
    dotPath (1,1) string = ""
end

navy = "#1f3557";
isLogical = view == "graph_logical";

if isLogical
    title = "Neo4j Logical Design (property graph model)";
else
    title = "Neo4j Physical Design: " + graph.dbms;
end

g = strings(0, 1);
g(end + 1) = "digraph " + view + " {";
g(end + 1) = "graph [rankdir=LR, compound=true, splines=spline, nodesep=0.35, ranksep=1.0, " + ...
    "pad=0.4, fontname=""Helvetica"", labelloc=t, fontsize=20, " + ...
    "label=<<B>" + esc(graph.name + ": " + title) + "</B><BR/><FONT POINT-SIZE=""11"">" + ...
    esc(graph.author + " · " + graph.course) + "</FONT>>];";
g(end + 1) = "node [shape=plaintext, fontname=""Helvetica"", fontsize=10];";
g(end + 1) = "edge [color=""" + navy + """, fontname=""Helvetica"", fontsize=9, arrowsize=0.8, fontcolor=""#333333""];";

for layer = graph.layers'

    g(end + 1) = "subgraph cluster_" + layer.name + " {"; %#ok<AGROW>
    g(end + 1) = "label=<<B>" + esc(layer.title) + "</B>>; fontsize=13; style=""rounded,filled""; " + ...
        "fillcolor=""" + layer.color + """; color=""#9aa7b8"";"; %#ok<AGROW>

    for lbl = graph.labels([graph.labels.layer] == layer.name)'
        g(end + 1) = """" + lbl.name + """ [label=<" + labelHtml(graph, lbl, isLogical, navy) + ">];"; %#ok<AGROW>
    end

    g(end + 1) = "}"; %#ok<AGROW>

end

for r = graph.relationships'

    text = "<B>:" + esc(r.type) + "</B>";

    if isLogical && startsWith(r.source, "fk:")
        text = text + "<BR/><FONT POINT-SIZE=""8"">from FK " + esc(extractAfter(r.source, "fk:")) + "</FONT>";
    elseif isLogical && startsWith(r.source, "table:")
        text = text + "<BR/><FONT POINT-SIZE=""8"">from join table " + esc(extractAfter(r.source, "table:")) + "</FONT>";
    end

    if isLogical && strlength(r.note) > 0
        text = text + "<BR/><FONT POINT-SIZE=""8""><I>" + esc(r.note) + "</I></FONT>";
    end

    style = "solid";

    if r.layer ~= "catalog"
        style = "dashed";
    end

    % Edges that cross layers do not rank the layout, so each layer keeps
    % its own block instead of lineage pushing the catalog aside.
    fromLayer = graph.labels([graph.labels.name] == r.from).layer;
    toLayer = graph.labels([graph.labels.name] == r.to).layer;
    constraint = "true";

    if fromLayer ~= toLayer
        constraint = "false";
    end

    g(end + 1) = sprintf("""%s"" -> ""%s"" [label=<%s>, style=%s, constraint=%s];", ...
        r.from, r.to, text, style, constraint); %#ok<AGROW>

end

if isLogical
    g(end + 1) = "legend [label=<" + logicalLegend(graph, relationalModel, navy) + ">];";
else
    g(end + 1) = "legend [label=<" + physicalLegend(graph, relationalModel, navy) + ">];";
end

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


function html = labelHtml(graph, lbl, isLogical, navy)

nCols = 1 + 2 * ~isLogical;
rows = strings(0, 1);

rows(end + 1) = "<TR><TD COLSPAN=""" + nCols + """ BGCOLOR=""" + navy + """ CELLPADDING=""5"">" + ...
    "<FONT COLOR=""white"" POINT-SIZE=""12""><B>:" + esc(lbl.name) + "</B></FONT></TD></TR>";

if isLogical && strlength(lbl.source_table) > 0
    rows(end + 1) = "<TR><TD><FONT POINT-SIZE=""8""><I>from table " + esc(lbl.source_table) + "</I></FONT></TD></TR>";
end

for p = lbl.properties'

    name = esc(p.name);

    if ismember(p.name, lbl.key)
        name = "<U><B>" + name + "</B></U>";
    end

    if isLogical
        rows(end + 1) = "<TR><TD ALIGN=""LEFT"">" + name + "</TD></TR>"; %#ok<AGROW>
    else
        if p.mandatory
            req = "required";
        else
            req = "optional";
        end

        rows(end + 1) = "<TR><TD ALIGN=""LEFT"">" + name + "</TD>" + ...
            "<TD ALIGN=""LEFT""><FONT COLOR=""#1f5537"">" + esc(p.type) + "</FONT></TD>" + ...
            "<TD ALIGN=""LEFT""><FONT POINT-SIZE=""8"">" + req + "</FONT></TD></TR>"; %#ok<AGROW>
    end

end

if ~isLogical

    footer = strings(0, 1);

    if strlength(lbl.key_constraint) > 0
        footer(end + 1) = esc("CONSTRAINT " + lbl.key_constraint + " UNIQUE (" + strjoin(lbl.key, ", ") + ")");
    else
        footer(end + 1) = esc("no constraint (" + strjoin(lbl.key, ", ") + " not enforced unique)");
    end

    for ix = graph.indexes([graph.indexes.label] == lbl.name)'

        line = ix.type + " INDEX " + ix.name + " (" + ix.properties + ")";

        if strlength(ix.options) > 0
            line = line + " " + ix.options;
        end

        footer(end + 1) = esc(line); %#ok<AGROW>

    end

    rows(end + 1) = "<TR><TD COLSPAN=""3"" ALIGN=""LEFT"" BALIGN=""LEFT"" BGCOLOR=""#eef2f8"">" + ...
        "<FONT POINT-SIZE=""8"">" + strjoin(footer, "<BR/>") + "</FONT></TD></TR>";

end

html = "<TABLE BORDER=""1"" CELLBORDER=""0"" CELLSPACING=""0"" CELLPADDING=""3"" STYLE=""ROUNDED"" " + ...
    "BGCOLOR=""white"" COLOR=""" + navy + """>" + strjoin(rows, "") + "</TABLE>";

end


function html = logicalLegend(graph, relationalModel, navy)

rows = strings(0, 1);
rows(end + 1) = header("Notation", navy);
rows(end + 1) = pair(":Label", "node label (one per entity table)");
rows(end + 1) = pair("<U><B>property</B></U>", "business key");
rows(end + 1) = pair("arrow :TYPE", "directed relationship; Neo4j has no cardinality or null markers");
rows(end + 1) = pair("solid / dashed", "catalog relationship / document or lineage relationship");

rows(end + 1) = header("Relational to graph conversion", navy);

for t = relationalModel.tables'

    lbl = graph.labels([graph.labels.source_table] == t.name);
    rel = graph.relationships([graph.relationships.source] == "table:" + t.name);
    ex = graph.excluded([graph.excluded.name] == t.name);

    if ~isempty(lbl)
        target = ":" + lbl.name + " (node label)";
    elseif ~isempty(rel)
        target = ":" + rel.type + " (join table became a relationship)";
    elseif ~isempty(ex)
        target = "not in graph: " + ex.reason;
    else
        target = "UNMAPPED";
    end

    rows(end + 1) = pair(esc("table " + t.name), esc(target)); %#ok<AGROW>

end

for fk = relationalModel.foreign_keys'

    rel = graph.relationships([graph.relationships.source] == "fk:" + fk.name);

    if ~isempty(rel)
        rows(end + 1) = pair(esc(fk.name), esc(":" + rel.type + " (" + rel.from + " to " + rel.to + ")")); %#ok<AGROW>
    end

end

html = wrapTable(rows, navy);

end


function html = physicalLegend(graph, relationalModel, navy)

rows = strings(0, 1);
rows(end + 1) = header("Community edition: what is and is not enforced", navy);
rows(end + 1) = pair("UNIQUE constraint", "one per keyed label; backs a RANGE index");
rows(end + 1) = pair("required / optional", "observed on every node or not; existence constraints are Enterprise-only");
rows(end + 1) = pair("composite keys", "NODE KEY is Enterprise-only: rd_key and chunk_key are concatenated strings");
rows(end + 1) = pair("relationships", "no properties, no constraints; type and direction only");

rows(end + 1) = header("Type or format differences from the SQL schema", navy);

for lbl = graph.labels(strlength([graph.labels.source_table]) > 0)'

    t = relationalModel.tables([relationalModel.tables.name] == lbl.source_table);

    for p = lbl.properties(strlength([lbl.properties.source_column]) > 0)'

        c = t.columns([t.columns.name] == p.source_column);
        expected = sqlToCypherType(c.type);

        if expected ~= p.type
            rows(end + 1) = pair(esc(":" + lbl.name + "." + p.name + "  " + p.type), ...
                esc(t.name + "." + c.name + "  " + c.type)); %#ok<AGROW>
        end

    end

end

rows(end + 1) = header("Load path", navy);
rows(end + 1) = "<TR><TD COLSPAN=""2"" ALIGN=""LEFT"" BALIGN=""LEFT"">" + ...
    "fred_load.py writes CSVs; LOAD CSV in neo4j/cypher/003-006 MERGEs on each key<BR/>" + ...
    "OBSERVATION stays in SQL; Document/Chunk come from the PDF registry</TD></TR>";

html = wrapTable(rows, navy);

end


function t = sqlToCypherType(sqlType)

sqlType = upper(sqlType);

if startsWith(sqlType, ["VARCHAR", "TEXT"])
    t = "STRING";
elseif ismember(sqlType, ["INTEGER", "SMALLINT"])
    t = "INTEGER";
elseif startsWith(sqlType, "DECIMAL")
    t = "FLOAT";
elseif sqlType == "TIMESTAMP"
    t = "LOCAL DATETIME";
else
    t = sqlType;   % DATE, BOOLEAN
end

end


function row = header(text, navy)

row = "<TR><TD COLSPAN=""2"" BGCOLOR=""" + navy + """><FONT COLOR=""white""><B>" + esc(text) + "</B></FONT></TD></TR>";

end


function row = pair(left, right)

row = "<TR><TD ALIGN=""LEFT"">" + left + "</TD><TD ALIGN=""LEFT"">" + right + "</TD></TR>";

end


function html = wrapTable(rows, navy)

html = "<TABLE BORDER=""1"" CELLBORDER=""0"" CELLSPACING=""0"" CELLPADDING=""3"" BGCOLOR=""white"" COLOR=""" + ...
    navy + """>" + strjoin(rows, "") + "</TABLE>";

end


function s = esc(s)

s = string(s);
s = replace(s, "&", "&amp;");
s = replace(s, "<", "&lt;");
s = replace(s, ">", "&gt;");
s = replace(s, """", "&quot;");

end
