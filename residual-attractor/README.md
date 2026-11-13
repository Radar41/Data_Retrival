# residual-attractor

The upstream of the residual diagnostic pipeline: configurations, forecast steps and residual fibers over any set of series. Source of truth: *Residual Attractor Space: Architecture Specification* (Oct 1, 2026, entries through Oct 16). Plan: `../docs/PLAN_residuals_to_relationship_graph.md`.

## The archive rule

The build derives every configuration's residuals for every series and archives each one individually. Nothing fuses, pools or takes a weighted average across residuals before the archive is finished: there is no fused configuration and no cross-configuration aggregate. The fiber bundle is a collection of points. Every later transform and analysis acts on each retained residual on its own, in strict order, and the same analyses run on every series. Redundant configurations are kept; the analyses sort them out later.

## State (2026-11-12)

Built and tested (202 tests, plus one expected failure that records a spec known answer its own rules cannot meet):

- **Contracts** (`schemas/`, `contracts.py`): exact columns, exact dtypes, no casting, primary keys; Parquet round trip, zero-row frames included. `list[float32]` columns (one float32 array per row, Arrow `list<float32>`) share one length per artifact.
- **Config** (`configs/default.yaml`, `schemas/config.yaml`): every key required, no defaults in code. Decisions 1 (training-span growth), 3 (plain 40-step window) and 4 (the spec's nine cadence labels) are decided.
- **Run specs** (`runs/`, `schemas/run_spec.yaml`): which series a build runs on and how they are read. The machinery never depends on the list.
- **Methods** behind one interface (`fit`, `forecast`, `state`, `state_forward`, `state_names`, `fisher`, `psi`): SES, AR(2) (AR(1) is the φ₂ = 0 face), Holt (SES is the β = 0 face; those twins stay in the registry).
- **Stage 1, ingest**: one query against the FRED catalog for the vintage current on `as_of` (realtime_start ≤ as_of ≤ realtime_end), then frequency alignment, declared interpolation of short gaps (flagged in `calendar.imputed`), gap policy, transform, split. Writes `series` and `calendar`.
- **Stage 2, register**: `config_id = hash(method, theta_spec, params, exog_set_id)`, `core_spec_id` without the exog set; ℓ closed form on one-parameter strata, flagged elsewhere (decision 12).
- **Stage 3, fit**: `states` for every admissible configuration; acceptance re-checks leakage and SES = ARIMA(0,1,1) on every build.
- **Stage 4, forecast**: `steps/<series>.parquet`, forward and backward ladders at every origin from o_min = test start + max(W_σ, W_ρ, H). Each row carries the raw y, ŷ and e, and scales that belong to its own configuration: σ, σ_h, σ_g and r, r_h, r_g, with the spec coordinates.
- **Stage 4b, fibers**: `fibers/<series>.parquet`, one row per (origin, ladder, h): x, the collection of every configuration's standardized residual at that point (`fiber_index.parquet` maps position k to `config_id`), with x_k = −u_f exactly, plus step and the issuance switch. No axes, norms or scores.
- **Stage 5, cadence**: `cadence/<series>.parquet`, one row per (configuration, eligible origin): the first crossings h₁–h₄ of the four thresholds on r_g, their gaps, and the first of the spec's nine labels that applies, in the order `cadence.labels` gives. Each row reads one ladder; pooled failure rates are views, not artifacts.
- **Stage 6, lag correlation**: `lagcorr/<series>.parquet`, one row per (configuration, base position t, lag k = −6..6): ρ of the configuration's own one-step residuals, past over (t − 24, t] and forward over [t, t + 24), with n_pairs; θ = arccos of a trailing 3-point mean of ρ along the base.
- **Stage 7, bundle summary**: `bundle_summary/<series>.parquet`, one row per configuration: sign flips of ρ at lags −1 and +1, total rotation in half twists, and closure at lag +1 (n/a on the default open base). The spec's alignment A(t) averages across configurations, so it is not built.
- **Stage 9, grid (the export to rdiag)**: `grid/*.parquet`, rdiag's input tables under its reworked contract v2, with no fused configuration. resid[k, i, t] = e₁(t) / σ(t − 1), each configuration's own one-step residual over its own σ at the month the forecast was made, over the months every series covers from its test split on. Provenance per value: the vintage read, data through t − 1, the value's first-release date, and the build id. The manifest reports whether rdiag's minimums (K ≥ 2, N ≥ 3, P ≥ 60) are met.
- **Build**: `builds/<build_id>/` plus `manifest.json` (inputs, provenance, artifact rows and hashes), written only when every check passed; failing rows go to `reports/<build_id>/<stage>.parquet`. A dirty tree gets a content hash in its code version, so different uncommitted states never share a build_id.

Run spec 0 (`runs/spec0_spring_adan7406.yaml`) builds on all 14 spring series as of 2026-05-03: 54 configurations, 1,621,080 step rows, 30,020 fiber rows, 29,376 cadence rows, 578,448 lagcorr rows and 756 bundle rows, and exports a grid of 54 configurations × 14 series × 98 months (2018-01 to 2026-02). WPU1197's four missing months (Oct 2016 – Jan 2017) are interpolated and flagged.

Next: rework rdiag for contract v2 (the plan, section 5), then the graph (8).

## Run

```
uv venv .venv && uv pip install --python .venv/bin/python -e ".[dev,catalog]"
.venv/bin/python -m pytest
.venv/bin/rattractor build fixture_six_regime.yaml
.venv/bin/rattractor build spec0_spring_adan7406.yaml
```

## Choices made here that the spec leaves open

- AR's running mean μ_t: `methods.ar.mean_window` (`expanding` or a trailing window length). The spec says "rolling mean" without a window.
- Initial states: SES l₀ = y₀; Holt l₀ = y₀, b₀ = 0 (so β = 0 is exactly SES); AR has no lag before t = 0.
- AR in-sample s₂ is the predicted deviation for t + 1, so the forward s₂ at h = 1 equals it.
- σ is the sample sd (`sigma.ddof: 1`) of the configuration's e₁ over the W_σ steps ending at issuance, two-pass per window. Backward rows are scaled by σ at their own issuance (o − H), so X_k = −u_f holds on both ladders.
- σ floor = `sigma.floor_factor` × training-span sd of the series; a flat training span uses its level (or 1) instead, so r is defined.
- σ_h uses each family's ψ weights with the running mean (AR) treated as known; Holt uses ψ_j = α(1 + jβ).
- σ_g = σ × g_c(h), where g_c(h) is the sd of the configuration's own h-step errors over training issuances W..ts−1−H divided by the sd of its one-step errors there. Every target falls before the test split; the build needs at least W such issuances. Flat one-step training errors give g = 1.
- v_s divides s₂ by the configuration's own training-span RMS of s₂ (the spec pools it by method, which would combine configurations).
- `window_spans_break` is `<NA>`: regime handling belongs to the analyses on the archive (`sigma.break_detector: none`).
- Ingest drops an aggregated period that has not ended by `as_of`, and `missing: longest_run` keeps the earliest run on a tie.
- The steps column the spec leaves unnamed is `issuance`, the name the fibers table uses.
- Cadence's fall-back drop is the rule text's 0.5 (`cadence.oscillation_drop`); the spec's config table proposes 1.0 but says 0.5 is the value the build uses. The fail level ("h₂") and the oscillation levels ("k ∈ {2, 3, 4}") are config keys that must name thresholds, and the label list must name all nine rules once with Mixed last.
- Gap-reading rules (Steady, Accelerating, Decelerating) need two gaps and Jump one, whatever their position in `cadence.labels`.

- Lag correlation: a pair is kept only when both indices lie in 1..N−1 and both values are finite; Pearson with each member centred on its own mean; ρ and θ are null where n_pairs < `lagcorr.min_pairs` or a member's sd is at or below the σ floor (a flat window); ρ = 1 and θ = 0 are assigned at k = 0.
- `lagcorr.smoothing: trailing3` is the spec's 3-point mean of ρ, taken along the base (never across lags) over t and the two base positions before it, so every past-lag field uses data at or before t; `centred3` is the alternative. Null ρ stays null; the ρ column keeps the raw estimate.
- Flips and closure read raw ρ with nulls and exact zeros removed, so closure is Möbius exactly when the lag +1 flips are odd; closure compares the first and last defined entries. Total rotation accumulates |Δθ| over all twelve nonzero lags, in half twists, and is null if any lag has fewer than two θ.

- The grid's release date is the earliest vintage at or before `as_of` holding the value (`calendar.first_release`); where ALFRED's vintage history has a gap it is the first vintage ALFRED holds, and for a month averaged from weekly values it is the latest first release among its weeks. The vintage id is `fred:<as_of>`; a build reads one vintage.

## Where the spec disagrees with itself

- The cadence table lists six labels; the rule list has nine. The schema carries all nine (decision 4).
- The known answer "linear trend plus noise, SES: cadence Steady in most origins" does not follow from the rule list: Steady is 0.3–9.4% of SES ladders on r_g for slopes 0.25–1, and 4.3% on r. It stays in the suite as an expected failure. "Holt with the true slope: Holds in most origins" holds on r_g (68%).
- The known answer "matched AR(1): past-lag ρ within ±2/√W_ρ for all k ≠ 0" cannot hold on every row of a 2σ band. It is tested in share form: at N = 2000 with seed 41, at least 85% at each past lag and 90% overall, and a φ = 0.3 mismatch must fail.

