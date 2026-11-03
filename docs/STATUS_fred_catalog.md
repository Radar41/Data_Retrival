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
