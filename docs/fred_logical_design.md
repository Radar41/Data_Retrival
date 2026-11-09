# FRED Metadata Catalog: Logical Design

Adrian Aziza · azizaa@bc.edu · ADIT2200-01 Database Management, Fall 2026
Stage 3 of the term project: relational model, functional dependencies, normalization, and the data representation plan for the non-relational components.

Notation follows the course text: primary key underlined (shown here in **bold**), foreign keys marked FK, derived attributes in [brackets].

---

## 1. ERD to relations (MAPER steps)

| Step | Rule applied | Result |
|---|---|---|
| 1 Regular entities | One relation each; no composite or multivalued attributes remain in the ERD | SOURCE, RELEASE, RELEASE_TABLE_ELEMENT, SERIES, CATEGORY, TAG, TAG_GROUP, FREQUENCY, UNITS, SEASONAL_ADJUSTMENT |
| 2 Weak entities | Owner key migrates in; PK = owner key + partial identifier | RELEASE_DATE (release_id, release_date); OBSERVATION (series_id, observation_date, realtime_start); VINTAGE_DATE (series_id, vintage_date) |
| 3A Binary 1:M | PK of the one side becomes FK on the many side | release_id, frequency_code, units_code, sa_code into SERIES; group_id into TAG; release_id into RELEASE_TABLE_ELEMENT |
| 3B Binary M:N | Resolved through associative entities (step 4) | see step 4 |
| 3C Binary 1:1 | none in the model | |
| 4 Associative, no identifier | New relation; PK = the two migrated keys | RELEASE_SOURCE, SERIES_CATEGORY, SERIES_TAG |
| 5A Unary 1:M | Self-referencing FK | parent_id in CATEGORY; parent_id in RELEASE_TABLE_ELEMENT |
| 6 Ternary | none | |

## 2. Relations

```
FREQUENCY            (frequency_code, frequency_name)
UNITS                (units_code, units_name)
SEASONAL_ADJUSTMENT  (sa_code, sa_name)
SOURCE               (source_id, source_name, source_link)
RELEASE              (release_id, release_name, press_release, release_link)
RELEASE_SOURCE       (release_id FK, source_id FK)
RELEASE_DATE         (release_id FK, release_date, date_status)
RELEASE_TABLE_ELEMENT (element_id, release_id FK, parent_id FK→RELEASE_TABLE_ELEMENT, element_type,
                      element_name, element_level, line_no, series_id)
CATEGORY             (category_id, category_name, parent_id FK→CATEGORY)
TAG_GROUP            (group_id, group_name)
TAG                  (tag_name, group_id FK, tag_notes, popularity)
SERIES               (series_id, title, release_id FK, frequency_code FK, units_code FK, sa_code FK,
                      [observation_start], [observation_end], last_updated, popularity, notes)
SERIES_CATEGORY      (series_id FK, category_id FK)
SERIES_TAG           (series_id FK, tag_name FK)
OBSERVATION          (series_id FK, observation_date, realtime_start, realtime_end, value)
VINTAGE_DATE         (series_id FK, vintage_date)
```
Primary keys: the first attribute of each relation, or the first two/three where the relation is weak or associative (RELEASE_SOURCE, RELEASE_DATE, SERIES_CATEGORY, SERIES_TAG, OBSERVATION, VINTAGE_DATE).

RELEASE_TABLE_ELEMENT.series_id is deliberately not a foreign key: FRED's table tree names every series of a release, and the catalog loads a chosen subset of them. In the graph the same fact is an edge that exists only where the series node does; audit rule A17 checks it.

## 3. Functional dependencies

```
frequency_code                              → frequency_name
units_code                                  → units_name
sa_code                                     → sa_name
source_id                                   → source_name, source_link
release_id                                  → release_name, press_release, release_link
release_id, release_date                    → date_status
element_id                                  → release_id, parent_id, element_type, element_name,
                                              element_level, line_no, series_id
category_id                                 → category_name, parent_id
group_id                                    → group_name
tag_name                                    → group_id, tag_notes, popularity
series_id                                   → title, release_id, frequency_code, units_code, sa_code,
                                              last_updated, popularity, notes,
                                              observation_start, observation_end   (derived, see §5)
series_id, observation_date, realtime_start → realtime_end, value
series_id, vintage_date                     → (all-key)
```
The three associative relations are all-key: no non-key attributes, so no FDs beyond the key itself.

Transitive chains that exist in the data but are **not** stored as dependencies in any one relation:

- `series_id → release_id → {source_id}`: a series reaches its publisher only through RELEASE and RELEASE_SOURCE. Storing source_id on SERIES would be a transitive dependency and would also be wrong, since a release can have more than one source.
- `tag_name → group_id → group_name`: group_name lives only in TAG_GROUP.
- `category_id → parent_id → (parent's) category_name`: the parent's name lives only on the parent's row.

