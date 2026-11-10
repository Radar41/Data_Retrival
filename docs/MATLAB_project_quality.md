# MATLAB project quality: what guards the catalog, and where each guard lives

Set up 4 and 5 Nov 2026 on MATLAB R2026a Update 3 (MATLAB Test, Requirements Toolbox, Database Toolbox installed). Everything below runs headless with `matlab -batch` and inside the open project.

## 1. One command

```bash
matlab -batch "buildtool"
```

`buildfile.m` at the project root defines the plan (MATLAB build tool):

| Task | What it does | Fails when |
|---|---|---|
| `check` | Code Analyzer over `src/`, `tests/`, `buildfile.m` (58 files) | any error or **any warning** (threshold 0) |
| `test` | every test under `tests/` with the MATLAB unit test framework; JUnit results and Cobertura coverage of `src/` in `derived/quality/` | any test fails. Live-database tests filter themselves when PostgreSQL or Neo4j is unreachable |
| `compat` | Code Compatibility Analyzer over `src/`, CSV in `derived/quality/` | any Error-severity recommendation |
| `diagrams` | `docs/design/*` from the checked model (incremental: skipped while inputs are older than outputs) | the model disagrees with either DDL file or the graph model |
| `requirements` | `requirements/fred_catalog.slreqx` and the per-test link sets from `src/build_fred_requirements.m` | a test method named in the generator no longer exists |

Default tasks: `check` then `test`. `derived/` and `.buildtool/` are git-ignored; they are rebuilt on every run.

State on 10 Nov 2026 (after FRED Data List 101: 1,645 series, 11,848,156 observation rows; units_code widened to 80; `refresh_series_range` per statement in PostgreSQL): `check` 0 errors, 0 warnings; `test` 44 passed, 0 failed, 0 incomplete (13 of them the new `SeriesReaderSqlTest` and `LiveSeriesReaderTest`); `compat` 0 recommendations; `diagrams` regenerated from the 16-table model; `requirements` 31 requirements, 33 Verify links.

## 2. Tests (MATLAB Test / unit test framework)

| File | Tag | Checks | Needs |
|---|---|---|---|
| `tests/unit/DesignModelTest.m` | Design | model = PostgreSQL DDL; model = MySQL DDL; graph model covers the relational model; `physical_type` table; every table, label and relationship appears in every diagram view; each `.dot` compiles with Graphviz; the degree-audit file has 17 statements A01..A17 and names only declared relationship types | nothing (Graphviz optional) |
| `tests/unit/NaiveAdapterPayloadTest.m` | – | the naive random-walk fit payload has all six uncertainty fields. Regression for commit ab38d13, which spliced two assignment lines together and lost two fields without any test noticing | nothing |
| `tests/integration/LiveCatalogTest.m` | Live | live PostgreSQL = model; live Neo4j = graph model; degree audit A07–A17 return zero rows; A01–A05 only ever flag data-list series; A06 (every release has a source) is verified like the rest since the loader fetches `release/sources` for every release (7 Nov 2026) | PostgreSQL on 5432, Neo4j HTTP on 21004 (radar-41 port registry, data band), password from `NEO4J_PASSWORD` or the vault secret `neo4j_pw` |
| `tests/test_run_totbkcrnsa_naive_evaluation.m` | – | the GDSS forecasting pipeline (pre-existing) | nothing |

In the project: **Project > Run Tests** or the Test Browser runs the same files; the Classification label `Test` is set on all of them. Coverage with MC/DC needs MATLAB Test's Test Manager; the build tool writes statement coverage to `derived/quality/coverage.xml`.

## 3. Requirements (Requirements Toolbox)

`src/build_fred_requirements.m` generates `requirements/fred_catalog.slreqx`:

| Container | Requirements | Source of the text | Verified by |
|---|---|---|---|
| CARD | A01–A17, one per cardinality rule | the comment block above each statement in `neo4j/cypher/fred_degree_audit.cypher` | the three audit methods in `LiveCatalogTest` |
| MODEL | M01–M07, model agreement with DDL, graph, live stores, diagrams, audit file | the generator | `DesignModelTest`, `LiveCatalogTest` |
| READ | R01–R06, the MATLAB readers return what SQL returns for the same vintage; ids are identifiers | the generator | `LiveSeriesReaderTest`, `SeriesReaderSqlTest` |
| GDSS | G01, fit-payload contract | the generator | `NaiveAdapterPayloadTest` |

31 requirements, 33 **Verify** links. Each link's source is a line range of the test method (`tests/**/<Test>~m.slmx` holds them; commit those files). Open the set in the Requirements Editor (`slreq.open("requirements/fred_catalog.slreqx")`), then **Traceability Matrix** shows requirement × test, and after a test run **Verification Status** colours each rule by its last result. Do not edit the `.slreqx` by hand: change the audit file or the generator and run `buildtool requirements`.

