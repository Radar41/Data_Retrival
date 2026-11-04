"""Design diagrams for the FRED catalog beyond the ERD.

  fred_fd_maps.png      functional-dependency maps, one per relation (course notation:
                        determinant -> dependents, PK underlined, transitive/partial shown)
  fred_table_map.png    the logical model as a table map: PK, FK arrows between relations
  fred_graph_schema.png the Neo4j meta-graph: labels, key properties, relationship types

Run:  python3 docs/erd/build_design_diagrams.py
"""
import pathlib, subprocess

OUT = pathlib.Path(__file__).parent
NAVY, RED, GREEN = "#1f3557", "#8a1c22", "#2f7a4f"

# relation -> (pk attrs, non-key attrs, fks {attr: target relation})
REL = {
    "FREQUENCY": (["frequency_code"], ["frequency_name"], {}),
    "UNITS": (["units_code"], ["units_name"], {}),
    "SEASONAL_ADJUSTMENT": (["sa_code"], ["sa_name"], {}),
    "SOURCE": (["source_id"], ["source_name", "source_link"], {}),
    "RELEASE": (["release_id"], ["release_name", "press_release", "release_link"], {}),
    "RELEASE_SOURCE": (["release_id", "source_id"], [], {"release_id": "RELEASE", "source_id": "SOURCE"}),
    "RELEASE_DATE": (["release_id", "release_date"], ["date_status"], {"release_id": "RELEASE"}),
    "CATEGORY": (["category_id"], ["category_name", "parent_id"], {"parent_id": "CATEGORY"}),
    "TAG_GROUP": (["group_id"], ["group_name"], {}),
    "TAG": (["tag_name"], ["group_id", "tag_notes", "popularity"], {"group_id": "TAG_GROUP"}),
    "SERIES": (["series_id"], ["title", "release_id", "frequency_code", "units_code", "sa_code",
                               "[observation_start]", "[observation_end]", "last_updated", "popularity", "notes"],
               {"release_id": "RELEASE", "frequency_code": "FREQUENCY", "units_code": "UNITS", "sa_code": "SEASONAL_ADJUSTMENT"}),
    "SERIES_CATEGORY": (["series_id", "category_id"], [], {"series_id": "SERIES", "category_id": "CATEGORY"}),
    "SERIES_TAG": (["series_id", "tag_name"], [], {"series_id": "SERIES", "tag_name": "TAG"}),
    "OBSERVATION": (["series_id", "observation_date", "realtime_start"], ["realtime_end", "value"], {"series_id": "SERIES"}),
}


def fd_maps():
    """One dependency map per relation with non-key attributes: a bar for the key,
    arrows to each dependent. All-key relations are listed as a note."""
    g = ['digraph FD {', 'graph [rankdir=LR, fontname="Helvetica", labelloc=t, fontsize=18, '
         'label="Functional dependency maps (all relations in 3NF: every determinant is the whole primary key)", '
         'nodesep=0.25, ranksep=0.5, compound=true];',
         'node [fontname="Helvetica", fontsize=10, shape=box, style="rounded,filled", fillcolor="white", color="%s"];' % NAVY,
         'edge [color="%s", arrowsize=0.7];' % NAVY]
    i = 0
    for name, (pk, nk, fk) in REL.items():
        if not nk:
            continue
        g.append(f'subgraph cluster_{i} {{ label="{name}"; style="rounded"; color="{NAVY}"; fontname="Helvetica-Bold"; fontsize=11;')
        key = f'k{i}'
        g.append(f'{key} [label=<<U>{"<BR/>".join(pk)}</U>>, fillcolor="#e8eef7"];')
        for j, a in enumerate(nk):
            fill = "#fbefdc" if a.startswith("[") else "white"
            lab = a + (" (FK)" if a in fk else "")
            g.append(f'a{i}_{j} [label="{lab}", fillcolor="{fill}"];')
            g.append(f'{key} -> a{i}_{j};')
        g.append('}')
        i += 1
    allkey = [n for n, (pk, nk, fk) in REL.items() if not nk]
    g.append(f'note [shape=note, fillcolor="#f8f0dc", label="All-key relations (no non-key attributes, nothing to depend):\\n{", ".join(allkey)}\\n\\n'
             f'Derived attributes in [brackets] are kept as controlled denormalization\\nand maintained by trigger (fred_triggers.sql)."];')
    g.append('}')
    return "\n".join(g)