## 4. Normal form analysis

**1NF.** No repeating groups and no composite attributes. The two candidates for repeating groups in FRED's own API output, the list of tags on a series and the list of categories on a series, are already split into SERIES_TAG and SERIES_CATEGORY. Addresses and names are atomic.

**2NF.** Only relations with composite keys can have partial dependencies. Checking each:

- RELEASE_DATE: date_status depends on the pair (a date is scheduled or actual *for that release*), not on release_id or release_date alone. Full dependency.
- OBSERVATION: realtime_end and value depend on all three key attributes. A value is specific to a series, a period, and a vintage. Full dependency.
- RELEASE_SOURCE, SERIES_CATEGORY, SERIES_TAG: all-key, nothing to be partially dependent.

All relations are in 2NF.

**3NF.** A relation is in 3NF if no non-key attribute determines another non-key attribute. Checking the relations that have more than one non-key attribute:

- SOURCE, RELEASE, TAG_GROUP, CATEGORY, the three lookups: each non-key attribute depends only on the key.
- TAG: group_id, tag_notes and popularity are independent of each other. group_name was deliberately **not** placed here; it would be `tag_name → group_id → group_name`, a transitive dependency, and it is held in TAG_GROUP instead.
- SERIES: the four codes (release, frequency, units, SA) do not determine one another or any other SERIES attribute. The names behind those codes are in their own relations.
- OBSERVATION: realtime_end and value are independent.

All relations are in 3NF. Every determinant in every FD above is a candidate key, so the relations are also in BCNF.

## 5. Controlled denormalization (and why)

Two SERIES attributes are derivable and were kept anyway. The physical-design chapter calls this *controlled redundancy*; the decision follows its three tests (query rate, update rate, accessed together).

| Attribute | Derivation | Reason to keep | How consistency is kept |
|---|---|---|---|
| observation_start | MIN(observation_date) over OBSERVATION | Read in nearly every catalog query ("which series cover 1990 to today"); OBSERVATION will hold millions of rows per catalog and a MIN/MAX scan per series is the single most expensive query in the information-needs list | AFTER INSERT trigger on OBSERVATION (fred_triggers.sql) |
| observation_end | MAX(observation_date) over OBSERVATION | Same, and it drives the "overdue series" query (Q11) | Same trigger |

Updates to these columns happen only when a release posts (a few times a month per series); reads happen on every catalog browse. That is exactly the low-update, high-read profile the course gives for denormalizing.

**Rejected denormalizations.** Storing source_id or source_name on SERIES was considered for the same reason (it is read constantly) and rejected because the relationship is M:N through RELEASE_SOURCE, so a single column cannot represent it without losing information.

**A redundancy that is FRED's, not the design's.** FRED's tag system includes tag groups for frequency (`freq`), seasonal adjustment (`seas`) and source (`src`). A series tagged `monthly` also has frequency_code = 'M'. The two can disagree in FRED's own data. The catalog keeps the lookup columns as the authoritative values and keeps the tags for search, and Q09/Q12 can be used to audit disagreements. This answers the instructor's proposal comment ("Do you think there will be redundant data?"): yes, and it is inherited from the source system, documented, and auditable rather than designed in.

## 6. Vintages: the realtime columns

Business rule 11 says a revision never overwrites a value. The relational representation is the ALFRED convention: every value row carries `realtime_start` (first day it was the published value) and `realtime_end` (last day; `9999-12-31` while current). Three consequences:

1. The current value of a period is the row with `realtime_end = '9999-12-31'`.
2. "What did we know on date D" is `D BETWEEN realtime_start AND realtime_end`. Function `value_as_of()` wraps this.
3. The revision count of a period is the number of rows for that (series, observation_date) minus one.

A BEFORE INSERT trigger closes the prior vintage so the application code never has to remember to.

## 7. Data representation plan for the non-relational components

The project description requires one semi-structured and one unstructured source with a plan for each rather than relational normalization.

### 7.1 Semi-structured: FRED API payloads, held in Neo4j

**Structure of the source.** Every FRED endpoint returns one JSON object with pagination fields (`count`, `offset`, `limit`, `order_by`) and a nested array named for the endpoint: `seriess[]`, `releases[]`, `categories[]`, `tags[]`, `release_dates[]`, `observations[]`. Keys inside the arrays vary by endpoint and by record: `notes` is often absent; `link` is sometimes empty; `observations[].value` is the string `"."` for missing; `realtime_start`/`realtime_end` appear on nearly every object. Nested and repeating elements: `tags[]` and `categories[]` for a series, `sources[]` for a release.

