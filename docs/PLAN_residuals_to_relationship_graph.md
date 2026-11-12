# Plan: from forecast residuals to a growing graph of economic relationships

Status: plan, 2026-11-12 (revised after the Architecture Specification arrived). Nothing in this document is built yet. It ties together these pieces:

| Piece | Where | State |
|---|---|---|
| FRED catalog (all vintages) | PostgreSQL `fred`, mirrored to Neo4j | built: 1,645 series, 11.8M observation rows, 578,786 vintage dates |
| **Residual Attractor Space: Architecture Specification** (Oct 1, entries through Oct 16) | `downloads/Residual Attractor Space Architecture Specification.docx` | spec, 26 open decisions; defines the **upstream**: configurations, forecast steps, the residual fiber, cadence, lag correlation, e3nn export |
| Forecast Failure Cadence page | `downloads/Forecast Failure Cadence.md` | prototype text for the spec's cadence view |
| Residual Grid Walkthrough | `downloads/Residual Grid Walkthrough.{html,md}` | prototype for the **downstream** grid, synthetic data with planted structure |
| Residual diagnostic pipeline (rdiag) + Standing Intent (Oct 6) | `downloads/residual_diagnostic.zip`, PDF | the **downstream**: DuckDB store built (17/18 tests pass); 30 analysis stages are stubs |
| residual-attractor monorepo layout | `downloads/residual-attractor-DIRECTORY.md` | layout only; merges upstream (stages 1–8) and downstream (9–17) in one package |
| GDSS forecasting harness | `src/+gdss/`, `src/run_gdss_*.m` (MATLAB) | runs; restart (Phase 1) |
| Inference layer (Memgraph, Cognee, Mem0) | `docs/INFERENCE_LAYER_design.md` (Nov 4) | design only |
| The first run (spring, ADAN7406) | `~/projects/adan7406-final-presentation/_outputs_final/`; email and glyph reader's guide in `~/Radar_41-purge/The_Game_of_Games/email_sharma_2026-05-06_friday_meeting/` | done: 7 targets × 7 indicators × 7 models, holdout 2018-01 to 2026-03 |

**How the pieces fit.** The spec and rdiag aren't competitors. The spec is the upstream: it fits configurations, forecasts from every origin, and builds the residual fiber X (one standardized residual per configuration). rdiag is the downstream: it receives that field as R[k, i, t] and analyses it across series. rdiag's `RECONCILIATION.md` removed most spec items with the reason "upstream of this database", so they are kept, just at the other end. The spec says so directly: the fiber "is the same object as the residual grid R[f, c, t]". I'm reading the Standing Intent's "Fiber Bundle from Residuals" as the spec's residual-fiber section.

## 0. Scope: machinery that doesn't depend on the choices

The system runs on whatever is in the FRED database, over any set of series, and looks for the same kinds of structure every time. Nothing in the machinery is specific to a series, an indicator, a commodity or a model family. A particular run (the spring panel, or any other) is a **run specification**, a config file, and nothing more.

Rules that make that hold (most are already in the spec or rdiag):

1. **Indices, not names.** Stages see series and configurations as integers. Names are looked up only by a person after a finding (rdiag rule; `meta_names` is read by no stage).
2. **No branching on identity.** No stage branches on a method name (spec, method interface) or on a series id.
3. **Groupings come from data or from declared rules stored as data.** Adjacency comes from coherence (spec decision 26, rdiag). Predictor sets come from set rules with ids. Never a hand-written list inside code.
4. **Invariants don't depend on counts.** Every test and statistic is valid for any number of series and configurations (spec decision 25).
5. **Every tunable number lives in the config.** No defaults in code; a missing key fails (spec and rdiag).
6. **Frequency handling is a rule, not a choice per series.** The aggregation of weekly/daily series to the common frequency is a declared rule.

**Run specification** = series list (or a rule that selects one) + predictor-set rule + configuration registry + cutoff date(s) + config file. The spring panel is run spec 0. Rerunning it is the first end-to-end test, and its results can be checked against the spring outputs.

## 1. The goal

