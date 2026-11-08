# ADIT2200 course elements: where each one lives in the FRED catalog, or why it is absent

Built from the 41 Canvas and lecture screenshots in `Boston College/2026_Fall/DBMS/` (3 and 4 Nov 2026) and checked against the repository on 4 Nov 2026. "Former" is the relational side (ERD, logical design, PostgreSQL, MySQL); "latter" is the Neo4j graph. The rule for the term: every element the course grades must be either present in both, or present in one with the reason for its absence in the other written down.

The one element that genuinely thins out on the way across is **cardinality**. It is the first section for that reason.

## 1. Cardinality (ERD crow's feet, Week 2 rubric "Notation")

| Where | How it is expressed | Enforced by |
|---|---|---|
| ERD (`docs/erd/fred_erd_*.png`, `fred.er`) | Crow's feet, min/max on both ends | Notation only |
| Logical design (`docs/design/fred_logical_design.png`, `docs/fred_logical_design.md` §1) | Crow's feet with verbs; identifying (solid) vs non-identifying (dashed); FK columns | The MAPER rules decide where the key migrates |
| PostgreSQL / MySQL (`docs/design/fred_physical_*.png`, `sql/*/fred_schema.sql`) | `NOT NULL` on the FK column = mandatory one; PK of the join table = many-to-many; `ON DELETE` | The DBMS, on every write |
| Neo4j (`docs/design/fred_neo4j_*.png`) | Not expressible. A relationship type connects any number of nodes either way; Community edition has no existence or cardinality constraints. The legend says so in one line. | Nothing at write time |
| Neo4j, compensating | `neo4j/cypher/fred_degree_audit.cypher`: seventeen queries, one per crow's-foot constraint, each expected to return zero rows | A query run after each load |

So in the graph cardinality is not an afterthought by neglect; it moves from a declaration to a check. That is the Königsberg point from the course map: the connection is the object, and the multiplicity rule becomes a question you ask of the graph.

### 1.1 What the audit found on 4 Nov 2026

Run against the live graph (Neo4j 2026.07.1; 21 labels and 26 relationship patterns since the release table tree arrived on 7 Nov):

| Rule | Result | Meaning |
|---|---|---|
| A01–A05 Series → Release, Frequency, Units, SeasonalAdjustment, Category | 41 rows each, all with `dataset_id` set | The 41 data-list series (`ALLACBW027NBOG` …) came from the FRED data-list archive, not the series API. They carry frequency, units, release and source as text properties and have none of the catalog edges. Documented exception until the catalog crawl reaches them. |
| **A06 Release → Source** | 4 Nov: **331 of 335 releases had no `PUBLISHED_BY`**. 7 Nov: 0 rows | Was not a graph problem. `src/python/fred_load.py` fetched `releases` in bulk but `release/sources` and `release/dates` only for the release ids on the command line (4). PostgreSQL agreed: `release_source` covered 4 of 335. The ERD says a release has at least one source, so the relational copy violated its own ERD too, silently, because `release_source` is a separate table and nothing forces a row to exist. Fixed 7 Nov: the loader calls `release/sources` for every release and the bulk `releases/dates`; after the reload `release_source` has 383 rows over 337 releases, `release_date` 119,991, and the graph the same 383 `PUBLISHED_BY` edges and 119,991 `ReleaseDate` nodes. |
| A07 ReleaseDate ← Release | 0 rows | Weak entity holds |
| A08 Category → parent | 0 rows | Unary 1:M holds, root is the only orphan |
| A09 Tag → TagGroup | 0 rows | |
| A10–A11 Document → Release, Chunk ← Document | 0 rows | Checked over 164 documents (13 dated PDFs + 151 release pages) and 3,375 chunks after the 8 Nov 2026 load |
| A12 SeriesVariant | 0 rows | |
| A13–A14 key-property drift | 0 rows | The FK value kept as a property agrees with the edge |
| A15–A17 ReleaseTableElement → Release, parent, Series (added 7 Nov) | 0 rows | The release table tree from `release/tables`: 19,982 elements over the four loaded releases, each in exactly one release, each non-section under one parent; 521 `SHOWS` edges, one per series row whose series is in the catalog (the other 16,140 series rows name series the catalog has not loaded, which rule A17 allows) |

