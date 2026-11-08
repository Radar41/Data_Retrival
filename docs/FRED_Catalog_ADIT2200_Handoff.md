# FRED Metadata Catalog: handoff to the local coding agent

Read this whole file before touching anything. It is the brief for whoever (or whatever) is coding on Adrian's T9 workstation. It was written by the cloud session that built the files on branch `fred-catalog-adit2200`; that session cannot reach the T9, Neo4j, or the FRED API, so everything below that says "untested" is yours to run first.

Owner: Adrian Aziza (azizaa@bc.edu). Machine: Ubuntu, user `radar-41-0`, repo expected at `~/Documents/Data_Retrival`.

---

## 0. The mission in one paragraph

Stand up the FRED Metadata Catalog end to end on the T9: PostgreSQL holds the normalized relational core including every observation vintage; the existing Neo4j container (`neo4j/compose.yaml`) holds the catalog graph, its provenance, and the press-release document layer; `src/python/fred_load.py` fills both from the FRED API. Then run the two query sets and make sure every query returns sensible rows against real data. This is Adrian's Boston College ADIT2200 term project, and the same two stores are the data infrastructure for his other projects (section 7), so build it clean, not fast.

Adrian writes his own prose for class submissions and wants to write and debug the Cypher himself where learning is the point. Your job is the plumbing: environments, loads, verification, fixes to the scripts, and a status report he can read. Do not write discussion posts or report narrative for him.

---

## 1. What is on this branch

