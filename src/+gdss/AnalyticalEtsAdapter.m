classdef AnalyticalEtsAdapter < gdss.DynamicModelAdapter
    %ANALYTICALETSADAPTER Exponential smoothing in innovations state-space
    % form (ETS, Hyndman, Koehler, Ord and Snyder 2008).
    %
    % ModelConfig fields read here:
    %   ets_error   "A" | "M"
    %   ets_trend   "N" | "A" | "Ad"
    %   ets_season  "N" | "A" | "M"
    %   season_period               (default 12; ignored when ets_season = "N")
    %   prediction_interval_levels  (in (0, 1); none when absent)
    %   target_transform            ("identity" only)
    %   forecast_strategy           ("recursive" only)
    %   forecast_scale              (copied to point_forecast_scale; "LEVEL" when absent)
    %   simulation_path_count       (optional, default 2000)
    %   simulation_seed             (optional, default 20080101)
    %
    % fit estimates the smoothing parameters and the initial states by
    % maximum likelihood (fmincon, SQP) inside the usual region
    % 0 < alpha < 1, 0 < beta <= alpha, 0 < gamma <= 1 - alpha,
    % 0.8 <= phi <= 0.98, with the initial states started at the heuristic
    % values of Hyndman et al. (2008, sec. 2.6.1) and the smoothing
    % parameters started from a fixed grid (best run kept; no random
    % numbers). The innovation variance is concentrated out of the
    % likelihood. convergence_status comes from the selected run's exit
    % flag and any warning raised during it.
    %
    % forecast re-runs the state recursion from the fitted initial states
    % over fitPayload.training_values, whatever that vector holds, so a
    % caller filters forward with fixed parameters by overwriting it with
    % a longer series that starts at the same t = 1.
    %
    % Forecast variance is analytic for the linear classes (additive
    % error, season N or A; Hyndman et al. 2008, ch. 6, class 1) and comes
    % from a seeded simulation for every class with a multiplicative
    % component. The simulation uses its own RandStream; the caller's
    % global stream is never drawn from.

    properties (Constant, Hidden)
        AdapterId = "analytical.ets"
        DefaultSeasonPeriod = 12
        DefaultSimulationPathCount = 2000
        DefaultSimulationSeed = 20080101
        SmoothingLowerBound = 1e-4
        SmoothingUpperBound = 0.9999
        PhiLowerBound = 0.8
        PhiUpperBound = 0.98
        MultiplicativeSeasonFloor = 1e-3
        BoundActiveTolerance = 1e-5
    end

    methods

        function obj = AnalyticalEtsAdapter(modelConfig)
            obj@gdss.DynamicModelAdapter(modelConfig);
        end

        function validation = validate(obj, dataContext)

            validation = struct();

            validation.status = "VALID";
            validation.status_reason = "";
            validation.adapter_id = gdss.AnalyticalEtsAdapter.AdapterId;
            validation.backend_id = "analytical";
            validation.backend_version = "v1";

            validation.supported_target_dimension = 1;
            validation.supported_target_transform = "identity";
            validation.supported_forecast_strategy = "recursive";
            validation.supported_distribution_kinds = ["normal"; "empirical_simulation"];

            validation.required_covariates = false;
            validation.required_minimum_training_observations = 10;
            validation.warnings = strings(0, 1);

            if ~isfield(dataContext, "target_dimension") || ...
                    dataContext.target_dimension ~= 1
                validation.status = "INVALID_CONFIGURATION";
                validation.status_reason = ...
                    "ETS adapter requires a univariate target.";
                return
            end

            if ~isfield(obj.ModelConfig, "target_transform") || ...
                    string(obj.ModelConfig.target_transform) ~= "identity"
                validation.status = "UNSUPPORTED_TARGET_TRANSFORM";
                validation.status_reason = ...
                    "ETS adapter v1 supports identity target transform only.";
                return
            end

            if ~isfield(obj.ModelConfig, "forecast_strategy") || ...
                    string(obj.ModelConfig.forecast_strategy) ~= "recursive"
                validation.status = "UNSUPPORTED_FORECAST_STRATEGY";
                validation.status_reason = ...
                    "ETS adapter v1 supports recursive forecasting only.";
                return
            end

            [spec, problem] = etsSpecification(obj.ModelConfig);

            if problem ~= ""
                validation.status = "INVALID_CONFIGURATION";
                validation.status_reason = problem;
                return
            end

            if isempty(which("fmincon"))
                validation.status = "INVALID_CONFIGURATION";
                validation.status_reason = ...
                    "ETS adapter requires fmincon (Optimization Toolbox).";
                return
            end

            validation.backend_model_class = spec.model_class;
            validation.required_minimum_training_observations = ...
                spec.minimum_training_observations;

            if spec.requires_positive_data
                [known, allPositive] = dataContextPositivity(dataContext);
                if known && ~allPositive
                    validation.status = "INVALID_CONFIGURATION";
                    validation.status_reason = spec.model_class + ...
                        " has a multiplicative component and requires " + ...
                        "strictly positive training values.";
                    return
                end
                if ~known
                    validation.warnings(end + 1, 1) = ...
                        "Positivity of the training values is not in " + ...
                        "dataContext; fit enforces it.";
                end
            end

            if ~isfield(dataContext, "training_observation_count") || ...
                    dataContext.training_observation_count < ...
                    spec.minimum_training_observations
                validation.status = "INSUFFICIENT_TRAINING_DATA";
                validation.status_reason = spec.model_class + ...
                    " requires at least " + ...
                    string(spec.minimum_training_observations) + ...
                    " training observations.";
            end

        end

        function fitPayload = fit(obj, trainingData, fitContext)

            assert(isfield(trainingData, "target_values"), ...
                "trainingData.target_values is required.");

            y = trainingData.target_values(:);

            assert(isnumeric(y) && ~isempty(y), ...
                "trainingData.target_values must be a nonempty numeric vector.");

            y = double(y);

            assert(all(isfinite(y)), ...
                "ETS adapter requires finite training values.");

            [spec, problem] = etsSpecification(obj.ModelConfig);

            assert(problem == "", "gdss:AnalyticalEtsAdapter:InvalidConfiguration", ...
                "%s", problem);

            if spec.requires_positive_data && any(y <= 0)
                error("gdss:AnalyticalEtsAdapter:NonpositiveData", ...
                    "%s has a multiplicative component and requires " + ...
                    "strictly positive training values.", spec.model_class);
            end

            assert(numel(y) >= spec.minimum_training_observations, ...
                "gdss:AnalyticalEtsAdapter:InsufficientTrainingData", ...
                "%s requires at least %d training observations.", ...
                spec.model_class, spec.minimum_training_observations);

            fitTimer = tic;

            layout = optimizerLayout(spec, y);

            objective = @(x) etsObjective(x, y, layout);

            options = optimoptions("fmincon", ...
                "Algorithm", "sqp", ...
                "Display", "off", ...
                "MaxIterations", 2000, ...
                "MaxFunctionEvaluations", 40000, ...
                "OptimalityTolerance", 1e-8, ...
                "StepTolerance", 1e-12, ...
                "ConstraintTolerance", 1e-10);

            % The ETS likelihood is multimodal (a slope smoothing pinned at
            % its lower bound is a common local optimum), so fmincon runs
            % from a fixed grid of smoothing starts and keeps the best run.
            % The grid is deterministic: no random numbers are drawn.
            starts = smoothingStarts(layout);
            startCount = size(starts, 2);

            startObjective = nan(startCount, 1);
            startExitFlag = nan(startCount, 1);
            startWarningId = strings(startCount, 1);
            startWarningMessage = strings(startCount, 1);
            startX = cell(startCount, 1);
            startOutput = cell(startCount, 1);

            [previousWarningMessage, previousWarningId] = lastwarn;

            for s = 1:startCount
                x0 = layout.x0;
                x0(1:layout.smoothing_count) = starts(:, s);

                lastwarn("", "");

                [startX{s}, startObjective(s), startExitFlag(s), startOutput{s}] = ...
                    fmincon(objective, x0, layout.Aineq, layout.bineq, ...
                    layout.Aeq, layout.beq, layout.lb, layout.ub, [], options);

                [runWarningMessage, runWarningId] = lastwarn;
                startWarningId(s) = string(runWarningId);
                startWarningMessage(s) = string(runWarningMessage);
            end

            candidate = isfinite(startObjective) & startExitFlag >= 0;
            if ~any(candidate)
                candidate = isfinite(startObjective);
            end
            if ~any(candidate)
                candidate = true(startCount, 1);
            end

            rankedObjective = startObjective;
            rankedObjective(~candidate | isnan(rankedObjective)) = Inf;
            [~, selected] = min(rankedObjective);

            xHat = startX{selected};
            objectiveValue = startObjective(selected);
            exitFlag = startExitFlag(selected);
            optimizerOutput = startOutput{selected};
            warningId = startWarningId(selected);
            warningMessage = startWarningMessage(selected);
            optimizerWarned = strlength(warningMessage) > 0;

            if ~any(strlength(startWarningMessage) > 0)
                lastwarn(previousWarningMessage, previousWarningId);
            end

            params = unpackParameters(xHat, layout);

            [mu, finalState] = etsFilter(y, params, spec);
            [~, sigma2, logLikelihood] = etsLikelihood(y, mu, spec);

            params.innovation_variance = sigma2;

            fitPayload = struct();

            optimizerMessage = firstLine(string(optimizerOutput.message));

            [convergenceStatus, convergenceMessage] = convergenceFromOptimizer( ...
                exitFlag, optimizerMessage, optimizerWarned, ...
                string(warningId), string(warningMessage));

            if exitFlag < 0 || ~isfinite(logLikelihood) || ...
                    ~isfinite(objectiveValue)
                fitPayload.status = "FAILED";
                fitPayload.status_reason = "fmincon exit flag " + ...
                    string(exitFlag) + ": " + optimizerMessage;
            else
                fitPayload.status = "COMPLETE";
                fitPayload.status_reason = "";
            end

            fitPayload.backend_id = "analytical";
            fitPayload.backend_version = "v1";
            fitPayload.backend_model_class = spec.model_class;
            fitPayload.backend_optimizer = "fmincon.sqp";
            fitPayload.backend_optimizer_version = version;

            fitPayload.model_artifact_reference = "";
            fitPayload.model_artifact_sha256 = "";
            fitPayload.model_artifact_format = "NOT_REQUIRED";

            boundActive = activeBounds(xHat, layout);

            [naturalValue, naturalName, naturalRole, naturalConstraint, ...
                naturalEstimationScale, optimizerScaleValue] = ...
                parameterColumns(params, xHat, layout, spec);

            fitPayload.parameter_table = table( ...
                naturalName, ...
                naturalRole, ...
                naturalValue, ...
                repmat("natural", numel(naturalName), 1), ...
                naturalConstraint, ...
                naturalEstimationScale, ...
                optimizerScaleValue, ...
                boundActive, ...
                'VariableNames', { ...
                'parameter_name', ...
                'parameter_role', ...
                'estimated_value', ...
                'natural_scale', ...
                'constraint', ...
                'estimation_scale', ...
                'optimizer_scale_value', ...
                'at_bound'});

            fitPayload.fixed_parameter_table = table();

            % Smoothing parameters on a bound are held fixed for the
            % Hessian; their rows and columns of the covariance are NaN.
            [parameterCovariance, hessianStatus] = naturalCovariance( ...
                y, params, spec, smoothingAtBound(xHat, layout));

            fitPayload.parameter_covariance = parameterCovariance;
            fitPayload.parameter_covariance_scale = "natural";

            if hessianStatus ~= "POSITIVE_DEFINITE"
                fitPayload.parameter_covariance_status = "NOT_AVAILABLE";
                fitPayload.parameter_standard_error = ...
                    nan(numel(naturalName), 1);
                fitPayload.parameter_standard_error_status = "NOT_AVAILABLE";
            else
                if any(boundActive) || convergenceStatus ~= "CONVERGED"
                    reliability = "UNRELIABLE";
                else
                    reliability = "AVAILABLE";
                end
                fitPayload.parameter_covariance_status = reliability;
                fitPayload.parameter_standard_error = ...
                    sqrt(diag(parameterCovariance));
                fitPayload.parameter_standard_error_status = reliability;
            end

            fitPayload.parameter_covariance_method = ...
                "inverse_numerical_hessian_of_loglikelihood_" + ...
                lower(hessianStatus);

            fitPayload.parameter_covariance_reference = "";
            fitPayload.parameter_standard_error_reference = "";

            fitPayload.predictive_context_kind = ...
                "ets_state_recursion_from_fitted_initial_states";

            fitPayload.predictive_context_reference = "";
            fitPayload.state_at_origin = finalState;
            fitPayload.state_at_origin_layout = stateLayout(spec);
            fitPayload.state_covariance_at_origin_reference = "";

            fitPayload.lag_buffer_at_origin_reference = "";
            fitPayload.feature_context_reference = "";
            fitPayload.neural_context_reference = "";
            fitPayload.regime_context_reference = "";
            fitPayload.particle_context_reference = "";

            parameterCount = spec.free_parameter_count;
            observationCount = numel(y);

            fitPayload.log_likelihood = logLikelihood;
            fitPayload.aic = -2 * logLikelihood + 2 * parameterCount;
            if observationCount - parameterCount - 1 > 0
                fitPayload.aicc = fitPayload.aic + ...
                    2 * parameterCount * (parameterCount + 1) / ...
                    (observationCount - parameterCount - 1);
            else
                fitPayload.aicc = NaN;
            end
            fitPayload.bic = -2 * logLikelihood + ...
                log(observationCount) * parameterCount;
            fitPayload.objective_value = objectiveValue;
            fitPayload.objective_definition = ...
                "log(mean(e.^2)) + 2*mean(log(abs(k))), k = 1 or one-step mean";

            fitPayload.convergence_status = convergenceStatus;
            fitPayload.convergence_message = convergenceMessage;
            fitPayload.optimizer_exit_flag = exitFlag;
            fitPayload.optimizer_warning_id = string(warningId);
            fitPayload.optimizer_warning_message = string(warningMessage);
            fitPayload.iterations = optimizerOutput.iterations;
            fitPayload.function_evaluations = optimizerOutput.funcCount;
            fitPayload.runtime_seconds = toc(fitTimer);

            fitPayload.optimizer_start_count = startCount;
            fitPayload.optimizer_selected_start = selected;
            fitPayload.optimizer_start_smoothing_values = starts;
            fitPayload.optimizer_start_objective_values = startObjective;
            fitPayload.optimizer_start_exit_flags = startExitFlag;
            fitPayload.optimizer_start_warning_ids = startWarningId;
            fitPayload.optimizer_total_function_evaluations = ...
                sum(cellfun(@(o) o.funcCount, startOutput));

            fitPayload.estimation_output = optimizerOutput;

            fitPayload.in_sample_fitted_values_reference = "";
            fitPayload.in_sample_residuals_reference = "";
            fitPayload.in_sample_innovation_residuals_reference = "";
            fitPayload.in_sample_diagnostics_reference = "";

            fitPayload.fitted_value_information_scope = ...
                "one_step_ahead_state_recursion";

            fitPayload.fit_context = fitContext;
            fitPayload.ets_parameters = params;
            fitPayload.training_values = y;

        end

        function forecastPayload = forecast(obj, fitPayload, forecastContext)

            assert(isfield(fitPayload, "ets_parameters"), ...
                "fitPayload.ets_parameters is required.");

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
                "ETS adapter v1 requires contiguous horizons 1:N.");

            params = fitPayload.ets_parameters;
            spec = specificationFromParameters(params);

            y = double(fitPayload.training_values(:));

            assert(~isempty(y) && all(isfinite(y)), ...
                "fitPayload.training_values must be a nonempty finite vector.");

            if spec.requires_positive_data && any(y <= 0)
                error("gdss:AnalyticalEtsAdapter:NonpositiveData", ...
                    "%s has a multiplicative component and requires " + ...
                    "strictly positive training values.", spec.model_class);
            end

            [~, originState] = etsFilter(y, params, spec);

            maxHorizon = max(horizon);
            originCount = numel(y);

            pointForecast = pointForecastFromState( ...
                originState, params, spec, originCount, maxHorizon);

            intervalLevels = intervalLevelsFrom(obj.ModelConfig);
            levelCount = numel(intervalLevels);

            if spec.is_linear
                forecastVariance = linearForecastVariance(params, spec, maxHorizon);
                forecastStandardDeviation = sqrt(forecastVariance);

                z = norminv((1 + intervalLevels) ./ 2);
                intervalLower = pointForecast - forecastStandardDeviation .* z;
                intervalUpper = pointForecast + forecastStandardDeviation .* z;

                distributionFamily = "normal";
                distributionMethod = "ets_class1_analytic_variance";
                intervalMethod = "normal_quantile";
                simulationPathCount = 0;
                simulationSeed = NaN;
            else
                simulationPathCount = optionalPositiveInteger(obj.ModelConfig, ...
                    "simulation_path_count", ...
                    gdss.AnalyticalEtsAdapter.DefaultSimulationPathCount);
                simulationSeed = optionalNonnegativeInteger(obj.ModelConfig, ...
                    "simulation_seed", ...
                    gdss.AnalyticalEtsAdapter.DefaultSimulationSeed);

                samplePaths = simulateForecastPaths(originState, params, spec, ...
                    originCount, maxHorizon, simulationPathCount, simulationSeed);

                forecastVariance = var(samplePaths, 1, 2);
                forecastStandardDeviation = sqrt(forecastVariance);

                intervalLower = nan(maxHorizon, levelCount);
                intervalUpper = nan(maxHorizon, levelCount);
                for j = 1:levelCount
                    intervalLower(:, j) = quantile(samplePaths, ...
                        (1 - intervalLevels(j)) / 2, 2);
                    intervalUpper(:, j) = quantile(samplePaths, ...
                        (1 + intervalLevels(j)) / 2, 2);
                end

                distributionFamily = "empirical_simulation";
                distributionMethod = "ets_seeded_simulation_" + ...
                    string(simulationPathCount) + "_paths";
                intervalMethod = "simulation_quantile";
            end

            forecastPayload = struct();

            forecastPayload.status = "COMPLETE";
            forecastPayload.status_reason = "";

            forecastPayload.horizon = horizon;
            forecastPayload.point_forecast = pointForecast(horizon);
            forecastPayload.point_forecast_status = ...
                repmat("AVAILABLE", numel(horizon), 1);

            forecastPayload.point_forecast_scale = ...
                repmat(forecastScaleFrom(obj.ModelConfig), numel(horizon), 1);

            forecastPayload.point_forecast_method = ...
                repmat("ets_state_recursion_zero_future_innovations", ...
                numel(horizon), 1);

            forecastPayload.forecast_distribution_status = ...
                repmat("AVAILABLE", numel(horizon), 1);

            forecastPayload.forecast_distribution_family = ...
                repmat(distributionFamily, numel(horizon), 1);

            forecastPayload.forecast_distribution_method = ...
                repmat(distributionMethod, numel(horizon), 1);

            forecastPayload.forecast_variance = forecastVariance(horizon);
            forecastPayload.forecast_standard_deviation = ...
                forecastStandardDeviation(horizon);

            forecastPayload.distribution_parameter_reference = ...
                repmat("", numel(horizon), 1);

            forecastPayload.forecast_sample_artifact_reference = ...
                repmat("", numel(horizon), 1);

            if levelCount > 0
                intervalStatus = "AVAILABLE";
            else
                intervalStatus = "NOT_AVAILABLE";
                intervalMethod = "not_requested";
            end

            forecastPayload.prediction_interval_status = ...
                repmat(intervalStatus, numel(horizon), 1);

            forecastPayload.prediction_interval_method = ...
                repmat(intervalMethod, numel(horizon), 1);

            forecastPayload.prediction_interval_levels = intervalLevels;
            forecastPayload.interval_lower = intervalLower(horizon, :);
            forecastPayload.interval_upper = intervalUpper(horizon, :);

            forecastPayload.simulation_path_count = simulationPathCount;
            forecastPayload.simulation_seed = simulationSeed;
            forecastPayload.filtered_observation_count = originCount;
            forecastPayload.state_at_forecast_origin = originState;

        end

    end