A06 stays in the write-up as a teaching example even though it is closed: it was the one place where SQL and Cypher failed in the same way for different reasons. SQL cannot express "at least one row in the join table" without a trigger or a deferred constraint; Neo4j cannot express it at all.

## 2. Element by element

| Week / element (from the screenshots) | Relational side | Graph side | Absent on purpose? |
|---|---|---|---|
| **W1** kinds of DBMS; business rules | The numbered rules are cited where the model enforces them (`fred_relational_model.m` FK and join-table rows: rules 1, 2, 5, 7, 8, 11) and now stated as requirements CARD.A01–A17 in `requirements/fred_catalog.slreqx`; discussion post of 6 Sep | Rules 1–11 reappear as the relationship rows in `src/+dbdesign/fred_graph_model.m` | – |
| **W2** ERD: entities, attributes, binary / unary / ternary, associative, weak entities | ERD: 16 entities, 17 relationships; weak: RELEASE_DATE, OBSERVATION, VINTAGE_DATE; associative: RELEASE_SOURCE, SERIES_CATEGORY, SERIES_TAG; unary: CATEGORY, RELEASE_TABLE_ELEMENT | Weak entities keep their own label (ReleaseDate, Chunk) with the owner's key folded into `rd_key` / `chunk_key`; associative entities disappear into relationship types (`PUBLISHED_BY`, `IN_CATEGORY`, `TAGGED`) because none carries attributes | Associative entities absent: nothing to store on them. The day one gains an attribute (e.g. `SERIES_TAG.added_on`) it becomes a relationship property, not a node |
| **W2 rubric** Notation / Entity sets / … | Hoffer crow's foot throughout `docs/design/` | Arrow notation, `:TYPE` labels, as in the Neo4j slides | – |
| **W3** EERD: supertype / subtype, discriminator, disjoint / complete | **Absent.** The catalog has no specialisation: every series has the same attributes whatever its frequency; tags differ by group, not by attributes. Hoffer's test (subtypes have their own attributes or their own relationships) is not met | Would be a second label, `(:Series:Monthly)`; the course map plans this as the HW2 preamble | Yes. Say so in the write-up: a subtype with no attributes of its own is a `WHERE`, not an entity |
| **W4** logical design, MAPER steps 1–4, key migration | `docs/fred_logical_design.md` §1–2; `docs/design/fred_logical_design.png`, `fred_table_map.png` | Each label and edge in `fred_neo4j_logical.png` names the table or FK it came from; the legend is the conversion checklist | Key migration absent: a relationship needs no migrated key. The audit (§1) is what replaces it |
| **W5** FDs, 1NF → 3NF, derived attributes | `docs/fred_logical_design.md` §3–5; `docs/design/fred_fd_maps.png` | FDs still govern properties inside a node. `Series.observation_start/end` stay derived; the data-list text copies (`frequency`, `units_level` …) on `Series` are a deliberate 2NF violation, listed as such in `fred_graph_model.m` | Partly. Normalisation of relationships has no counterpart; normalisation of properties is unchanged |
| **W6** physical design, datatypes per DBMS, indexes, denormalisation | `docs/design/fred_physical_postgresql.png`, `fred_physical_mysql.png`; `src/+dbdesign/physical_type.m` maps declared → stored types; discussion topic "datatypes between DBMSs" is exactly that table | `fred_neo4j_physical.png`: Cypher types, uniqueness constraints, RANGE / FULLTEXT / VECTOR indexes, and every type difference from SQL (`category_id` STRING vs INTEGER, `LIST<FLOAT>`) | – |
| **W6** Database Explorer (MATLAB) | PostgreSQL and MySQL data sources in the Explorer screenshot; `src/project_startup.m` | No native Neo4j source; the HTTP API via `webwrite` (`src/export_fred_graph_explorer_data.m`) | Neo4j absent from the Explorer: no JDBC driver configured. Could be added through the Neo4j JDBC driver if the course needs it there |
| **W7** single-table queries, aggregates, inner join | `sql/fred_queries.sql` Q01–Q03 | `neo4j/cypher/fred_queries.cypher` Q01–Q03 (`WITH … count()` is the implicit `GROUP BY`) | – |
| **W8** outer joins, subqueries, GROUP BY discussion | Q04 (`LEFT JOIN`), Q05 (`IN`), Q12 | Q04 (`OPTIONAL MATCH`), Q05, Q12 | – |
| **W9** set operations, CASE, window functions, vendor differences (`EXCEPT` vs `MINUS`) | Q07 (CASE), Q08 (`LAG … OVER`), Q09 (`EXCEPT`); MySQL notes inline | Q09 only (`WHERE NOT EXISTS` pattern). Q07, Q08 **absent**: they are about observation vintages | Yes. Observations are PostgreSQL-only by design (`fred_graph_model.m` excluded list, `fred_logical_design.md` §7.1). Cypher has no window functions either; `collect()` + list indexing is the workaround, worth one paragraph in the HW7 preamble |
| **W10** stored procedures vs functions; triggers that write a change log | `sql/fred_triggers.sql`: `close_prior_vintage` (BEFORE INSERT), `refresh_series_range` (AFTER INSERT), `value_as_of()` function, `post_release()` procedure; MySQL: `add_vintage()` procedure instead of the self-updating trigger (error 1442) | **Absent.** Community Neo4j has no triggers (APOC `apoc.trigger.*` only) and no stored procedures without a Java plugin | Yes. The vintage-closing trigger is the strongest argument in the project for keeping observations relational |
| Lecture slides: declarative vs procedural, PL/SQL vs T-SQL | PL/pgSQL and MySQL/MariaDB dialects side by side in `sql/` and `sql/mysql/`; `fred_triggers.sql` comments name the differences | Cypher is declarative only | – |
| Neo4j video: labeled property graph, `:RETWEETED` self-relationship, Cypher vs SQL recommendation query | `Category-[:CHILD_OF]->Category` is the project's self-relationship (the one neo4jd3 cannot draw) | Q06 / Q06b (variable-length `CHILD_OF*`) against the recursive CTE in SQL Q06 is the project's version of the slide's "5 lines vs 25" | – |
| neo4jd3 demo page | – | `docs/graph_explorer/` renders the live schema and six data views | – |
| Observations (vintages, realtime columns) | OBSERVATION weak entity, 284,430 rows over 103 series (7 Nov, after the first `--updates` run), Q10 | **Absent** | Yes. Dense, append-only, queried by range: a table. `fred_logical_design.md` §6–7 |

