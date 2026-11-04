# GDSS Model Family Catalog

## Purpose

This catalog defines the model-family basis for the GDSS forecasting and
residual-analysis program.

The objective is not to implement every known forecasting method. The objective
is to construct a deliberately diverse, reproducible set of forecast generators
whose rolling-origin residual fields can be analyzed for:

- forecast performance by origin and horizon
- shared and model-specific failure modes
- residual sign persistence and autocorrelation
- horizon-dependent disagreement
- regime-conditioned forecast errors
- tail events and stress episodes
- residual geometry, recurrence, and attractor-like structure
- economically meaningful contraction of the viable model space

The common execution contract is:

```text
ImmutableDataVersion
  -> TargetSeries
    -> ModelConfig
      -> FitRealization
        -> ForecastRealization
          -> ForecastLeaf
        -> ForecastScorecard
```

A `ForecastLeaf` is the atomic observation:

```text
(model configuration, data version, origin, horizon, target)
  -> point forecast, actual value, signed error, uncertainty status
```

The signed forecast error convention is:

```text
forecast_error = actual_value - point_forecast
```

Positive error means underforecasting. Negative error means overforecasting.

## Catalog rules

1. One adapter implements a reusable backend/model family, not one numerical
   hyperparameter setting.

2. One immutable `ModelConfig` represents one concrete candidate
   specification within a family.

3. A sweep declaration expands ranges and admissibility rules into many
   concrete configurations.

4. A fit is origin-specific. No fit may use target observations after its
   origin.

5. Forecast leaves, not only aggregate scores, are retained as primary
   empirical objects.

6. Model selection, model comparison, and final assessment are separate
   operations. A future evaluation segment must not be reused casually for
   both tuning and final performance claims.

7. A model family is added only when it introduces a distinct predictive
   mechanism, uncertainty representation, or residual hypothesis.

8. Physical storage may be normalized and partitioned later, but logical
   provenance and recoverability must remain intact.

## Current architecture

### Implemented adapter families

| Family ID | Adapter ID | Current configuration dimensions | Predictive hypothesis | Output status |
|---|---|---|---|---|
| `naive_random_walk` | `analytical.naive_random_walk` | Drift policy later; training-window policy; transform | Future level equals most recently observed level | Point forecast; uncertainty explicitly unavailable |
| `structural_local_level` | `matlab.ssm.local_level` | Initialization policy; variance constraints; transform; training-window policy | Observed level is a noisy measurement of a latent random-walk level | Normal point/variance/interval output from MATLAB SSM |
| `structural_local_linear_trend` | `matlab.ssm.local_linear_trend` | Initialization policy; level/slope variance constraints; transform; training-window policy | Latent level and stochastic slope jointly evolve through time | Normal point/variance/interval output from MATLAB SSM |
| `structural_damped_trend` | `matlab.ssm.damped_trend` | Damping constraint/fixed-versus-estimated policy; initialization; variance constraints | Latent slope persists but can decay toward a long-run level path | Normal point/variance/interval output from MATLAB SSM |
| `nonseasonal_arima` | `matlab.arima` | \(p,d,q\); lag pattern later; constant policy; training-window policy | Differenced series follows autoregressive and moving-average dynamics | Normal point/variance/interval output from MATLAB ARIMA |

### Current validated artifacts

| Artifact | Status | Role |
|---|---|---|
| `gdss.DynamicModelAdapter` | Validated | Minimal backend-neutral adapter contract: `validate`, `fit`, `forecast` |
| `gdss.create_model_adapter` | Validated | Adapter routing by immutable `adapter_id` |
| `run_gdss_evaluation` | Validated | One origin-specific model evaluation |
| `gdss.expand_model_config_sweep` | Validated for nonseasonal ARIMA | Declarative constrained ARIMA grid expansion |
| `run_gdss_config_sweep` | Validated | Serial execution across materialized model configurations |
| `gdss.create_origin_grid` | Validated | Declarative ordered origin-index grid |
| `run_gdss_rolling_config_sweep` | Validated by smoke matrix | Serial execution across configuration × origin combinations |
| `gdss.summarize_config_sweep` | Validated | Compact configuration-level summary of a single-origin sweep |
| `gdss.summarize_rolling_config_sweep` | Implemented | Configuration × origin summary of a rolling sweep |
| `gdss.load_normalized_target` | Validated | Shared target loader against the canonical normalized-observation contract |
| `gdss.create_target_reference` | Implemented | Data-free validated reference to one normalized target series |
| `gdss.run_arima_rolling_residual_sweep` | Validated | Fixed-horizon rolling ARIMA grid; writes per-leaf residual and per-model scorecard CSVs |
| `run_gdss_evaluation` horizon policy | Validated | `forecast_horizon_policy` = `to_data_end` (with `maximum_forecast_horizon` = NaN) or `fixed` (positive integer) — now required in every config |

