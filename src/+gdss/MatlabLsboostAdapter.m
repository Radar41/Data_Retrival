classdef MatlabLsboostAdapter < gdss.DynamicModelAdapter
    %MATLABLSBOOSTADAPTER Gradient-boosted regression trees on lagged
    % values of the target (fitrensemble, Method "LSBoost").
    %
    % The configuration is the hyperparameter point: nothing is tuned and
    % nothing is cross-validated. ModelConfig fields, with the default used
    % when a field is absent:
    %
    %   boost_lags                 12       lags of the modeled series
    %   boost_target               "level"  "level": model y_t from
    %                                       y_{t-1..t-L}; "difference": model
    %                                       dy_t from dy_{t-1..t-L}, then add
    %                                       the cumulated forecast differences
    %                                       back to the last level
    %   num_learning_cycles        200      boosting rounds (trees)
    %   learn_rate                 0.1      shrinkage
    %   max_num_splits             4        splits per tree
    %   min_leaf_size              5        observations per leaf
    %   boost_bootstrap_paths      500      residual-bootstrap paths
    %   boost_bootstrap_seed       0        seed of the bootstrap draws
    %   prediction_interval_levels [0.80 0.95]
    %   forecast_scale             "LEVEL"
    %
    % Minimum training length: n >= L + max(30, 3 L), L = boost_lags, so
    % the level design has at least max(30, 3 L) rows (the difference
    % design one fewer).
    %
    % forecast reads its lag buffer from the tail of
    % fitPayload.training_values, so a caller may overwrite that field with
    % a longer series to forecast from a later origin with the same fitted
    % ensemble.

    methods

        function obj = MatlabLsboostAdapter(modelConfig)
            obj@gdss.DynamicModelAdapter(modelConfig);
        end

        function validation = validate(obj, dataContext)

            validation = struct();

            validation.status = "VALID";
            validation.status_reason = "";
            validation.adapter_id = "matlab.ml.lsboost";
            validation.backend_id = "matlab.stats.fitrensemble_lsboost";
            validation.backend_version = version;

            validation.supported_target_dimension = 1;
            validation.supported_target_transform = "identity";
            validation.supported_forecast_strategy = "recursive";
            validation.supported_distribution_kinds = "empirical";

            validation.required_covariates = false;
            validation.required_minimum_training_observations = NaN;
            validation.warnings = strings(0, 1);

            if ~isfield(dataContext, "target_dimension") || ...
                    dataContext.target_dimension ~= 1
                validation.status = "INVALID_CONFIGURATION";
                validation.status_reason = ...
                    "LSBoost adapter requires a univariate target.";
                return
            end

            if ~isfield(obj.ModelConfig, "target_transform") || ...
                    string(obj.ModelConfig.target_transform) ~= "identity"
                validation.status = "UNSUPPORTED_TARGET_TRANSFORM";
                validation.status_reason = ...
                    "LSBoost adapter v1 supports identity target transform only.";
                return
            end

            if ~isfield(obj.ModelConfig, "forecast_strategy") || ...
                    string(obj.ModelConfig.forecast_strategy) ~= "recursive"
                validation.status = "UNSUPPORTED_FORECAST_STRATEGY";
                validation.status_reason = ...
                    "LSBoost adapter v1 supports recursive forecasting only.";
                return
            end

            [settings, problem] = resolveSettings(obj.ModelConfig);

            if problem ~= ""
                validation.status = "INVALID_CONFIGURATION";
                validation.status_reason = problem;
                return
            end

            minimumTrainingObservations = ...
                minimumTrainingCount(settings.boost_lags);

            validation.required_minimum_training_observations = ...
                minimumTrainingObservations;

            if ~isfield(dataContext, "training_observation_count") || ...
                    dataContext.training_observation_count < ...
                    minimumTrainingObservations
                validation.status = "INSUFFICIENT_TRAINING_DATA";
                validation.status_reason = ...
                    "LSBoost adapter requires at least " + ...
                    string(minimumTrainingObservations) + ...
                    " training observations (boost_lags + max(30, 3*boost_lags)).";
            end

        end

        function fitPayload = fit(obj, trainingData, fitContext)

            assert(isfield(trainingData, "target_values"), ...
                "trainingData.target_values is required.");

            y = double(trainingData.target_values(:));

            assert(isnumeric(y) && ~isempty(y), ...
                "trainingData.target_values must be a nonempty numeric vector.");

            assert(all(isfinite(y)), ...
                "LSBoost adapter requires finite training values.");

            [settings, problem] = resolveSettings(obj.ModelConfig);

            assert(problem == "", "LSBoost adapter: %s", problem);

            L = settings.boost_lags;

            assert(numel(y) >= minimumTrainingCount(L), ...
                "LSBoost adapter has insufficient training observations.");

            z = modeledSeries(y, settings.boost_target);

            [X, Y] = lagDesign(z, L);

            fitTimer = tic;

            [previousMessage, previousId] = lastwarn;
            lastwarn("", "");

            treeTemplate = templateTree( ...
                "MaxNumSplits", settings.max_num_splits, ...
                "MinLeafSize", settings.min_leaf_size, ...
                "NumVariablesToSample", "all", ...
                "Surrogate", "off");

            fullEnsemble = fitrensemble(X, Y, ...
                "Method", "LSBoost", ...
                "NumLearningCycles", settings.num_learning_cycles, ...
                "LearnRate", settings.learn_rate, ...
                "Learners", treeTemplate);

            estimatedModel = compact(fullEnsemble);
            fittedValues = predict(estimatedModel, X);

            [warningMessage, warningId] = lastwarn;

            if warningMessage == ""
                lastwarn(previousMessage, previousId);
            end

            runtimeSeconds = toc(fitTimer);

            residuals = Y - fittedValues;
            trainedCount = estimatedModel.NumTrained;

            backendWarned = warningMessage ~= "";
            residualsFinite = all(isfinite(residuals));

            fitPayload = struct();

            if ~residualsFinite
                fitPayload.status = "PARTIAL_COMPLETE";
                fitPayload.status_reason = ...
                    "In-sample residuals contain non-finite values.";
            elseif backendWarned
                fitPayload.status = "COMPLETE";
                fitPayload.status_reason = ...
                    "Backend warning: " + string(warningMessage);
            else
                fitPayload.status = "COMPLETE";
                fitPayload.status_reason = "";
            end

            fitPayload.backend_id = "matlab.stats.fitrensemble_lsboost";
            fitPayload.backend_version = version;
            fitPayload.backend_model_class = ...
                "lsboost_regression_trees_on_" + settings.boost_target + "_lags";

            fitPayload.model_artifact_reference = "";
            fitPayload.model_artifact_sha256 = "";
            fitPayload.model_artifact_format = "IN_MEMORY_COMPACT_REGRESSION_ENSEMBLE";

            parameterName = [ ...
                "boost_lags"
                "num_learning_cycles"
                "learn_rate"
                "max_num_splits"
                "min_leaf_size"
                "boost_target_is_difference"];

            parameterValue = [ ...
                L
                settings.num_learning_cycles
                settings.learn_rate
                settings.max_num_splits
                settings.min_leaf_size
                double(settings.boost_target == "difference")];

            parameterConstraint = [ ...
                "positive_integer"
                "positive_integer"
                "0 < learn_rate <= 1"
                "positive_integer"
                "positive_integer"
                "0 = level, 1 = difference"];

            parameterCount = numel(parameterName);

            fitPayload.parameter_table = table( ...
                parameterName, ...
                repmat("fixed", parameterCount, 1), ...
                parameterValue, ...
                repmat("natural", parameterCount, 1), ...
                parameterConstraint, ...
                repmat("not_estimated", parameterCount, 1), ...
                nan(parameterCount, 1), ...
                'VariableNames', { ...
                'parameter_name', ...
                'parameter_role', ...
                'estimated_value', ...
                'natural_scale', ...
                'constraint', ...
                'estimation_scale', ...
                'optimizer_scale_value'});

            fitPayload.fixed_parameter_table = table();

            % The ensemble has no finite parameter vector with a sampling
            % covariance, and the hyperparameters are fixed, not estimated.
            fitPayload.parameter_covariance = [];
            fitPayload.parameter_covariance_status = "NOT_AVAILABLE";
            fitPayload.parameter_standard_error = nan(parameterCount, 1);
            fitPayload.parameter_standard_error_status = "NOT_AVAILABLE";

            fitPayload.parameter_covariance_reference = "";
            fitPayload.parameter_standard_error_reference = "";

            fitPayload.predictive_context_kind = ...
                "lag_buffer_from_training_values_tail";

            fitPayload.predictive_context_reference = "";
            fitPayload.state_at_origin = NaN;
            fitPayload.state_covariance_at_origin_reference = "";

            fitPayload.lag_buffer_at_origin_reference = "";
            fitPayload.feature_context_reference = "";
            fitPayload.neural_context_reference = "";
            fitPayload.regime_context_reference = "";
            fitPayload.particle_context_reference = "";

            inSampleMse = mean(residuals .^ 2);

            fitPayload.log_likelihood = NaN;
            fitPayload.aic = NaN;
            fitPayload.aicc = NaN;
            fitPayload.bic = NaN;
            fitPayload.objective_value = inSampleMse;

            if backendWarned
                fitPayload.convergence_status = "BACKEND_WARNING";
                fitPayload.convergence_message = ...
                    string(warningId) + ": " + string(warningMessage);
            elseif trainedCount < settings.num_learning_cycles
                fitPayload.convergence_status = "STOPPED_EARLY";
                fitPayload.convergence_message = ...
                    "Trained " + string(trainedCount) + " of " + ...
                    string(settings.num_learning_cycles) + " learning cycles.";
            else
                fitPayload.convergence_status = "BACKEND_OUTPUT_AVAILABLE";
                fitPayload.convergence_message = "";
            end

            fitPayload.iterations = trainedCount;
            fitPayload.function_evaluations = NaN;
            fitPayload.runtime_seconds = runtimeSeconds;

            fitPayload.estimation_output = struct( ...
                "num_trained", trainedCount, ...
                "design_row_count", size(X, 1), ...
                "design_column_count", size(X, 2), ...
                "in_sample_mse", inSampleMse, ...
                "backend_warning_id", string(warningId), ...
                "backend_warning_message", string(warningMessage));

            fitPayload.in_sample_fitted_values_reference = "";
            fitPayload.in_sample_residuals_reference = "";
            fitPayload.in_sample_innovation_residuals_reference = "";
            fitPayload.in_sample_diagnostics_reference = "";

            fitPayload.fitted_value_information_scope = ...
                "in_sample_resubstitution_on_" + settings.boost_target + "_scale";

            fitPayload.fit_context = fitContext;
            fitPayload.estimated_model = estimatedModel;
            fitPayload.boost_lags = L;
            fitPayload.boost_target = settings.boost_target;
            fitPayload.in_sample_fitted_values = fittedValues;
            fitPayload.in_sample_residuals = residuals;
            fitPayload.training_values = y;

        end

        function forecastPayload = forecast(obj, fitPayload, forecastContext)

            requiredFields = [ ...
                "estimated_model"
                "training_values"
                "boost_lags"
                "boost_target"
                "in_sample_residuals"];

            for i = 1:numel(requiredFields)
                assert(isfield(fitPayload, requiredFields(i)), ...
                    "fitPayload." + requiredFields(i) + " is required.");
            end

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
                "LSBoost adapter v1 requires contiguous horizons 1:N.");

            [settings, problem] = resolveSettings(obj.ModelConfig);

            assert(problem == "", "LSBoost adapter: %s", problem);

            model = fitPayload.estimated_model;
            L = double(fitPayload.boost_lags);
            boostTarget = string(fitPayload.boost_target);

            y = double(fitPayload.training_values(:));

            assert(all(isfinite(y)), ...
                "fitPayload.training_values must be finite.");

            z = modeledSeries(y, boostTarget);

            assert(numel(z) >= L, ...
                "fitPayload.training_values is too short for boost_lags.");

            maxHorizon = max(horizon);
            pathCount = settings.boost_bootstrap_paths;

            residuals = double(fitPayload.in_sample_residuals(:));
            residuals = residuals(isfinite(residuals));
            residuals = residuals - mean(residuals);

            % Lag buffer: column j holds lag j, newest first.
            lagBuffer = z(end:-1:(end - L + 1))';

            [previousMessage, previousId] = lastwarn;
            lastwarn("", "");

            pointPath = zeros(1, maxHorizon);
            buffer = lagBuffer;

            for h = 1:maxHorizon
                pointPath(h) = predict(model, buffer);
                buffer = [pointPath(h), buffer(1:(end - 1))];
            end

            distributionAvailable = ~isempty(residuals);

            if distributionAvailable

                savedRngState = rng;
                restoreRng = onCleanup(@() rng(savedRngState));
                rng(settings.boost_bootstrap_seed, "twister");

                drawIndex = randi(numel(residuals), pathCount, maxHorizon);

                delete(restoreRng);

                shocks = reshape(residuals(drawIndex), pathCount, maxHorizon);

                samplePaths = zeros(pathCount, maxHorizon);
                buffers = repmat(lagBuffer, pathCount, 1);

                for h = 1:maxHorizon
                    samplePaths(:, h) = predict(model, buffers) + shocks(:, h);
                    buffers = [samplePaths(:, h), buffers(:, 1:(end - 1))];
                end

            else
                samplePaths = nan(1, maxHorizon);
            end

            [warningMessage, warningId] = lastwarn;

            if warningMessage == ""
                lastwarn(previousMessage, previousId);
            end

            if boostTarget == "difference"
                pointLevel = y(end) + cumsum(pointPath);
                sampleLevel = y(end) + cumsum(samplePaths, 2);
            else
                pointLevel = pointPath;
                sampleLevel = samplePaths;
            end

            pointForecast = pointLevel(horizon)';
            sampleLevel = sampleLevel(:, horizon);

            forecastVariance = var(sampleLevel, 0, 1)';
            forecastStandardDeviation = sqrt(forecastVariance);

            intervalLevels = settings.prediction_interval_levels;
            levelCount = numel(intervalLevels);

            intervalLower = nan(numel(horizon), levelCount);
            intervalUpper = nan(numel(horizon), levelCount);

            if distributionAvailable
                for k = 1:levelCount
                    tail = (1 - intervalLevels(k)) / 2;
                    bounds = quantile(sampleLevel, [tail, 1 - tail], 1);
                    intervalLower(:, k) = bounds(1, :)';
                    intervalUpper(:, k) = bounds(2, :)';
                end
            end

            pointAvailable = isfinite(pointForecast);
            distributionAvailableAtH = distributionAvailable & ...
                isfinite(forecastVariance);
            intervalAvailableAtH = distributionAvailableAtH & ...
                all(isfinite(intervalLower), 2) & ...
                all(isfinite(intervalUpper), 2);

            forecastPayload = struct();

            if ~all(pointAvailable)
                forecastPayload.status = "PARTIAL_COMPLETE";
                forecastPayload.status_reason = ...
                    "Some point forecasts are non-finite.";
            elseif warningMessage ~= ""
                forecastPayload.status = "COMPLETE";
                forecastPayload.status_reason = ...
                    "Backend warning: " + string(warningId) + ": " + ...
                    string(warningMessage);
            else
                forecastPayload.status = "COMPLETE";
                forecastPayload.status_reason = "";
            end

            forecastPayload.horizon = horizon;
            forecastPayload.point_forecast = pointForecast;
            forecastPayload.point_forecast_status = ...
                availabilityStatus(pointAvailable);

            forecastPayload.point_forecast_scale = ...
                repmat(settings.forecast_scale, numel(horizon), 1);

            forecastPayload.point_forecast_method = ...
                repmat("lsboost_recursive_" + boostTarget, ...
                numel(horizon), 1);

            forecastPayload.forecast_distribution_status = ...
                availabilityStatus(distributionAvailableAtH);

            forecastPayload.forecast_distribution_family = ...
                repmat("empirical", numel(horizon), 1);

            forecastPayload.forecast_distribution_method = ...
                repmat("residual_bootstrap_recursive", numel(horizon), 1);

            forecastPayload.forecast_variance = forecastVariance;
            forecastPayload.forecast_standard_deviation = ...
                forecastStandardDeviation;

            forecastPayload.distribution_parameter_reference = ...
                repmat("", numel(horizon), 1);

            forecastPayload.forecast_sample_artifact_reference = ...
                repmat("", numel(horizon), 1);

            forecastPayload.prediction_interval_status = ...
                availabilityStatus(intervalAvailableAtH);

            forecastPayload.prediction_interval_method = ...
                repmat("residual_bootstrap_quantile", numel(horizon), 1);

            forecastPayload.prediction_interval_levels = intervalLevels;
            forecastPayload.interval_lower = intervalLower;
            forecastPayload.interval_upper = intervalUpper;

            forecastPayload.bootstrap_path_count = size(samplePaths, 1);
            forecastPayload.bootstrap_seed = settings.boost_bootstrap_seed;

        end

    end

