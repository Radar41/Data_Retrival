function targetData = load_normalized_target( ...
    normalizedCsvPath, targetSelector, options)

arguments
    normalizedCsvPath (1,1) string {mustBeFile}
    targetSelector (1,1) struct
    options.MissingValuePolicy (1,1) string = "reject_nonfinite"
    options.DataVersionReference (1,1) string = ""
end

requiredSelectorFields = [ ...
    "source_member"
    "series_id"
    "data_variant"
    "target_transform"];

assert(all(isfield(targetSelector, requiredSelectorFields)), ...
    "targetSelector is missing one or more required fields.");

sourceMember = string(targetSelector.source_member);
seriesId = string(targetSelector.series_id);
dataVariant = string(targetSelector.data_variant);
targetTransform = string(targetSelector.target_transform);

assert(isscalar(sourceMember) && ...
    ~ismissing(sourceMember) && ...
    strlength(sourceMember) > 0, ...
    "targetSelector.source_member must be one nonempty scalar string.");

assert(isscalar(seriesId) && ...
    ~ismissing(seriesId) && ...
    strlength(seriesId) > 0, ...
    "targetSelector.series_id must be one nonempty scalar string.");

assert(isscalar(dataVariant) && ...
    ~ismissing(dataVariant) && ...
    strlength(dataVariant) > 0, ...
    "targetSelector.data_variant must be one nonempty scalar string.");

assert(isscalar(targetTransform) && ...
    ~ismissing(targetTransform) && ...
    strlength(targetTransform) > 0, ...
    "targetSelector.target_transform must be one nonempty scalar string.");

missingValuePolicy = string(options.MissingValuePolicy);

assert(isscalar(missingValuePolicy) && ...
    any(missingValuePolicy == [ ...
    "reject_nonfinite"
    "drop_missing_with_audited_gap_policy"]), ...
    "Unsupported MissingValuePolicy.");

T = readtable( ...
    normalizedCsvPath, ...
    "TextType", "string", ...
    "VariableNamingRule", "preserve");

requiredColumns = [ ...
    "observation_date"
    "series_id"
    "transformation_code"
    "value"
    "source_member"
    "source_column"];

assert(all(ismember(requiredColumns, ...
    string(T.Properties.VariableNames))), ...
    "Normalized input does not satisfy the canonical observation contract.");

S = T( ...
    string(T.source_member) == sourceMember & ...
    string(T.series_id) == seriesId & ...
    string(T.transformation_code) == dataVariant, ...
    requiredColumns);

assert(~isempty(S), ...
    "No normalized rows match the requested target selector.");

dateText = string(S.observation_date);

observationDates = datetime( ...
    dateText, ...
    "InputFormat", "yyyy-MM-dd");

values = S.value;

assert(isnumeric(values) && isvector(values), ...
    "Selected normalized target values must be numeric.");

values = values(:);
observationDates = observationDates(:);

assert(numel(observationDates) == numel(values), ...
    "Selected observation date/value counts differ.");

assert(all(~isnat(observationDates)), ...
    "Selected target contains unparsable observation dates.");

[observationDates, sortIndex] = sort(observationDates);
values = values(sortIndex);

sourceColumns = string(S.source_column);
sourceColumns = sourceColumns(sortIndex);

assert(all(diff(observationDates) > days(0)), ...
    "Selected target observation dates must be strictly increasing.");

if missingValuePolicy == "reject_nonfinite"

    assert(all(isfinite(values)), ...
        "Selected target contains nonfinite values under " + ...
        """reject_nonfinite"" policy.");

else

    keepMask = isfinite(values);

    observationDates = observationDates(keepMask);
    values = values(keepMask);
    sourceColumns = sourceColumns(keepMask);

    assert(~isempty(values), ...
        "No finite observations remain after applying missing-value policy.");

    assert(all(diff(observationDates) > days(0)), ...
        "Date sequence is invalid after applying missing-value policy.");

end

uniqueSourceColumns = unique(sourceColumns);

assert(numel(uniqueSourceColumns) == 1, ...
    "Selected target resolves to multiple source columns.");

targetData = struct();

targetData.record_type = "NORMALIZED_TARGET_DATA";

targetData.normalized_csv_path = normalizedCsvPath;
targetData.data_version_reference = ...
    string(options.DataVersionReference);

targetData.source_member = sourceMember;
targetData.source_column = uniqueSourceColumns;
targetData.series_id = seriesId;
targetData.data_variant = dataVariant;
targetData.target_transform = targetTransform;

targetData.observation_dates = observationDates;
targetData.target_values = values;

targetData.observation_count = numel(values);
targetData.first_observation_date = observationDates(1);
targetData.last_observation_date = observationDates(end);

targetData.missing_value_policy = missingValuePolicy;
targetData.loaded_at_utc = datetime( ...
    "now", ...
    "TimeZone", "UTC", ...
    "Format", "yyyy-MM-dd'T'HH:mm:ss.SSS'Z'");

end