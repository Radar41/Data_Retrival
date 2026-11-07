"""Build the FRED Metadata Catalog ERD (Hoffer crow's foot notation) as Graphviz.

Writes two diagrams:
  fred_erd_attributes  - entities with attributes, identifiers underlined
  fred_erd_entities    - entities and relationships only
"""
import subprocess, pathlib

OUT = pathlib.Path(__file__).parent

# name -> (kind, [attributes]); "_x" marks an identifier, "{x}" multivalued, "[x]" derived
ENT = {
    "SOURCE": ("strong", ["_Source ID", "Source Name", "Source Link"]),
    "RELEASE": ("strong", ["_Release ID", "Release Name", "Press Release Flag", "Release Link"]),
    "RELEASE_SOURCE": ("assoc", []),
    "RELEASE_DATE": ("weak", ["_Release Date", "Date Status (scheduled / actual)"]),
    "RELEASE_TABLE_ELEMENT": ("strong", ["_Element ID", "Element Type", "Element Name", "Element Level",
                                          "Line No", "Series ID (text)"]),
    "SERIES": ("strong", ["_Series ID", "Title", "[Observation Start]", "[Observation End]",
                           "Last Updated", "Popularity", "Notes"]),
    "FREQUENCY": ("strong", ["_Frequency Code", "Frequency Name"]),
    "UNITS": ("strong", ["_Units Code", "Units Name"]),
    "SEASONAL_ADJUSTMENT": ("strong", ["_SA Code", "SA Name"]),
    "CATEGORY": ("strong", ["_Category ID", "Category Name"]),
    "SERIES_CATEGORY": ("assoc", []),
    "TAG": ("strong", ["_Tag Name", "Tag Notes", "Popularity"]),
    "TAG_GROUP": ("strong", ["_Group ID", "Group Name"]),
    "SERIES_TAG": ("assoc", []),
    "OBSERVATION": ("weak", ["_Observation Date", "_Realtime Start", "Realtime End", "Value"]),
    "VINTAGE_DATE": ("weak", ["_Vintage Date"]),
}

# Crow's foot ends, Graphviz arrow strings drawn outward from the entity:
ONE = "teetee"          # exactly one
ONE_MANY = "crowtee"    # one or many
ZERO_MANY = "crowodot"  # zero or many
ZERO_ONE = "teeodot"    # zero or one

# (a, b, end at a, end at b, label, identifying?)
REL = [
    ("SOURCE", "RELEASE_SOURCE", ONE, ONE_MANY, "Publishes", False),
    ("RELEASE_SOURCE", "RELEASE", ONE_MANY, ONE, "Published By", False),
    ("RELEASE", "RELEASE_DATE", ONE, ONE_MANY, "Is Scheduled", True),
    ("RELEASE", "RELEASE_TABLE_ELEMENT", ONE, ZERO_MANY, "Structures", False),
    ("RELEASE_TABLE_ELEMENT", "RELEASE_TABLE_ELEMENT", ZERO_ONE, ZERO_MANY, "Contains", False),
    ("RELEASE", "SERIES", ONE, ONE_MANY, "Contains", False),
    ("FREQUENCY", "SERIES", ONE, ZERO_MANY, "Describes", False),
    ("UNITS", "SERIES", ONE, ZERO_MANY, "Measures", False),
    ("SEASONAL_ADJUSTMENT", "SERIES", ONE, ZERO_MANY, "Adjusts", False),
    ("SERIES", "SERIES_CATEGORY", ONE, ONE_MANY, "Classified In", False),
    ("SERIES_CATEGORY", "CATEGORY", ZERO_MANY, ONE, "Holds", False),
    ("CATEGORY", "CATEGORY", ZERO_ONE, ZERO_MANY, "Parent Of", False),
    ("SERIES", "SERIES_TAG", ONE, ZERO_MANY, "Carries", False),
    ("SERIES_TAG", "TAG", ONE_MANY, ONE, "Applied As", False),
    ("TAG_GROUP", "TAG", ONE, ONE_MANY, "Groups", False),
    ("SERIES", "OBSERVATION", ONE, ZERO_MANY, "Has", True),
    ("SERIES", "VINTAGE_DATE", ONE, ZERO_MANY, "Revised On", True),
]

NAVY = "#1f3557"


def label(name, kind, attrs, with_attrs):
    title = name.replace("_", " ")
    border = 2 if kind == "weak" else 1
    style = ' STYLE="ROUNDED"' if kind == "assoc" else ""
    head = (f'<TR><TD BGCOLOR="{NAVY}" CELLPADDING="6"><FONT COLOR="white" POINT-SIZE="13">'
            f'<B>{title}</B></FONT></TD></TR>')
    rows = ""
    if with_attrs and attrs:
        lines = []
        for a in attrs:
            if a.startswith("_"):
                lines.append(f"<U>{a[1:]}</U>")
            else:
                lines.append(a)
        body = '<BR ALIGN="LEFT"/>'.join(lines) + '<BR ALIGN="LEFT"/>'
        rows = f'<TR><TD ALIGN="LEFT" BALIGN="LEFT" CELLPADDING="6">{body}</TD></TR>'
    outer = (f'<TABLE BORDER="{border}" CELLBORDER="0" CELLSPACING="{2 if kind == "weak" else 0}"'
             f' COLOR="{NAVY}"{style}>')
    if kind == "weak":
        inner = f'<TABLE BORDER="1" CELLBORDER="0" CELLSPACING="0" COLOR="{NAVY}">{head}{rows}</TABLE>'
        return f"<{outer}<TR><TD>{inner}</TD></TR></TABLE>>"
    return f"<{outer}{head}{rows}</TABLE>>"


def build(stem, with_attrs):
    g = ['digraph ERD {',
         'graph [rankdir=LR, splines=polyline, nodesep=0.7, ranksep=1.1, pad=0.4, fontname="Helvetica", '
         'labelloc=t, fontsize=18, label="FRED Metadata Catalog: E-R Diagram'
         + (' (attributes and identifiers)' if with_attrs else ' (entities and relationships)') + '"];',
         'node [shape=plaintext, fontname="Helvetica", fontsize=11];',
         f'edge [dir=both, color="{NAVY}", fontname="Helvetica", fontsize=10, arrowsize=0.9];']
    for n, (k, a) in ENT.items():
        g.append(f'"{n}" [label={label(n, k, a, with_attrs)}];')
    for a, b, ea, eb, lab, ident in REL:
        style = "solid" if ident else "solid"
        pen = 2.0 if ident else 1.1
        g.append(f'"{a}" -> "{b}" [arrowtail={ea}, arrowhead={eb}, label="{lab}", penwidth={pen}, style={style}];')
    g.append('{rank=same; FREQUENCY; UNITS; SEASONAL_ADJUSTMENT;}')
    g.append('{rank=same; TAG_GROUP; TAG;}')
    g.append('}')
    dot = OUT / f"{stem}.dot"
    dot.write_text("\n".join(g))
    for fmt in ("png", "svg"):
        args = ["dot", f"-T{fmt}", str(dot), "-o", str(OUT / f"{stem}.{fmt}")]
        if fmt == "png":
            args.insert(1, "-Gdpi=170")
        subprocess.run(args, check=True)


build("fred_erd_attributes", True)
build("fred_erd_entities", False)
print("ok")