end

% ---------------------------------------------------------------------
% Specification
% ---------------------------------------------------------------------

function [spec, problem] = etsSpecification(modelConfig)

spec = struct();
problem = "";

required = ["ets_error", "ets_trend", "ets_season"];
for name = required
    if ~isfield(modelConfig, name)
        problem = "ETS adapter requires modelConfig." + name + ".";
        return
    end
end

errorType = string(modelConfig.ets_error);
trendType = string(modelConfig.ets_trend);
seasonType = string(modelConfig.ets_season);

if ~isscalar(errorType) || ~ismember(errorType, ["A", "M"])
    problem = "modelConfig.ets_error must be ""A"" or ""M"".";
    return
end

if ~isscalar(trendType) || ~ismember(trendType, ["N", "A", "Ad"])
    problem = "modelConfig.ets_trend must be ""N"", ""A"" or ""Ad"".";
    return
end

if ~isscalar(seasonType) || ~ismember(seasonType, ["N", "A", "M"])
    problem = "modelConfig.ets_season must be ""N"", ""A"" or ""M"".";
    return
end

if seasonType == "N"
    seasonPeriod = 1;
else
    if isfield(modelConfig, "season_period") && ~isempty(modelConfig.season_period)
        seasonPeriod = modelConfig.season_period;
    else
        seasonPeriod = gdss.AnalyticalEtsAdapter.DefaultSeasonPeriod;
    end
    if ~(isnumeric(seasonPeriod) && isscalar(seasonPeriod) && ...
            isfinite(seasonPeriod) && seasonPeriod == floor(seasonPeriod) && ...
            seasonPeriod >= 2)
        problem = "modelConfig.season_period must be one integer >= 2.";
        return
    end
    seasonPeriod = double(seasonPeriod);
