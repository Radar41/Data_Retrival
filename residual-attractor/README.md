# residual-attractor

The upstream of the residual diagnostic pipeline: configurations, forecast steps and residual fibers over any set of series. Source of truth: *Residual Attractor Space: Architecture Specification* (Oct 1, 2026, entries through Oct 16). Plan: `../docs/PLAN_residuals_to_relationship_graph.md`.

## State (2026-11-12)

Built and tested (128 tests):

- **Contracts** (`schemas/`, `contracts.py`): exact columns, exact dtypes, no casting, primary keys; Parquet round trip, zero-row frames included. `list[float32]` columns (one float32 array per row, Arrow `list<float32>`) share one length per artifact.
- **Config** (`configs/default.yaml`, `schemas/config.yaml`): every key required, no defaults in code. Spec decisions 1, 3, 16 and 17 use the spec's proposed defaults, to be confirmed before results are read.
- **Run specs** (`runs/`, `schemas/run_spec.yaml`): which series a build runs on and how they are read. The machinery never depends on the list.
- **Methods** behind one interface (`fit`, `forecast`, `state`, `state_forward`, `state_names`, `fisher`, `psi`): SES, AR(2) (AR(1) is the φ₂ = 0 face), Holt (SES is the β = 0 face), and the fused configuration.
- **Fused configuration** (`configs/registry/fused.yaml`): the equal-weight mean of every admissible configuration's forecasts, with its own `config_id` and `core_spec_id` (rdiag compares members against it with Diebold-Mariano, not Clark-West). s₁ = consensus, s₂ = dispersion of the member forecasts (rdiag's `ensemble_spread`).
- **Stage 1, ingest**: one query against the FRED catalog for the vintage current on `as_of` (realtime_start ≤ as_of ≤ realtime_end), then frequency alignment, declared interpolation of short gaps (flagged in `calendar.imputed`), gap policy, transform, split. Writes `series` and `calendar`.
- **Stage 2, register**: `config_id = hash(method, theta_spec, params, exog_set_id)`, `core_spec_id` without the exog set; ℓ closed form on one-parameter strata, flagged elsewhere (decision 12), not applicable to fused.
- **Stage 3, fit**: `states` for every admissible configuration; acceptance re-checks leakage and SES = ARIMA(0,1,1) on every build.
- **Stage 4, forecast**: `steps/<series>.parquet`, forward and backward ladders at every origin from o_min = test start + max(W_σ, W_ρ, H), with σ, σ_h, r, r_h and the spec coordinates.
- **Stage 4b, fibers**: `fibers/<series>.parquet`, one row per (origin, ladder, h). x is every configuration's standardized residual (fused last; `fiber_index.parquet` maps position k to `config_id`), and x_k = −u_f exactly. u and w are the common and specific axes at issuance; the row also carries norm, rms, common and specific scores, common share, and transport to the next step (rotation in degrees, log magnitude, issuance switch flagged).
- **Build**: `builds/<build_id>/` plus `manifest.json` (inputs, provenance, artifact rows and hashes), written only when every check passed; failing rows go to `reports/<build_id>/<stage>.parquet`. A dirty tree gets a content hash in its code version, so different uncommitted states never share a build_id.

Run spec 0 (`runs/spec0_spring_adan7406.yaml`) builds on all 14 spring series as of 2026-05-03: 55 fiber coordinates, 1,651,100 step rows and 30,020 fiber rows in about 12 s. WPU1197's four missing months (Oct 2016 – Jan 2017) are interpolated and flagged.

Next: cadence (5), lag correlation (6), then the export to rdiag.

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
- σ is the sample sd (`sigma.ddof: 1`) of e₁ over the W_σ steps ending at issuance. Backward rows are scaled by σ at their own issuance (o − H), so X_k = −u_f holds on both ladders.
- σ floor = `sigma.floor_factor` × training-span sd; a flat training span uses its level (or 1) instead, so r is defined.
- σ_h uses each family's ψ weights with the running mean (AR) treated as known; Holt uses ψ_j = α(1 + jβ).
- σ₂(M) is floored like σ.
- `window_spans_break` is `<NA>` because no break detector is chosen yet (`sigma.break_detector: none`, decision 3).
- Ingest drops an aggregated period that has not ended by `as_of`, and `missing: longest_run` keeps the earliest run on a tie.
- The steps column the spec leaves unnamed is `issuance`, the name the fibers table uses.
- u and w are the first two eigenvectors of the correlation matrix of the one-step residuals over the W_σ steps ending at issuance (centered over the window and scaled by σ_k at issuance), as in the walkthrough's rolling common mode (`corrMat`, `rollLam`). The eigenvalues are stored as `lam1`, `lam2`.
- Sign ties are broken by coordinate order, never by rounding: "largest |loading|" is the first coordinate within a relative 1e-9 of the largest, and a loading sum within 1e-12 of zero hands u to that rule.
- An axis whose eigenvalue is ≤ `fibers.eig_tol` × |C| is not determined by its window. u then falls back to uniform, and w to e_j for the first j with |u_j| ≤ 1/√2, made orthogonal to u.
- `share` is NaN where X = 0, like `rot_out` and `dlog_out` where a norm is 0.
- Fused: members stored sorted by `config_id`; s₂ is the sd with ddof 0; ψ is the mean of the members' ψ (exact when every member's h-step error filters one shared innovation sequence); ℓ is `not_applicable`.
- σ uses a two-pass sd per window, so a large mean in the residuals costs no precision.
