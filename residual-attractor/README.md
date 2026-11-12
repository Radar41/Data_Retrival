# residual-attractor

The upstream of the residual diagnostic pipeline: configurations, forecast steps and residual fibers over any set of series. Source of truth: *Residual Attractor Space: Architecture Specification* (Oct 1, 2026, entries through Oct 16). Plan: `../docs/PLAN_residuals_to_relationship_graph.md`.

## State (2026-11-12)

Spec milestones 1 and 2 are built and tested:

- **Contracts** (`schemas/`, `contracts.py`): exact columns, exact dtypes, no casting, primary keys; Parquet round trip.
- **Config** (`configs/default.yaml`, `schemas/config.yaml`): every key required, no defaults in code. Spec decisions 1 and 3 use the spec's proposed defaults, to be confirmed before the first real-data build.
- **Fixture**: the seeded six-regime series (constant, trend, sinusoid period 8, AR(1) φ = 0.7, random walk, shift with a variance burst).
- **Methods** behind one interface (`fit`, `forecast`, `state`, `state_forward`, `state_names`, `fisher`): SES, AR(2) (AR(1) is the φ₂ = 0 face), Holt (SES is the β = 0 face).
- **Registry**: `config_id = hash(method, theta_spec, params, exog_set_id)`, `core_spec_id` without the exog set. ℓ is closed form on one-parameter strata (SES, the AR(1) face, Holt's β = 0 face) and flagged `not_defined_multiparameter` elsewhere (spec decision 12).

Next: stages 1–4 (ingest from the FRED catalog as of a cutoff, register, fit, forecast ladders), then fibers (4b).

## Run

```
uv venv .venv && uv pip install --python .venv/bin/python -e ".[dev]"
.venv/bin/python -m pytest
```

## Choices made here that the spec leaves open

- AR's running mean μ_t: `methods.ar.mean_window` (`expanding` or a trailing window length). The spec says "rolling mean" without a window.
- Initial states: SES l₀ = y₀; Holt l₀ = y₀, b₀ = 0 (so β = 0 is exactly SES); AR has no lag before t = 0.
- AR in-sample s₂ is the predicted deviation for t + 1, so the forward s₂ at h = 1 equals it.
