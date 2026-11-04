# Status: FRED catalog on T9   (2026-11-03T23:40Z)

**Result:** sections 3, 4.1, 4.2, 4.3, 4.4 and 5.1 pass on real data. 5.2 (`fred_integrated.py`) and 5.3 (`run_all.sh`) are not built yet. Branch `fred-catalog-adit2200`, not merged.

## Environment

| Component | Version / state |
|---|---|
| psql | client 18.6; server **PostgreSQL 16.15**, cluster `16/main`, port 5432; database `fred` owned by `radar-41-0` |
| python | 3.14.4, venv `~/.venvs/fred`: psycopg 3.3.7, requests 2.34.2, pypdf 6.21.4, sentence-transformers 6.2.0, torch 2.15.0+cu132 (CUDA on the RTX 4000 Ada) |
| docker | 29.1.3 |
| neo4j | **Community 2026.07.1**, container `data_retrival_neo4j` (password in `neo4j/.env`, git-ignored) |
| cypher-shell | 2026.07.1, run inside the container: `docker exec -i -e NEO4J_USERNAME=neo4j -e NEO4J_PASSWORD=… data_retrival_neo4j cypher-shell` |
| graphviz | 14.1.2 |
| erd | `ghcr.io/burntsushi/erd:latest` (Docker); no local `erd`/`stack` |

Setup notes:
- `createdb fred` first failed with `permission denied to create database`. Adrian ran `sudo -u postgres psql -c 'ALTER ROLE "radar-41-0" CREATEDB'`.
- `FRED_API_KEY` is not in the shell environment. It is set in `~/Documents/MATLAB/startup.m` (`setenv`), and the loader was given it from there for this run only. It was never printed or written anywhere else.

## 4.1 sample run: PASS

All four scripts ran with `ON_ERROR_STOP=1` and no errors. The sample file has **21** observation INSERTs; the handoff says 22, which is a miscount.

```
Q07  series_id | n_revisions | revision_band
     PAYEMS    | 3 | revised repeatedly
     GDPC1     | 2 | revised repeatedly
     INDPRO    | 1 | revised once
     UNRATE    | 1 | revised once
     CPIAUCSL  | 0 | never revised
     STALE1    | 0 | never revised
Q10  as of 2026-09-15 | 159150      current | 159090
Q11  STALE1 | Monthly | 2024-06-01 | 885
```
Trigger proof: after `INSERT … ('UNRATE','2026-09-01','2026-11-06',DEFAULT,4.5)`, the 2026-10-02 row ends `2026-11-05`; `value_as_of('UNRATE','2026-09-01','2026-10-15')` = `4.4`; `series.observation_end` for UNRATE = 2026-09-01.

## 4.2 real load: PASS

```
python src/python/fred_load.py --releases 50 10 53 13 \
    --observations UNRATE PAYEMS GDPC1 CPIAUCSL INDPRO --max-series 100
-> loaded 400 series from 4 releases      (22:51:14Z to 23:14:50Z, wall 1416 s, exit 0)
```
- **Why `--max-series 100`:** the four releases hold 3,571 + 4,609 + 12,715 + 2,672 = **23,567** series. At 2 calls per series and FRED's 120 requests/min that is about 6.5 h, and the original loader had no throttle on those calls, so it would have hit HTTP 429. With the cap it is 100 most-popular series per release; the five observation series were all inside the top 100.
- **Row counts:** source 127, release 335, release_date 3,913, series 400, category 112, series_category 416, tag 303, series_tag 5,296, units 27, **observation 63,047**.
- **Observation vintages per series:** INDPRO 39,368 · PAYEMS 13,691 · GDPC1 4,426 · CPIAUCSL 3,363 · UNRATE 2,199.
- **Raw artifacts:** 16 payloads in `payloads/manifest.json` (27 MB).
- **Schema edits:** none. Longest `units_short` is 32 characters, under the VARCHAR(40) limit.
- **Queries:** `sql/fred_queries.sql` gives all 13 queries rows. Row counts Q01–Q13: 214, 7, 1, 335, 100, 102, 5, 18117, 145, 2, 49, 184, 4.
  - Q05: the 2026-11-02 week holds Employment Situation 2026-11-06, so the window needs no change.
  - Q10 (PAYEMS 2026-07): 158913 as of 2026-09-15, 158882 current.
  - Q13: INDPRO 45, PAYEMS 19, GDPC1 9, CPIAUCSL 1 revisions in 2026.
