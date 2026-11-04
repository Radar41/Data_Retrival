function sweepRun = run_gdss_config_sweep(modelConfigs)

arguments
modelConfigs (:,1) struct
end

assert(~isempty(modelConfigs), ...
    "modelConfigs must contain at least one configuration.");

requiredConfigFields = [ ...
    "model_id"
    "adapter_id"
    "series_id"
    "data_variant"
    "target_transform"
    "origin_index"];

for configIndex = 1:numel(modelConfigs)

    currentConfig = modelConfigs(configIndex);

    for fieldIndex = 1:numel(requiredConfigFields)

        fieldName = requiredConfigFields(fieldIndex);

        assert(isfield(currentConfig, fieldName), ...
            "modelConfigs(" + string(configIndex) + ...
            ") is missing required field: " + fieldName);

    end

end

sweepRun = struct();

sweepRun.record_type = "GDSS_CONFIG_SWEEP";
sweepRun.status = "RUNNING";
sweepRun.status_reason = "";

sweepRun.model_count = numel(modelConfigs);

sweepRun.series_id = string(modelConfigs(1).series_id);
sweepRun.data_variant = string(modelConfigs(1).data_variant);
sweepRun.target_transform = string(modelConfigs(1).target_transform);
sweepRun.origin_index = modelConfigs(1).origin_index;

sweepRun.created_at_utc = ...
datetime("now", "TimeZone", "UTC", ...
    "Format", "yyyy-MM-dd'T'HH:mm:ss.SSS'Z'");

sweepRun.model_configs = modelConfigs;

resultTemplate = struct( ...
    "model_id", "", ...
    "adapter_id", "", ...
    "status", "NOT_STARTED", ...
    "status_reason", "", ...
    "evaluation_run", [], ...
    "error_identifier", "", ...
    "error_message", "", ...
    "started_at_utc", NaT(1, 1, "TimeZone", "UTC"), ...
    "completed_at_utc", NaT(1, 1, "TimeZone", "UTC"), ...
    "runtime_seconds", NaN);

sweepRun.results = repmat(resultTemplate, numel(modelConfigs), 1);

for configIndex = 1:numel(modelConfigs)

    currentConfig = modelConfigs(configIndex);

    currentResult = resultTemplate;

    currentResult.model_id = string(currentConfig.model_id);
    currentResult.adapter_id = string(currentConfig.adapter_id);

    currentResult.status = "RUNNING";
    currentResult.started_at_utc = ...
        datetime("now", "TimeZone", "UTC", ...
            "Format", "yyyy-MM-dd'T'HH:mm:ss.SSS'Z'");

    startTime = tic;

    try

        evaluationRun = run_gdss_evaluation(currentConfig);

        currentResult.evaluation_run = evaluationRun;

        if isfield(evaluationRun, "status")
            currentResult.status = string(evaluationRun.status);
        else
            currentResult.status = "COMPLETE";
        end

        if isfield(evaluationRun, "status_reason")
            currentResult.status_reason = ...
                string(evaluationRun.status_reason);
        end

    catch exception

        currentResult.status = "FAILED";
        currentResult.status_reason = ...
            "Unhandled evaluation exception.";

        currentResult.error_identifier = ...
            string(exception.identifier);

        currentResult.error_message = ...
            string(getReport(exception, "extended", ...
                "hyperlinks", "off"));

    end

    currentResult.runtime_seconds = toc(startTime);

    currentResult.completed_at_utc = ...
        datetime("now", "TimeZone", "UTC", ...
            "Format", "yyyy-MM-dd'T'HH:mm:ss.SSS'Z'");

    sweepRun.results(configIndex, 1) = currentResult;

end

resultStatus = string({sweepRun.results.status})';

completeCount = sum(resultStatus == "COMPLETE");
failedCount = sum(resultStatus == "FAILED");
otherCount = numel(resultStatus) - completeCount - failedCount;

sweepRun.complete_count = completeCount;
sweepRun.failed_count = failedCount;
sweepRun.other_count = otherCount;

if failedCount == 0 && otherCount == 0

    sweepRun.status = "COMPLETE";
    sweepRun.status_reason = "";

elseif completeCount > 0

    sweepRun.status = "PARTIAL_COMPLETE";
    sweepRun.status_reason = ...
        "One or more configurations did not complete.";

else

    sweepRun.status = "FAILED";
    sweepRun.status_reason = ...
        "No configurations completed.";

end

sweepRun.completed_at_utc = ...
datetime("now", "TimeZone", "UTC", ...
    "Format", "yyyy-MM-dd'T'HH:mm:ss.SSS'Z'");

end