end

if isfield(modelConfig, "prediction_interval_levels")
    levels = modelConfig.prediction_interval_levels;
    if ~isempty(levels) && ~(isnumeric(levels) && all(isfinite(levels(:))) && ...
            all(levels(:) > 0) && all(levels(:) < 1))
        problem = "modelConfig.prediction_interval_levels must lie in (0, 1).";
        return
    end
end

spec = buildSpecification(errorType, trendType, seasonType, seasonPeriod);

end

function spec = specificationFromParameters(params)

spec = buildSpecification(string(params.error_type), string(params.trend_type), ...
    string(params.season_type), double(params.season_period));

end

function spec = buildSpecification(errorType, trendType, seasonType, seasonPeriod)

spec = struct();

spec.error_type = errorType;
spec.trend_type = trendType;
spec.season_type = seasonType;
spec.season_period = seasonPeriod;
spec.model_class = "ETS(" + errorType + "," + trendType + "," + seasonType + ")";

spec.multiplicative_error = errorType == "M";
spec.has_trend = trendType ~= "N";
spec.damped = trendType == "Ad";
spec.has_season = seasonType ~= "N";
spec.multiplicative_season = seasonType == "M";

spec.requires_positive_data = spec.multiplicative_error || spec.multiplicative_season;
spec.is_linear = ~spec.multiplicative_error && ~spec.multiplicative_season;

