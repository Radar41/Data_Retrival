function evaluationRun = run_gdss_evaluation(config)

arguments
    config (1,1) struct
end

requiredFields = [ ...
    "adapter_id"
    "normalized_csv_path"
    "source_member"
    "series_id"
    "data_variant"
    "target_transform"
    "origin_index"];

assert(all(isfield(config, requiredFields)), ...
    "config is missing one or more required fields.");

assert(isfile(config.normalized_csv_path), ...
    "The configured normalized CSV path does not exist.");

assert(isscalar(string(config.source_member)) && ...
    strlength(string(config.source_member)) > 0, ...
    "config.source_member must be one nonempty scalar string.");

assert(isscalar(string(config.series_id)) && ...
    strlength(string(config.series_id)) > 0, ...
    "config.series_id must be one nonempty scalar string.");

assert(isscalar(string(config.data_variant)) && ...
    strlength(string(config.data_variant)) > 0, ...
    "config.data_variant must be one nonempty scalar string.");

assert(isscalar(string(config.target_transform)) && ...
    strlength(string(config.target_transform)) > 0, ...
    "config.target_transform must be one nonempty scalar string.");

assert(isscalar(config.origin_index) && ...
    isnumeric(config.origin_index) && ...
    isfinite(config.origin_index) && ...
    config.origin_index == floor(config.origin_index) && ...
    config.origin_index >= 1, ...
    "origin_index must be a positive integer scalar.");

createdAtUtc = datetime( ...
    "now", ...
    "TimeZone", "UTC", ...
    "Format", "yyyy-MM-dd'T'HH:mm:ss.SSS'Z'");

T = readtable(config.normalized_csv_path, "TextType", "string");

requiredInputColumns = [ ...
    "source_member"
    "series_id"
    "transformation_code"
    "observation_date"
    "value"];

assert(all(ismember(requiredInputColumns, ...
    string(T.Properties.VariableNames))), ...
    "Normalized input is missing one or more required columns.");

S = T( ...
    string(T.source_member) == string(config.source_member) & ...
    string(T.series_id) == string(config.series_id) & ...
    string(T.transformation_code) == string(config.data_variant), ...
    ["observation_date", "value"]);

assert(~isempty(S), ...
    "No normalized rows match source_member, series_id, and data_variant.");

S = sortrows(S, "observation_date");

dates = datetime(string(S.observation_date), ...
    "InputFormat", "yyyy-MM-dd");
dates = dates(:);

x = S.value;

assert(isnumeric(x) && isvector(x), ...
    "Normalized series values must be a numeric vector.");

x = x(:);

assert(numel(dates) == numel(x), ...
    "Observation-date count must equal value count.");

assert(all(isfinite(x)), ...
    "Normalized series values must all be finite.");

assert(all(diff(dates) > days(0)), ...
    "Normalized observation dates must be strictly increasing.");

seriesTT = timetable(dates, x, ...
    'VariableNames', {'target_value'});

assert(config.origin_index < height(seriesTT), ...
    "origin_index must leave at least one held-out observation.");

originIndex = config.origin_index;
originTime = seriesTT.dates(originIndex);

trainTT = seriesTT(1:originIndex, :);
actualTT = seriesTT((originIndex + 1):end, :);

forecastHorizons = (1:height(actualTT))';

assert(height(trainTT) == originIndex, ...
    "Training partition length does not equal origin_index.");

assert(numel(forecastHorizons) == height(actualTT), ...
    "Forecast horizon count does not equal held-out count.");

dataContext = struct();
dataContext.target_dimension = 1;
dataContext.observation_count = height(seriesTT);
dataContext.training_observation_count = height(trainTT);
dataContext.frequency_days = unique(days(diff(dates)));
dataContext.series_id = string(config.series_id);
dataContext.data_variant = string(config.data_variant);
dataContext.target_transform = string(config.target_transform);

adapter = gdss.create_model_adapter(config);

validation = adapter.validate(dataContext);

assert(isfield(validation, "status"), ...
    "Adapter validation payload must contain status.");

assert(isequal(string(validation.status), "VALID"), ...
    "Adapter validation failed: %s", string(validation.status_reason));

trainingData = struct();
trainingData.target_values = trainTT.target_value;