### Current validated experiments

| Experiment | Result |
|---|---|
| Naive random-walk single-origin evaluation | Complete |
| Local-level SSM single-origin evaluation | Complete; fit covariance/standard errors honestly marked unreliable when applicable |
| Local-linear-trend SSM single-origin evaluation | Complete; fit covariance/standard errors honestly marked unreliable when applicable |
| Damped-trend SSM single-origin evaluation | Complete |
| ARIMA(1,1,0) single-origin evaluation | Complete |
| Constrained ARIMA grid expansion | 43 admissible candidates |
| Six-model ARIMA smoke configuration sweep | 6/6 complete |
| Three-origin × six-model rolling smoke experiment | 18/18 complete |

## Residual-basis families

The following families form the intended initial basis. Each family is included
because it supplies a different inductive bias and can create meaningfully
different residual fields.

| Family ID | Hypothesis role | Configuration dimensions | Data requirements | Forecast representation | Residual contribution | Status | Priority |
|---|---|---|---|---|---|---|---|
| `naive_random_walk` | Persistence baseline | Drift/no-drift; optional seasonal period | Univariate target | Point; no estimated uncertainty in current implementation | Baseline for detecting whether any model beats persistence | Implemented | Current |
| `structural_ssm` | Latent level, slope, season, cycle, and observation-noise dynamics | Component inclusion; damping; variance constraints; initialization | Univariate initially; covariates later | Gaussian state predictive distribution | Separates state evolution from measurement disturbance | Implemented partially | Current |
| `nonseasonal_arima` | Linear integrated lag dynamics | \(p,d,q\); constant policy; lag restrictions | Univariate target | Gaussian forecast mean/variance | Tests integration and finite-memory serial dependence | Implemented | Current |
| `seasonal_arima` | Seasonal lag and seasonal integration dynamics | \(p,d,q,P,D,Q,s\); constant policy; seasonal-period policy | Regularly sampled series | Gaussian forecast mean/variance | Tests periodic structure omitted by nonseasonal models | Planned | Near |
| `ets_smoothing` | Exponential level/trend/seasonal updating | Error/trend/season type; damping; seasonal period | Regularly sampled series | Point and backend-supported uncertainty | Contrasts recursive smoothing with ARIMA and latent-state fits | Planned | Near |
| `theta_decomposition` | Trend plus transformed-curvature decomposition | Theta variant; seasonal adjustment policy; drift policy | Univariate target | Point; uncertainty method must be explicit | Provides low-complexity trend extrapolation distinct from ARIMA | Planned | Near |
| `dynamic_regression` | Interpretable lagged economic predictor channels | Predictor set; lag set; distributed-lag restriction; regularization | Aligned covariate panel with origin-safe availability | Point; analytic/bootstrap/conformal uncertainty declared explicitly | Tests whether residual structure is explained by observable macro/credit covariates | Planned | Near |
| `arimax_sarimax` | Exogenous regression plus serially correlated disturbances | Predictor set; lags; \(p,d,q\); seasonal orders later | Origin-safe covariates | Gaussian forecast mean/variance when backend supports it | Distinguishes predictor value from residual autocorrelation control | Planned | Near |
| `regularized_lag_regression` | Sparse linear dependence among target and covariate lags | Feature recipe; lag windows; ridge/LASSO/elastic-net penalties | Feature matrix built only through origin | Point; bootstrap/conformal uncertainty later | Tests high-dimensional linear predictive structure | Planned | Near |
| `var_varx` | Joint autoregressive dynamics among selected economic variables | Variable set; lag order; deterministic terms; exogenous variables | Synchronized multivariate panel | Multivariate point/covariance forecast | Tests directed cross-series dynamics unavailable to univariate models | Planned | Medium |
| `vecm` | Cointegration and equilibrium-correction dynamics | Variable set; rank; lag order; deterministic terms | Integrated multivariate panel with cointegration evidence | Multivariate point/covariance forecast | Separates short-run residual dynamics from long-run equilibrium restoration | Planned | Medium |
| `dynamic_factor_model` | Shared latent macro/credit factors | Panel membership; factor count; lag order; measurement specification | Broad aligned panel | Point and latent-factor uncertainty where supported | Tests whether common latent conditions explain otherwise persistent residuals | Planned | Medium |
| `regime_switching` | Different predictive laws in latent or observed regimes | Regime count; transition assumptions; base dynamics; initialization | Univariate initially; covariates later | Regime-weighted point/distribution forecast | Tests whether residual bursts reflect state changes rather than parameter noise | Planned | Medium |
| `change_point` | Structural breaks and piecewise parameter changes | Break detection policy; window lengths; model per segment | Univariate or multivariate | Point; uncertainty method explicit | Identifies periods where global-model residuals become systematically nonstationary | Planned | Medium |
| `threshold_dynamics` | Nonlinear response above/below endogenous thresholds | Threshold variable; delay; regime lag orders; smoothness | Univariate target or covariates | Point; bootstrap/conformal uncertainty later | Tests nonlinear asymmetry in economic expansions, contractions, and stress | Planned | Medium |
| `garch_residual_variance` | Conditional scale/volatility dynamics of innovations | Mean model; variance order; innovation distribution | Returns, growth rates, or residual series more than raw credit levels | Conditional variance/density | Adds heteroskedastic residual structure; not a substitute for mean forecasting | Deferred by target suitability | Medium |
| `quantile_distributional` | Conditional quantiles/tails rather than only means | Quantile grid; loss; features; calibration method | Target plus origin-safe features | Quantiles/intervals/distributions | Allows tail-oriented residual and coverage analysis | Planned | Medium |
| `gaussian_process` | Kernel-defined nonlinear dependence and posterior uncertainty | Kernel; lag features; inducing-point policy; noise model | Manageable feature/sample scale or sparse approximation | Posterior mean/variance | Tests smooth nonlinear temporal geometry with principled uncertainty | Planned | Medium |
| `tree_boosting` | Nonlinear interactions and threshold effects in lag/covariate features | Feature recipe; depth; learning rate; tree count; regularization; seed | Origin-safe tabular features | Point; quantile/conformal uncertainty later | Tests interaction structure not captured by linear dynamic regression | Planned | Medium |
| `random_forest` | Bagged nonlinear partitions | Feature recipe; trees; leaf size; feature subsampling; seed | Origin-safe tabular features | Point; quantile forest later | Robust nonlinear comparator with different bias/variance profile than boosting | Planned | Medium |
| `svr_kernel` | Margin-based nonlinear regression | Kernel; \(C\); epsilon; gamma; feature scaling | Origin-safe tabular features | Point; calibrated uncertainty later | Tests kernel response geometry with controlled capacity | Planned | Deferred |
| `neural_sequence` | Learned nonlinear temporal state from sequences | Context length; architecture; hidden width; depth; optimizer; seed; regularization | Enough rolling windows; GPU when appropriate | Point, quantile, or distribution depending on head/loss | Tests learned representations beyond manual lag features | Planned | Later |
| `tcn_nbeats` | Long-context convolutional or basis-expansion sequence dynamics | Context length; dilation/blocks; widths; basis count; seed | Sufficient rolling windows; GPU optional | Point/quantile depending on implementation | Strong structured deep baselines before very large transformers | Planned | Later |
| `transformer_forecasting` | Attention-based multivariate and long-context sequence modeling | Context, patching, width, layers, attention, covariates, seed | Large aligned datasets; GPU | Point/quantile/distribution depending on head | Tests attention-based dependency structure and covariate fusion | Planned | Later |
| `foundation_forecasting` | Pretrained time-series representation or zero/few-shot forecast | Foundation model version; context policy; adaptation policy | Compatible numeric time series; careful version provenance | Model-specific point/quantile/distribution | Comparator for pretrained general-purpose temporal structure | Planned | Later |
| `ensemble_meta` | Combination of complementary forecasts | Candidate set; weights; training-only fitting rule; constraints | Base forecast archive | Point/interval/density based on combiner | Tests whether residual diversity can be converted into improved forecasts | Planned | Late |
| `residual_meta_model` | Predictability of model error, disagreement, or regime-specific failure | Residual features; base-model set; horizon treatment; calibration | Historical forecast-leaf archive only | Point/quantile/probability depending on task | Directly supports residual-attractor and meta-forecasting objectives | Planned | Late |

