# MATLAB reports on the FRED catalog: setup, step by step

Goal: query the FRED catalog from MATLAB (PostgreSQL `fred` and the Neo4j container `data_retrival_neo4j`) and rebuild the verification snapshots in `docs/STATUS_fred_catalog.md` as MATLAB reports. This is a personal project, beyond the ADIT2200 scope.

State on 2026-11-03, tested from MATLAB R2026a with `matlab -batch`:

| Piece | Status |
|---|---|
| Database Toolbox | installed (`postgresql`, `neo4j`, `executeCypher`) |
| MATLAB Report Generator | installed (`mlreportgen.report`, `mlreportgen.dom`) |
| Neo4j from MATLAB | **blocked**: `Database Toolbox Interface for Neo4j Bolt Protocol has not been installed.` |
| PostgreSQL from MATLAB | **blocked**: `fe_sendauth: no password supplied` (role `radar-41-0` has no password) |

Steps 1 and 2 fix the two blockers. Steps 3 to 5 confirm everything works.

---

## Step 1: Install the Neo4j Bolt add-on

MATLAB's `neo4j` function accepts `bolt://` URLs, which Neo4j 2026 requires, but only once the Bolt support package is installed.

1. In MATLAB: **Home → Add-Ons → Get Add-Ons**, search **"Neo4j Bolt"**, and install *Database Toolbox Interface for Neo4j Bolt Protocol*. Or run:
   ```matlab
   matlab.addons.supportpackage.internal.explorer.showSupportPackages('NEO4JBOLT','tripwire')
   ```
2. Sign in with your MathWorks account when asked.
3. Check it installed:
   ```matlab
   exist('database.neo4j.bolt.Neo4jConnect','class')   % should return 8
   ```

## Step 2: Give your PostgreSQL role a password and store it in the vault

MATLAB connects over TCP (`localhost:5432`), which requires a password. `psql` in the terminal does not, because it uses the local socket.

1. In a terminal:
   ```bash
   psql -d fred
   ```
   then at the `fred=#` prompt:
   ```
   \password
   ```
   Enter a new password twice, then `\q`.
2. In MATLAB, store it in the vault (it prompts; the password is never typed into code):
   ```matlab
   setSecret("fred_pg")
   ```
3. Store the Neo4j password the same way. It is the value in `neo4j/.env`, which is git-ignored, so don't paste it anywhere else:
   ```matlab
   setSecret("neo4j_pw")
   ```

This matches how `src/fred_api_request.m` already gets the FRED key (`getSecret("MyFREDKey")`).

## Step 3: Make sure the databases are running

```bash
pg_lsclusters                         # 16 main 5432 online
docker ps --filter name=data_retrival_neo4j   # Up ...
```
If Neo4j is not running: `cd neo4j && docker compose up -d` (needs `NEO4J_PASSWORD` exported in that shell).

## Step 4: Connection test in MATLAB

```matlab
% PostgreSQL
conn = postgresql("radar-41-0", getSecret("fred_pg"), ...
    "Server","localhost", "PortNumber",5432, "DatabaseName","fred");
fetch(conn, "SELECT count(*) AS categories FROM category")     % expect 5200
close(conn)

% Neo4j
nc = neo4j("bolt://localhost:7687", "neo4j", getSecret("neo4j_pw"));
executeCypher(nc, "MATCH (c:Category {provider_id:'fred'}) RETURN count(c) AS categories")   % expect 5200
close(nc)
```
Both return MATLAB tables. If both say 5200, the setup is complete.

## Step 5: Expected values to check your reports against

These come from `docs/STATUS_fred_catalog.md`. If a report disagrees, either the query or the data changed.

| Check | Expected |
|---|---|
| series (PostgreSQL) = Series in the latest load snapshot (Neo4j) | 400 = 400 |
| observation vintages (PostgreSQL only) | 63,047 |
| categories in both stores / parent links / max depth | 5,200 / 5,199 / 9 |
| Q06 on category 10, SQL vs Cypher | 102 rows each, identical |
| Q06 on category 3008 | 29 rows each, 15 distinct series |
| Documents / Chunks (Neo4j) | 12 / 1,853 (768-dim embeddings) |
| SQL Q01–Q13 row counts | 214, 7, 1, 335, 100, 102, 5, 18117, 145, 2, 49, 184, 4 |

---

## Snapshots to rebuild as reports

| Snapshot | PostgreSQL source | Neo4j source |
|---|---|---|
| Row counts per table; vintages per series | `SELECT count(*)` per table; `observation GROUP BY series_id` | none (observations are not in the graph by design) |
| Sample-data checks (Q07, Q10, Q11, trigger proof) | `sql/fred_queries.sql`; the checks in the `sample` step of `run_all.sh` | none |
| Q01–Q13, SQL vs Cypher | `sql/fred_queries.sql` | `neo4j/cypher/fred_queries.cypher` (same numbering) |
| Q06 identity (category 10, category 3008) | Q06 recursive CTE | Q06 `[:CHILD_OF*0..]` |
| Category tree: counts, depth, the 8 top-level subtrees | the recursive queries in the `categories` step of `run_all.sh` | `006_fred_category_crawl_load.cypher` summary; depth query in the same step |
| Load cross-checks (400 = 400, 1,853 chunks) | `count(*)` | return values of `004` and `005` |
| Integrated Q13 (revisions plus top passage) | Q13 | Q13 with `$revised`; `src/python/fred_integrated.py` shows the join |
| Snapshot provenance | none | `MATCH (s:CatalogSnapshot) RETURN s` (level-one 2026-09-02T04-42-54Z, crawl 2026-09-02T16-48-53Z, loads 2026-11-03T23-15-31Z and later) |

Notes for writing the queries in MATLAB:
- **Category IDs:** `category_id` is an integer in SQL (`3008`) but a string in the graph (`'3008'`), following the key convention from 001.
- **Comments in the query files:** they contain `;`, so strip `--` / `//` comment lines before splitting a file on `;`.
- **Cypher parameters:** pass them with `executeCypher` rather than pasting values into the query string. Check `doc executeCypher` in your release for the parameter syntax.

## When something fails

| Symptom | Likely cause |
|---|---|
| `Bolt Protocol has not been installed` | Step 1 not done |
| `fe_sendauth: no password supplied` / `password authentication failed` | Step 2 not done, or the wrong secret name |
| Neo4j connection refused | container stopped (Step 3) |
| Counts differ from Step 5 | data reloaded since 2026-11-03; rerun `./run_all.sh graph categories documents` to compare |