- **CSV location:** the loader's default `NEO4J_IMPORT` (`data/catalog/neo4j-import/`) is owned by the container (uid 7474, mode 2700), so the first run failed with `PermissionError: [Errno 13] Permission denied: '…/data/catalog/neo4j-import/fred_catalog'`. CSVs now go to the git-ignored staging folder and are copied in:
  ```
  NEO4J_IMPORT=$PWD/data/staging/neo4j-import python src/python/fred_load.py ...
  docker cp data/staging/neo4j-import/fred_catalog/. data_retrival_neo4j:/var/lib/neo4j/import/fred_catalog/
  docker exec -u 0 data_retrival_neo4j chown -R 7474:7474 /var/lib/neo4j/import/fred_catalog
  ```

## 4.3 neo4j: PASS

- **Constraints changed:** the two `IS NODE KEY` constraints became uniqueness constraints on `ReleaseDate.rd_key` (`<release_key>:<date>`) and `Chunk.chunk_key` (`<doc_id>:<seq>`). 004 and 005 set those keys along with the component properties.
  - The handoff says Community has no composite uniqueness. That is wrong for 2026.07.1: the existing `category_key_unique` on `(provider_id, category_id)` works. Only NODE KEY is Enterprise-only. The concatenated keys still work and port to Memgraph more easily, so they stay.
- **003:** runs clean. FULLTEXT `chunk_text` and VECTOR `chunk_embedding` (768, cosine) are ONLINE.
- **004** with `snapshot_id = 2026-11-03T23-15-31Z`: **series_loaded = 400 = SQL `count(*) FROM series`**.
- **Q06:** **SQL 102 rows, Cypher 102 rows, and the (series_id, category_id) sets are identical** (diffed); that is 101 distinct series, one of them in two subtree categories.
- **Other Cypher row counts**, each equal to its SQL counterpart: Q01 214, Q02 7, Q03 1, Q04 335, Q05 100, Q09 145, Q11 49, Q12 184. Q06b 1 row. **Q12b 0 rows**: no frequency lookup/tag disagreements in this data, which is a valid answer.
- **Q13**, with `$revised` from SQL Q13 after 005: 20 rows. **Q13c**, with `$qvec` = embedding of "why were payroll figures revised down": top hits are the BLS revision paragraphs, for example `fred:release:50:2026-08-07` seq 8, sim 0.775, "*The change in total nonfarm payroll employment for May was revised down by 66,000…*".

## 4.4 ERD: PASS

`docker run -i ghcr.io/burntsushi/erd:latest -f png < docs/erd/fred.er > docs/erd/fred_erd_erdtool.png`. It shows the same 14 entities and 14 relationships as `fred_erd_entities.png`. `build_erd.py` reran fine; its PNGs differed only at the byte level, so the committed versions were kept.

## 5.x built

**5.1 `fred_load.py --documents`:** built and verified.
```
NEO4J_IMPORT=$PWD/data/staging/neo4j-import python src/python/fred_load.py --documents --releases 50 13 --doc-last 6
-> documents: 12 registered, 1853 chunks embedded with sentence-transformers/all-mpnet-base-v2
```
- **What it does:** takes the latest N `actual` release dates from PostgreSQL, downloads the agency PDF, and registers it unchanged at `data/raw/documents/<release_id>/<date>.pdf` with SHA-256 in `data/raw/documents/manifest.json`. It never overwrites a file and errors if a registered file has changed. It then extracts text with pypdf, makes ~800-char chunks, embeds them at 768 dims (normalized, GPU), and writes `documents.csv` and `chunks.csv`.
- **Options:** `--doc-dir` registers hand-downloaded PDFs; `FRED_DOC_USER_AGENT` overrides the client name (default `fred-catalog-loader/0.1`).
- **Downloaded:** six Employment Situation releases (2026-05-08 … 2026-10-02) from `bls.gov/news.release/archives/empsit_MMDDYYYY.pdf`, and six G.17 releases (2026-05-15 … 2026-10-16) from `federalreserve.gov/releases/g17/YYYYMMDD/g17.pdf`. Both URL patterns are confirmed.
- **005:** loads 12 Document and 1,853 Chunk nodes, all with 768-dim embeddings.

**5.2 `fred_integrated.py` and 5.3 `run_all.sh`:** not built. 5.4 (MATLAB entry point) not started.

## Diffs to review