Find lead-lag relationships between upstream and downstream economic indicators (raw materials and producer prices, intermediate production, final goods, consumer prices). Store each as a node-to-node edge, and watch how its lag changes over time. A lag measured on the spring run (data as of March 2026) and the same lag measured now are two observations of one quantity. Lags shortening and series moving into step indicate contraction and condensing in the market.

The system keeps growing. Each series added comes with its economic definition (what it is an input to, what it measures, what it substitutes for). The system then tests the relationships those definitions imply, and records any it finds on its own.

## 2. The loop

```
          ┌──────────────────────────────────────────────────────────────────────────┐
          ▼                                                                          │
PostgreSQL catalog ──▶ UPSTREAM (spec stages 1–8) ──▶ DOWNSTREAM (rdiag) ──▶ relationship graph
 every vintage         configurations × series ×      cross-config tests,      definitional edges (yours)
 as of any date        origins → steps, fibers X,     transforms, cross-series empirical LEADS edges
                       cadence, lag correlation       lagged co-occurrence     (versioned)
                       → R[k, i, t]                                                  │
                                                                                     │
                       predictor sets for the next run are read off the graph ◀──────┘
```

GDSS's role is the upstream box.

## 3. Model identity: the one equation and its concatenation

There are currently three identity schemes:

| Source | A configuration is | θ |
|---|---|---|
| Architecture Spec | c = (M, θ), `config_id` = hash of method + params | fixed per configuration (parameter grid; Fisher coordinate ℓ) |
| rdiag / Standing Intent | `core_spec_id` × `exog_set` | opaque |
| GDSS | `model_id` from series + variant + (p, d, q) | estimated by maximum likelihood at each origin |

They unify as one key:

```
config_id = hash( method M,  θ-spec,  exog_set )
core_spec_id = hash( M, θ-spec )          θ-spec = fixed values (spec)  or  estimation policy (GDSS)
exog_set = set_id → { series ids }        empty for univariate configurations
```

- Every method is a restriction of the general state-space form (section 4 of the earlier note: x₊ = f(x, u, s) + η, y = g(x, u, s) + ε).
- Every method declares its state pair (s₁, s₂) before it can run (spec).
- Observationally equivalent configurations are tested as invariants, not hidden: SES(α) = ARIMA(0,1,1) with MA α − 1, AR(1) is the φ₂ = 0 face of AR(2), SES is the β = 0 face of Holt. GDSS hit the same thing (local level with zero noise = naive; damped φ = 1 = local linear trend).
- Nesting (which decides Diebold-Mariano vs Clark-West downstream) is a subset check on `exog_set` within one `core_spec_id`.
- The parameter grid is a display; it carries no adjacency into any test (rdiag reconciliation, your call).

## 4. Phase 1: build the upstream

Follows the spec's milestones (contracts → methods → fit/forecast → cadence and correlation → views → graph export → real data), with the GDSS lessons and the rdiag hand-off added.

