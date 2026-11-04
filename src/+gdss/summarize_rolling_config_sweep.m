function summaryTable = summarize_rolling_config_sweep(rollingSweepRun)

arguments
    rollingSweepRun (1,1) struct
end

assert(isfield(rollingSweepRun, "origin_results"), ...
    "rollingSweepRun.origin_results is required.");

assert(isfield(rollingSweepRun, "model_configs"), ...
    "rollingSweepRun.model_configs is required.");

originResults = rollingSweepRun.origin_results;
modelConfigs = rollingSweepRun.model_configs;

assert(isstruct(originResults), ...
    "rollingSweepRun.origin_results must be a struct array.");

assert(isstruct(modelConfigs) && ~isempty(modelConfigs), ...
    "rollingSweepRun.model_configs must be a nonempty struct array.");

modelCount = numel(modelConfigs);
originCount = numel(originResults);

rowCount = modelCount * originCount;

modelId = strings(rowCount, 1);
adapterId = strings(rowCount, 1);
status = strings(rowCount, 1);
statusReason = strings(rowCount, 1);

seriesId = strings(rowCount, 1);
dataVariant = strings(rowCount, 1);
targetTransform = strings(rowCount, 1);

originIndex = nan(rowCount, 1);
originTime = NaT(rowCount, 1);

arimaP = nan(rowCount, 1);
arimaD = nan(rowCount, 1);
arimaQ = nan(rowCount, 1);

backendId = strings(rowCount, 1);
backendVersion = strings(rowCount, 1);
backendModelClass = strings(rowCount, 1);

logLikelihood = nan(rowCount, 1);
aicValue = nan(rowCount, 1);
aiccValue = nan(rowCount, 1);
bicValue = nan(rowCount, 1);

convergenceStatus = strings(rowCount, 1);
covarianceStatus = strings(rowCount, 1);
standardErrorStatus = strings(rowCount, 1);

meanError = nan(rowCount, 1);
meanAbsoluteError = nan(rowCount, 1);
rootMeanSquaredError = nan(rowCount, 1);

minimumError = nan(rowCount, 1);
maximumError = nan(rowCount, 1);

underforecastCount = nan(rowCount, 1);
overforecastCount = nan(rowCount, 1);
exactForecastCount = nan(rowCount, 1);

horizonCount = nan(rowCount, 1);
firstHorizon = nan(rowCount, 1);
lastHorizon = nan(rowCount, 1);

firstTargetTime = NaT(rowCount, 1);
lastTargetTime = NaT(rowCount, 1);

runtimeSeconds = nan(rowCount, 1);

errorIdentifier = strings(rowCount, 1);
errorMessage = strings(rowCount, 1);

rowIndex = 0;