| Path | What it is | State |
|---|---|---|
| `sql/fred_schema.sql` | DDL: 16 tables, named PK/FK/CHECK constraints, 14 indexes, commented per column. ANSI SQL; parses as PostgreSQL and MySQL 8. **This file is the Week 9 Physical Design submission, due Sat 2026-11-08.** | Ran clean on PostgreSQL 16 |
| `sql/fred_triggers.sql` | BEFORE INSERT trigger that closes the prior vintage (business rule 11), AFTER INSERT trigger that maintains the derived `series.observation_start/end`, `value_as_of()` function, `post_release()` procedure. PL/pgSQL; MySQL equivalents in comments. | Ran and tested |
| `sql/fred_sample_data.sql` | Real FRED ids and names, illustrative values, 5 releases, 7 series, 21 observation vintages. For proving the schema before a real load. | Ran |
| `sql/fred_queries.sql` | Q01 to Q13, each tied to a course technique (joins, outer joins, subqueries, recursive CTE, CASE, window LAG, EXCEPT, vintage lookup). | All 13 ran, output checked |
| `neo4j/cypher/003_fred_catalog_schema.cypher` | Constraints and indexes for the catalog graph, plus full-text and vector indexes on `Chunk`. Extends 001/002; keys follow this repo's conventions. | Ran on Community 2026.07.1 |
| `neo4j/cypher/004_fred_catalog_load.cypher` | LOAD CSV import of the catalog CSVs, linked to a `CatalogSnapshot`. Needs `:param snapshot_id`. | Ran; all row counts equal the SQL counterparts |
| `neo4j/cypher/005_fred_documents_load.cypher` | Document and Chunk import with embeddings parsed from a JSON-array string. Documents are dated PDFs (`kind = press_release_pdf`) and release pages (`kind = release_page`). | Ran 2026-11-08: 164 documents (13 PDFs, 151 release pages), 3,375 chunks |
| `neo4j/cypher/fred_queries.cypher` | Graph versions of Q01 to Q06, Q09, Q11, Q12, Q13, plus graph-only Q06b and Q12b. | Ran; all row counts equal the SQL counterparts |
| `src/python/fred_load.py` | FRED API to PostgreSQL + Neo4j CSVs + raw payload manifest; `--max-series`, throttled; `--documents` for press releases: dated PDFs plus the `release_link` page of every `press_release` release. | Run against the live API 2026-11-03: 400 series, 63,047 vintages, 12 documents; 2026-11-08: 164 documents |
| `docs/erd/fred.er` | ERD in BurntSushi `erd` text format (Adrian's `erd` repo is a fork of that tool). | Not rendered yet |
| `docs/erd/build_erd.py`, `*.png` | Graphviz ERD (Hoffer crow's foot) and the data architecture diagram. | Rendered |
| `docs/fred_logical_design.md` | Relations, FDs, 1NF to 3NF proof, denormalization reasons, JSON and document representation plan. Week 6 submission (overdue). | Written |
| `docs/ADIT2200_course_map.md` | Every graded item in the course, due dates, status, what each needs. | Current as of 2026-11-03 |

---

## 2. Conventions you must keep (they come from this repo's README and are not negotiable)

1. **Raw payloads are immutable.** `fred_load.py` writes every API response to `payloads/*.json` plus `payloads/manifest.json` with SHA-256, byte count, and UTC retrieval time. Never edit those files; delete and re-pull if wrong. `payloads/` is git-ignored.
2. **Dense observations never go in Neo4j.** Every vintage goes to PostgreSQL `observation`. The graph gets catalog, provenance, documents. If you find yourself writing `(:Observation)` nodes, stop.
3. **Keys match the existing graph.** `Provider {provider_id:"fred"}`, `Category {provider_id, category_id}` with `category_key = "fred:category:<id>"`, `Series.series_catalog_key = "fred:<series_id>"`, `Release.release_key = "fred:release:<id>"`, `Source.source_key = "fred:source:<id>"`. The `Series` label is shared with the datalist graph from `cypher/import_fred_datalist_banks_weekly_catalog.cypher`; same key format means same node.
4. **No APOC dependency.** Everything loads with LOAD CSV from the mounted import directory `data/catalog/neo4j-import/` (container path `/var/lib/neo4j/import/`). `fred_load.py` writes into `data/catalog/neo4j-import/fred_catalog/`.
5. **No secrets in git or in graph properties.** `FRED_API_KEY` and `NEO4J_PASSWORD` come from the environment only.
6. **Every graph load is a snapshot.** Pass `:param snapshot_id => "<UTC timestamp>"` to 004 so the `CatalogSnapshot` node records it.
7. **Natural keys, no surrogates.** FRED's ids are stable and public; the SQL uses them as primary keys. Do not add `SERIAL` columns.
8. **Leave the forecasting code alone.** `src/+gdss/`, `src/*totbkcrnsa*`, `src/run_gdss_evaluation.m`, `docs/GDSS_*`, `docs/forecasting_models_taxonomy.md`, `docs/Model_ssm.txt` are a different project (regression and state-space work). Out of scope here.

---

## 3. Environment on the T9

Check, install what is missing, record versions in the status report.

```bash
# PostgreSQL 16 (or 15): a local cluster, database "fred", your user as owner
psql --version
sudo -u postgres createuser -s radar-41-0 2>/dev/null; createdb fred

# Python 3.11+ for the loader
python3 -m venv ~/.venvs/fred && source ~/.venvs/fred/bin/activate
pip install -r src/python/requirements.txt

# Neo4j: the project container
cd neo4j && NEO4J_PASSWORD=... docker compose up -d && cd ..
# cypher-shell: either `docker exec -it data_retrival_neo4j cypher-shell -u neo4j -p ...`
# or install cypher-shell locally and point at bolt://127.0.0.1:21003
# (ports follow the radar-41 registry: 21003 Bolt, 21004 HTTP; 7687 belongs to the native Memgraph)

# Graphviz (ERD rendering) and the erd tool
dot -V
# erd: Adrian's fork at github.com/Radar41/erd; `stack install` there, or
# docker run -i ghcr.io/burntsushi/erd:latest < docs/erd/fred.er > docs/erd/fred_erd.pdf

export FRED_API_KEY=...        # from Adrian, never written anywhere
export FRED_PG="dbname=fred"
export NEO4J_IMPORT="$PWD/data/catalog/neo4j-import"
export FRED_PAYLOADS="$PWD/payloads"
```

Neo4j notes (resolved 2026-11-03, see `docs/STATUS_fred_catalog.md`): the container is Community 2026.07.1. `IS NODE KEY` is Enterprise-only, so 003 uses single-property uniqueness on concatenated keys `ReleaseDate.rd_key` and `Chunk.chunk_key`. Composite `IS UNIQUE` does work on Community (001 already uses one). The loader cannot write into the container-owned import directory; write CSVs to `data/staging/neo4j-import/` and `docker cp` them in (commands in the status report).

---

## 4. Run order and what "working" looks like

### 4.1 PostgreSQL, sample data first
```bash
psql -d fred -v ON_ERROR_STOP=1 -f sql/fred_schema.sql
psql -d fred -v ON_ERROR_STOP=1 -f sql/fred_triggers.sql
psql -d fred -v ON_ERROR_STOP=1 -f sql/fred_sample_data.sql
psql -d fred -v ON_ERROR_STOP=1 -f sql/fred_queries.sql > /tmp/q_sample.txt
```
Expected: no errors; Q07 shows PAYEMS 3 revisions, GDPC1 2, INDPRO 1, UNRATE 1; Q10 shows 159150 as of 2026-09-15 and 159090 current; Q11 shows only STALE1.

Trigger proof (this is also the Week 10 homework pattern):
```sql
INSERT INTO observation VALUES ('UNRATE', DATE '2026-09-01', DATE '2026-11-06', DEFAULT, 4.5);
SELECT * FROM observation WHERE series_id='UNRATE' AND observation_date=DATE '2026-09-01' ORDER BY realtime_start;
-- the 2026-10-02 row must now end 2026-11-05
SELECT value_as_of('UNRATE', DATE '2026-09-01', DATE '2026-10-15');  -- 4.4
```

### 4.2 Real data
Start small so a mistake costs minutes, not an API quota:
```bash
psql -d fred -c 'TRUNCATE source, release, category, tag_group, tag CASCADE'
python src/python/fred_load.py --releases 50 10 53 13 --observations UNRATE PAYEMS GDPC1 CPIAUCSL INDPRO
```
Expected output ends with `loaded N series from 4 releases` (N is in the hundreds; release 50 alone is large), `payloads/manifest.json` exists, and `data/catalog/neo4j-import/fred_catalog/` holds 10 CSVs. Then rerun `sql/fred_queries.sql`; every query must return rows (Q05's date window is the week of 2026-11-02; widen it if the release calendar moved).

Known soft spots in the loader, check them against real responses:
- `last_updated` arrives as `"2026-10-02 07:46:02-05"`; the loader slices `[:19]` and drops the offset. Fine for the class; note it.
- `release/dates` with `include_release_dates_with_no_data=true` can be thousands of rows per release. Fine.
- `series/tags` and `series/categories` are one call per series. For release 50 that is ~2,000 calls at 120/min. Either accept the wait or add `--max-series N` to the loader.
- Category walk-up assumes `parent_id` chains terminate at 0. They do.
- If a series' `units_short` is longer than 40 chars, `series.units_code VARCHAR(40)` rejects it. Widen to 80 in the DDL and in the lookup table if it happens; record it.

### 4.3 Neo4j
```
:param snapshot_id => "2026-11-04T00-00-00Z"   # the real UTC time of the load
:source neo4j/cypher/003_fred_catalog_schema.cypher
:source neo4j/cypher/004_fred_catalog_load.cypher
```
004 ends by returning `series_loaded`; it must equal the SQL `SELECT count(*) FROM series`. Then run `neo4j/cypher/fred_queries.cypher` statement by statement. Q06 (`[:CHILD_OF*0..]` from category 10) must return the same series as SQL Q06 (the recursive CTE). That equality is the whole point of the SQL-vs-Cypher comparison Adrian presents at the end, so record both counts.

Q13 needs the SQL result passed in: run SQL Q13, then
```
:param revised => [{series_id:'PAYEMS', release_id:50, n_revisions:3}, ...]
```
It returns nothing until 005 has documents loaded, which is section 5.

### 4.4 ERD render
```bash
erd -i docs/erd/fred.er -f png -o docs/erd/fred_erd_erdtool.png
python3 docs/erd/build_erd.py      # regenerates the Graphviz versions (16 entities since 7 Nov: RELEASE_TABLE_ELEMENT, VINTAGE_DATE)
```
Compare the two visually; they should show the same 16 entities and 17 relationships.

---

## 5. What does not exist yet (build these, in this order)

1. ~~`fred_load.py --documents`~~ **Done 2026-11-03.** Covers releases 50, 10, 13; GDP (53) has no stable URL pattern and is skipped. **Widened 2026-11-08:** the same step now also fetches the page behind FRED's `release_link` for every release flagged `press_release` (151 of 180 fetched; the rest are listed as `skipped:` in the documents log: no link, blocked host, or no text). Original spec: for each `release_date` with `date_status='actual'` in the loaded releases, download the agency press release PDF (BLS: `https://www.bls.gov/news.release/archives/empsit_MMDDYYYY.pdf` and `cpi_MMDDYYYY.pdf`; BEA GDP: `https://www.bea.gov/sites/default/files/YYYY-MM/gdpNqYY_adv.pdf` style, verify the pattern; FRB G.17: `https://www.federalreserve.gov/releases/g17/YYYYMMDD/g17.pdf`), register it unchanged under `data/raw/documents/<release_id>/<release_date>.pdf` with SHA-256, extract text (pypdf), split into ~800-character chunks, embed with a local sentence-transformer (`all-mpnet-base-v2` is 768-dim and matches 003; if you choose another model, change the dimension in 003), and write `documents.csv` and `chunks.csv` in the shapes 005 documents. Start with the last 6 Employment Situation releases; that is enough for Q13.
2. **`src/python/fred_integrated.py`**: runs SQL Q13, passes the result to Cypher Q13 (neo4j Python driver, read-only), prints a joined table: series, release, revisions, top passage. This is the project's required integrated question and the demo for the presentation.
3. **A `Makefile` or `run_all.sh`** at repo root that does 4.1 through 4.3 in order with `set -e`, so the whole thing is reproducible in one command on a clean machine.
4. **Optional, only if time**: a MATLAB entry point `src/fred_catalog_pg.m` that reads the PostgreSQL tables via Database Toolbox, so the catalog is reachable from Adrian's MATLAB-first workflow without going through Python.

---

## 6. How to report back

Write `docs/STATUS_fred_catalog.md` and commit it on this branch. Format:

```
# Status: FRED catalog on T9   (UTC timestamp)
## Environment     versions of psql, python, neo4j, cypher-shell, docker
## 4.1 sample run   pass/fail, paste the Q07/Q10/Q11 rows
## 4.2 real load    releases, series count, observation row count, wall time, any schema edits
## 4.3 neo4j        constraints that needed changing, series_loaded, Q06 SQL count vs Cypher count
## 5.x built        what exists now, how to run it
## Diffs to review  every file you changed under sql/ neo4j/ src/, one line each on why
## Open             anything blocked, with the exact error text
```
Commit messages: short imperative subject, body says what was verified. One commit per logical change. Push the branch; do not merge to `main` (Adrian merges after review).

The cloud session reads that status file and the diff next time Adrian opens it. Be specific: exact error strings, row counts, and the command that produced them.

---

## 7. How this connects to Adrian's other projects (so you do not build it twice)

- **ADIT2200 Database Management (the class).** The FRED catalog is the term project. Deliverables and dates are in `docs/ADIT2200_course_map.md`. The class also requires him to present SQL against Cypher, which is why the two query files are numbered identically.
- **This repo's existing pipeline.** Path A (API category crawl) and Path B (downloaded datalist archives) already produce `Category` and `Series` nodes. The new scripts extend that graph; they do not replace `001`, `002`, or `cypher/import_fred_datalist_banks_weekly_catalog.cypher`.
- **K-Space.** A philanthropic project Adrian is pitching soon. It will run on this same PostgreSQL + Neo4j stack. Nothing K-Space-specific goes in this repo, but keep the schema general: no class-specific hacks.
- **Vector graph database / Memgraph / Mem0.** Adrian intends to port the Cypher to Memgraph and use Mem0 as a memory layer on top, and later to feed an e3nn-based graph model. Memgraph speaks Cypher; keep the queries free of Neo4j-only procedures where you can, and flag every `db.index.*` and `db.create.*` call in a comment as "Neo4j-specific".
- **`erd` repo.** His fork of BurntSushi/erd. `docs/erd/fred.er` is for it. Nothing to change there.
- **Atlas / DFSA, radar-41 cluster, Archimedes, residual work.** Separate. Do not pull them in.

---

## 8. Things that will waste your time if you do them

- Running `fred_load.py` against all of FRED. Four releases is the scope. The full catalog is ~840k series.
- Re-deriving the ERD. It was approved in principle by the instructor ("looks pretty good"); the only open comment was about redundant data, which `docs/fred_logical_design.md` section 5 answers.
- Converting the SQL to MySQL. It already parses as MySQL 8; the class accepts PostgreSQL.
- Adding an ORM. Plain `psycopg` and plain Cypher are what the class grades and what Adrian is learning.
- Touching `data/catalog/fred/crawls/active/checkpoint.mat`. The README says never delete it.
