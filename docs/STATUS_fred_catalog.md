# Status: FRED catalog on T9   (2026-11-03T22:43:10Z)

**Result: stopped in section 3, before 4.1.** Two blockers need Adrian (listed under Open). Nothing under `sql/`, `neo4j/` or `src/` has been run or changed yet.

## Environment

| Component | Version / state |
|---|---|
| psql | client 18.6; server **PostgreSQL 16.15** (cluster `16/main`, port 5432, online) |
| python | 3.14.4; venv `~/.venvs/fred` created, `psycopg[binary]` 3.3.7 and `requests` 2.34.2 installed from `src/python/requirements.txt` |
| docker | 29.1.3; container `data_retrival_neo4j` running (up 26h) |
| neo4j | **Community 2026.07.1** (`neo4j:community`). Password is in `neo4j/.env`, not in git. |
| cypher-shell | not installed locally; use `docker exec data_retrival_neo4j cypher-shell` |
| graphviz | `dot` 14.1.2 |
| erd / stack | not installed; 4.4 will use `docker run -i ghcr.io/burntsushi/erd:latest` |

Because the container is Community, the three `IS NODE KEY` constraints in `003_fred_catalog_schema.cypher` are expected to fail. The fix is the concatenated-key workaround in handoff section 3 (`rd_key`, `chunk_key`); it hasn't been applied yet.

## 4.1 sample run

Not run, because the `fred` database couldn't be created (see Open).

## 4.2 real load

Not run: no PostgreSQL database and no FRED API key.

## 4.3 neo4j

Not run. 003 is expected to need the NODE KEY workaround. 004 needs the CSVs that 4.2 produces.

## 5.x built

Nothing built yet.

## Diffs to review

None. The only file added is this status report.

## Open

1. **No permission to create the database (blocks 4.1).**
   ```
   $ createdb fred
   createdb: error: database creation failed: ERROR:  permission denied to create database
   ```
   Role `radar-41-0` has `rolsuper=f, rolcreatedb=f`. `sudo -n true` → `sudo: interactive authentication is required`, so the agent can't grant it. Adrian needs to run:
   ```bash
   sudo -u postgres createuser -s radar-41-0   # or: sudo -u postgres psql -c 'ALTER ROLE "radar-41-0" CREATEDB'
   createdb fred
   ```
   The existing `atlas` database wasn't used, because it belongs to another project.

2. **No FRED API key (blocks 4.2, and 004 in 4.3).** Neither `FRED_API_KEY` nor `MYFREDKey` is set in the environment or in the shell profiles. Fix: `export FRED_API_KEY=...` in the shell that launches the agent. Never commit the key.

When both are fixed, resume at 4.1.
