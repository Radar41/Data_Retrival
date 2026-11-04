function dotText = write_schema_dot(model, view, dotPath)
%WRITE_SCHEMA_DOT Render one design view of a relational model as Graphviz.
%
% dotText = dbdesign.write_schema_dot(model, view, dotPath)
%
%   view = "logical"     relations, PK underlined, FK italic, derived in
%                        [brackets], crow's-foot relationships with verbs
%   view = "postgresql"  physical design for PostgreSQL 16
%   view = "mysql"       physical design for MySQL 8 / MariaDB (InnoDB)
%
% Every view uses the same template; only the dialect-specific parts
% (stored types, identifier quoting, defaults, indexes, routines, table
% options) differ. Identifying relationships (migrated key is part of the
% child's primary key) are solid; non-identifying ones are dashed.

arguments
    model (1,1) struct
    view (1,1) string {mustBeMember(view, ["logical", "postgresql", "mysql"])}
    dotPath (1,1) string = ""
end

navy = "#1f3557";
tables = model.tables;

titles = struct( ...
    "logical", "Logical Design (relational model, DBMS-independent)", ...
    "postgresql", "Physical Design: PostgreSQL 16", ...
    "mysql", "Physical Design: MySQL 8 / MariaDB (InnoDB)");

g = strings(0, 1);
g(end + 1) = "digraph " + view + " {";
g(end + 1) = "graph [rankdir=LR, splines=spline, nodesep=0.45, ranksep=1.2, " + ...
    "pad=0.4, fontname=""Helvetica"", labelloc=t, fontsize=20, " + ...
    "label=<<B>" + esc(model.name + ": " + titles.(view)) + "</B><BR/>" + ...
    "<FONT POINT-SIZE=""11"">" + esc(model.author + " · " + model.course) + ...
    "</FONT>>];";
g(end + 1) = "node [shape=plaintext, fontname=""Helvetica"", fontsize=10];";
g(end + 1) = "edge [dir=both, color=""" + navy + """, fontname=""Helvetica"", " + ...
    "fontsize=9, arrowsize=0.9, fontcolor=""#333333""];";

for t = tables'
    g(end + 1) = """" + t.name + """ [label=<" + tableLabel(model, t, view, navy) + ">];"; %#ok<AGROW>
end

for fk = model.foreign_keys'

    if fk.identifying
        style = "solid";
        pen = "1.6";
    else
        style = "dashed";
        pen = "1.1";
    end

    if view == "logical"
        edgeLabel = esc(fk.verb);
    else
        edgeLabel = esc(fk.name) + "<BR/><FONT POINT-SIZE=""8"">ON DELETE " + ...
            esc(fk.on_delete) + "</FONT>";
    end

    % Referenced key leaves from the right edge of its row; the FK column
    % is entered at the left edge, so lines never cross the column text.
    if view == "logical"
        tailPort = fk.parent_columns(1);
        headPort = fk.child_columns(1);
    else
        tailPort = fk.parent_columns(1) + "_out";
        headPort = fk.child_columns(1) + "_in";
    end

    g(end + 1) = sprintf( ...
        """%s"":""%s"":e -> ""%s"":""%s"":w [arrowtail=%s, arrowhead=%s, style=%s, penwidth=%s, label=<%s>];", ...
        fk.parent, tailPort, fk.child, headPort, ...
        crowEnd(fk.parent_end), crowEnd(fk.child_end), style, pen, edgeLabel); %#ok<AGROW>

end

g(end + 1) = "{rank=same; frequency; units; seasonal_adjustment;}";
g(end + 1) = "{rank=same; tag_group; source;}";
g(end + 1) = "legend [label=<" + legendLabel(model, view, navy) + ">];";
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


function html = tableLabel(model, t, view, navy)

isLogical = view == "logical";
fkColumns = [strings(1, 0), ...
    model.foreign_keys([model.foreign_keys.child] == t.name).child_columns];

if isLogical
    nCols = 1;
    heading = t.entity;
else
    nCols = 4;
    heading = quoteIdentifier(t.name, view);
end

rows = strings(0, 1);

rows(end + 1) = "<TR><TD COLSPAN=""" + nCols + """ BGCOLOR=""" + navy + """ CELLPADDING=""5"">" + ...
    "<FONT COLOR=""white"" POINT-SIZE=""12""><B>" + esc(heading) + "</B></FONT></TD></TR>";

if isLogical && t.kind ~= "strong"
    rows(end + 1) = "<TR><TD><FONT POINT-SIZE=""8""><I>" + t.kind + ...
        " entity</I></FONT></TD></TR>";
end

for c = t.columns'

    isPk = ismember(c.name, t.primary_key);
    isFk = ismember(c.name, fkColumns);

    if isLogical

        text = esc(c.name);

        if c.derived
            text = "[" + text + "]";
        end

        if isFk
            text = "<I>" + text + "</I> (FK)";
        end

        if isPk
            text = "<U>" + text + "</U>";
        end

        rows(end + 1) = "<TR><TD ALIGN=""LEFT"" PORT=""" + c.name + """>" + text + "</TD></TR>"; %#ok<AGROW>

    else

        keyMarks = strjoin([repmat("PK", 1, isPk), repmat("FK", 1, isFk)], ",");

        if strlength(keyMarks) == 0
            keyMarks = " ";   % Graphviz rejects an empty <FONT></FONT>
        end

        nameText = esc(c.name);

        if isPk
            nameText = "<B>" + nameText + "</B>";
        end

        if c.derived
            nameText = nameText + " <FONT POINT-SIZE=""8"">(derived)</FONT>";
        end

        if c.not_null
            nullText = "NOT NULL";
        else
            nullText = "NULL";
        end

        defaultText = physicalDefault(c, view);

        if strlength(defaultText) > 0
            nullText = nullText + " DEFAULT " + defaultText;
        end

        rows(end + 1) = "<TR>" + ...
            "<TD ALIGN=""LEFT"" PORT=""" + c.name + "_in""><FONT POINT-SIZE=""8"" COLOR=""#7a1f1f"">" + keyMarks + "</FONT></TD>" + ...
            "<TD ALIGN=""LEFT"">" + nameText + "</TD>" + ...
            "<TD ALIGN=""LEFT""><FONT COLOR=""#1f5537"">" + esc(dbdesign.physical_type(c.type, view)) + "</FONT></TD>" + ...
            "<TD ALIGN=""LEFT"" PORT=""" + c.name + "_out""><FONT POINT-SIZE=""8"">" + esc(nullText) + "</FONT></TD>" + ...
            "</TR>"; %#ok<AGROW>

    end

end

if ~isLogical
    rows(end + 1) = "<TR><TD COLSPAN=""4"" ALIGN=""LEFT"" BALIGN=""LEFT"" BGCOLOR=""#eef2f8"">" + ...
        "<FONT POINT-SIZE=""8"">" + strjoin(physicalFooter(model, t, view), "<BR/>") + ...
        "</FONT></TD></TR>";
end

body = strjoin(rows, "");

if isLogical && t.kind == "weak"
    % Hoffer weak entity: double border.
    html = "<TABLE BORDER=""1"" CELLBORDER=""0"" CELLSPACING=""2"" COLOR=""" + navy + """><TR><TD>" + ...
        "<TABLE BORDER=""1"" CELLBORDER=""0"" CELLSPACING=""0"" CELLPADDING=""3"" COLOR=""" + navy + """>" + ...
        body + "</TABLE></TD></TR></TABLE>";
elseif isLogical && t.kind == "associative"
    html = "<TABLE BORDER=""1"" CELLBORDER=""0"" CELLSPACING=""0"" CELLPADDING=""3"" STYLE=""ROUNDED"" COLOR=""" + ...
        navy + """>" + body + "</TABLE>";
else
    html = "<TABLE BORDER=""1"" CELLBORDER=""0"" CELLSPACING=""0"" CELLPADDING=""3"" COLOR=""" + ...
        navy + """>" + body + "</TABLE>";
end

end


function lines = physicalFooter(model, t, view)

lines = esc(t.primary_key_name + " PRIMARY KEY (" + strjoin(t.primary_key, ", ") + ")");

for ck = model.checks([model.checks.table] == t.name)'
    lines(end + 1) = esc(ck.name + " CHECK (" + ck.expression + ")"); %#ok<AGROW>
end

explicit = model.indexes([model.indexes.table] == t.name);
explicit = explicit(arrayfun(@(ix) ismember(view, ix.dialects), explicit));

for ix = explicit'
    lines(end + 1) = esc("INDEX " + ix.name + " (" + strjoin(ix.columns, ", ") + ")"); %#ok<AGROW>
end

if view == "mysql"

    % InnoDB creates an index named after each FK whose columns are not
    % already the leftmost prefix of the primary key or an explicit index.
    prefixes = {t.primary_key};

    for ix = explicit'
        prefixes{end + 1} = ix.columns; %#ok<AGROW>
    end

    for fk = model.foreign_keys([model.foreign_keys.child] == t.name)'

        covered = any(cellfun(@(p) numel(p) >= numel(fk.child_columns) && ...
            isequal(p(1:numel(fk.child_columns)), fk.child_columns), prefixes));

        if ~covered
            lines(end + 1) = "<I>" + esc("INDEX " + fk.name + " (" + ...
                strjoin(fk.child_columns, ", ") + ") — implicit, InnoDB FK") + "</I>"; %#ok<AGROW>
            prefixes{end + 1} = fk.child_columns; %#ok<AGROW>
        end

    end

    lines(end + 1) = "ENGINE=InnoDB  DEFAULT CHARSET=utf8mb4";

end

end


function html = legendLabel(model, view, navy)

rows = strings(0, 1);

rows(end + 1) = "<TR><TD COLSPAN=""2"" BGCOLOR=""" + navy + """><FONT COLOR=""white""><B>Notation</B></FONT></TD></TR>";
rows(end + 1) = "<TR><TD ALIGN=""LEFT"">solid line</TD><TD ALIGN=""LEFT"">identifying (FK is part of the PK)</TD></TR>";
rows(end + 1) = "<TR><TD ALIGN=""LEFT"">dashed line</TD><TD ALIGN=""LEFT"">non-identifying</TD></TR>";
rows(end + 1) = "<TR><TD ALIGN=""LEFT"">|| and crow's foot</TD><TD ALIGN=""LEFT"">exactly one / many; a circle means zero is allowed</TD></TR>";

if view == "logical"
    rows(end + 1) = "<TR><TD ALIGN=""LEFT""><U>underlined</U></TD><TD ALIGN=""LEFT"">primary key</TD></TR>";
    rows(end + 1) = "<TR><TD ALIGN=""LEFT""><I>italic</I> (FK)</TD><TD ALIGN=""LEFT"">foreign key</TD></TR>";
    rows(end + 1) = "<TR><TD ALIGN=""LEFT"">[brackets]</TD><TD ALIGN=""LEFT"">derived attribute (controlled denormalization)</TD></TR>";
    rows(end + 1) = "<TR><TD ALIGN=""LEFT"">double border</TD><TD ALIGN=""LEFT"">weak entity</TD></TR>";
    rows(end + 1) = "<TR><TD ALIGN=""LEFT"">rounded border</TD><TD ALIGN=""LEFT"">associative entity</TD></TR>";
else
    rows(end + 1) = "<TR><TD ALIGN=""LEFT""><B>bold</B> / PK, FK</TD><TD ALIGN=""LEFT"">key columns</TD></TR>";
    rows(end + 1) = "<TR><TD ALIGN=""LEFT"">edge label</TD><TD ALIGN=""LEFT"">FK constraint name and ON DELETE action</TD></TR>";

    routines = model.routines(arrayfun(@(r) ismember(view, r.dialects), model.routines));

    rows(end + 1) = "<TR><TD COLSPAN=""2"" BGCOLOR=""" + navy + """><FONT COLOR=""white""><B>Triggers, functions, procedures</B></FONT></TD></TR>";

    for r = routines'
        rows(end + 1) = "<TR><TD ALIGN=""LEFT""><B>" + esc(r.name) + "</B><BR/><FONT POINT-SIZE=""8"">" + ...
            esc(r.kind + " " + r.signature) + "</FONT></TD><TD ALIGN=""LEFT"">" + esc(r.purpose) + "</TD></TR>"; %#ok<AGROW>
    end

    if view == "mysql"
        rows(end + 1) = "<TR><TD COLSPAN=""2"" BGCOLOR=""" + navy + """><FONT COLOR=""white""><B>Differences from PostgreSQL</B></FONT></TD></TR>";
        rows(end + 1) = "<TR><TD COLSPAN=""2"" ALIGN=""LEFT"" BALIGN=""LEFT"">" + ...
            "RELEASE is reserved: table is `release`<BR/>" + ...
            "INTEGER stored as INT, BOOLEAN as TINYINT(1)<BR/>" + ...
            "Vintage rule is the add_vintage() procedure, not a trigger<BR/>" + ...
            "FK-only indexes omitted: InnoDB creates them (shown in italics)</TD></TR>";
    end
end

html = "<TABLE BORDER=""1"" CELLBORDER=""0"" CELLSPACING=""0"" CELLPADDING=""4"" COLOR=""" + navy + """>" + ...
    strjoin(rows, "") + "</TABLE>";

end


function text = physicalDefault(c, view)

text = c.default;

if strlength(text) == 0
    return
end

if view == "postgresql" && upper(c.type) == "DATE" && startsWith(text, "'")
    text = "DATE " + text;
end

end


function name = quoteIdentifier(name, view)

mysqlReserved = ["release", "order", "group", "key", "range", "rank"];

if view == "mysql" && ismember(lower(name), mysqlReserved)
    name = "`" + name + "`";
end

end


function arrow = crowEnd(endKind)

switch endKind
    case "one"
        arrow = "teetee";
    case "zero_one"
        arrow = "teeodot";
    case "one_many"
        arrow = "crowtee";
    case "zero_many"
        arrow = "crowodot";
    otherwise
        error("dbdesign:write_schema_dot:UnknownEnd", ...
            "Unknown relationship end: %s", endKind);
end

end


function s = esc(s)

s = string(s);
s = replace(s, "&", "&amp;");
s = replace(s, "<", "&lt;");
s = replace(s, ">", "&gt;");
s = replace(s, """", "&quot;");

end