**Representation.** Every payload is kept unchanged on disk with a SHA-256 manifest (the raw-artifact rule from the Data_Retrival repo), and the catalog part of it is loaded into the existing Neo4j catalog graph with LOAD CSV (neo4j/003 and 004). Node keys follow that repo's conventions (`fred:<series_id>`, `fred:category:<id>`, a `Provider` node, a `CatalogSnapshot` per load), so this project's graph and the earlier category-crawl and data-list graphs are one graph. Series identity equals the relational primary key, so a Series node and a `series` row join on the same `series_id`. Associative relations become relationship types; the three M:N tables disappear. Observation vintages are deliberately **not** graph nodes: dense values stay in PostgreSQL, the graph holds the catalog and its lineage.

**Why this is better than tables for these questions.** The two questions that are awkward in SQL and one-liners in Cypher are the category hierarchy (recursive CTE vs `[:CHILD_OF*0..]`, Q06) and co-occurrence questions across tags, categories and releases ("which tags appear together on series in this release's subtree"). The raw JSON is also kept, which the relational load discards.

### 7.2 Unstructured: agency press releases, held in Neo4j with a file store

**Objects.** Two kinds of `Document`, told apart by `kind`. `press_release_pdf` is the agency's dated PDF for a release date (BLS Employment Situation, BLS CPI, Federal Reserve G.17; BEA GDP has no stable URL pattern yet), registered unchanged under `data/raw/documents/<release_id>/<release_date>.pdf`. `release_page` is the page behind FRED's own `release_link` for every release FRED flags `press_release = TRUE`, HTML or PDF, registered as `data/raw/documents/<release_id>/page_<date>.<ext>`. A page is a capture, not an archive: it is the page as it stood after the latest actual release date on or before the fetch, and that date is its `release_date`, so a later run after the next release adds a new capture beside the old one. FRED serves no press-release text itself (only the link and the flag), which is why the catalog has to go to the agencies for it. Every raw file carries its SHA-256 on the node and in `data/raw/documents/manifest.json`.

**Metadata retained.** `doc_id`, `release_key` (FK into both stores), `release_date`, `kind`, `file_type`, `source_name` (agency), `path`, `title`, `sha256`, `source` (the final URL fetched, or where a hand-placed file was copied from) and `retrieved_at`. Text is split into `Chunk` nodes (`seq`, `text`, `embedding`) with a full-text index and a vector index.

**Linking.** `(:Document)-[:DESCRIBES]->(:Release)` and `releaseDate` matches a `release_date` row. From a Series, the path is Series → Release ← Document → Chunk.

**Why not a relational table.** The content is prose; its value is in search, not in fields. A `TEXT` column with `LIKE` cannot rank results or find paraphrases. The metadata that *is* structured (release, date, agency) is in the relational store already, so the document layer only has to point at it.

### 7.3 The integrated question

> Which series were revised most this year, and what do the release documents say caused the revisions?

Relational half: Q13 in fred_queries.sql (vintage counts per series and release for 2026). Graph half: Q13 in neo4j/fred_queries.cypher, which takes that SQL result as a parameter and searches the documents attached to those releases (full-text, or vector for paraphrases). The same question cannot be answered from either store alone, and that is the point of keeping observations in one store and documents in the other.

## 8. Metadata listing (relational)

| Table | PK | FKs | Rows (full catalog, approx.) |
|---|---|---|---|
| frequency | frequency_code | | 7 |
| units | units_code | | ~400 |
| seasonal_adjustment | sa_code | | 3 |
| source | source_id | | ~110 |
| release | release_id | | ~330 |
| release_source | release_id, source_id | release, source | ~350 |
| release_date | release_id, release_date | release | ~50,000 |
| release_table_element | element_id | release, release_table_element (parent) | ~2,000 per release with tables |
| category | category_id | category (parent) | ~5,000 |
| tag_group | group_id | | 8 |
| tag | tag_name | tag_group | ~5,000 |
| series | series_id | release, frequency, units, seasonal_adjustment | ~840,000 |
| series_category | series_id, category_id | series, category | ~1,000,000 |
| series_tag | series_id, tag_name | series, tag | ~10,000,000 |
| observation | series_id, observation_date, realtime_start | series | billions for all of FRED; the catalog loads a chosen subset |
| vintage_date | series_id, vintage_date | series | ~500 per series |

Column-level metadata (types, lengths, nullability, defaults, checks) is the DDL itself: fred_schema.sql is commented per column.

**Rows actually loaded (PostgreSQL `fred`, 2026-11-09).** The catalog scope is 4 releases capped at 100 series each, plus every release and category FRED publishes (tags are those carried by the loaded series):
observation 1,368,712 · release_date 119,992 · vintage_date 96,937 · release_table_element 19,982 · series_tag 5,296 · category 5,200 · series_category 416 · series 400 · release_source 383 · release 337 · tag 303 · source 127 · units 27 · tag_group 8 · frequency 6 · seasonal_adjustment 3.
