classdef MatlabArimaAdapter < gdss.DynamicModelAdapter

methods

function obj = MatlabArimaAdapter(modelConfig)
obj@gdss.DynamicModelAdapter(modelConfig);
end

function validation = validate(obj, dataContext)

validation = struct();

validation.status = "VALID";
validation.status_reason = "";
validation.adapter_id = "matlab.arima";
validation.backend_id = "matlab.econometrics.arima";
validation.backend_version = version;

validation.supported_target_dimension = 1;
validation.supported_target_transform = "identity";
validation.supported_forecast_strategy = "recursive";
validation.supported_distribution_kinds = "normal";

validation.required_covariates = false;
validation.required_minimum_training_observations = 10;
validation.warnings = strings(0, 1);

if ~isfield(dataContext, "target_dimension") || ...
dataContext.target_dimension ~= 1

validation.status = "INVALID_CONFIGURATION";
validation.status_reason = ...
"ARIMA adapter requires a univariate target.";
return

end

if ~isfield(obj.ModelConfig, "target_transform") || ...
string(obj.ModelConfig.target_transform) ~= "identity"

validation.status = "UNSUPPORTED_TARGET_TRANSFORM";
validation.status_reason = ...
"ARIMA adapter v1 supports identity target transform only.";
return

end

if ~isfield(obj.ModelConfig, "forecast_strategy") || ...
string(obj.ModelConfig.forecast_strategy) ~= "recursive"

validation.status = "UNSUPPORTED_FORECAST_STRATEGY";
validation.status_reason = ...
"ARIMA adapter v1 supports recursive forecasting only.";
return

end

requiredOrderFields = [ ...
"arima_p"
"arima_d"
"arima_q"];

for i = 1:numel(requiredOrderFields)

fieldName = requiredOrderFields(i);

if ~isfield(obj.ModelConfig, fieldName)

validation.status = "INVALID_CONFIGURATION";
validation.status_reason = ...
"ARIMA adapter requires modelConfig." + fieldName + ".";
return

end

orderValue = obj.ModelConfig.(fieldName);

if ~(isnumeric(orderValue) && isscalar(orderValue) && ...
isfinite(orderValue) && orderValue >= 0 && ...
orderValue == floor(orderValue))

validation.status = "INVALID_CONFIGURATION";
validation.status_reason = ...
"modelConfig." + fieldName + ...
" must be one nonnegative integer.";
return

end

end

minimumTrainingObservations = ...
max(10, double(obj.ModelConfig.arima_p) + ...
double(obj.ModelConfig.arima_d) + ...
double(obj.ModelConfig.arima_q) + 5);

validation.required_minimum_training_observations = ...
minimumTrainingObservations;

if ~isfield(dataContext, "training_observation_count") || ...
dataContext.training_observation_count < ...
minimumTrainingObservations

validation.status = "INSUFFICIENT_TRAINING_DATA";
validation.status_reason = ...
"ARIMA adapter requires at least " + ...
string(minimumTrainingObservations) + ...
" training observations for the configured order.";

end

end

function fitPayload = fit(obj, trainingData, fitContext)

assert(isfield(trainingData, "target_values"), ...
"trainingData.target_values is required.");

y = trainingData.target_values(:);

assert(isnumeric(y) && ~isempty(y), ...
"trainingData.target_values must be a nonempty numeric vector.");

assert(all(isfinite(y)), ...
"ARIMA adapter requires finite training values.");

p = double(obj.ModelConfig.arima_p);
d = double(obj.ModelConfig.arima_d);
q = double(obj.ModelConfig.arima_q);

minimumTrainingObservations = max(10, p + d + q + 5);

assert(numel(y) >= minimumTrainingObservations, ...
"ARIMA adapter has insufficient training observations.");

modelSpecification = arima( ...
"ARLags", 1:p, ...
"D", d, ...
"MALags", 1:q, ...
"Constant", NaN, ...
"Variance", NaN);

[estimatedModel, estimatedParameterCovariance, ...
logLikelihood, estimationOutput] = estimate( ...
modelSpecification, ...
y, ...
"Display", "off");

fitPayload = struct();

fitPayload.status = "COMPLETE";
fitPayload.status_reason = "";

fitPayload.backend_id = "matlab.econometrics.arima";
fitPayload.backend_version = version;
fitPayload.backend_model_class = "nonseasonal_arima";

fitPayload.model_artifact_reference = "";
fitPayload.model_artifact_sha256 = "";
fitPayload.model_artifact_format = "IN_MEMORY_ARIMA";

