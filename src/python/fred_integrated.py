#!/usr/bin/env python3
"""
The project's integrated question, across both stores:

    "Which series were revised most in 2026, and what do their agencies'
     press releases say about those revisions?"

Step 1  PostgreSQL  Q13 in sql/fred_queries.sql        (revision counts per series)
Step 2  Neo4j       Q13 in neo4j/cypher/fred_queries.cypher, with the step-1 rows
                    passed as $revised                  (top passages per series)
Step 3  Python      join on series_id and print one line per series.

Both queries are read from the query files, not copied here, so the files
stay the single source. Both connections are read-only.

    export NEO4J_PASSWORD=...          # required; never read from anywhere else
    python src/python/fred_integrated.py [--passages N]

Optional environment: FRED_PG (default "dbname=fred"), NEO4J_URI
(default bolt://127.0.0.1:7687), NEO4J_USER (default neo4j).
"""
import argparse, os, pathlib, re, sys, textwrap
import psycopg
from neo4j import GraphDatabase, READ_ACCESS

ROOT = pathlib.Path(__file__).resolve().parents[2]
SQL_FILE = ROOT / "sql" / "fred_queries.sql"
CYPHER_FILE = ROOT / "neo4j" / "cypher" / "fred_queries.cypher"


def sql_query(label: str) -> str:
    """The statement that follows the '-- <label>' header in fred_queries.sql."""
    text = SQL_FILE.read_text()
    m = re.search(rf"^-- {label}\b.*$", text, re.M)
    if not m:
        raise SystemExit(f"{label} not found in {SQL_FILE}")
    # drop comment lines first: comments may contain ';'
    code = "\n".join(l for l in text[m.end():].splitlines() if not l.lstrip().startswith("--"))
    return code.split(";", 1)[0].strip()


def cypher_query(label: str) -> str:
    """The statement that follows the '// <label>' header in fred_queries.cypher."""
    for block in CYPHER_FILE.read_text().split(";\n"):
        if re.search(rf"^// {label}\s", block, re.M):
            return "\n".join(l for l in block.splitlines() if not l.lstrip().startswith("//")).strip()
    raise SystemExit(f"{label} not found in {CYPHER_FILE}")


def main(passages: int) -> None:
    password = os.environ.get("NEO4J_PASSWORD")
    if not password:
        raise SystemExit("NEO4J_PASSWORD is not set; export it and rerun.")

    # Step 1: PostgreSQL, read-only session
    with psycopg.connect(os.environ.get("FRED_PG", "dbname=fred")) as conn:
        conn.read_only = True
        with conn.cursor() as cur:
            cur.execute(sql_query("Q13"))
            revised = [{"series_id": sid, "release_id": rid, "n_revisions": int(nrev)}
                       for sid, rid, _nvint, nrev in cur.fetchall()]
            cur.execute("SELECT release_id, release_name FROM release WHERE release_id = ANY(%s)",
                        ([r["release_id"] for r in revised],))
            release_names = dict(cur.fetchall())
    if not revised:
        raise SystemExit("SQL Q13 returned no rows: load observations first (fred_load.py).")

    # Step 2: Neo4j, read transaction in a READ-mode session
    driver = GraphDatabase.driver(os.environ.get("NEO4J_URI", "bolt://127.0.0.1:7687"),
                                  auth=(os.environ.get("NEO4J_USER", "neo4j"), password))
    with driver, driver.session(default_access_mode=READ_ACCESS) as session:
        hits = session.execute_read(lambda tx: tx.run(cypher_query("Q13"), revised=revised).data())

    # Step 3: join on series_id, keep each series' best passages (Cypher already orders them)
    by_series: dict[str, list[dict]] = {}
    for h in hits:
        by_series.setdefault(h["se.series_id"], []).append(h)

    print(f"{'series':<10} {'release':<46} {'revisions':>9}  top passage")
    print("-" * 110)
    for rv in revised:
        sid = rv["series_id"]
        rows = by_series.get(sid, [])[:passages]
        release = release_names.get(rv["release_id"], f"release {rv['release_id']}")
        if not rows:
            print(f"{sid:<10} {release[:46]:<46} {rv['n_revisions']:>9}  (no press-release documents loaded)")
            continue
        for i, h in enumerate(rows):
            head = f"{sid:<10} {release[:46]:<46} {rv['n_revisions']:>9}" if i == 0 else " " * 67
            cite = f"[{h['hit.release_date']}, chunk {h['chunk']}, relevance {h['hit.relevance']}]"
            body = textwrap.shorten(" ".join(h["hit.passage"].split()), 200)
            print(f"{head}  {cite}\n{'':67}  {body}")
    print(f"\n{len(revised)} revised series from PostgreSQL; {len(hits)} passages from Neo4j.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[1].strip())
    ap.add_argument("--passages", type=int, default=1, help="passages to print per series (Cypher returns up to 3)")
    main(ap.parse_args().passages)
