# GDSS / Data_Retrival — Project Continuation Handoff

**Prepared:** 2026-09-16  
**Purpose:** Start a fresh chat without losing implementation context. This is a MATLAB project using FRED data and a generalized dynamic state-space (GDSS) evaluation framework.

## First instruction for the next chat

Begin by asking me for both of the following before prescribing or editing code:

1. The MATLAB project root directory.
2. The exact active working directory (`pwd`) and, if relevant, the paths of the adapter/config/runner files being edited.

Then ask me to paste the relevant current file(s), especially the adapter under repair, rather than assuming their contents. The prior conversation has only partial file snapshots and may not match the current disk state.

## Project goal

Build a reusable, origin-based forecasting/evaluation system for FRED series. The core current use case is `TOTBKCRNSA` (Total Consumer Credit Owned and Securitized, Not Seasonally Adjusted), with the framework designed to expand to other FRED series and dynamic models.

The evaluation architecture is:

```text
ImmutableDataVersion
  -> TargetSeries
    -> ModelConfig
      -> FitRealization
        -> ForecastRealization
          -> ForecastLeaf (one target/horizon forecast)
        -> ForecastScorecard (derived metrics)
```

A fit is always origin-specific. An origin is the last observed training point. No fit or forecast may use actual target values after its origin.

## Current MATLAB architecture

Known project components include:

```text
src/+gdss/DynamicModelAdapter.m
src/+gdss/AnalyticalNaiveRandomWalkAdapter.m
src/+gdss/MatlabSsmLocalLevelAdapter.m
src/+gdss/MatlabSsmLocalLinearTrendAdapter.m
src/+gdss/MatlabSsmDampedTrendAdapter.m
src/+gdss/create_model_adapter.m
src/run_gdss_evaluation.m
```

Known evaluation/configuration functions include variants such as:

```text
totbkcrnsa_naive_evaluation_config.m
totbkcrnsa_local_level_ssm_evaluation_config.m
totbkcrnsa_local_linear_trend_ssm_evaluation_config.m
totbkcrnsa_damped_trend_ssm_evaluation_config.m
```

Exact names and locations must be confirmed from the restarted MATLAB project.

## Implementation status

### Completed / validated

1. **Naive random-walk adapter** exists and produces point forecasts. Its uncertainty/distribution fields must remain explicitly unavailable if the adapter does not estimate them; do not fabricate zero variance or zero-width intervals.

2. **Damped local-linear-trend SSM adapter** was modified successfully to expose fit-time parameter metadata.

3. The damped-trend validation output showed a populated `parameter_table`, a finite log likelihood, and available covariance/standard-error status:

```text
level_state_disturbance_variance    477.94
slope_state_disturbance_variance    0.079244
observation_disturbance_variance    2.0646e-10
slope_persistence_phi               approximately 1

Log likelihood: -11459.661313
Parameter covariance status: AVAILABLE
Parameter standard-error status: AVAILABLE
```

4. Interpretation of the damped-trend result: `phi` was estimated extremely close to 1, so the fitted damped model behaved nearly as an undamped local-linear-trend model for that specific series/origin. This is a fit outcome, not necessarily an implementation defect.

### Intended adapter fit payload

Adapters should return a fit payload that makes origin-specific estimation results visible. The precise fields may be adapted to the existing project conventions, but the intended common surface is:

```matlab
fit_payload.parameter_table
fit_payload.log_likelihood
fit_payload.parameter_covariance_status
fit_payload.parameter_standard_error_status
```

The parameter table should contain, at minimum:

```text
parameter_name
parameter_role
estimated_value
natural_scale
constraint
estimation_scale
optimizer_scale_value
```

Suggested status values:

```text
AVAILABLE
NOT_AVAILABLE
UNRELIABLE
```

Do not claim covariance/standard errors are substantively reliable merely because MATLAB returns an object. Boundary estimates or inversion/identifiability warnings should be represented as `UNRELIABLE` (or a clear diagnostic status) while preserving the computed output when appropriate.

## Remaining immediate task

Port the same fit-metadata pattern proven in `MatlabSsmDampedTrendAdapter.m` into:

1. `src/+gdss/MatlabSsmLocalLevelAdapter.m`
2. `src/+gdss/MatlabSsmLocalLinearTrendAdapter.m`