[parameterName, parameterRole, parameterValue, ...
parameterScale, parameterConstraint, parameterEstimationScale, ...
optimizerScaleValue] = arimaParameterTableColumns(estimatedModel, p, q);

fitPayload.parameter_table = table( ...
parameterName, ...
parameterRole, ...
parameterValue, ...
parameterScale, ...
parameterConstraint, ...
parameterEstimationScale, ...
optimizerScaleValue, ...
'VariableNames', { ...
'parameter_name', ...
'parameter_role', ...
'estimated_value', ...
'natural_scale', ...
'constraint', ...
'estimation_scale', ...
'optimizer_scale_value'});

fitPayload.fixed_parameter_table = table();

fitPayload.parameter_covariance = estimatedParameterCovariance;

if isempty(estimatedParameterCovariance) || ...
any(~isfinite(estimatedParameterCovariance), "all")

fitPayload.parameter_covariance_status = "NOT_AVAILABLE";
fitPayload.parameter_standard_error = ...
nan(height(fitPayload.parameter_table), 1);

fitPayload.parameter_standard_error_status = "NOT_AVAILABLE";

else

fitPayload.parameter_covariance_status = "UNRELIABLE";

fitPayload.parameter_standard_error = ...
sqrt(diag(estimatedParameterCovariance));

fitPayload.parameter_standard_error_status = "UNRELIABLE";

end

fitPayload.parameter_covariance_reference = "";
fitPayload.parameter_standard_error_reference = "";

fitPayload.predictive_context_kind = ...
"estimated_nonseasonal_arima";

fitPayload.predictive_context_reference = "";
fitPayload.state_at_origin = NaN;
fitPayload.state_covariance_at_origin_reference = "";

fitPayload.lag_buffer_at_origin_reference = "";
fitPayload.feature_context_reference = "";
fitPayload.neural_context_reference = "";
fitPayload.regime_context_reference = "";
fitPayload.particle_context_reference = "";

parameterCount = height(fitPayload.parameter_table);
observationCount = numel(y);

fitPayload.log_likelihood = logLikelihood;
fitPayload.aic = -2 * logLikelihood + 2 * parameterCount;
fitPayload.aicc = NaN;
fitPayload.bic = -2 * logLikelihood + ...
    log(observationCount) * parameterCount;
fitPayload.objective_value = -logLikelihood;

fitPayload.convergence_status = ...
"BACKEND_OUTPUT_AVAILABLE";

fitPayload.convergence_message = "";
fitPayload.iterations = NaN;
fitPayload.function_evaluations = NaN;
fitPayload.runtime_seconds = NaN;

fitPayload.estimation_output = estimationOutput;

fitPayload.in_sample_fitted_values_reference = "";
fitPayload.in_sample_residuals_reference = "";
fitPayload.in_sample_innovation_residuals_reference = "";
fitPayload.in_sample_diagnostics_reference = "";

fitPayload.fitted_value_information_scope = ...
"backend_declared_fitted_value";

fitPayload.fit_context = fitContext;
fitPayload.estimated_model = estimatedModel;
fitPayload.training_values = y;

end

function forecastPayload = forecast(obj, fitPayload, forecastContext)

assert(isfield(fitPayload, "estimated_model"), ...
"fitPayload.estimated_model is required.");

assert(isfield(fitPayload, "training_values"), ...
"fitPayload.training_values is required.");

assert(isfield(forecastContext, "horizon"), ...
"forecastContext.horizon is required.");

horizon = forecastContext.horizon(:);

assert(isnumeric(horizon) && ~isempty(horizon), ...
"forecastContext.horizon must be a nonempty numeric vector.");

assert(all(isfinite(horizon)) && ...
all(horizon == floor(horizon)) && ...
all(horizon > 0), ...
"forecastContext.horizon must contain positive integer horizons.");

