classdef MatlabSsmLocalLevelAdapter < gdss.DynamicModelAdapter

    methods

        function obj = MatlabSsmLocalLevelAdapter(modelConfig)
            obj@gdss.DynamicModelAdapter(modelConfig);
        end

        function validation = validate(obj, dataContext)

            validation = struct();

            validation.status = "VALID";
            validation.status_reason = "";
            validation.adapter_id = "matlab.ssm.local_level";
            validation.backend_id = "matlab.econometrics.ssm";
            validation.backend_version = version;

            validation.supported_target_dimension = 1;
            validation.supported_target_transform = "identity";
            validation.supported_forecast_strategy = "recursive";
            validation.supported_distribution_kinds = "normal";

            validation.required_covariates = false;
            validation.required_minimum_training_observations = 2;
            validation.warnings = strings(0, 1);

            if ~isfield(dataContext, "target_dimension") || ...
                    dataContext.target_dimension ~= 1
                validation.status = "INVALID_CONFIGURATION";
                validation.status_reason = ...
                    "Local-level SSM adapter requires a univariate target.";
                return
            end

            if ~isfield(obj.ModelConfig, "target_transform") || ...
                    string(obj.ModelConfig.target_transform) ~= "identity"
                validation.status = "UNSUPPORTED_TARGET_TRANSFORM";
                validation.status_reason = ...
                    "Local-level SSM adapter v1 supports identity target transform only.";
                return
            end

            if ~isfield(obj.ModelConfig, "forecast_strategy") || ...
                    string(obj.ModelConfig.forecast_strategy) ~= "recursive"
                validation.status = "UNSUPPORTED_FORECAST_STRATEGY";
                validation.status_reason = ...
                    "Local-level SSM adapter v1 supports recursive forecasting only.";
                return
            end

            if ~isfield(dataContext, "training_observation_count") || ...
                    dataContext.training_observation_count < 2
                validation.status = "INSUFFICIENT_TRAINING_DATA";
                validation.status_reason = ...
                    "Local-level SSM adapter requires at least two training observations.";
            end

        end

        function fitPayload = fit(obj, trainingData, fitContext)

            assert(isfield(trainingData, "target_values"), ...
                "trainingData.target_values is required.");

            y = trainingData.target_values(:);

            assert(isnumeric(y) && ~isempty(y), ...
                "trainingData.target_values must be a nonempty numeric vector.");

            assert(all(isfinite(y)), ...
                "Local-level SSM adapter requires finite training values.");

            assert(numel(y) >= 2, ...
                "Local-level SSM adapter requires at least two training observations.");

            paramMap = @(u) localLevelMap(u, y(1));

            specification = ssm(paramMap);

            firstDifferenceVariance = var(diff(y), 1);

            stateVarianceStart = max(firstDifferenceVariance, eps);
            observationVarianceStart = max(var(y, 1) / 100, eps);

            initialParameters = [ ...
                log(stateVarianceStart); ...
                log(observationVarianceStart)];

            [estimatedModel, estimatedParameters, estimatedParameterCovariance, ...
                logLikelihood, estimationOutput] = estimate( ...
                specification, ...
                y, ...
                initialParameters, ...
                "Display", "off");

            fitPayload = struct();

            fitPayload.status = "COMPLETE";
            fitPayload.status_reason = "";

            fitPayload.backend_id = "matlab.econometrics.ssm";
            fitPayload.backend_version = version;
            fitPayload.backend_model_class = "local_level";

            fitPayload.model_artifact_reference = "";
            fitPayload.model_artifact_sha256 = "";
            fitPayload.model_artifact_format = "IN_MEMORY_SSM";

            qState = exp(estimatedParameters(1));
            rObservation = exp(estimatedParameters(2));

            parameterName = [ ...
                "state_disturbance_variance"
                "observation_disturbance_variance"];

            parameterRole = [ ...
                "state_disturbance_variance"
                "observation_disturbance_variance"];

            parameterValue = [ ...
                qState
                rObservation];

            parameterScale = [ ...
                "variance"
                "variance"];

            parameterConstraint = [ ...
                "nonnegative"
                "nonnegative"];

            parameterEstimationScale = [ ...
                "log_variance"
                "log_variance"];

            fitPayload.parameter_table = table( ...
                parameterName, ...
                parameterRole, ...
                parameterValue, ...
                parameterScale, ...
                parameterConstraint, ...
                parameterEstimationScale, ...
                estimatedParameters(:), ...
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
                    nan(numel(estimatedParameters), 1);

                fitPayload.parameter_standard_error_status = "NOT_AVAILABLE";

            else

                fitPayload.parameter_covariance_status = "UNRELIABLE";

                fitPayload.parameter_standard_error = ...
                    sqrt(diag(estimatedParameterCovariance));

                fitPayload.parameter_standard_error_status = "UNRELIABLE";

            end

            fitPayload.parameter_covariance_reference = "";
            fitPayload.parameter_standard_error_reference = "";

            fitPayload.predictive_context_kind = "estimated_local_level";
            fitPayload.predictive_context_reference = "";
            fitPayload.state_at_origin = NaN;
            fitPayload.state_covariance_at_origin_reference = "";

            fitPayload.lag_buffer_at_origin_reference = "";
            fitPayload.feature_context_reference = "";
            fitPayload.neural_context_reference = "";
            fitPayload.regime_context_reference = "";
            fitPayload.particle_context_reference = "";

            fitPayload.log_likelihood = logLikelihood;
            fitPayload.aic = NaN;
            fitPayload.aicc = NaN;
            fitPayload.bic = NaN;
            fitPayload.objective_value = -logLikelihood;

            fitPayload.convergence_status = "BACKEND_OUTPUT_AVAILABLE";
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
                "Local-level SSM adapter v1 requires contiguous horizons 1:N.");

            maxHorizon = max(horizon);

            [pointForecastFull, forecastMseFull] = forecast( ...
                fitPayload.estimated_model, ...
                maxHorizon, ...
                fitPayload.training_values);

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
                repmat("ssm_forecast", numel(horizon), 1);

            forecastPayload.forecast_distribution_status = ...
                repmat("AVAILABLE", numel(horizon), 1);

            forecastPayload.forecast_distribution_family = ...
                repmat("normal", numel(horizon), 1);

            forecastPayload.forecast_distribution_method = ...
                repmat("ssm_forecast_mse", numel(horizon), 1);

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

function [A, B, C, D, Mean0, Cov0, StateType] = localLevelMap(u, initialLevel)

q = exp(u(1));
r = exp(u(2));

A = 1;
B = sqrt(q);
C = 1;
D = sqrt(r);

Mean0 = initialLevel;
Cov0 = 1e6;
StateType = 2;

end