for originPosition = 1:originCount

    currentOriginResult = originResults(originPosition);

    currentOriginIndex = currentOriginResult.origin_index;

    if isfield(currentOriginResult, "sweep_run") && ...
            ~isempty(currentOriginResult.sweep_run) && ...
            isfield(currentOriginResult.sweep_run, "results")

        configResults = currentOriginResult.sweep_run.results;

    else

        configResults = repmat(struct(), modelCount, 1);

    end

    for configIndex = 1:modelCount

        rowIndex = rowIndex + 1;

        currentConfig = modelConfigs(configIndex);

        modelId(rowIndex) = string(currentConfig.model_id);
        adapterId(rowIndex) = string(currentConfig.adapter_id);

        if isfield(currentConfig, "series_id")
            seriesId(rowIndex) = string(currentConfig.series_id);
        end

        if isfield(currentConfig, "data_variant")
            dataVariant(rowIndex) = ...
                string(currentConfig.data_variant);
        end

        if isfield(currentConfig, "target_transform")
            targetTransform(rowIndex) = ...
                string(currentConfig.target_transform);
        end

        originIndex(rowIndex) = currentOriginIndex;

        if isfield(currentConfig, "arima_p")
            arimaP(rowIndex) = currentConfig.arima_p;
        end

        if isfield(currentConfig, "arima_d")
            arimaD(rowIndex) = currentConfig.arima_d;
        end

        if isfield(currentConfig, "arima_q")
            arimaQ(rowIndex) = currentConfig.arima_q;
        end

        if configIndex > numel(configResults) || ...
                isempty(fieldnames(configResults(configIndex)))

            status(rowIndex) = "NOT_AVAILABLE";
            statusReason(rowIndex) = ...
                "No configuration result was recorded for this origin.";
            continue

        end

        currentConfigResult = configResults(configIndex);

        if isfield(currentConfigResult, "status")
            status(rowIndex) = string(currentConfigResult.status);
        else
            status(rowIndex) = "NOT_AVAILABLE";
        end

        if isfield(currentConfigResult, "status_reason")
            statusReason(rowIndex) = ...
                string(currentConfigResult.status_reason);
        end

        if isfield(currentConfigResult, "runtime_seconds")
            runtimeSeconds(rowIndex) = ...
                currentConfigResult.runtime_seconds;
        end

        if isfield(currentConfigResult, "error_identifier")
            errorIdentifier(rowIndex) = ...
                string(currentConfigResult.error_identifier);
        end

        if isfield(currentConfigResult, "error_message")
            errorMessage(rowIndex) = ...
                string(currentConfigResult.error_message);
        end

        if ~isfield(currentConfigResult, "evaluation_run") || ...
                isempty(currentConfigResult.evaluation_run)

            continue

        end

        evaluationRun = currentConfigResult.evaluation_run;

        if isfield(evaluationRun, "origin_time")
            originTime(rowIndex) = evaluationRun.origin_time;
        end

        if isfield(evaluationRun, "backend_id")
            backendId(rowIndex) = string(evaluationRun.backend_id);
        end

        if isfield(evaluationRun, "backend_version")
            backendVersion(rowIndex) = ...
                string(evaluationRun.backend_version);
        end

        if isfield(evaluationRun, "backend_model_class")
            backendModelClass(rowIndex) = ...
                string(evaluationRun.backend_model_class);
        end

        if isfield(evaluationRun, "fit_realization") && ...
                isfield(evaluationRun.fit_realization, "fit_payload")

            fitPayload = evaluationRun.fit_realization.fit_payload;

            if isfield(fitPayload, "log_likelihood")
                logLikelihood(rowIndex) = fitPayload.log_likelihood;
            end

            if isfield(fitPayload, "aic")
                aicValue(rowIndex) = fitPayload.aic;
            end

            if isfield(fitPayload, "aicc")
                aiccValue(rowIndex) = fitPayload.aicc;
            end

            if isfield(fitPayload, "bic")
                bicValue(rowIndex) = fitPayload.bic;
            end

            if isfield(fitPayload, "convergence_status")
                convergenceStatus(rowIndex) = ...
                    string(fitPayload.convergence_status);
            end

            if isfield(fitPayload, "parameter_covariance_status")
                covarianceStatus(rowIndex) = ...
                    string(fitPayload.parameter_covariance_status);
            end

            if isfield(fitPayload, ...
                    "parameter_standard_error_status")

                standardErrorStatus(rowIndex) = ...
                    string(fitPayload.parameter_standard_error_status);
            end

        end

        if isfield(evaluationRun, "forecast_scorecard")

            scorecard = evaluationRun.forecast_scorecard;

            if isfield(scorecard, "mean_error")
                meanError(rowIndex) = scorecard.mean_error;
            end

            if isfield(scorecard, "mean_absolute_error")
                meanAbsoluteError(rowIndex) = ...
                    scorecard.mean_absolute_error;
            end

            if isfield(scorecard, "root_mean_squared_error")
                rootMeanSquaredError(rowIndex) = ...
                    scorecard.root_mean_squared_error;
            end

            if isfield(scorecard, "minimum_error")
                minimumError(rowIndex) = scorecard.minimum_error;
            end

            if isfield(scorecard, "maximum_error")
                maximumError(rowIndex) = scorecard.maximum_error;
            end

            if isfield(scorecard, "underforecast_count")
                underforecastCount(rowIndex) = ...
                    scorecard.underforecast_count;
            end

            if isfield(scorecard, "overforecast_count")
                overforecastCount(rowIndex) = ...
                    scorecard.overforecast_count;
            end

            if isfield(scorecard, "exact_forecast_count")
                exactForecastCount(rowIndex) = ...
                    scorecard.exact_forecast_count;
            end

            if isfield(scorecard, "horizon_count")
                horizonCount(rowIndex) = scorecard.horizon_count;
            end

            if isfield(scorecard, "first_horizon")
                firstHorizon(rowIndex) = scorecard.first_horizon;
            end

            if isfield(scorecard, "last_horizon")
                lastHorizon(rowIndex) = scorecard.last_horizon;
            end

            if isfield(scorecard, "first_target_time")
                firstTargetTime(rowIndex) = ...
                    scorecard.first_target_time;
            end

            if isfield(scorecard, "last_target_time")
                lastTargetTime(rowIndex) = ...
                    scorecard.last_target_time;
            end

        end

    end

end

summaryTable = table( ...
    modelId, ...
    adapterId, ...
    status, ...
    statusReason, ...
    seriesId, ...
    dataVariant, ...
    targetTransform, ...
    originIndex, ...
    originTime, ...
    arimaP, ...
    arimaD, ...
    arimaQ, ...
    backendId, ...
    backendVersion, ...
    backendModelClass, ...
    logLikelihood, ...
    aicValue, ...
    aiccValue, ...
    bicValue, ...
    convergenceStatus, ...
    covarianceStatus, ...
    standardErrorStatus, ...
    meanError, ...
    meanAbsoluteError, ...
    rootMeanSquaredError, ...
    minimumError, ...
    maximumError, ...
    underforecastCount, ...
    overforecastCount, ...
    exactForecastCount, ...
    horizonCount, ...
    firstHorizon, ...
    lastHorizon, ...
    firstTargetTime, ...
    lastTargetTime, ...
    runtimeSeconds, ...
    errorIdentifier, ...
    errorMessage, ...
    'VariableNames', { ...
    'model_id', ...
    'adapter_id', ...
    'status', ...
    'status_reason', ...
    'series_id', ...
    'data_variant', ...
    'target_transform', ...
    'origin_index', ...
    'origin_time', ...
    'arima_p', ...
    'arima_d', ...
    'arima_q', ...
    'backend_id', ...
    'backend_version', ...
    'backend_model_class', ...
    'log_likelihood', ...
    'aic', ...
    'aicc', ...
    'bic', ...
    'convergence_status', ...
    'parameter_covariance_status', ...
    'parameter_standard_error_status', ...
    'mean_error', ...
    'mean_absolute_error', ...
    'root_mean_squared_error', ...
    'minimum_error', ...
    'maximum_error', ...
    'underforecast_count', ...
    'overforecast_count', ...
    'exact_forecast_count', ...
    'horizon_count', ...
    'first_horizon', ...
    'last_horizon', ...
    'first_target_time', ...
    'last_target_time', ...
    'runtime_seconds', ...
    'error_identifier', ...
    'error_message'});

assert(height(summaryTable) == modelCount * originCount, ...
    "Rolling summary row count is inconsistent with model × origin count.");

end