## 3. What still needs doing for the course pass

1. ~~`fred_load.py`: fetch `release/sources` and `release/dates` for every release~~ Done 7 Nov 2026: the loader now calls `release/sources` once per release and the bulk `releases/dates` endpoint, so both stores carry a source and the date calendar for all 335 releases (finding A06 closed).
2. HW2 preamble: add the `(:Series:Monthly)` style second label and the matching PostgreSQL supertype/subtype sketch, then write down why the production model does not use it.
3. HW7 preamble: the `collect()` workaround for window functions in Cypher, next to Q08.
4. Rerun `neo4j/cypher/fred_degree_audit.cypher` after each load and keep the A-rule table in this file current (the MATLAB test suite does this: `matlab -batch "buildtool"`).
5. ~~Press-release text for every release~~ Done 8 Nov 2026: `--documents` fetches the page behind `release_link` for every release FRED flags `press_release` (151 of 180; the misses are hosts that refuse non-browser clients, releases with no link, and pages with no extractable text, all named in the documents log). FRED itself serves no press-release text, so this is the catalog's only prose per release besides `series.notes`.
6. `fred_load.py --updates` refreshes PostgreSQL only (series rows, vintages, vintage dates). The graph's `Series` properties catch up at the next `./run_all.sh load graph`; a graph-side refresh from the same `series/updates` call is the next piece of the self-updating loop, together with the `event` table from `docs/INFERENCE_LAYER_design.md` step 1.