| Commit | File | Why |
|---|---|---|
| 8e81856 | `src/python/fred_load.py` | Global request throttle (≥ 0.55 s, ~109/min) with backoff on 429/5xx; `--max-series N` |
| 9204123 | `src/python/fred_load.py` | `--documents` mode (5.1) |
| 9204123 | `src/python/requirements.txt` | pypdf, fonttools, sentence-transformers for `--documents` |
| cc70833 | `neo4j/cypher/003_fred_catalog_schema.cypher` | NODE KEY → unique `rd_key` / `chunk_key`; FULLTEXT/VECTOR DDL flagged Neo4j-specific |
| cc70833 | `neo4j/cypher/004_fred_catalog_load.cypher` | ReleaseDate merged on `rd_key` |
| cc70833 | `neo4j/cypher/005_fred_documents_load.cypher` | Chunk merged on `chunk_key`; `db.create.setNodeVectorProperty` flagged |
| cc70833 | `neo4j/cypher/fred_queries.cypher` | `db.index.fulltext/vector.queryNodes` flagged Neo4j-specific (no query logic changed) |
| 120dedd | `neo4j/cypher/004_fred_catalog_load.cypher` | Series MERGE on `catalog_key` (the datalist graph's key, 41 existing nodes) and also sets `series_catalog_key`; otherwise one series would become two nodes |
| 2925156 | `docs/erd/fred_erd_erdtool.png` | 4.4 render |

No changes under `sql/`.

## Open

1. **Q13 only ever shows INDPRO.** The query orders by `n_revisions DESC` and then `LIMIT 20`, and INDPRO (45 revisions) has more than 20 matching chunks, so PAYEMS never appears. This is a query-design choice for Adrian; it is unchanged. Possible fixes: limit per series, or `collect(...)[0..3]` per series.
2. **The loader's default CSV path is not writable** (see 4.2). Either keep the staging + `docker cp` step (5.3's `run_all.sh` should script it), or change the default `NEO4J_IMPORT`. Changing the import folder's permissions was avoided because the Neo4j entrypoint can reset them.
3. **GDP (release 53) has no press-release URL pattern**, so `--documents` skips it with `release 53: no verified press-release URL pattern`.
4. **Constraint-name collision.** `cypher/import_fred_datalist_banks_weekly_catalog.cypher` creates `series_catalog_key_unique IF NOT EXISTS` on `catalog_key`, and that name now belongs to 003's constraint on `series_catalog_key`. Rerunning the datalist script will silently skip that statement. Harmless today, because `fred_series_catalog_key_unique` already covers `catalog_key`, but it is worth renaming one of them.
5. **Known soft spot, as the handoff notes:** `last_updated` drops the UTC offset (`[:19]`).
6. **The FRED API key is in plaintext** in `~/Documents/MATLAB/startup.m`, outside the repo. It works, but the shell never sees it, so run the loader with `export FRED_API_KEY=…` or source it from a single private file.

---

# Round two   (2026-11-04T00:50Z)

Brief: pull b6c5d26, re-run 003 and Q13, build 5.2 and 5.3, fix `fred_pull.m` line 45. All done; one item needs Adrian (the full `run_all.sh` run, below).

## b6c5d26 verified

- **Stale constraint dropped.** b6c5d26 removed `series_catalog_key_unique` from 003, but the round-one run had already created it in the live graph. Ran `DROP CONSTRAINT series_catalog_key_unique IF EXISTS`; the only Series constraint now is `fred_series_catalog_key_unique` on `catalog_key`. 003 reruns clean. Open item 4 above is resolved.
- **Q13 (top 3 per series):** 6 rows, 3 INDPRO + **3 PAYEMS**. PAYEMS' top passage is Employment Situation 2026-08-07, chunk 8, relevance 5.07: "*The change in total nonfarm payroll employment for May was revised down by 66,000…*". GDPC1 and CPIAUCSL return no rows (no GDP/CPI documents loaded), as expected. Open item 1 above is resolved.

## 5.2 `src/python/fred_integrated.py`: built, verified

```
export NEO4J_PASSWORD=...
~/.venvs/fred/bin/python src/python/fred_integrated.py [--passages N]
```
- **Queries:** reads Q13 from both query files (no copies). The SQL runs in a read-only psycopg session; its rows go as `$revised` to a read transaction in a `READ_ACCESS` neo4j session. The script joins on series_id and prints series / release / revisions / top passage.
- **Output** (`--passages 1`): INDPRO 45 → G.17 2026-06-15 chunk 8; PAYEMS 19 → Employment Situation 2026-08-07 chunk 8; GDPC1 9 and CPIAUCSL 1 → "no press-release documents loaded". "4 revised series from PostgreSQL; 6 passages from Neo4j."
- **Missing password:** exits with `NEO4J_PASSWORD is not set; export it and rerun.`
- **New dependency:** `neo4j>=5.20` (installed: 6.4.1).