assert(isequal(horizon, (1:numel(horizon))'), ...
"ARIMA adapter v1 requires contiguous horizons 1:N.");

maxHorizon = max(horizon);

[pointForecastFull, forecastMseFull] = forecast( ...
fitPayload.estimated_model, ...
maxHorizon, ...
"Y0", fitPayload.training_values);

pointForecast = pointForecastFull(horizon);
forecastVariance = forecastMseFull(horizon);
forecastStandardDeviation = sqrt(forecastVariance);

intervalLevels = ...
double(obj.ModelConfig.prediction_interval_levels(:))';

z = norminv((1 + intervalLevels) ./ 2);

intervalLower = pointForecast - ...
forecastStandardDeviation .* z;

intervalUpper = pointForecast + ...
forecastStandardDeviation .* z;

forecastPayload = struct();

forecastPayload.status = "COMPLETE";
forecastPayload.status_reason = "";

forecastPayload.horizon = horizon;
forecastPayload.point_forecast = pointForecast;
forecastPayload.point_forecast_status = ...
repmat("AVAILABLE", numel(horizon), 1);

forecastPayload.point_forecast_scale = ...
repmat(string(obj.ModelConfig.forecast_scale), ...
numel(horizon), 1);

forecastPayload.point_forecast_method = ...
repmat("arima_forecast", numel(horizon), 1);

forecastPayload.forecast_distribution_status = ...
repmat("AVAILABLE", numel(horizon), 1);

forecastPayload.forecast_distribution_family = ...
repmat("normal", numel(horizon), 1);

forecastPayload.forecast_distribution_method = ...
repmat("arima_forecast_mse", numel(horizon), 1);

forecastPayload.forecast_variance = forecastVariance;
forecastPayload.forecast_standard_deviation = ...
forecastStandardDeviation;

forecastPayload.distribution_parameter_reference = ...
repmat("", numel(horizon), 1);

forecastPayload.forecast_sample_artifact_reference = ...
repmat("", numel(horizon), 1);

forecastPayload.prediction_interval_status = ...
repmat("AVAILABLE", numel(horizon), 1);

forecastPayload.prediction_interval_method = ...
repmat("normal_quantile", numel(horizon), 1);

forecastPayload.prediction_interval_levels = intervalLevels;
forecastPayload.interval_lower = intervalLower;
forecastPayload.interval_upper = intervalUpper;

end

end

end

function [parameterName, parameterRole, parameterValue, ...
parameterScale, parameterConstraint, parameterEstimationScale, ...
optimizerScaleValue] = arimaParameterTableColumns( ...
estimatedModel, p, q)

parameterName = strings(0, 1);
parameterRole = strings(0, 1);
parameterValue = zeros(0, 1);
parameterScale = strings(0, 1);
parameterConstraint = strings(0, 1);
parameterEstimationScale = strings(0, 1);
optimizerScaleValue = zeros(0, 1);

if ~isempty(estimatedModel.Constant) && ...
isfinite(estimatedModel.Constant)

parameterName(end + 1, 1) = "constant";
parameterRole(end + 1, 1) = "intercept";
parameterValue(end + 1, 1) = estimatedModel.Constant;
parameterScale(end + 1, 1) = "natural";
parameterConstraint(end + 1, 1) = "unconstrained";
parameterEstimationScale(end + 1, 1) = "backend_native";
optimizerScaleValue(end + 1, 1) = NaN;

end

if p > 0

arCoefficient = estimatedModel.AR(:);

for i = 1:numel(arCoefficient)

if iscell(arCoefficient)
coefficientValue = arCoefficient{i};
else
coefficientValue = arCoefficient(i);
end

parameterName(end + 1, 1) = "ar_" + string(i);
parameterRole(end + 1, 1) = "autoregressive_coefficient";
parameterValue(end + 1, 1) = coefficientValue;
parameterScale(end + 1, 1) = "natural";
parameterConstraint(end + 1, 1) = "stationarity_constrained";
parameterEstimationScale(end + 1, 1) = "backend_native";
optimizerScaleValue(end + 1, 1) = NaN;

end

end

if q > 0

maCoefficient = estimatedModel.MA(:);

for i = 1:numel(maCoefficient)

if iscell(maCoefficient)
coefficientValue = maCoefficient{i};
else
coefficientValue = maCoefficient(i);
end

parameterName(end + 1, 1) = "ma_" + string(i);
parameterRole(end + 1, 1) = "moving_average_coefficient";
parameterValue(end + 1, 1) = coefficientValue;
parameterScale(end + 1, 1) = "natural";
parameterConstraint(end + 1, 1) = "invertibility_constrained";
parameterEstimationScale(end + 1, 1) = "backend_native";
optimizerScaleValue(end + 1, 1) = NaN;

end

end

if ~isempty(estimatedModel.Variance) && ...
isfinite(estimatedModel.Variance)

parameterName(end + 1, 1) = "innovation_variance";
parameterRole(end + 1, 1) = "innovation_variance";
parameterValue(end + 1, 1) = estimatedModel.Variance;
parameterScale(end + 1, 1) = "variance";
parameterConstraint(end + 1, 1) = "nonnegative";
parameterEstimationScale(end + 1, 1) = "backend_native";
optimizerScaleValue(end + 1, 1) = NaN;

end

end