| # | Work | Source |
|---|---|---|
| 1.1 | **Bulk as-of panel extract**: one query pulls every vintage for a run's series; an in-memory panel resolves "value known at cutoff c". Replaces per-fit file reads. | GDSS appraisal (scaling) |
| 1.2 | **Contracts, config loader, seeded fixture** (the spec's six-regime series). | spec milestone 1 |
| 1.3 | **Method interface** `fit`, `forecast`, `state`, `state_forward`, `state_names`, `fisher`; first families SES, AR, Holt (spec), then the GDSS families (naive, local level, local linear trend, damped trend, ARIMA) and ARIMAX/SARIMAX with exog inputs as known at the origin. | spec milestone 2; GDSS |
| 1.4 | **Registry**: `config_id` per section 3; set rules produce `exog_set`s (catalog structure: release tables, categories, tags, graph neighbourhood; later the relationship graph). | spec stage 2; this plan |
| 1.5 | **Fit and forecast**: forward and backward ladders at every eligible origin; `states`, `steps`. Honest status fields (derived from captured warnings, never constant). | spec stages 3–4; GDSS appraisal 1 |
| 1.6 | **Fibers** (stage 4b): X, common and specific axes at issuance, transport. Standardization σ(c, o) over the W_σ one-step residuals ending at issuance, so it's real-time; this is the `standardization_id` rdiag records. | spec; rdiag input contract |
| 1.7 | **Cadence and lag correlation** (stages 5–7). | spec |
| 1.8 | **Fused configuration**, defined once (open decision 10.6). | spec decision 16; rdiag |
| 1.9 | **Storage**: run, registry and step metadata in PostgreSQL (`forecast` schema); step and fiber arrays as Parquet per build, loaded into DuckDB downstream. | GDSS appraisal; rdiag |
| 1.10 | **Export to rdiag**: R[k, i, t], `config_structure`, `provenance` (`data_cutoff`, `release_date`, `vintage_id` come straight from the catalog's vintages). | rdiag `schemas/00_input.yaml` |
| 1.11 | **Tests**: the spec's known answers and seven invariants, leakage test, conformance per method, round-trip export. | spec validation plan |
| 1.12 | **Load missing series**: IMPMANUS and EXPMANUS (in run spec 0, absent from the catalog files). | coverage |

**Blocking before code** (the spec says so itself): decisions 1–3. They decide which σ scales failure at horizon h, what that implies for integrated methods, and how the σ window behaves across regime changes.

**Done when:** one command takes a run specification and writes a valid rdiag input bundle plus the spec's artifacts and manifest, every forecast traceable to its vintage cutoff, and run spec 0 reproduces.

**Scale.** The spec's own size check: steps = |series| × |C| × |O| × 2H. With 1,000 configurations, 180 origins and H = 20, that's 7.2M rows per series; 100 series is 720M rows. That decides the storage: steps and fibers live as Parquet arrays and DuckDB tables, never as graph nodes, and fits run in parallel. Earlier fits are reused because `config_id` is a content hash.

## 5. Phase 2: implement rdiag stages in the order the relationships need

1. `loss`, `pairwise` (Diebold-Mariano with small-sample correction / Clark-West), `mcs`, `fluctuation`: does conditioning on a set improve forecasts, and when?
2. `cwt`, `coherence` (relative phase = who leads), `adjacency`.
3. `tails`, `events`, `coincidence` (events in one series followed by events in another within a lag window).
4. `common_mode`, `factors`, `signatures` (collapse / collusion / consolidation).
5. `fdr`, then `replay`.

**Where cross-series lag comes from.** The spec's lag-correlation fan ρ(c, t, k) is within one series' residuals. Lead-lag *between* series comes from rdiag stage 3 (coherence phase, coincidence) and stage 1 (predictive gain from an exog set). Edges in Phase 3 draw on those.

**Parameter change required.** `coincidence.delta_max` is 2 months; supply-chain pass-through runs longer. Make it a scanned lag grid, and count every scanned lag in the FDR family.

**Two kinds of lead-lag evidence, kept separate on each edge:**
- **Predictive**: series X at lag L improves the forecast of Y.
- **Co-movement**: X's and Y's residuals move together with lag L. This is shock propagation, and it can hold even without predictive gain.

## 6. Phase 3: the relationship graph

### 6.1 Two kinds of edges

| Kind | Author | Example | Rules |
|---|---|---|---|
| **Definitional** | you, from public sources | `(copper)-[:INPUT_TO]->(electrical wire)`, `(PCOPPUSDM)-[:PRICE_OF]->(copper)` | carries a citation; written before any test; never estimated |
| **Empirical** | a pipeline build | `(X)-[:LEADS {lag, kind, build_id, cutoff, estimate, ci, q_value}]->(Y)` | versioned, never overwritten; names its build and vintage cutoff |

Definitional edges are pre-registered hypotheses: declared before testing, they form a small confirmatory family. Edges the pipeline finds itself are exploratory, carry FDR control, and stay candidates until vintage replay confirms them.

### 6.2 Starting vocabulary (you extend it)

- **Nodes:** `Series`, `Entity` (commodity, product, industry), `Stage` (raw material → intermediate → final good → consumer price), `Build`, `Policy` (thresholds as data).
- **Definitional relationships:** `MEASURES`, `PRICE_OF`, `QUANTITY_OF`, `INPUT_TO`, `PRODUCES`, `SUBSTITUTE_FOR`, `PASSES_THROUGH_TO`, `AT_STAGE`.
- **Empirical relationships:** `LEADS`, `COHERES_WITH`, `CO_OCCURS_WITH`, with `SUPPORTED_BY` / `CONTRADICTED_BY` evidence.

### 6.3 Which store

- Neo4j keeps the catalog graph.
- Memgraph holds the live relationship graph (triggers on new builds).
- Mem0 holds distilled per-entity memory.

These follow `INFERENCE_LAYER_design.md`. Steps, fibers and residuals never go into a graph store. The spec's e3nn graphs (one per series and origin) are training files (`graph.pt`), not database content.

## 7. Phase 4: lags over time

Every build is tied to a vintage cutoff. Two time axes: the **cutoff** (what was knowable) and the **sample window** (which months the estimate used).

1. **Lag history per edge.** Versions L(e, c) with confidence intervals, one per build. The spring run is the one point made at the time, with the methods of the time. Because every vintage is stored, any cutoff can be rebuilt, so the history extends in both directions.
2. **Hindsight drift.** For the same cutoff: first-release vs revised data (rdiag `replay.drift`, applied to edges).
3. **Contraction / condensing.** Lags shortening across many edges at once, together with rdiag's consolidation signature. Reported as a measured pattern; the interpretation is yours.
4. **Path consistency.** Along a chain, the direct lags should roughly add up to the end-to-end lag. A chain that fails to close is a signal: the graph form of the holonomy idea.
5. **Queries:**
   - edges whose lag moved beyond its interval between two builds
   - chains whose total lag shrank
   - entities gaining LEADS edges

Macro, micro and game-theoretic readings are annotations you author on top.

## 8. Growth

Append-only and incremental:

1. **Add a series.** It isn't active until it has at least one definitional edge with a citation (your side of the bargain, enforced as a rule).
2. **The loader** fetches it with every vintage.
3. **Set rules** produce new exog sets.
4. **Only new `config_id`s are fit.**
5. **A new rdiag build** runs.
6. **New edge versions** are written to the graph.

A narrow run (one target, one set) is the same machinery with a smaller run specification.

## 9. Order of work

1. Close spec decisions 1–3 (they block the forecast stage).
2. Phase 1.1–1.3: panel extract, contracts and fixture, method interface with SES/AR/Holt; spec known answers pass.
3. Phase 1.4–1.7 and 1.9: registry and set rules, fit/forecast, fibers, cadence and lag correlation, storage.
4. Phase 1.8, 1.10, 1.12: fused, export, missing series. **Run spec 0** (the spring panel) end to end; compare with the spring outputs.
5. Phase 2 steps 1–3: first empirical LEADS edges.
6. Phase 3: definitional vocabulary; Memgraph per the inference doc.
7. Phase 4: lag history, with the spring run registered as the first point.
8. Phase 2 steps 4–5; spec views and e3nn export; further run specifications.

## 10. Open decisions

1. **Spec decisions 1–3** (σ at horizon h; its consequence; σ window across breaks). Building on the spec's proposed defaults, which it offers "so the build can start": one-step σ scales failure, with σ_h stored beside it; both r and r_h recorded, cadence on r until decided; fixed W_σ = 40, with origins whose window spans a break flagged. Still to be confirmed before the first real-data build (spec milestone 7 gate).
2. ~~Language for the upstream.~~ **Decided 2026-11-12: Python.** The package lives at `residual-attractor/` in this repository (layout per `downloads/residual-attractor-DIRECTORY.md`, package `rattractor`). GDSS's evaluation contracts carry over; the MATLAB code is retired as reference.
3. **θ-spec**: fixed grids (spec), estimated per origin (GDSS), or both. Both fit the identity in section 3.
4. **Neo4j alone vs Neo4j + Memgraph** for the relationship graph.
5. **Lag grid** for co-movement tests, and how it enters the FDR family.
6. **Fused definition** (spec decision 16 / rdiag reconciliation issue 5): it decides Diebold-Mariano vs Clark-West against fused.
7. **Common frequency and aggregation rule** (rdiag requires monthly).
8. **Definitional edges from Cognee**: proposals only, accepted by you.

## 11. Still needed

Nothing blocking. The spec names three more prototypes (Residual Correlation Bundle, Configuration Top View, the Forecast Failure Cadence page as HTML); they'd help when building the views, if they exist.