Do **not** change model equations, forecast behavior, evaluator logic, factory routing, test design, or parallel/Slurm configuration solely to do this metadata task.

### Local-level parameter table

The local-level model should report two origin-specific estimates:

```text
state_disturbance_variance
observation_disturbance_variance
```

### Local-linear-trend parameter table

The local-linear-trend model should report three origin-specific estimates:

```text
level_state_disturbance_variance
slope_state_disturbance_variance
observation_disturbance_variance
```

For reference, the structural state-space specifications are:

```text
Local level:
  State: level
  A = [1]
  C = [1]

Local linear trend:
  State: [level, slope]
  A = [1 1;
       0 1]
  C = [1 0]

Damped local linear trend:
  State: [level, slope]
  A = [1 phi;
       0 phi]
  C = [1 0]
  0 < phi < 1
```

## Latest run and current blocker

The latest attempt was for the local-level configuration:

```matlab
clear evaluationRun
rehash
config = totbkcrnsa_local_level_ssm_evaluation_config(pwd);
evaluationRun = run_gdss_evaluation(config);
disp(evaluationRun.fit_realization.fit_payload.parameter_table)
fprintf("Log likelihood: %.6f\n", ...
    evaluationRun.fit_realization.fit_payload.log_likelihood);
fprintf("Parameter covariance status: %s\n", ...
    evaluationRun.fit_realization.fit_payload.parameter_covariance_status);
fprintf("Parameter standard-error status: %s\n", ...
    evaluationRun.fit_realization.fit_payload.parameter_standard_error_status);
```

MATLAB output:

```text
Warning: Covariance matrix of estimators cannot be computed precisely due to inversion difficulty.
Check parameter identifiability. Also try different starting values and other options to
compute the covariance matrix.

In statespace/estimate
In ssm/estimate
In gdss/MatlabSsmLocalLevelAdapter/fit
  /home/radar-41-0/Documents/Data_Retrival/src/+gdss/MatlabSsmLocalLevelAdapter.m, line 83
In run_gdss_evaluation
  /home/radar-41-0/Documents/Data_Retrival/src/run_gdss_evaluation.m, line 145

Log likelihood: NaN
Unrecognized field name "parameter_covariance_status".
```

### What this most likely means

The local-level adapter did not finish assigning the enhanced metadata payload, or an exception/incorrect result-handling path caused it to return its older default payload. The covariance warning itself is not necessarily fatal: MATLAB may complete estimation but be unable to compute a precise covariance matrix. The adapter must preserve the finite fitted model/log likelihood if `estimate` returns them, while recording that parameter covariance and standard errors are unavailable or unreliable.

The new chat should inspect the exact current contents around line 83 in `MatlabSsmLocalLevelAdapter.m`, and compare the full `fit` method against the currently working damped-trend adapter. Do not assume the output signature of `estimate` or the ordering of values; confirm from the current code and MATLAB version.

## Recommended debugging sequence

1. In the MATLAB project root, run:

```matlab
pwd
which run_gdss_evaluation -all
which gdss.MatlabSsmLocalLevelAdapter -all
which gdss.MatlabSsmDampedTrendAdapter -all
```

2. Display the current adapter files and identify the local-level `fit` method around line 83:

```matlab
type(fullfile("src", "+gdss", "MatlabSsmLocalLevelAdapter.m"))
type(fullfile("src", "+gdss", "MatlabSsmDampedTrendAdapter.m"))
```

3. Compare only the extraction/output-handling portions of the two adapters:

- The `estimate(...)` call and all returned outputs.
- How `estimatedParameters`, covariance, log likelihood, and optimizer/output structures are handled.
- Construction of `fit_payload`.
- Any `try/catch` that could discard successful fit results following a covariance warning.

4. Update the local-level adapter so it always returns a consistent payload after a successful estimate, including explicit status fields.

5. Rerun after clearing the old in-memory result:

```matlab
clear evaluationRun
rehash
config = totbkcrnsa_local_level_ssm_evaluation_config(pwd);
evaluationRun = run_gdss_evaluation(config);

payload = evaluationRun.fit_realization.fit_payload;
disp(payload.parameter_table)
disp(payload.log_likelihood)
disp(payload.parameter_covariance_status)
disp(payload.parameter_standard_error_status)
```

6. Confirm whether the run itself completed before interpreting the payload:

```matlab
disp(evaluationRun.fit_realization.status)
disp(evaluationRun.fit_realization.status_reason)
```

Use actual field names if the current class/struct uses different names.

7. Only after local level is validated, port the corresponding approach to `MatlabSsmLocalLinearTrendAdapter.m` and run its configuration.

## Covariance warning policy

A covariance inversion/identifiability warning should not automatically be treated as model-estimation failure. The desired behavior is:

| Estimation outcome | `log_likelihood` | covariance status | standard-error status |
|---|---:|---|---|
| Estimate succeeded and covariance is usable | Finite | `AVAILABLE` | `AVAILABLE` |
| Estimate succeeded but MATLAB cannot compute covariance precisely | Finite if returned | `UNRELIABLE` or `NOT_AVAILABLE` | `UNRELIABLE` or `NOT_AVAILABLE` |
| Estimate failed | `NaN` | `NOT_AVAILABLE` | `NOT_AVAILABLE` |

The adapter should retain the MATLAB warning/diagnostic message in a suitable diagnostics field if the project has one. Do not conceal the warning.

## Schema/ERD refactor direction

The uploaded `fred_erd_full_schema.html` is a draft to refactor, not a final source of truth. The governing distinction is:

> `ModelConfig` defines reusable structure. `FitRealization` and `FitParameterEstimate` record numerical outcomes for a particular origin-specific fit.

### ModelConfig belongs to the immutable layer

Examples:

```text
model_id
model_family
structure_id
adapter_id
state representation
estimation method
training-window policy
forecast strategy
forecast-distribution policy
interval coverage policy
parameter declarations, constraints, and fixed-vs-estimable status
```

### FitRealization belongs to the origin-specific layer

Examples:

```text
data fingerprint
origin index/time
training range/count
model config reference
backend/model artifact reference
log likelihood, AIC/BIC where available
convergence/runtime/diagnostics
parameter covariance status
state/predictive context at origin
```

### FitParameterEstimate contains numeric estimates

Examples:

```text
fit realization reference
parameter definition reference
parameter order
estimated value on natural scale
optimizer-scale value
standard error/status
fixed vs estimated flag
```

### Forecast layer

```text
ForecastRealization:
  forecast generated from one fit; forecast policy and distribution status

ForecastLeaf:
  one `(origin, target, horizon)` forecast
  target_index = origin_index + horizon
  point_forecast
  actual_value when observed
  forecast_error = actual_value - point_forecast
  forecast variance / distribution metadata

PredictionInterval:
  one normalized row per forecast leaf and coverage probability

ForecastScorecard:
  derived, reproducible metrics such as MAE/RMSE
```

Do not make `origin_step` part of a fit identity. It is an origin-selection policy, not an intrinsic dimension of the fit.

## Invariants to preserve

```text
1. A fit at an origin may use observations only through that origin.
2. target_index = origin_index + horizon.
3. forecast_error = actual_value - point_forecast.
4. absolute_error = abs(forecast_error).
5. squared_error = forecast_error^2.
6. Scorecards are reproducible from forecast leaves.
7. Unavailable distributions/intervals use explicit status and null/NaN numeric values.
8. Model structure is immutable across origins; estimated values are fit-specific.
9. Execution mode (serial/parpool/Slurm) is operational provenance, not model semantics.
```

## Out of scope for the immediate fix

Do not expand scope into any of the following until local-level and local-linear-trend metadata validation is complete:

- Redesigning the entire ERD/database.
- Changing SSM equations or optimizer choices.
- Adding alternate initial values merely to silence the warning.
- Treating the covariance warning as a reason to fabricate standard errors.
- Refactoring the evaluator, factory, tests, or parallel computing setup.
- Turning `origin_step` into a fit-level entity/key.

## Definition of done for this phase

This phase is complete when:

1. Local-level evaluation finishes and its `fit_payload` includes a populated parameter table, log likelihood (when MATLAB estimation succeeds), and covariance/standard-error status fields.
2. Local-linear-trend evaluation provides the corresponding three parameter estimates and statuses.
3. Damped trend remains working and retains its four-parameter payload.
4. Warnings about covariance identifiability are represented honestly in diagnostics/status rather than causing missing payload fields or `NaN` likelihood after an otherwise successful fit.
5. The schema material can be updated to preserve the `ModelConfig` vs. `FitRealization` vs. `FitParameterEstimate` separation.