end

function [settings, problem] = resolveSettings(modelConfig)
% Every ModelConfig field this adapter reads, with its default, checked.

settings = struct( ...
    "boost_lags", 12, ...
    "boost_target", "level", ...
    "num_learning_cycles", 200, ...
    "learn_rate", 0.1, ...
    "max_num_splits", 4, ...
    "min_leaf_size", 5, ...
    "boost_bootstrap_paths", 500, ...
    "boost_bootstrap_seed", 0, ...
    "prediction_interval_levels", [0.80 0.95], ...
    "forecast_scale", "LEVEL");

problem = "";

names = string(fieldnames(settings))';

for name = names
    if isfield(modelConfig, name)
        settings.(name) = modelConfig.(name);
    end
end

positiveIntegerNames = [ ...
    "boost_lags", "num_learning_cycles", "max_num_splits", ...
    "min_leaf_size", "boost_bootstrap_paths"];

for name = positiveIntegerNames
    value = settings.(name);
    if ~(isnumeric(value) && isscalar(value) && isfinite(value) && ...
            value >= 1 && value == floor(value))
        problem = "modelConfig." + name + " must be one positive integer.";
        return
    end
    settings.(name) = double(value);
end

seed = settings.boost_bootstrap_seed;
if ~(isnumeric(seed) && isscalar(seed) && isfinite(seed) && ...
        seed >= 0 && seed == floor(seed) && seed < 2^32)
    problem = "modelConfig.boost_bootstrap_seed must be one integer in [0, 2^32).";
    return
