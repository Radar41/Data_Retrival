function targetReference = create_target_reference( ...
    normalizedCsvPath, targetSelector, options)
%CREATE_TARGET_REFERENCE Validated, data-free reference to one target series.
%
% targetReference = gdss.create_target_reference(path, selector, ...)
%
% Records which normalized series an evaluation targets without reading the
% CSV. Pass the result to gdss.load_normalized_target (via its fields) when
% the observations are actually needed.

arguments
    normalizedCsvPath (1,1) string
    targetSelector (1,1) struct
    options.DataVersionReference (1,1) string = ""
    options.MissingValuePolicy (1,1) string = "reject_nonfinite"
end

assert(~ismissing(normalizedCsvPath) && ...
    strlength(normalizedCsvPath) > 0, ...
    "normalizedCsvPath must be one nonempty scalar string.");

requiredSelectorFields = [ ...
    "source_member"
    "series_id"
    "data_variant"
    "target_transform"];

assert(all(isfield(targetSelector, requiredSelectorFields)), ...
    "targetSelector is missing one or more required fields.");

for i = 1:numel(requiredSelectorFields)

    fieldName = requiredSelectorFields(i);
    fieldValue = string(targetSelector.(fieldName));

    assert(isscalar(fieldValue) && ...
        ~ismissing(fieldValue) && ...
        strlength(fieldValue) > 0, ...
        "targetSelector." + fieldName + ...
        " must be one nonempty scalar string.");

end

missingValuePolicy = string(options.MissingValuePolicy);

assert(any(missingValuePolicy == [ ...
    "reject_nonfinite"
    "drop_missing_with_audited_gap_policy"]), ...
    "Unsupported MissingValuePolicy.");

targetReference = struct();

targetReference.record_type = "NORMALIZED_TARGET_REFERENCE";

targetReference.normalized_csv_path = normalizedCsvPath;
targetReference.data_version_reference = ...
    string(options.DataVersionReference);

targetReference.source_member = string(targetSelector.source_member);
targetReference.series_id = string(targetSelector.series_id);
targetReference.data_variant = string(targetSelector.data_variant);
targetReference.target_transform = ...
    string(targetSelector.target_transform);

targetReference.missing_value_policy = missingValuePolicy;

targetReference.created_at_utc = datetime( ...
    "now", ...
    "TimeZone", "UTC", ...
    "Format", "yyyy-MM-dd'T'HH:mm:ss.SSS'Z'");

end