## Family-selection principle

A family should enter the active evaluation basis when it adds at least one of:

- a new temporal mechanism
- a new economic-information channel
- a new nonlinearity mechanism
- a new regime or structural-break mechanism
- a new uncertainty representation
- a new long-memory or seasonal mechanism
- a new residual geometry likely to be nonredundant

A family should not enter only because it has a different package name, optimizer,
or superficial variation of an existing specification.

Examples:

```text
Add:
  ETS after ARIMA because smoothing-state dynamics differ from lag-polynomial dynamics.

Add:
  dynamic regression after univariate models because it introduces observable
  economic covariate channels.

Do not immediately add:
  many near-identical ARIMA orders beyond the declared constrained sweep,
  unless rolling-origin evidence indicates meaningful residual diversity.

Defer:
  a large Transformer grid until the feature/origin/interval discipline is
  proven for smaller nonlinear models.
```

## Configuration and sweep policy

### Adapter versus configuration

```text
Adapter:
  reusable implementation of a family/backend contract.

ModelConfig:
  one fully specified, immutable candidate.

Sweep specification:
  declarative set or constrained Cartesian product of candidates.

Evaluation plan:
  candidate configurations × origins × horizons × immutable data version.
```

### Required configuration identity

Every materialized configuration must have a deterministic identity including at
least:

