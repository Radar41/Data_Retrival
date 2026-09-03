# Data_Retrival

MATLAB-first economic-data retrieval, provenance, normalization, and cataloging project for FRED and ALFRED data.

The project is designed to build a broad, traceable economic-data catalog before selecting research-specific panels or imposing model assumptions. It supports FRED API catalog discovery and manually downloaded FRED/ALFRED data-list exports.

## Design principles

- Preserve downloaded source files unchanged in immutable raw storage.
- Record source URLs, timestamps, file sizes, and SHA-256 digests.
- Separate raw files, staging outputs, normalized observations, derived panels, and Neo4j catalog exports.
- Preserve FRED-provided transformations instead of recomputing them during intake.
- Keep distinct source frequency/date conventions separate through normalization.
- Store catalog metadata and lineage in Neo4j; keep dense date/value observations outside Neo4j.
- Avoid choosing causal or model-specific variables during broad catalog construction.
- Make data-processing stages auditable, idempotent where practical, and safe to rerun.

## Project layout

```text
src/                         MATLAB functions
cypher/                      Neo4j Cypher import scripts
data/raw/fred/               Immutable registered FRED source files
data/raw/alfred/             Immutable registered ALFRED source files
data/raw/manual/             Other manually obtained source files
data/manifests/incoming/     Intake manifests created during registration
data/manifests/approved/     Approved dataset provenance records
data/staging/normalized/     Controlled extraction and normalization outputs
data/derived/panels/         Research-specific panels
data/derived/features/       Derived feature sets
data/derived/model-inputs/   Model-ready data
data/catalog/fred/           FRED category-catalog artifacts
data/catalog/neo4j/exports/  Neo4j-ready catalog CSV exports
data/catalog/neo4j-import/   Files mounted into Neo4j's import directory
neo4j/                       Local Neo4j Docker configuration and state
```

Raw data, staging output, derived data, Neo4j runtime data, logs, credentials, and local environment files are excluded from Git.

## Ingestion paths

### Path A: FRED API category discovery

Path A catalogs FRED categories using the FRED API.

Key functions:

```matlab
fred_api_request(...)
fred_category_children(categoryID)
fred_category_level_one_build()
fred_category_tree_crawl(...)
```

`fred_category_children(categoryID)` makes one API request for a parent category and receives all of that parent’s direct children. A valid leaf response may decode in MATLAB as an empty `double`; it must be treated as an empty child table, not an API failure.

The category crawler uses a persistent checkpoint under:

```text
data/catalog/fred/crawls/active/checkpoint.mat
```

Do not delete that directory or checkpoint. Future crawl work should use explicit request-batch limits and persistent checkpoints rather than unbounded execution.

### Path B: Downloaded archive intake

Path B processes manually downloaded FRED or ALFRED public data-list archives without making FRED API requests.

Workflow:

```text
manual download
  -> register raw file
  -> immutable raw copy and incoming manifest
  -> archive inventory
  -> controlled extraction into staging
  -> CSV normalization
  -> README metadata extraction
  -> consistency audit
  -> Neo4j catalog CSV export
  -> deliberate Neo4j catalog import
```

Validated Path B artifacts remain local by default. Dense normalized date/value observations are not imported as Neo4j nodes.

## Validated example: FRED "banks weekly"

A manually downloaded FRED public data-list export was processed end to end.

Source data-list URL:

```text
https://fredaccount.stlouisfed.org/public/datalist/10578
```

Source list title:

```text
banks weekly
```

Registered dataset identity:

```text
fred_public_datalist_banks_weekly
```

The archive contains:

```text
README.txt
weekly.csv
weekly,_ending_wednesday.csv
```

The README identifies Board of Governors H.8 commercial-bank assets and liabilities series. The two source members remain semantically distinct:

| Source member | Base series | Data columns | Frequency |
|---|---:|---:|---|
| `weekly.csv` | 13 | 117 | Weekly |
| `weekly,_ending_wednesday.csv` | 28 | 252 | Weekly, Ending Wednesday |

Each base series has nine cataloged variants:

```text
LEVEL
CCA
CCH
CH1
CHG
LOG
PC1
PCA
PCH
```

The normalized outputs contain 1,032,831 rows in total:

| Source member | Normalized rows | Nonmissing values |
|---|---:|---:|
| `weekly.csv` | 327,483 | 134,294 |
| `weekly,_ending_wednesday.csv` | 705,348 | 522,085 |

The metadata audit passed:

```text
41 base-series metadata records
13 Weekly series
28 Weekly, Ending Wednesday series
41 unique series total
369 series variants
```

The Neo4j catalog import contains:

```text
1 Provider
1 Dataset
1 RawArtifact
2 SourceMembers
41 Series
369 SeriesVariants
```

No normalized observation rows are stored in Neo4j.

## Neo4j catalog model

The Neo4j graph is a catalog and provenance layer:

```text
(:Provider)-[:PUBLISHED]->(:Dataset)
(:Dataset)-[:HAS_RAW_ARTIFACT]->(:RawArtifact)
(:Dataset)-[:HAS_SOURCE_MEMBER]->(:SourceMember)
(:Dataset)-[:CONTAINS_SERIES]->(:Series)
(:Series)-[:HAS_TRANSFORMATION]->(:SeriesVariant)
(:SeriesVariant)-[:AVAILABLE_IN]->(:SourceMember)
```

Deterministic keys include:

```text
Provider:       provider_id
Dataset:        dataset_id
RawArtifact:    sha256
SourceMember:   dataset_id + ":" + member_path
Series:         fred:<series_id>
SeriesVariant:  fred:<series_id>:<transformation_code>
```

## Local setup

MATLAB project root:

```matlab
root = currentProject().RootFolder;
addpath(fullfile(root, "src"));
```

The local Neo4j Docker container mounts:

```text
data/catalog/neo4j-import/
```

to Neo4j's configured server import directory:

```text
/var/lib/neo4j/import/
```

Use only compact catalog exports for Neo4j imports. Do not place raw ZIPs or normalized observation files in the Neo4j import directory.

## Data and security policy

Do not commit:

- API keys, passwords, tokens, or `.env` files
- private keys or certificate files
- raw source ZIPs
- normalized/derived observation files
- Neo4j data and logs
- temporary files or MATLAB autosaves

Before every commit:

```bash
git status --short
git diff --cached --name-only
```

Before adding a new downloaded dataset:

1. Keep the original download unchanged.
2. Register it into `data/raw/<provider>/`.
3. Confirm the raw-file SHA-256 and incoming manifest.
4. Inspect archive contents before extraction.
5. Normalize only into checksum-linked staging output.
6. Extract metadata and pass a consistency audit.
7. Export compact Neo4j catalog CSVs.
8. Review before any Neo4j graph import.

## Status

- FRED API wrappers and direct-category child retrieval: working.
- FRED root and level-one category import: completed.
- Broad FRED category crawl: checkpoint retained; future crawl runs should be budget bounded.
- FRED "banks weekly" downloaded-archive pipeline: validated end to end.
- Neo4j catalog import for the validated data list: completed.