fitContext = struct();
fitContext.origin_index = originIndex;
fitContext.origin_time = originTime;
fitContext.training_start_index = 1;
fitContext.training_end_index = originIndex;
fitContext.training_start_time = trainTT.dates(1);
fitContext.training_end_time = trainTT.dates(end);
fitContext.training_observation_count = height(trainTT);

fitPayload = adapter.fit(trainingData, fitContext);

assert(isfield(fitPayload, "status") && ...
    isequal(string(fitPayload.status), "COMPLETE"), ...
    "Adapter fit did not complete.");

forecastContext = struct();
forecastContext.horizon = forecastHorizons;
forecastContext.origin_index = originIndex;
forecastContext.origin_time = originTime;
forecastContext.target_index = originIndex + forecastHorizons;
forecastContext.target_time = actualTT.dates;

forecastPayload = adapter.forecast(fitPayload, forecastContext);

assert(isfield(forecastPayload, "status") && ...
    isequal(string(forecastPayload.status), "COMPLETE"), ...
    "Adapter forecast did not complete.");

assert(isequal(forecastPayload.horizon(:), forecastHorizons), ...
    "Adapter forecast horizons differ from requested horizons.");

assert(numel(forecastPayload.point_forecast) == ...
    numel(forecastHorizons), ...
    "Adapter point-forecast count differs from requested horizon count.");

assert(numel(forecastPayload.forecast_distribution_status) == ...
    numel(forecastHorizons), ...
    "Forecast-distribution status count differs from horizon count.");

assert(numel(forecastPayload.prediction_interval_status) == ...
    numel(forecastHorizons), ...
    "Prediction-interval status count differs from horizon count.");

pointForecast = forecastPayload.point_forecast(:);

assert(all(isfinite(pointForecast)), ...
    "Adapter point forecasts must all be finite.");

fitRealization = struct();

fitRealization.realization_type = "FIT_REALIZATION";
fitRealization.status = string(fitPayload.status);
fitRealization.status_reason = string(fitPayload.status_reason);

fitRealization.origin_index = originIndex;
fitRealization.origin_time = originTime;

fitRealization.source_member = string(config.source_member);
fitRealization.series_id = string(config.series_id);
fitRealization.data_variant = string(config.data_variant);
fitRealization.target_transform = string(config.target_transform);

fitRealization.adapter_id = string(config.adapter_id);
fitRealization.backend_id = string(fitPayload.backend_id);
fitRealization.backend_version = string(fitPayload.backend_version);
fitRealization.backend_model_class = ...
    string(fitPayload.backend_model_class);

fitRealization.predictive_context_kind = ...
    string(fitPayload.predictive_context_kind);

fitRealization.state_at_origin = fitPayload.state_at_origin;
fitRealization.convergence_status = ...
    string(fitPayload.convergence_status);

fitRealization.created_at_utc = createdAtUtc;
fitRealization.validation = validation;
fitRealization.fit_payload = fitPayload;

forecastRealization = struct();

forecastRealization.realization_type = "FORECAST_REALIZATION";
forecastRealization.status = string(forecastPayload.status);
forecastRealization.status_reason = ...
    string(forecastPayload.status_reason);

forecastRealization.origin_index = originIndex;
forecastRealization.origin_time = originTime;

forecastRealization.source_member = fitRealization.source_member;
forecastRealization.series_id = fitRealization.series_id;
forecastRealization.data_variant = fitRealization.data_variant;
forecastRealization.target_transform = ...
    fitRealization.target_transform;

forecastRealization.adapter_id = fitRealization.adapter_id;
forecastRealization.backend_id = fitRealization.backend_id;
forecastRealization.backend_version = fitRealization.backend_version;
forecastRealization.backend_model_class = ...
    fitRealization.backend_model_class;

forecastRealization.horizon = forecastHorizons;
forecastRealization.target_index = originIndex + forecastHorizons;
forecastRealization.target_time = actualTT.dates;
forecastRealization.point_forecast = pointForecast;

forecastRealization.point_forecast_status = ...
    string(forecastPayload.point_forecast_status(:));

forecastRealization.point_forecast_scale = ...
    string(forecastPayload.point_forecast_scale(:));

forecastRealization.point_forecast_method = ...
    string(forecastPayload.point_forecast_method(:));

forecastRealization.forecast_distribution_status = ...
    string(forecastPayload.forecast_distribution_status(:));

forecastRealization.prediction_interval_status = ...
    string(forecastPayload.prediction_interval_status(:));