```text
model_id
model_family
structure_id
adapter_id
schema_version
target transform
training-window policy
forecast strategy
parameter/hyperparameter declaration
```

The data version and origin do not belong to reusable `ModelConfig`; they belong
to realization/evaluation identity.

### Sweep constraints

Every family sweep must declare admissibility constraints. Examples:

```text
ARIMA:
  p, d, q ranges
  p + d + q cap
  constant/drift policy
  exclusion of duplicate lag specifications

Dynamic regression:
  candidate predictor groups
  maximum total lag count
  availability lag rules
  regularization grid
  no contemporaneous features unavailable at origin

Tree boosting:
  maximum feature count
  depth/trees/learning-rate bounds
  seed policy
  early-stopping split that respects time order

Neural models:
  context range
  capacity bounds
  seed set
  epoch/early-stopping policy
  GPU/memory resource request
```

## Evaluation policy

### Origin discipline

All models use the same leakage-safe rule:

```text
Training data for origin o:
  observations available at or before o only.

Forecast target at horizon h:
  target_index = origin_index + h.
```

### Metric discipline

Forecast scorecards are derived from leaves:

```text
forecast_error = actual_value - point_forecast
absolute_error = abs(forecast_error)
squared_error = forecast_error^2
```

At minimum, retain:

```text
mean_error
mean_absolute_error
root_mean_squared_error
underforecast_count
overforecast_count
exact_forecast_count
```

Later model-family-appropriate metrics include:

```text
MASE
RMSSE
quantile/pinball loss
CRPS
log score
interval coverage
interval width
Winkler score
Diebold-Mariano comparisons
Giacomini-White comparisons
Model Confidence Set procedures
```

### Selection discipline

Do not use one realized future segment both to tune a candidate grid and to claim
unbiased final performance.

Use one of:

```text
Training-only selection:
  AIC, BIC, likelihood, or other fit criterion within each origin.

Nested rolling selection:
  inner historical origins choose configurations;
  outer origins evaluate the selected procedure.

Fixed predeclared configurations:
  compare a declared basis without post-hoc tuning claims.
```

## Residual archive policy

The residual archive is a primary research product, not a byproduct.

### Required leaf facts