smoothingCount = 1 + spec.has_trend + spec.has_season + spec.damped;
freeStateCount = 1 + spec.has_trend + spec.has_season * (seasonPeriod - 1);

% Free parameters for the information criteria include the innovation
% variance, as in Hyndman et al. (2008, sec. 7.1).
spec.free_parameter_count = smoothingCount + freeStateCount + 1;

if spec.has_season
    spec.minimum_training_observations = ...
        max(2 * seasonPeriod + 2, spec.free_parameter_count + 4);
else
    spec.minimum_training_observations = ...
        max(10, spec.free_parameter_count + 4);
end

end

function [known, allPositive] = dataContextPositivity(dataContext)

known = false;
allPositive = true;

if isfield(dataContext, "training_minimum_value") && ...
        ~isempty(dataContext.training_minimum_value)
    known = true;
    allPositive = allPositive && double(dataContext.training_minimum_value) > 0;
end

if isfield(dataContext, "training_all_positive") && ...
        ~isempty(dataContext.training_all_positive)
    known = true;
    allPositive = allPositive && logical(dataContext.training_all_positive);
end

for name = ["training_values", "target_values"]
    if isfield(dataContext, name) && isnumeric(dataContext.(name)) && ...
            ~isempty(dataContext.(name))
        known = true;
        allPositive = allPositive && all(dataContext.(name)(:) > 0);
    end
end

end

% ---------------------------------------------------------------------
% State recursion and likelihood
% ---------------------------------------------------------------------

function [mu, finalState] = etsFilter(y, params, spec)
% One-step means mu(t) = E[y(t) | y(1:t-1)] from the initial states at
% t = 0. Given y, the state updates do not depend on the error type:
% writing them with the absolute one-step error e = y - mu gives the
% additive- and multiplicative-error forms of Hyndman et al. (2008,
% Table 2.3) alike.

[alpha, beta, gamma, phi, level, slope, season, m] = recursionScalars(params, spec);

seasonCode = double(spec.has_season) + double(spec.multiplicative_season);

n = numel(y);
mu = zeros(n, 1);

for t = 1:n
    position = mod(t - 1, m) + 1;
    trendPart = level + phi * slope;

    if seasonCode == 0
        mu(t) = trendPart;
        e = y(t) - mu(t);
        level = trendPart + alpha * e;
        slope = phi * slope + beta * e;
    elseif seasonCode == 1
        mu(t) = trendPart + season(position);
        e = y(t) - mu(t);
        level = trendPart + alpha * e;
        slope = phi * slope + beta * e;
        season(position) = season(position) + gamma * e;
    else
        seasonValue = season(position);
        mu(t) = trendPart * seasonValue;
        e = y(t) - mu(t);
        level = trendPart + alpha * e / seasonValue;
        slope = phi * slope + beta * e / seasonValue;
        season(position) = seasonValue + gamma * e / trendPart;
    end
end

finalState = struct( ...
    "level", level, ...
    "slope", slope, ...
    "season_by_position", season(:), ...
    "observation_count", n);

