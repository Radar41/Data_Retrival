function rollingSweepRun = run_gdss_rolling_config_sweep( ...
    modelConfigs, originIndices)

arguments
    modelConfigs (:,1) struct
    originIndices (:,1) double
end

assert(~isempty(modelConfigs), ...
    "modelConfigs must contain at least one configuration.");

assert(~isempty(originIndices), ...
    "originIndices must contain at least one origin index.");

assert(all(isfinite(originIndices)) && ...
    all(originIndices >= 1) && ...
    all(originIndices == floor(originIndices)), ...
    "originIndices must contain positive integer indices.");

assert(numel(unique(originIndices)) == numel(originIndices), ...
    "originIndices must not contain duplicates.");

assert(issorted(originIndices), ...
    "originIndices must be sorted in ascending order.");

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

rollingSweepRun = struct();

rollingSweepRun.record_type = "GDSS_ROLLING_CONFIG_SWEEP";
rollingSweepRun.status = "RUNNING";
rollingSweepRun.status_reason = "";

rollingSweepRun.model_count = numel(modelConfigs);
rollingSweepRun.origin_count = numel(originIndices);
rollingSweepRun.origin_indices = originIndices;

rollingSweepRun.series_id = string(modelConfigs(1).series_id);
rollingSweepRun.data_variant = string(modelConfigs(1).data_variant);
rollingSweepRun.target_transform = ...
    string(modelConfigs(1).target_transform);

rollingSweepRun.created_at_utc = ...
    datetime("now", "TimeZone", "UTC", ...
    "Format", "yyyy-MM-dd'T'HH:mm:ss.SSS'Z'");

rollingSweepRun.model_configs = modelConfigs;

originResultTemplate = struct( ...
    "origin_index", NaN, ...
    "status", "NOT_STARTED", ...
    "status_reason", "", ...
    "sweep_run", [], ...
    "error_identifier", "", ...
    "error_message", "", ...
    "started_at_utc", NaT(1, 1, "TimeZone", "UTC"), ...
    "completed_at_utc", NaT(1, 1, "TimeZone", "UTC"), ...
    "runtime_seconds", NaN);

rollingSweepRun.origin_results = repmat( ...
    originResultTemplate, numel(originIndices), 1);

for originPosition = 1:numel(originIndices)

    currentOriginIndex = originIndices(originPosition);

    currentOriginResult = originResultTemplate;

    currentOriginResult.origin_index = currentOriginIndex;
    currentOriginResult.status = "RUNNING";

    currentOriginResult.started_at_utc = ...
        datetime("now", "TimeZone", "UTC", ...
        "Format", "yyyy-MM-dd'T'HH:mm:ss.SSS'Z'");

    originStartTime = tic;

    try

        originConfigs = modelConfigs;

        for configIndex = 1:numel(originConfigs)

            originConfigs(configIndex).origin_index = ...
                currentOriginIndex;

        end

        currentOriginResult.sweep_run = ...
            run_gdss_config_sweep(originConfigs);

        currentOriginResult.status = ...
            string(currentOriginResult.sweep_run.status);

        currentOriginResult.status_reason = ...
            string(currentOriginResult.sweep_run.status_reason);

    catch exception

        currentOriginResult.status = "FAILED";
        currentOriginResult.status_reason = ...
            "Unhandled origin-sweep exception.";

        currentOriginResult.error_identifier = ...
            string(exception.identifier);

        currentOriginResult.error_message = ...
            string(getReport(exception, "extended", ...
            "hyperlinks", "off"));

    end

    currentOriginResult.runtime_seconds = toc(originStartTime);

    currentOriginResult.completed_at_utc = ...
        datetime("now", "TimeZone", "UTC", ...
        "Format", "yyyy-MM-dd'T'HH:mm:ss.SSS'Z'");

    rollingSweepRun.origin_results(originPosition, 1) = ...
        currentOriginResult;

end

originStatus = string({rollingSweepRun.origin_results.status})';

completeCount = sum(originStatus == "COMPLETE");
partialCount = sum(originStatus == "PARTIAL_COMPLETE");
failedCount = sum(originStatus == "FAILED");

rollingSweepRun.complete_origin_count = completeCount;
rollingSweepRun.partial_origin_count = partialCount;
rollingSweepRun.failed_origin_count = failedCount;

if completeCount == numel(originIndices)

    rollingSweepRun.status = "COMPLETE";
    rollingSweepRun.status_reason = "";

elseif completeCount + partialCount > 0

    rollingSweepRun.status = "PARTIAL_COMPLETE";
    rollingSweepRun.status_reason = ...
        "One or more origin sweeps did not fully complete.";

else

    rollingSweepRun.status = "FAILED";
    rollingSweepRun.status_reason = ...
        "No origin sweeps completed.";

end

rollingSweepRun.completed_at_utc = ...
    datetime("now", "TimeZone", "UTC", ...
    "Format", "yyyy-MM-dd'T'HH:mm:ss.SSS'Z'");

end