```text
immutable_data_version_id or fingerprint
model_config_id
fit_realization_id
forecast_realization_id
origin_index
origin_time
target_index
target_time
horizon
point_forecast
actual_value
forecast_error
absolute_error
squared_error
forecast distribution status
prediction interval status
created_at_utc
```

### Fit-level facts

```text
fit realization identity
model config reference
training range/count
log likelihood and information criteria where available
convergence status and backend diagnostics
parameter covariance/standard-error status
parameter estimates
backend model artifact reference
runtime
```

### Storage progression

```text
Smoke/debug runs:
  nested MATLAB structures are acceptable.

Medium experiments:
  compact scorecard tables plus partitioned leaf tables.

Large experiments:
  immutable manifests/dimensions plus partitioned columnar leaf facts,
  fit-parameter tables, interval tables, and compact diagnostics artifacts.

Do not:
  serialize full training vectors, full fitted backend objects, or complete
  config structs redundantly inside each leaf.
```

## Active research sequence

### Phase A — Existing basis validation

- Complete rolling-origin summary extraction for the current ARIMA smoke matrix.
- Persist compact scorecards and leaf facts in a storage-aware form.
- Run the full constrained ARIMA grid only after incremental persistence exists.
- Compare fixed-order ARIMA candidates across origins and horizon buckets.
- Identify a small retained ARIMA subset using a declared selection rule.

### Phase B — Compact cross-family classical basis

Add only enough families to create mechanistic diversity:

```text
1. Seasonal state-space or SARIMA capability.
2. ETS / Holt-Winters or Theta capability.
3. Dynamic regression / ARIMAX capability using explicitly origin-safe FRED covariates.
4. A multivariate macro architecture: VAR/VARX, VECM, or dynamic factor model.
5. One regime or break-aware family.
```

### Phase C — Nonlinear economic feature basis

```text
1. Regularized lagged-feature regression.
2. Gradient boosting.
3. Random forest or Gaussian-process comparator.
4. Quantile/conformal uncertainty calibration where appropriate.
```

### Phase D — Deep sequence basis

```text
1. TCN or N-BEATS/N-HiTS.
2. LSTM/GRU comparison.
3. Transformer/TFT or selected time-series foundation model.
4. Probabilistic deep forecast heads only when their calibration can be evaluated.
```

### Phase E — Residual meta-analysis and synthesis

```text
1. Cross-model residual correlation and disagreement analysis.
2. Horizon-conditional and regime-conditional residual analysis.
3. Tail, coverage, and calibration analysis.
4. Residual feature construction and attractor/recurrence investigations.
5. Ensemble, stacking, dynamic model averaging, or residual correction.
6. Nested evaluation of any selected/combined procedure.
```

## Current non-goals

The following are deliberately deferred unless target/data requirements justify
them:

```text
Tick-level market microstructure models
Hawkes and duration models
Count/demand-specific models
Survival/hazard models
Spatial and graph forecasting
Spatio-temporal neural networks
Physics-informed/PDE models
Large uncontrolled Transformer hyperparameter sweeps
Every named ARIMA/GARCH/ML/deep-learning variant
```

Deferral does not mean exclusion from the long-term research space. It means the
family has not yet earned implementation priority for the current FRED
forecasting and residual-analysis substrate.

## Decision rule for adding a family

Before implementing a new family, write a short decision note answering:

1. What mechanism does this family represent that current active models do not?
2. What configuration dimensions will be swept?
3. What constraints prevent an uncontrolled combinatorial grid?
4. What data and feature-availability rules are required at an origin?
5. What output does it provide: point, variance, intervals, quantiles, samples,
   or a density?
6. How will uncertainty be labeled if the backend does not provide it?
7. What residual behavior or economic mechanism is expected to be informative?
8. What rolling-origin protocol will test it fairly?
9. What compact persisted facts must be retained?
10. What observation would justify retiring, narrowing, or expanding this family?

## Current decision

The immediate next engineering task is not to add another model family and not to
launch the full large rolling grid in memory.

The immediate next task is:

```text
Implement compact rolling-sweep summary extraction and incremental result
persistence for origin × model scorecards and forecast leaves.
```

That storage/evaluation layer will support the current ARIMA basis, the existing
structural models, and later MATLAB/Python/PyTorch implementations without
changing the atomic forecasting contract.