forecastRealization.fit_realization_created_at_utc = ...
    fitRealization.created_at_utc;

forecastRealization.created_at_utc = createdAtUtc;
forecastRealization.forecast_payload = forecastPayload;

nForecasts = numel(forecastHorizons);

forecastLeaves = repmat(struct( ...
    "record_type", "", ...
    "status", "", ...
    "origin_index", NaN, ...
    "origin_time", NaT, ...
    "target_index", NaN, ...
    "target_time", NaT, ...
    "horizon", NaN, ...
    "source_member", "", ...
    "series_id", "", ...
    "data_variant", "", ...
    "target_transform", "", ...
    "adapter_id", "", ...
    "backend_id", "", ...
    "backend_version", "", ...
    "backend_model_class", "", ...
    "point_forecast", NaN, ...
    "actual_value", NaN, ...
    "forecast_error", NaN, ...
    "absolute_error", NaN, ...
    "squared_error", NaN, ...
    "forecast_distribution_status", "", ...
    "prediction_interval_status", "", ...
    "created_at_utc", NaT), ...
    nForecasts, 1);

for i = 1:nForecasts
    forecastValue = forecastRealization.point_forecast(i);
    actualValue = actualTT.target_value(i);
    forecastError = actualValue - forecastValue;

    forecastLeaves(i).record_type = "FORECAST_LEAF";
    forecastLeaves(i).status = forecastRealization.status;

    forecastLeaves(i).origin_index = originIndex;
    forecastLeaves(i).origin_time = originTime;

    forecastLeaves(i).target_index = ...
        forecastRealization.target_index(i);

    forecastLeaves(i).target_time = ...
        forecastRealization.target_time(i);

    forecastLeaves(i).horizon = ...
        forecastRealization.horizon(i);

    forecastLeaves(i).source_member = ...
        forecastRealization.source_member;

    forecastLeaves(i).series_id = ...
        forecastRealization.series_id;

    forecastLeaves(i).data_variant = ...
        forecastRealization.data_variant;

    forecastLeaves(i).target_transform = ...
        forecastRealization.target_transform;

    forecastLeaves(i).adapter_id = ...
        forecastRealization.adapter_id;

    forecastLeaves(i).backend_id = ...
        forecastRealization.backend_id;

    forecastLeaves(i).backend_version = ...
        forecastRealization.backend_version;

    forecastLeaves(i).backend_model_class = ...
        forecastRealization.backend_model_class;

    forecastLeaves(i).point_forecast = forecastValue;
    forecastLeaves(i).actual_value = actualValue;

    forecastLeaves(i).forecast_error = forecastError;
    forecastLeaves(i).absolute_error = abs(forecastError);
    forecastLeaves(i).squared_error = forecastError ^ 2;

    forecastLeaves(i).forecast_distribution_status = ...
        forecastRealization.forecast_distribution_status(i);

    forecastLeaves(i).prediction_interval_status = ...
        forecastRealization.prediction_interval_status(i);

    forecastLeaves(i).created_at_utc = createdAtUtc;
end

assert(numel(forecastLeaves) == nForecasts, ...
    "Forecast-leaf count differs from forecast count.");