end
settings.boost_bootstrap_seed = double(seed);

learnRate = settings.learn_rate;
if ~(isnumeric(learnRate) && isscalar(learnRate) && isfinite(learnRate) && ...
        learnRate > 0 && learnRate <= 1)
    problem = "modelConfig.learn_rate must be one number in (0, 1].";
    return
end
settings.learn_rate = double(learnRate);

boostTarget = string(settings.boost_target);
if ~(isscalar(boostTarget) && ismember(boostTarget, ["level", "difference"]))
    problem = "modelConfig.boost_target must be ""level"" or ""difference"".";
    return
end
settings.boost_target = boostTarget;

levels = settings.prediction_interval_levels;
if ~(isnumeric(levels) && ~isempty(levels) && all(isfinite(levels(:))) && ...
        all(levels(:) > 0) && all(levels(:) < 1))
    problem = "modelConfig.prediction_interval_levels must lie in (0, 1).";
    return
end
settings.prediction_interval_levels = double(levels(:))';

settings.forecast_scale = string(settings.forecast_scale);

end

function n = minimumTrainingCount(lagCount)
n = lagCount + max(30, 3 * lagCount);
end

function z = modeledSeries(y, boostTarget)
if boostTarget == "difference"
    z = diff(y);
else
    z = y;
end
end

function [X, Y] = lagDesign(z, lagCount)
% Row r predicts z(lagCount + r) from z(lagCount + r - j), j = 1..lagCount.
n = numel(z);
X = zeros(n - lagCount, lagCount);
for j = 1:lagCount
    X(:, j) = z((lagCount + 1 - j):(n - j));
end
Y = z((lagCount + 1):n);
end

function status = availabilityStatus(isAvailable)
status = repmat("NOT_AVAILABLE", numel(isAvailable), 1);
status(isAvailable(:)) = "AVAILABLE";
end