## 5.3 `run_all.sh`: built, partly verified

```
export FRED_API_KEY=... NEO4J_PASSWORD=...
./run_all.sh                   # sample, load, graph, documents into a NEW database "fred"
./run_all.sh --fresh           # drop and recreate the database first
./run_all.sh graph documents   # selected steps against a loaded database
```
- **Behaviour:** `set -euo pipefail`. Credentials come from the environment only, and only the ones the chosen steps need. The script refuses an existing database unless `--fresh`, because the schema script is not rerunnable and `sql/` was left unchanged. Logs go to `data/staging/run_all/<UTC>/`.
- **Checks it runs:**
  - 4.1: 21 sample rows, Q07 revision counts, both Q10 values, Q11 = STALE1, trigger proof (inside a rolled-back transaction).
  - 4.2: no SQL query returns 0 rows.
  - 4.3: 004 `series_loaded` = SQL count, Q06 Cypher rows = SQL rows.
  - 5.1: 005 `chunks_loaded` = chunks.csv rows.
- **Neo4j setup:** the script creates `Provider {provider_id:"fred"}` and 001's two constraints inline, because 001 needs the MATLAB crawl CSV and 002 hardcodes one snapshot from this machine, so neither can run on a clean machine. It writes CSVs to staging, then `docker cp` + `chown 7474:7474` into the container (resolves open item 2).

| Test | Result |
|---|---|
| no `FRED_API_KEY` / no `NEO4J_PASSWORD` | `FAIL: FRED_API_KEY is not set. Export it in this shell and rerun.` / same for NEO4J_PASSWORD, exit 1 |
| `FRED_DB=fred_runall_test ./run_all.sh sample` | 6/6 checks ok |
| same again, without `--fresh` | `FAIL: database 'fred_runall_test' already exists. …`; real `fred` also protected (still 400 series) |
| `--fresh sample` | drops, rebuilds, checks ok |
| `load` with an invalid key | stops at 4.2, exit 1 |
| `./run_all.sh graph documents` on the loaded `fred` | 400 = 400, Q06 102 = 102, 1853 = 1853 chunks; 37 s, exit 0 |

**Not run: a full `./run_all.sh` including the live load.** The brief says to read `FRED_API_KEY` from the environment only, and this shell does not have it. Adrian, to finish the check: after moving the key to `~/.config/fred/env`, run `FRED_DB=fred_check ./run_all.sh` (about 25 min). That builds everything into a separate database and leaves `fred` alone.

## Also fixed

- **`src/fred_pull.m` line 45** now reads `getenv("FRED_API_KEY")` instead of `MYFREDKey`, matching its help text and `fred_api_request.m`. Not run in MATLAB.
- **API key leak in loader errors.** On any failed request, `requests` printed the full URL including `api_key=`. Errors now say e.g. `FRED sources: HTTP 400: Bad Request.  The value for variable api_key is not registered. …`; the key appeared 0 times in the test output.

## Diffs to review (round two)

| Commit | File | Why |
|---|---|---|
| 1b587b4 | `src/fred_pull.m` | env var name fix (line 45) |
| 39f29df | `src/python/fred_integrated.py` | 5.2 |
| 39f29df | `src/python/requirements.txt` | `neo4j` driver |
| 9af90af | `src/python/fred_load.py` | keep api_key out of error messages |
| b77c265 | `run_all.sh` | 5.3 |

No changes under `sql/` or `neo4j/`. The `.asv` files and the uncommitted GDSS work were left untouched.

## Open (round two)

1. **Full `run_all.sh` run with the live load:** needs `FRED_API_KEY` in the environment (see above).
2. **GDP (53) and CPI (10) have no documents.** CPI's BLS pattern (`cpi_MMDDYYYY.pdf`) is in the loader but was not requested; add `10` to `DOC_RELEASES` to try it. GDP still has no verified URL pattern.
3. **The loader's default `NEO4J_IMPORT`** still points at the container-owned folder. `run_all.sh` overrides it, but running `fred_load.py` by hand without `NEO4J_IMPORT=$PWD/data/staging/neo4j-import` still fails with the round-one PermissionError.