def table_map():
    """Table map: each relation as a record, PK underlined, FK columns tagged, FK arrows."""
    g = ['digraph TM {', 'graph [rankdir=LR, fontname="Helvetica", labelloc=t, fontsize=18, '
         'label="Table map (logical model): underline = primary key, FK = foreign key, arrows point to the referenced key", '
         'nodesep=0.35, ranksep=0.9, splines=true];',
         'node [fontname="Helvetica", fontsize=10, shape=plain];', 'edge [color="%s", arrowsize=0.7, penwidth=1.1];' % RED]
    for name, (pk, nk, fk) in REL.items():
        rows = [f'<TR><TD BGCOLOR="{NAVY}" COLSPAN="2"><FONT COLOR="white"><B>{name}</B></FONT></TD></TR>']
        for a in pk:
            rows.append(f'<TR><TD PORT="{a}" ALIGN="LEFT"><U>{a}</U></TD><TD>{"FK" if a in fk else "PK"}</TD></TR>')
        for a in nk:
            port = a.strip("[]")
            rows.append(f'<TR><TD PORT="{port}" ALIGN="LEFT">{a}</TD><TD>{"FK" if a in fk else ""}</TD></TR>')
        g.append(f'"{name}" [label=<<TABLE BORDER="1" CELLBORDER="0" CELLSPACING="0" CELLPADDING="3" COLOR="{NAVY}">{"".join(rows)}</TABLE>>];')
    for name, (pk, nk, fk) in REL.items():
        for a, tgt in fk.items():
            tpk = REL[tgt][0][0] if tgt != "CATEGORY" else "category_id"
            g.append(f'"{name}":"{a}" -> "{tgt}":"{tpk}";')
    g.append('{rank=same; FREQUENCY; UNITS; SEASONAL_ADJUSTMENT;}')
    g.append('}')
    return "\n".join(g)


def graph_schema():
    """Neo4j meta-graph: one node per label with its key property, edges for relationship types."""
    labels = {
        "Provider": "provider_id", "CatalogSnapshot": "snapshot_id", "Source": "source_key", "Release": "release_key",
        "ReleaseDate": "rd_key", "Series": "catalog_key", "Frequency": "code", "Units": "code",
        "SeasonalAdjustment": "code", "Category": "(provider_id, category_id)", "Tag": "tag_name",
        "TagGroup": "group_id", "Document": "doc_id", "Chunk": "chunk_key",
    }
    rels = [("Provider", "EXPOSED_IN", "CatalogSnapshot"), ("CatalogSnapshot", "CONTAINS_SERIES", "Series"),
            ("CatalogSnapshot", "CONTAINS_CATEGORY", "Category"), ("Release", "PUBLISHED_BY", "Source"),
            ("Release", "SCHEDULED_ON", "ReleaseDate"), ("Series", "IN_RELEASE", "Release"),
            ("Series", "HAS_FREQUENCY", "Frequency"), ("Series", "MEASURED_IN", "Units"),
            ("Series", "ADJUSTED", "SeasonalAdjustment"), ("Series", "IN_CATEGORY", "Category"),
            ("Category", "CHILD_OF", "Category"), ("Series", "TAGGED", "Tag"), ("Tag", "IN_GROUP", "TagGroup"),
            ("Document", "DESCRIBES", "Release"), ("Document", "HAS_CHUNK", "Chunk")]
    g = ['digraph GS {', 'graph [rankdir=LR, fontname="Helvetica", labelloc=t, fontsize=18, '
         'label="Neo4j graph schema: node label {key property}, relationship types. '
         'Associative tables and foreign keys from the table map become relationship types here.", nodesep=0.4, ranksep=0.8];',
         'node [fontname="Helvetica", fontsize=10, shape=ellipse, style=filled, fillcolor="#e3f2e9", color="%s"];' % GREEN,
         'edge [fontname="Helvetica", fontsize=9, color="%s", arrowsize=0.7];' % GREEN]
    for lab, key in labels.items():
        fill = "#fbefdc" if lab in ("Document", "Chunk") else "#e8eef7" if lab in ("Provider", "CatalogSnapshot") else "#e3f2e9"
        g.append(f'"{lab}" [label=<<B>:{lab}</B><BR/><FONT POINT-SIZE="8">{{{key}}}</FONT>>, fillcolor="{fill}"];')
    for a, r, b in rels:
        g.append(f'"{a}" -> "{b}" [label=":{r}"];')
    g.append('note [shape=note, fillcolor="#f8f0dc", fontsize=9, label="Not in the graph by design:\\nOBSERVATION vintages (PostgreSQL only)\\n\\n'
             'Indexes: fulltext chunk_text on Chunk.text,\\nvector chunk_embedding on Chunk.embedding (768, cosine)"];')
    g.append('}')
    return "\n".join(g)


for stem, src in (("fred_fd_maps", fd_maps()), ("fred_table_map", table_map()), ("fred_graph_schema", graph_schema())):
    (OUT / f"{stem}.dot").write_text(src)
    subprocess.run(["dot", "-Gdpi=160", "-Tpng", str(OUT / f"{stem}.dot"), "-o", str(OUT / f"{stem}.png")], check=True)
    print("wrote", stem)