The empty `requierments.slreqx` created in the editor on 4 Nov at the project root is superseded by this set and can be closed without saving and deleted.

## 4. Project metadata (MATLAB project)

Registered on 4 Nov: `src/`, `tests/`, `sql/`, `neo4j/cypher/`, `neo4j/conf/`, `docs/design/`, `docs/erd/`, `docs/graph_explorer/`, the design documents, `README.md`, `buildfile.m`, `run_all.sh`. Classification labels: Design (code, SQL, Cypher, docs), Test, Artifact (PNG/SVG deliverables), Derived (`.dot`, `fred_graph_data.js`), Convenience (build and shell scripts). Startup file `src/project_startup.m`, shutdown file `src/project_shutdown.m`. Autosaves (`*.asv`), bytecode and the Test Manager databases are excluded.

Done 7 Nov 2026, from the terminal and headless MATLAB:

1. **Project path**: `requirements` is on the project path, so the link sets resolve the requirement set by name.
2. **Project checks**: all 11 pass (`runChecks`). Two things were needed: the Neo4j bind-mount folders inside the project root are owned by the container user (uid 7474) and were unreadable, fixed once with `sudo chmod -R o+rX neo4j/import data/catalog/neo4j-import` (recursive: the files inside were the blockers, not only the folders); and 28 git-tracked files were not registered in the project (design docs, the requirement set, link sets, compose file, catalog snapshots), now added with their Classification labels. The Dependency Analyzer runs on the same precondition; its graph export is the untracked `docs/Dependency Graph.graphml`.
3. **Code Quality Dashboard** (MATLAB Test): `codeQualityDashboard` reads the same Code Analyzer and test results per project; it is the MATLAB equivalent of the Simulink dashboard in §5.

## 5. The dashboard that cannot apply

The screenshot of 4 Nov (`Unable to open Model Maintainability Dashboard … project does not contain any supported artifacts`) is the Simulink Check Model Testing / Model Maintainability dashboard. Its units are Simulink and System Composer models labelled *Unit* or *Component*. This project has none and should not fake any; the MATLAB-code equivalents are the build tool (§1), the test framework with coverage (§2), requirements traceability (§3) and the Code Quality Dashboard (§4.3). The Model Testing tab will keep showing zero test cases; that is correct.

## 6. Defects the first pass found

| Where | Defect | Fix |
|---|---|---|
| `src/+gdss/AnalyticalNaiveRandomWalkAdapter.m` | two lines spliced together since commit ab38d13: `parameter_covariance_refefitPayload.parameter_covariance = []` and `…status = "NOT_AVAILABLE";rence = "";`. The payload lost `parameter_covariance` and `parameter_covariance_reference`; the Code Analyzer had flagged the stray `rence` as an unused variable | restored the six assignments; regression test G01 |
| `src/fred_api_request.m` | read `FRED_API_KEY`, then unconditionally overwrote it with the vault secret, contradicting its own comment and `project_startup.m` | environment first, vault only when the variable is empty |
| four `+gdss` adapters | `obj` unused in `fit`/`forecast` | `~` |
| `src/project_shutdown.m` | `datestr` (compatibility recommendation) | `datetime` |
| `derived/*.dmr` | MATLAB Test Manager databases were tracked in git and changed on every MATLAB start | untracked, `derived/` ignored |
| Neo4j | a native `memgraph.service` (systemd) binds 0.0.0.0:7687, so the project container could not bind 127.0.0.1:7687 and restarted in a loop | resolved 5 Nov by the radar-41 port standardisation: the container now publishes HTTP on 127.0.0.1:21004 and Bolt on 127.0.0.1:21003 (data band 21xxx), with `server.bolt.advertised_address` set to match so drivers using `neo4j://` are not routed to Memgraph's 7687. Every client default in `src/`, `tests/` and `docs/graph_explorer/` follows |
| `tests/integration/LiveCatalogTest.m` | first live run (7 Nov): when every series flagged by A01–A05 was a data-list series, `cellfun` over the empty remainder returned a double and `strjoin` errored | force a string array (`UniformOutput=false`, then `string`) |
| `neo4j/cypher/005_fred_documents_load.cypher` | 8 Nov: a dated PDF that left the `--doc-last` window (Employment Situation, 8 May 2026) stayed in the graph as a `Document` with no `kind`, with 217 chunks nobody would reload; 005 was additive and the CSV listed only the current window | the loader re-lists every registered raw file so `documents.csv` is the complete set, and 005 first deletes any `Document` (and its chunks) not in the CSV, so it is a snapshot load like 004 |