end

function [alpha, beta, gamma, phi, level, slope, season, m] = ...
    recursionScalars(params, spec)

alpha = params.alpha;

if spec.has_trend
    beta = params.beta;
    slope = params.initial_slope;
    if spec.damped
        phi = params.phi;
    else
        phi = 1;
    end
else
    beta = 0;
    slope = 0;
    phi = 0;
end

if spec.has_season
    gamma = params.gamma;
    season = params.initial_season(:);
    m = spec.season_period;
else
    gamma = 0;
    season = 0;
    m = 1;
end

level = params.initial_level;

end

function [scaledErrors, sigma2, logLikelihood] = etsLikelihood(y, mu, spec)

n = numel(y);

if spec.multiplicative_error
    scaledErrors = (y - mu) ./ mu;
    logScale = sum(log(abs(mu)));
else
    scaledErrors = y - mu;
    logScale = 0;
end

sigma2 = mean(scaledErrors .^ 2);
logLikelihood = -0.5 * n * (log(2 * pi * sigma2) + 1) - logScale;

if ~isfinite(logLikelihood) || ~isreal(logLikelihood)
    logLikelihood = -Inf;
end

end

function f = etsObjective(x, y, layout)

params = unpackParameters(x, layout);
spec = layout.spec;

mu = etsFilter(y, params, spec);

if ~all(isfinite(mu)) || (spec.requires_positive_data && any(mu <= 0))
    f = Inf;
    return
end

if spec.multiplicative_error
    e = (y - mu) ./ mu;
    f = log(mean(e .^ 2)) + 2 * mean(log(mu));
else
    f = log(mean((y - mu) .^ 2));
end

if ~isfinite(f) || ~isreal(f)
    f = Inf;
end

end

% ---------------------------------------------------------------------
% Optimizer layout: smoothing parameters on their natural scale, initial
% states centred on the heuristic values and divided by a data scale.
% ---------------------------------------------------------------------

function layout = optimizerLayout(spec, y)

lowerS = gdss.AnalyticalEtsAdapter.SmoothingLowerBound;
upperS = gdss.AnalyticalEtsAdapter.SmoothingUpperBound;

heuristic = heuristicInitialStates(y, spec);

dataScale = std(y);
if ~(isfinite(dataScale) && dataScale > 0)
    dataScale = max(abs(mean(y)), 1);
end

m = spec.season_period;

layout = struct();
layout.spec = spec;
layout.heuristic = heuristic;
layout.level_scale = dataScale;
layout.slope_scale = dataScale / 10;
if spec.multiplicative_season
    layout.season_scale = 1;
else
    layout.season_scale = dataScale;
end

next = 0;
x0 = zeros(0, 1);
lb = zeros(0, 1);
ub = zeros(0, 1);

% Starting smoothing values follow forecast::ets (Hyndman et al.).
alpha0 = lowerS + 0.2 * (upperS - lowerS) / m;
beta0 = lowerS + 0.1 * (alpha0 - lowerS);
gamma0 = lowerS + 0.05 * (1 - alpha0 - lowerS);
phi0 = gdss.AnalyticalEtsAdapter.PhiLowerBound + 0.99 * ...
    (gdss.AnalyticalEtsAdapter.PhiUpperBound - gdss.AnalyticalEtsAdapter.PhiLowerBound);

next = next + 1; layout.iAlpha = next;
x0(next, 1) = alpha0; lb(next, 1) = lowerS; ub(next, 1) = upperS;

layout.iBeta = [];
if spec.has_trend
    next = next + 1; layout.iBeta = next;
    x0(next, 1) = beta0; lb(next, 1) = lowerS; ub(next, 1) = upperS;
end

layout.iGamma = [];
if spec.has_season
    next = next + 1; layout.iGamma = next;
    x0(next, 1) = gamma0; lb(next, 1) = lowerS; ub(next, 1) = upperS;
end

layout.iPhi = [];
if spec.damped
    next = next + 1; layout.iPhi = next;
    x0(next, 1) = phi0;
    lb(next, 1) = gdss.AnalyticalEtsAdapter.PhiLowerBound;
    ub(next, 1) = gdss.AnalyticalEtsAdapter.PhiUpperBound;
end

layout.smoothing_count = next;

next = next + 1; layout.iLevel = next;
x0(next, 1) = 0; lb(next, 1) = -Inf; ub(next, 1) = Inf;

layout.iSlope = [];
if spec.has_trend
    next = next + 1; layout.iSlope = next;
    x0(next, 1) = 0; lb(next, 1) = -Inf; ub(next, 1) = Inf;
end

layout.iSeason = [];
if spec.has_season
    layout.iSeason = (next + 1):(next + m);
    next = next + m;
    x0(layout.iSeason, 1) = 0;
    if spec.multiplicative_season
        lb(layout.iSeason, 1) = ...
            gdss.AnalyticalEtsAdapter.MultiplicativeSeasonFloor - heuristic.season(:);
    else
        lb(layout.iSeason, 1) = -Inf;
    end
    ub(layout.iSeason, 1) = Inf;
end

layout.parameter_count = next;
layout.x0 = x0;
layout.lb = lb;
layout.ub = ub;

% Linear inequalities: beta - alpha <= 0, alpha + gamma <= 1.
Aineq = zeros(0, next);
bineq = zeros(0, 1);
if spec.has_trend
    row = zeros(1, next);
    row(layout.iBeta) = 1;
    row(layout.iAlpha) = -1;
    Aineq(end + 1, :) = row;
    bineq(end + 1, 1) = 0;
end
if spec.has_season
    row = zeros(1, next);
    row(layout.iAlpha) = 1;
    row(layout.iGamma) = 1;
    Aineq(end + 1, :) = row;
    bineq(end + 1, 1) = 1;
end
layout.Aineq = Aineq;
layout.bineq = bineq;

% Seasonal normalisation: initial states sum to 0 (A) or to m (M).
if spec.has_season
    Aeq = zeros(1, next);
    Aeq(layout.iSeason) = layout.season_scale;
    if spec.multiplicative_season
        target = m;
    else
        target = 0;
    end
    layout.Aeq = Aeq;
    layout.beq = target - sum(heuristic.season);
else
    layout.Aeq = [];
    layout.beq = [];
end

end

function params = unpackParameters(x, layout)

spec = layout.spec;
heuristic = layout.heuristic;

params = struct();
params.error_type = spec.error_type;
params.trend_type = spec.trend_type;
params.season_type = spec.season_type;
params.season_period = spec.season_period;
params.model_class = spec.model_class;

params.alpha = x(layout.iAlpha);

if spec.has_trend
    params.beta = x(layout.iBeta);
