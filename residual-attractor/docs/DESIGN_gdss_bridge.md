# GDSS adapters feed the residual archive

Status: built 2026-11-14 (Adrian: "yes, build it and the additional adapters too"), with two new adapters, ETS and LSBoost. Answers REPORT_2026-11-13 decision 2 (θ-spec) with **both**: the fixed SES/AR/Holt grids stay, and the GDSS families join as configurations estimated at the origin. The 2026-11-12 choice of Python as the upstream is revised: MATLAB's `+gdss` adapters produce the estimated families, Python owns the archive and everything after it.

## What changes and what doesn't

- **The adapters are untouched.** `gdss.create_model_adapter(modelConfig)` → `validate` / `fit` / `forecast`, as they are now. Each forecasts from `fitPayload.training_values`, so the driver estimates at a refit month and filters forward to any later issuance by setting that field to `y(1:i)`, with no adapter change.
- **One standardization for every model.** Estimated configurations go through rattractor's existing path unchanged: σ(c, t) = sd of the configuration's own one-step errors over the trailing 40 months, floored; `resid = e1 / σ(t − 1)` in the grid; σ_g, cadence, fibers and every later stage the same. Two additions:
  - the model's own forecast sd (√ forecast MSE) is stored as `sd_m` in `gdss/cube`, never mixed into σ;
  - σ_h for estimated families = σ × sd_m(i, h) / sd_m(i, 1), so the model gives the shape over h and the empirical σ gives the level. The fixed families keep their ψ weights.
- **Archive rule holds.** Each (adapter, order, estimation policy) is its own configuration k with its own residuals. Nothing selects a "best" order, and nothing averages across configurations.

## Configurations added (default sweep)

| Family | `adapter_id` | Configurations |
|---|---|---|
| ARIMA(p,d,q) | `matlab.arima` | p ∈ {0,1,2}, d ∈ {0,1}, q ∈ {0,1,2}, not (0,0,0), constant estimated: 17 |
| local level | `matlab.ssm.local_level` | 1 |
| local linear trend | `matlab.ssm.local_linear_trend` | 1 |
| damped trend | `matlab.ssm.damped_trend` | 1 |
| naive | `analytical.naive_random_walk` | 1 |
| ETS, additive error | `analytical.ets` (new) | trend ∈ {N, A, Ad} × season ∈ {N, A} (period 12): 6 |
| gradient-boosted trees | `matlab.ml.lsboost` (new) | lags ∈ {6, 12} × target ∈ {level, difference}, 200 trees, rate 0.1: 4 |

That makes 31 estimated configurations alongside the 54 fixed ones, so K = 85. The grids live in `configs/registry/gdss_*.yaml`, so changing the sweep is a YAML edit.

- **Identity** (plan section 3): `method = "gdss.<family>"`, `params = {orders}`, `theta_spec = "estimated:expanding:every12"`. The estimation policy is part of `core_spec_id`.

## Estimation policy (default)

- **Expanding window.** Re-estimate every 12 months; between refits, filter forward with the last parameters. Every forecast at issuance i uses parameters estimated on y(1..r) with r ≤ i, and data through i only.
- **`every1`** (re-estimate monthly) is the same code with a different `theta_spec`. It costs about 12× more, so it goes on Slurm when wanted.
- **A failed refit** keeps the previous parameters, and that issuance's status records why. Statuses come from captured warnings and errors, never constants (the appraisal finding).
- **A configuration that has no successful fit** before the first issuance a series needs is left out of the run, with the reason in the registry. This keeps the grid dense (K × N × P).

## State pair

Every estimated configuration declares the same forecast-derived pair, with no adapter change:
- s1 = ŷ(i, 1), the one-step forecast level;
- s2 = ŷ(i, 2) − ŷ(i, 1), the slope of the forecast path.

What that pair means per family:

| Family | s1, s2 |
|---|---|
| local level | level, 0 |
| local linear trend / damped trend | level + slope, (damped) slope |
| naive | y_i, 0 |
| ARIMA | one-step forecast, first step of the path |

`forecast_is = "s1"`, and state_forward(i, h) = (ŷ(i, h), ŷ(i, h + 1) − ŷ(i, h)), so the driver forecasts H + 1 steps.

## Flow

1. `rattractor build runs/spec0_spring_adan7406.yaml --config configs/gdss.yaml` runs ingest and register, writes `external/<request_id>/request.json` (the estimated configurations, H + 1, policy) and `series.parquet` (exactly what ingest produced). `request_id` = hash(series hash, configurations, policy, H). The build then stops and prints the sbatch command.
2. `sbatch src/gdss_bridge.sbatch external/<request_id>` runs MATLAB `gdss.run_rattractor_request(dir)`, with a `parfor` over (series, configuration) and 8 CPUs on head. It writes `cube/<series>.parquet` with one row per (config_id, issuance i): `fit_through`, `yhat[1..H+1]`, `sd_m[1..H+1]`, `status`, `params_json`. It also writes `fit_status.parquet` and `done.json` (counts, wall time, MATLAB version).
3. The same build command, rerun, finds the finished cube by `request_id`. It registers the estimated families through a `Precomputed` method backed by the cube, then runs every stage on K = 85.

## Checks

- **Python, on read:**
  - the cube's series hash matches ingest;
  - `fit_through ≤ issuance` on every row (leakage);
  - every configuration × series is present;
  - `e1 = y − ŷ(t − 1, 1)` is recomputed;
  - σ_h > 0.
- **MATLAB, once per configuration:** the driver repeats one perturbation run (y after a cut changed) and asserts every forecast issued at or before the cut is unchanged.
- **Known answers:**
  - naive ŷ(i, h) = y_i;
  - local level against SES at the estimated α, up to estimation;
  - ARIMA(0,1,1) against SES at α = 1 + θ_MA.

## Files

- **MATLAB (new):**
  - `src/+gdss/run_rattractor_request.m` (driver);
  - `src/+gdss/rattractor_model_config.m` (request row → `modelConfig` for the factory);
  - `src/gdss_bridge.sbatch`;
  - `src/+gdss/AnalyticalEtsAdapter.m`, `src/+gdss/MatlabLsboostAdapter.m` (the two new adapters, added to `create_model_adapter`);
  - `tests/unit/test_run_rattractor_request.m`, `test_analytical_ets_adapter.m`, `test_matlab_lsboost_adapter.m`.
- **Python:**
  - `methods/precomputed.py`;
  - `registry.py` (estimated families from YAML, `theta_spec`);
  - `stages/fit.py` (leakage check reads `fit_through` for precomputed families);
  - `stages/forecast.py` (σ_h hook);
  - `gdss.py` (request, cube read and checks), `build.py` (the gdss stage), `schemas/gdss_cube.yaml`, `schemas/gdss_fit_status.yaml`;
  - `configs/registry/gdss_*.yaml`;
  - tests on a synthetic cube.
- **Untouched:** the five existing adapter classes and every stage from the grid on.

## Cost (measured 2026-11-14)

- Smoke, 2 of spec 0's 14 series, all 31 configurations, 4 workers: about 930 CPU-seconds, peak 1.9 GB, every fit completed. Most of the time is LSBoost's 500-path bootstrap at every issuance, not fitting.
- End to end, 3 series, all 31 configurations: MATLAB 429 s wall (1,284 CPU-seconds), 2,989 refits, none failed; the build then passed every stage in 12 s with all 85 configurations admissible.
- Spec 0 in full: about 6,500 CPU-seconds, roughly 15 minutes on 8 CPUs (`src/gdss_bridge.sbatch`). One job at a time, under `nice`.
