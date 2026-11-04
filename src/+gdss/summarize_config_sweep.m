function summaryTable = summarize_config_sweep(sweepRun)

arguments
    sweepRun (1,1) struct
end

assert(isfield(sweepRun, "results"), ...
    "sweepRun.results is required.");

results = sweepRun.results;

assert(isstruct(results), ...
    "sweepRun.results must be a struct array.");

resultCount = numel(results);

modelId = strings(resultCount, 1);
adapterId = strings(resultCount, 1);
status = strings(resultCount, 1);
statusReason = strings(resultCount, 1);

arimaP = nan(resultCount, 1);
arimaD = nan(resultCount, 1);
arimaQ = nan(resultCount, 1);

logLikelihood = nan(resultCount, 1);
aicValue = nan(resultCount, 1);
bicValue = nan(resultCount, 1);

meanError = nan(resultCount, 1);
meanAbsoluteError = nan(resultCount, 1);
rootMeanSquaredError = nan(resultCount, 1);

underforecastCount = nan(resultCount, 1);
overforecastCount = nan(resultCount, 1);
exactForecastCount = nan(resultCount, 1);

horizonCount = nan(resultCount, 1);
runtimeSeconds = nan(resultCount, 1);

covarianceStatus = strings(resultCount, 1);
standardErrorStatus = strings(resultCount, 1);

errorIdentifier = strings(resultCount, 1);
errorMessage = strings(resultCount, 1);

for resultIndex = 1:resultCount

    currentResult = results(resultIndex);

    modelId(resultIndex) = string(currentResult.model_id);
    adapterId(resultIndex) = string(currentResult.adapter_id);
    status(resultIndex) = string(currentResult.status);
    statusReason(resultIndex) = string(currentResult.status_reason);
    runtimeSeconds(resultIndex) = currentResult.runtime_seconds;

    errorIdentifier(resultIndex) = ...
        string(currentResult.error_identifier);

    errorMessage(resultIndex) = ...
        string(currentResult.error_message);

    if ~isfield(currentResult, "evaluation_run") || ...
            isempty(currentResult.evaluation_run)
        continue
    end

    evaluationRun = currentResult.evaluation_run;

    if isfield(evaluationRun, "fit_realization") && ...
            isfield(evaluationRun.fit_realization, "fit_payload")

        fitPayload = evaluationRun.fit_realization.fit_payload;

        if isfield(fitPayload, "log_likelihood")
            logLikelihood(resultIndex) = fitPayload.log_likelihood;
        end

        if isfield(fitPayload, "aic")
            aicValue(resultIndex) = fitPayload.aic;
        end

        if isfield(fitPayload, "bic")
            bicValue(resultIndex) = fitPayload.bic;
        end

        if isfield(fitPayload, "parameter_covariance_status")
            covarianceStatus(resultIndex) = ...
                string(fitPayload.parameter_covariance_status);
        end

        if isfield(fitPayload, ...
                "parameter_standard_error_status")

            standardErrorStatus(resultIndex) = ...
                string(fitPayload.parameter_standard_error_status);
        end

    end

    if isfield(evaluationRun, "forecast_scorecard")

        scorecard = evaluationRun.forecast_scorecard;

        if isfield(scorecard, "mean_error")
            meanError(resultIndex) = scorecard.mean_error;
        end

        if isfield(scorecard, "mean_absolute_error")
            meanAbsoluteError(resultIndex) = ...
                scorecard.mean_absolute_error;
        end

        if isfield(scorecard, "root_mean_squared_error")
            rootMeanSquaredError(resultIndex) = ...
                scorecard.root_mean_squared_error;
        end

        if isfield(scorecard, "underforecast_count")
            underforecastCount(resultIndex) = ...
                scorecard.underforecast_count;
        end

        if isfield(scorecard, "overforecast_count")
            overforecastCount(resultIndex) = ...
                scorecard.overforecast_count;
        end

        if isfield(scorecard, "exact_forecast_count")
            exactForecastCount(resultIndex) = ...
                scorecard.exact_forecast_count;
        end

        if isfield(scorecard, "horizon_count")
            horizonCount(resultIndex) = scorecard.horizon_count;
        end

    end

    if isfield(sweepRun, "model_configs") && ...
            numel(sweepRun.model_configs) >= resultIndex

        modelConfig = sweepRun.model_configs(resultIndex);

        if isfield(modelConfig, "arima_p")
            arimaP(resultIndex) = modelConfig.arima_p;
        end

        if isfield(modelConfig, "arima_d")
            arimaD(resultIndex) = modelConfig.arima_d;
        end

        if isfield(modelConfig, "arima_q")
            arimaQ(resultIndex) = modelConfig.arima_q;
        end

    end

end

summaryTable = table( ...
    modelId, ...
    adapterId, ...
    status, ...
    statusReason, ...
    arimaP, ...
    arimaD, ...
    arimaQ, ...
    logLikelihood, ...
    aicValue, ...
    bicValue, ...
    meanError, ...
    meanAbsoluteError, ...
    rootMeanSquaredError, ...
    underforecastCount, ...
    overforecastCount, ...
    exactForecastCount, ...
    horizonCount, ...
    runtimeSeconds, ...
    covarianceStatus, ...
    standardErrorStatus, ...
    errorIdentifier, ...
    errorMessage, ...
    'VariableNames', { ...
    'model_id', ...
    'adapter_id', ...
    'status', ...
    'status_reason', ...
    'arima_p', ...
    'arima_d', ...
    'arima_q', ...
    'log_likelihood', ...
    'aic', ...
    'bic', ...
    'mean_error', ...
    'mean_absolute_error', ...
    'root_mean_squared_error', ...
    'underforecast_count', ...
    'overforecast_count', ...
    'exact_forecast_count', ...
    'horizon_count', ...
    'runtime_seconds', ...
    'parameter_covariance_status', ...
    'parameter_standard_error_status', ...
    'error_identifier', ...
    'error_message'});

end