else
    params.beta = NaN;
end

if spec.has_season
    params.gamma = x(layout.iGamma);
else
    params.gamma = NaN;
end

if spec.damped
    params.phi = x(layout.iPhi);
elseif spec.has_trend
    params.phi = 1;
else
    params.phi = NaN;
end

params.initial_level = heuristic.level + layout.level_scale * x(layout.iLevel);

if spec.has_trend
    params.initial_slope = heuristic.slope + layout.slope_scale * x(layout.iSlope);
else
    params.initial_slope = NaN;
end

if spec.has_season
    params.initial_season = heuristic.season(:) + ...
        layout.season_scale * x(layout.iSeason);
else
    params.initial_season = zeros(0, 1);
end

params.innovation_variance = NaN;

end

function heuristic = heuristicInitialStates(y, spec)
% Hyndman et al. (2008, sec. 2.6.1), as in forecast::ets: classical
% decomposition of the first three seasons (or what there is) for the
% seasonal indices, then a least-squares line through the first
% max(10, 2m) seasonally adjusted values for the level and slope at t = 0.

n = numel(y);
m = spec.season_period;

heuristic = struct("level", NaN, "slope", 0, "season", zeros(0, 1));

if spec.has_season
    span = min(n, 3 * m);
    window = y(1:span);

    if mod(m, 2) == 0
        weights = [0.5; ones(m - 1, 1); 0.5] / m;
    else
        weights = ones(m, 1) / m;
    end
    half = floor(m / 2);

    centredTrend = nan(span, 1);
    for t = (half + 1):(span - half)
        centredTrend(t) = weights' * window((t - half):(t + half));
    end

    if spec.multiplicative_season
        detrended = window ./ centredTrend;
    else
        detrended = window - centredTrend;
    end

    positions = mod((0:span - 1)', m) + 1;
    seasonalFigure = zeros(m, 1);
    for j = 1:m
        seasonalFigure(j) = mean(detrended(positions == j & ~isnan(detrended)));
    end

    if spec.multiplicative_season
        seasonalFigure = seasonalFigure / mean(seasonalFigure);
        adjusted = y ./ max(seasonalFigure(mod((0:n - 1)', m) + 1), 1e-2);
    else
        seasonalFigure = seasonalFigure - mean(seasonalFigure);
        adjusted = y - seasonalFigure(mod((0:n - 1)', m) + 1);
    end

    heuristic.season = seasonalFigure;
    maxn = min(max(10, 2 * m), n);
else
    adjusted = y;
    maxn = min(10, n);
end

if spec.has_trend
    design = [ones(maxn, 1), (1:maxn)'];
    coefficients = design \ adjusted(1:maxn);
    heuristic.level = coefficients(1);
    heuristic.slope = coefficients(2);
    if abs(heuristic.level + heuristic.slope) < 1e-8
        heuristic.level = heuristic.level * (1 + 1e-3);
        heuristic.slope = heuristic.slope * (1 - 1e-3);
    end
else
    heuristic.level = mean(adjusted(1:maxn));
end

end

% ---------------------------------------------------------------------
% Reporting
% ---------------------------------------------------------------------

function [value, name, role, constraint, estimationScale, optimizerValue] = ...
    parameterColumns(params, xHat, layout, spec)

value = zeros(0, 1);
name = strings(0, 1);
role = strings(0, 1);
constraint = strings(0, 1);
estimationScale = strings(0, 1);
optimizerValue = zeros(0, 1);

    function add(v, nm, rl, cn, es, ov)
        value(end + 1, 1) = v;
        name(end + 1, 1) = nm;
        role(end + 1, 1) = rl;
        constraint(end + 1, 1) = cn;
        estimationScale(end + 1, 1) = es;
        optimizerValue(end + 1, 1) = ov;
    end

add(params.alpha, "smoothing_alpha_level", "smoothing_parameter", ...
    "0 < alpha < 1", "natural", xHat(layout.iAlpha));

if spec.has_trend
    add(params.beta, "smoothing_beta_slope", "smoothing_parameter", ...
        "0 < beta <= alpha", "natural", xHat(layout.iBeta));
end

if spec.has_season
    add(params.gamma, "smoothing_gamma_season", "smoothing_parameter", ...
        "0 < gamma <= 1 - alpha", "natural", xHat(layout.iGamma));
end

if spec.damped
    add(params.phi, "damping_phi", "transition_coefficient", ...
        "0.8 <= phi <= 0.98", "natural", xHat(layout.iPhi));
end

add(params.initial_level, "initial_level", "initial_state", ...
    "unconstrained", "centred_scaled_state", xHat(layout.iLevel));

if spec.has_trend
    add(params.initial_slope, "initial_slope", "initial_state", ...
        "unconstrained", "centred_scaled_state", xHat(layout.iSlope));
end

if spec.has_season
    if spec.multiplicative_season
        seasonConstraint = "positive; initial seasonal states sum to m";
    else
        seasonConstraint = "initial seasonal states sum to 0";
    end
    for j = 1:spec.season_period
        add(params.initial_season(j), "initial_season_position_" + string(j), ...
            "initial_state", seasonConstraint, "centred_scaled_state", ...
            xHat(layout.iSeason(j)));
    end
end

add(params.innovation_variance, "innovation_variance", ...
    "innovation_variance", "positive", "concentrated_out", NaN);

end

function active = activeBounds(xHat, layout)
% One flag per parameter_table row; the innovation variance row is last.

tol = gdss.AnalyticalEtsAdapter.BoundActiveTolerance;
spec = layout.spec;

atBox = (xHat - layout.lb) < tol | (layout.ub - xHat) < tol;

if spec.has_trend
    betaRow = layout.iBeta;
    atBox(betaRow) = atBox(betaRow) || ...
        (xHat(layout.iAlpha) - xHat(betaRow)) < tol;
end

if spec.has_season
    gammaRow = layout.iGamma;
    linearActive = (1 - xHat(layout.iAlpha) - xHat(gammaRow)) < tol;
    atBox(gammaRow) = atBox(gammaRow) || linearActive;
    atBox(layout.iAlpha) = atBox(layout.iAlpha) || linearActive;
end

active = [atBox(:); false];

end

function layoutNames = stateLayout(spec)

layoutNames = "level";
if spec.has_trend
    layoutNames(end + 1, 1) = "slope";
end
if spec.has_season
    layoutNames(end + 1, 1) = "season_by_position (position = mod(t - 1, m) + 1)";
end

end

function [statusValue, message] = convergenceFromOptimizer( ...
    exitFlag, optimizerMessage, warned, warningId, warningMessage)

if exitFlag > 0
    if warned
        statusValue = "CONVERGED_WITH_WARNINGS";
    else
        statusValue = "CONVERGED";
    end
elseif exitFlag == 0
    statusValue = "ITERATION_LIMIT_REACHED";
elseif exitFlag == -2
    statusValue = "NO_FEASIBLE_POINT";
else
    statusValue = "FAILED";
end

message = "fmincon exit flag " + string(exitFlag) + ": " + optimizerMessage;

if warned
    message = message + " | warning " + warningId + ": " + ...
        firstLine(warningMessage);
end

end

function line = firstLine(text)

text = strtrim(text);
parts = splitlines(text);
parts = parts(strlength(strtrim(parts)) > 0);

if isempty(parts)
    line = "";
else
    line = strtrim(parts(1));
end

end

% ---------------------------------------------------------------------
% Parameter covariance: inverse of the negated numerical Hessian of the
% full log-likelihood in the natural parameters. The seasonal states are
% differentiated on their normalisation constraint (last position
% implied) and mapped back to all m positions.
% ---------------------------------------------------------------------

function [covariance, statusValue] = naturalCovariance(y, params, spec, heldFixed)

[thetaAll, typicalAll, mappingAll] = reducedNaturalVector(params, spec);

fullCount = size(mappingAll, 1);

free = true(numel(thetaAll), 1);
free(1:numel(heldFixed)) = ~heldFixed(:);

theta = thetaAll(free);
typical = typicalAll(free);
mapping = mappingAll(:, free);
k = numel(theta);

logLik = @(v) fullLogLikelihood(expandFree(v, thetaAll, free), y, params, spec);

step = 1e-4 * max(abs(theta), typical);
f0 = logLik(theta);

hessian = zeros(k);
plusValues = zeros(k, 1);
minusValues = zeros(k, 1);

for i = 1:k
    e = zeros(k, 1); e(i) = step(i);
    plusValues(i) = logLik(theta + e);
    minusValues(i) = logLik(theta - e);
    hessian(i, i) = (plusValues(i) - 2 * f0 + minusValues(i)) / step(i) ^ 2;
end

for i = 1:k
    ei = zeros(k, 1); ei(i) = step(i);
    for j = (i + 1):k
        ej = zeros(k, 1); ej(j) = step(j);
        value = (logLik(theta + ei + ej) - logLik(theta + ei - ej) - ...
            logLik(theta - ei + ej) + logLik(theta - ei - ej)) / ...
            (4 * step(i) * step(j));
        hessian(i, j) = value;
        hessian(j, i) = value;
    end
end

covariance = nan(fullCount);

if ~all(isfinite(hessian), "all") || ~isfinite(f0)
    statusValue = "NOT_FINITE";
    return
end

information = -(hessian + hessian') / 2;
[~, notPositive] = chol(information);

if notPositive
    statusValue = "NOT_POSITIVE_DEFINITE";
    return
end

reducedCovariance = information \ eye(k);
covariance = mapping * reducedCovariance * mapping';
covariance = (covariance + covariance') / 2;

fixedRows = ~any(mapping ~= 0, 2);
covariance(fixedRows, :) = NaN;
covariance(:, fixedRows) = NaN;

statusValue = "POSITIVE_DEFINITE";

end

function theta = expandFree(freeValues, thetaAll, free)

theta = thetaAll;
theta(free) = freeValues;

end

function fixed = smoothingAtBound(xHat, layout)
% One flag per smoothing parameter (alpha, beta, gamma, phi as present):
% on a box bound, or beta on alpha, or gamma on 1 - alpha.

tol = gdss.AnalyticalEtsAdapter.BoundActiveTolerance;
spec = layout.spec;
index = 1:layout.smoothing_count;

fixed = (xHat(index) - layout.lb(index)) < tol | ...
    (layout.ub(index) - xHat(index)) < tol;

if spec.has_trend
    fixed(layout.iBeta) = fixed(layout.iBeta) || ...
        (xHat(layout.iAlpha) - xHat(layout.iBeta)) < tol;
end

if spec.has_season
    fixed(layout.iGamma) = fixed(layout.iGamma) || ...
        (1 - xHat(layout.iAlpha) - xHat(layout.iGamma)) < tol;
end

fixed = fixed(:);

end

function starts = smoothingStarts(layout)
% Columns are starting values for (alpha, beta, gamma, phi) as present.
% The first column is the forecast::ets start; the others cover a high
% alpha and a slope or season smoothing at half its admissible range.

spec = layout.spec;
lowerS = gdss.AnalyticalEtsAdapter.SmoothingLowerBound;

alphaValues = unique([layout.x0(layout.iAlpha), 0.5, 0.9], "stable");

starts = zeros(layout.smoothing_count, 0);

for alpha = alphaValues
    if spec.has_trend
        betaValues = [lowerS + 0.1 * (alpha - lowerS), 0.5 * alpha];
    else
        betaValues = NaN;
    end
    if spec.has_season
        gammaValues = [lowerS + 0.05 * (1 - alpha - lowerS), 0.5 * (1 - alpha)];
    else
        gammaValues = NaN;
    end
    for beta = betaValues
        for gamma = gammaValues
            column = alpha;
            if spec.has_trend
                column(end + 1, 1) = beta; %#ok<AGROW>
            end
            if spec.has_season
                column(end + 1, 1) = gamma; %#ok<AGROW>
            end
            if spec.damped
                column(end + 1, 1) = layout.x0(layout.iPhi); %#ok<AGROW>
            end
            starts(:, end + 1) = column; %#ok<AGROW>
        end
    end
end

end

function [theta, typical, mapping] = reducedNaturalVector(params, spec)
% Order matches parameter_table: alpha, beta, gamma, phi, level, slope,
% season positions 1..m (m-th implied in the reduced vector), variance.

theta = params.alpha;
typical = 0.1;

if spec.has_trend
    theta(end + 1, 1) = params.beta;
    typical(end + 1, 1) = 0.1;
end
if spec.has_season
    theta(end + 1, 1) = params.gamma;
    typical(end + 1, 1) = 0.1;
end
if spec.damped
    theta(end + 1, 1) = params.phi;
    typical(end + 1, 1) = 0.1;
end

stateScale = max(abs(params.initial_level), 1);

theta(end + 1, 1) = params.initial_level;
typical(end + 1, 1) = stateScale;

if spec.has_trend
    theta(end + 1, 1) = params.initial_slope;
    typical(end + 1, 1) = stateScale / 100;
end

leadingCount = numel(theta);
m = spec.season_period;

if spec.has_season
    theta = [theta; params.initial_season(1:m - 1)];
    if spec.multiplicative_season
        typical = [typical; ones(m - 1, 1)];
    else
        typical = [typical; repmat(stateScale / 100, m - 1, 1)];
    end
end

theta(end + 1, 1) = params.innovation_variance;
typical(end + 1, 1) = params.innovation_variance;

reducedCount = numel(theta);

if spec.has_season
    fullCount = reducedCount + 1;
    mapping = zeros(fullCount, reducedCount);
    mapping(1:leadingCount, 1:leadingCount) = eye(leadingCount);
    seasonRows = leadingCount + (1:m);
    seasonColumns = leadingCount + (1:m - 1);
    mapping(seasonRows(1:m - 1), seasonColumns) = eye(m - 1);
    mapping(seasonRows(m), seasonColumns) = -1;
    mapping(fullCount, reducedCount) = 1;
else
    mapping = eye(reducedCount);
end

end

function value = fullLogLikelihood(theta, y, params, spec)

cursor = 1;
params.alpha = theta(cursor);

if spec.has_trend
    cursor = cursor + 1; params.beta = theta(cursor);
end
if spec.has_season
    cursor = cursor + 1; params.gamma = theta(cursor);
end
if spec.damped
    cursor = cursor + 1; params.phi = theta(cursor);
end

cursor = cursor + 1; params.initial_level = theta(cursor);

if spec.has_trend
    cursor = cursor + 1; params.initial_slope = theta(cursor);
end

if spec.has_season
    m = spec.season_period;
    free = theta(cursor + (1:m - 1));
    cursor = cursor + m - 1;
    if spec.multiplicative_season
        params.initial_season = [free; m - sum(free)];
    else
        params.initial_season = [free; -sum(free)];
    end
end

sigma2 = theta(cursor + 1);

mu = etsFilter(y, params, spec);

if sigma2 <= 0 || ~all(isfinite(mu)) || ...
        (spec.requires_positive_data && any(mu <= 0))
    value = NaN;
    return
end

n = numel(y);

if spec.multiplicative_error
    e = (y - mu) ./ mu;
    logScale = sum(log(mu));
else
    e = y - mu;
    logScale = 0;
end

value = -0.5 * n * log(2 * pi * sigma2) - sum(e .^ 2) / (2 * sigma2) - logScale;

end

% ---------------------------------------------------------------------
% Forecasting
% ---------------------------------------------------------------------

function pointForecast = pointForecastFromState(state, params, spec, originCount, maxHorizon)

[~, ~, ~, phi, ~, ~, ~, m] = recursionScalars(params, spec);

pointForecast = zeros(maxHorizon, 1);
dampedSum = 0;

for h = 1:maxHorizon
    dampedSum = dampedSum + phi ^ h;
    trendPart = state.level + dampedSum * state.slope;
    if ~spec.has_trend
        trendPart = state.level;
    end
    position = mod(originCount + h - 1, m) + 1;
    if ~spec.has_season
        pointForecast(h) = trendPart;
    elseif spec.multiplicative_season
        pointForecast(h) = trendPart * state.season_by_position(position);
    else
        pointForecast(h) = trendPart + state.season_by_position(position);
    end
end

end

function forecastVariance = linearForecastVariance(params, spec, maxHorizon)
% Class 1 of Hyndman et al. (2008, ch. 6): v_h = sigma^2 (1 + sum_{j=1}^{h-1}
% c_j^2) with c_j = alpha + beta * phi_j + gamma * [j mod m == 0] and
% phi_j = phi + ... + phi^j (phi = 1 for an undamped trend).

[alpha, beta, gamma, phi, ~, ~, ~, m] = recursionScalars(params, spec);

c = zeros(max(maxHorizon - 1, 0), 1);
dampedSum = 0;

for j = 1:(maxHorizon - 1)
    dampedSum = dampedSum + phi ^ j;
    c(j) = alpha + beta * dampedSum * spec.has_trend + ...
        gamma * spec.has_season * (mod(j, m) == 0);
end

forecastVariance = params.innovation_variance * (1 + [0; cumsum(c .^ 2)]);
forecastVariance = forecastVariance(1:maxHorizon);

end

function paths = simulateForecastPaths(state, params, spec, originCount, ...
    maxHorizon, pathCount, seed)

stream = RandStream("mt19937ar", "Seed", seed);

[alpha, beta, gamma, phi, ~, ~, ~, m] = recursionScalars(params, spec);
sigma = sqrt(params.innovation_variance);

level = repmat(state.level, 1, pathCount);
slope = repmat(state.slope * spec.has_trend, 1, pathCount);
season = repmat(state.season_by_position(:), 1, pathCount);

paths = zeros(maxHorizon, pathCount);

for h = 1:maxHorizon
    position = mod(originCount + h - 1, m) + 1;
    trendPart = level + phi * slope;

    if ~spec.has_season
        mu = trendPart;
    elseif spec.multiplicative_season
        mu = trendPart .* season(position, :);
    else
        mu = trendPart + season(position, :);
    end

    innovation = sigma * randn(stream, 1, pathCount);

    if spec.multiplicative_error
        draw = mu .* (1 + innovation);
    else
        draw = mu + innovation;
    end

    e = draw - mu;

    if spec.multiplicative_season
        seasonValue = season(position, :);
        level = trendPart + alpha * e ./ seasonValue;
        slope = phi * slope + beta * e ./ seasonValue;
        season(position, :) = seasonValue + gamma * e ./ trendPart;
    else
        level = trendPart + alpha * e;
        slope = phi * slope + beta * e;
        if spec.has_season
            season(position, :) = season(position, :) + gamma * e;
        end
    end

    paths(h, :) = draw;
end

end

function levels = intervalLevelsFrom(modelConfig)

if isfield(modelConfig, "prediction_interval_levels")
    levels = double(modelConfig.prediction_interval_levels(:))';
else
    levels = zeros(1, 0);
end

end

function scale = forecastScaleFrom(modelConfig)

if isfield(modelConfig, "forecast_scale")
    scale = string(modelConfig.forecast_scale);
else
    scale = "LEVEL";
end

end

function value = optionalPositiveInteger(modelConfig, name, default)

value = default;
if isfield(modelConfig, name) && ~isempty(modelConfig.(name))
    value = double(modelConfig.(name));
    assert(isscalar(value) && isfinite(value) && value >= 1 && ...
        value == floor(value), "modelConfig.%s must be a positive integer.", name);
end

end

function value = optionalNonnegativeInteger(modelConfig, name, default)

value = default;
if isfield(modelConfig, name) && ~isempty(modelConfig.(name))
    value = double(modelConfig.(name));
    assert(isscalar(value) && isfinite(value) && value >= 0 && ...
        value == floor(value), "modelConfig.%s must be a nonnegative integer.", name);
end

end