assert(isequal([forecastLeaves.horizon]', forecastHorizons), ...
    "Leaf horizons differ from requested horizons.");

assert(isequal([forecastLeaves.target_index]', ...
    originIndex + forecastHorizons), ...
    "Leaf target indices violate origin_index + horizon.");

assert(isequal([forecastLeaves.target_time]', actualTT.dates), ...
    "Leaf target times differ from held-out target dates.");

assert(all([forecastLeaves.point_forecast]' == pointForecast), ...
    "Leaf point forecasts differ from forecast realization.");

assert(all([forecastLeaves.actual_value]' == actualTT.target_value), ...
    "Leaf actual values differ from held-out values.");

leafErrors = [forecastLeaves.forecast_error]';
leafAbsoluteErrors = [forecastLeaves.absolute_error]';
leafSquaredErrors = [forecastLeaves.squared_error]';

assert(all(leafAbsoluteErrors == abs(leafErrors)), ...
    "Leaf absolute errors are inconsistent.");

assert(all(leafSquaredErrors == leafErrors .^ 2), ...
    "Leaf squared errors are inconsistent.");

forecastScorecard = struct();

forecastScorecard.record_type = "FORECAST_SCORECARD";
forecastScorecard.status = "COMPLETE";

forecastScorecard.origin_index = originIndex;
forecastScorecard.origin_time = originTime;

forecastScorecard.source_member = ...
    forecastRealization.source_member;

forecastScorecard.series_id = forecastRealization.series_id;
forecastScorecard.data_variant = forecastRealization.data_variant;

forecastScorecard.target_transform = ...
    forecastRealization.target_transform;

forecastScorecard.adapter_id = forecastRealization.adapter_id;

forecastScorecard.backend_id = forecastRealization.backend_id;
forecastScorecard.backend_version = ...
    forecastRealization.backend_version;

forecastScorecard.backend_model_class = ...
    forecastRealization.backend_model_class;

forecastScorecard.horizon_count = nForecasts;
forecastScorecard.first_horizon = forecastHorizons(1);
forecastScorecard.last_horizon = forecastHorizons(end);

forecastScorecard.first_target_time = actualTT.dates(1);
forecastScorecard.last_target_time = actualTT.dates(end);

forecastScorecard.mean_error = mean(leafErrors);
forecastScorecard.mean_absolute_error = mean(leafAbsoluteErrors);

forecastScorecard.root_mean_squared_error = ...
    sqrt(mean(leafSquaredErrors));

forecastScorecard.minimum_error = min(leafErrors);
forecastScorecard.maximum_error = max(leafErrors);

forecastScorecard.underforecast_count = sum(leafErrors > 0);
forecastScorecard.overforecast_count = sum(leafErrors < 0);
forecastScorecard.exact_forecast_count = sum(leafErrors == 0);

forecastScorecard.created_at_utc = createdAtUtc;

assert(forecastScorecard.underforecast_count + ...
    forecastScorecard.overforecast_count + ...
    forecastScorecard.exact_forecast_count == nForecasts, ...
    "Directional forecast counts do not sum to forecast count.");

assert(forecastScorecard.root_mean_squared_error >= ...
    forecastScorecard.mean_absolute_error, ...
    "RMSE must be at least as large as MAE.");

evaluationRun = struct();

evaluationRun.record_type = "EVALUATION_RUN";
evaluationRun.status = "COMPLETE";

evaluationRun.origin_index = originIndex;
evaluationRun.origin_time = originTime;

evaluationRun.source_member = fitRealization.source_member;
evaluationRun.series_id = fitRealization.series_id;

evaluationRun.data_variant = fitRealization.data_variant;
evaluationRun.target_transform = fitRealization.target_transform;

evaluationRun.adapter_id = fitRealization.adapter_id;

evaluationRun.backend_id = fitRealization.backend_id;
evaluationRun.backend_version = fitRealization.backend_version;
evaluationRun.backend_model_class = fitRealization.backend_model_class;

evaluationRun.horizon_count = forecastScorecard.horizon_count;
evaluationRun.first_horizon = forecastScorecard.first_horizon;
evaluationRun.last_horizon = forecastScorecard.last_horizon;

evaluationRun.first_target_time = ...
    forecastScorecard.first_target_time;

evaluationRun.last_target_time = ...
    forecastScorecard.last_target_time;

evaluationRun.fit_realization = fitRealization;
evaluationRun.forecast_realization = forecastRealization;
evaluationRun.forecast_leaves = forecastLeaves;
evaluationRun.forecast_scorecard = forecastScorecard;

evaluationRun.created_at_utc = createdAtUtc;

metricTolerance = 1e-9;

assert(isequal(string(evaluationRun.record_type), "EVALUATION_RUN"), ...
    "Evaluation-run record type is invalid.");

assert(isequal(string(evaluationRun.status), "COMPLETE"), ...
    "Evaluation-run status is invalid.");

assert(numel(evaluationRun.forecast_leaves) == ...
    evaluationRun.horizon_count, ...
    "Evaluation-run leaf count differs from horizon count.");

assert(abs(mean([evaluationRun.forecast_leaves.absolute_error]') - ...
    evaluationRun.forecast_scorecard.mean_absolute_error) <= ...
    metricTolerance, ...
    "Evaluation-run MAE is not reproducible from leaves.");

assert(abs(sqrt(mean([evaluationRun.forecast_leaves.squared_error]')) - ...
    evaluationRun.forecast_scorecard.root_mean_squared_error) <= ...
    metricTolerance, ...
    "Evaluation-run RMSE is not reproducible from leaves.");

end