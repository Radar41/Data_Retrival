classdef AnalyticalNaiveRandomWalkAdapter < gdss.DynamicModelAdapter
    methods
        function obj = AnalyticalNaiveRandomWalkAdapter(modelConfig)
            obj@gdss.DynamicModelAdapter(modelConfig);
        end

        function validation = validate(obj, dataContext)
            validation = struct();

            validation.status = "VALID";
            validation.status_reason = "";
            validation.adapter_id = "analytical.naive_random_walk";
            validation.backend_id = "analytical";
            validation.backend_version = "v1";

            validation.supported_target_dimension = 1;
            validation.supported_target_transform = "identity";
            validation.supported_forecast_strategy = "recursive";
            validation.supported_distribution_kinds = "NOT_AVAILABLE";

            validation.required_covariates = false;
            validation.required_minimum_training_observations = 1;
            validation.warnings = strings(0, 1);

            if ~isfield(dataContext, "target_dimension") || ...
                    dataContext.target_dimension ~= 1
                validation.status = "INVALID_CONFIGURATION";
                validation.status_reason = ...
                    "Naive random-walk adapter requires a univariate target.";
                return
            end

            if ~isfield(obj.ModelConfig, "target_transform") || ...
                    obj.ModelConfig.target_transform ~= "identity"
                validation.status = "UNSUPPORTED_TARGET_TRANSFORM";
                validation.status_reason = ...
                    "Naive random-walk adapter v1 supports identity target transform only.";
            end
        end

        function fitPayload = fit(obj, trainingData, fitContext)
            assert(isfield(trainingData, "target_values"), ...
                "trainingData.target_values is required.");

            y = trainingData.target_values;

            assert(isnumeric(y) && isvector(y) && ~isempty(y), ...
                "trainingData.target_values must be a nonempty numeric vector.");

            assert(all(isfinite(y)), ...
                "Naive random-walk adapter requires finite training values.");

            fitPayload = struct();

            fitPayload.status = "COMPLETE";
            fitPayload.status_reason = "";

            fitPayload.backend_id = "analytical";
            fitPayload.backend_version = "v1";
            fitPayload.backend_model_class = ...
                "random_walk_without_drift";

            fitPayload.model_artifact_reference = "";
            fitPayload.model_artifact_sha256 = "";
            fitPayload.model_artifact_format = "NOT_REQUIRED";

            fitPayload.parameter_table = table();
            fitPayload.fixed_parameter_table = table();
            fitPayload.parameter_covariance_reference = "";
            fitPayload.parameter_standard_error_reference = "";

            fitPayload.predictive_context_kind = ...
                "last_observed_training_value";

            fitPayload.predictive_context_reference = "";
            fitPayload.state_at_origin = y(end);
            fitPayload.state_covariance_at_origin_reference = "";
            fitPayload.lag_buffer_at_origin_reference = "";
            fitPayload.feature_context_reference = "";
            fitPayload.neural_context_reference = "";
            fitPayload.regime_context_reference = "";
            fitPayload.particle_context_reference = "";

            fitPayload.log_likelihood = NaN;
            fitPayload.aic = NaN;
            fitPayload.aicc = NaN;
            fitPayload.bic = NaN;
            fitPayload.objective_value = NaN;

            fitPayload.convergence_status = "NOT_APPLICABLE";
            fitPayload.convergence_message = ...
                "Analytical model has no estimated parameters.";

            fitPayload.iterations = NaN;
            fitPayload.function_evaluations = NaN;
            fitPayload.runtime_seconds = NaN;

            fitPayload.in_sample_fitted_values_reference = "";
            fitPayload.in_sample_residuals_reference = "";
            fitPayload.in_sample_innovation_residuals_reference = "";
            fitPayload.in_sample_diagnostics_reference = "";

            fitPayload.fitted_value_information_scope = ...
                "NOT_AVAILABLE";

            fitPayload.fit_context = fitContext;
        end

        function forecastPayload = forecast(obj, fitPayload, forecastContext)
            assert(isfield(fitPayload, "state_at_origin"), ...
                "fitPayload.state_at_origin is required.");

            assert(isfield(forecastContext, "horizon"), ...
                "forecastContext.horizon is required.");

            horizon = forecastContext.horizon(:);

            assert(isnumeric(horizon) && ~isempty(horizon), ...
                "forecastContext.horizon must be a nonempty numeric vector.");

            assert(all(isfinite(horizon)) && ...
                   all(horizon == floor(horizon)) && ...
                   all(horizon > 0), ...
                "forecastContext.horizon must contain positive integer horizons.");

            pointForecast = repmat( ...
                fitPayload.state_at_origin, numel(horizon), 1);

            forecastPayload = struct();

            forecastPayload.status = "COMPLETE";
            forecastPayload.status_reason = "";

            forecastPayload.horizon = horizon;
            forecastPayload.point_forecast = pointForecast;
            forecastPayload.point_forecast_status = ...
                repmat("AVAILABLE", numel(horizon), 1);

            forecastPayload.point_forecast_scale = ...
                repmat("LEVEL", numel(horizon), 1);

            forecastPayload.point_forecast_method = ...
                repmat("last_observed_training_value", ...
                       numel(horizon), 1);

            forecastPayload.forecast_distribution_status = ...
                repmat("NOT_AVAILABLE", numel(horizon), 1);

            forecastPayload.forecast_distribution_family = ...
                repmat("none", numel(horizon), 1);

            forecastPayload.forecast_distribution_method = ...
                repmat("not_estimated", numel(horizon), 1);

            forecastPayload.forecast_variance = ...
                nan(numel(horizon), 1);

            forecastPayload.forecast_standard_deviation = ...
                nan(numel(horizon), 1);

            forecastPayload.distribution_parameter_reference = ...
                repmat("", numel(horizon), 1);

            forecastPayload.forecast_sample_artifact_reference = ...
                repmat("", numel(horizon), 1);

            forecastPayload.prediction_interval_status = ...
                repmat("NOT_AVAILABLE", numel(horizon), 1);

            forecastPayload.prediction_interval_method = ...
                repmat("not_estimated", numel(horizon), 1);

            forecastPayload.prediction_interval_levels = ...
                nan(numel(horizon), 0);

            forecastPayload.interval_lower = ...
                nan(numel(horizon), 0);

            forecastPayload.interval_upper = ...
                nan(numel(horizon), 0);
        end
    end
end
