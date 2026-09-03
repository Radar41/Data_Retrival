function result = normalize_fred_datalist_zip(manifest)
%NORMALIZE_FRED_DATALIST_ZIP Normalize staged FRED data-list CSV exports.

arguments
    manifest (1,1) struct
end

requiredFields = [ ...
    "provider_id"
    "dataset_id"
    "source_url"
    "raw_file_path"
    "raw_file_sha256"
    "raw_file_bytes"
];

for k = 1:numel(requiredFields)
    assert(isfield(manifest, requiredFields(k)), ...
        "Manifest is missing required field: %s", requiredFields(k));
end

assert(string(manifest.provider_id) == "fred", ...
    "This normalizer requires provider_id = 'fred'.");
assert(isfile(manifest.raw_file_path), ...
    "Registered raw ZIP does not exist: %s", manifest.raw_file_path);

root = currentProject().RootFolder;
shaPrefix = extractBefore(string(manifest.raw_file_sha256), 13);

stagingDir = fullfile( ...
    root, ...
    "data", "staging", "normalized", "fred", ...
    "fred_public_datalist_10578_fed_assets_" + shaPrefix);

assert(isfolder(stagingDir), ...
    "Expected staging directory does not exist: %s", stagingDir);

sourceMembers = table( ...
    ["weekly.csv"; "weekly,_ending_wednesday.csv"], ...
    ["Weekly"; "Weekly, Ending Wednesday"], ...
    ["normalized_weekly.csv"; "normalized_weekly_ending_wednesday.csv"], ...
    VariableNames=[ ...
        "SourceMemberPath"
        "FrequencyLabel"
        "NormalizedFileName"]);

for k = 1:height(sourceMembers)
    sourcePath = fullfile(stagingDir, sourceMembers.SourceMemberPath(k));
    outputPath = fullfile(stagingDir, sourceMembers.NormalizedFileName(k));

    assert(isfile(sourcePath), ...
        "Expected source member does not exist: %s", sourcePath);

    if isfile(outputPath)
        error("Refusing to overwrite existing normalized output: %s", ...
            outputPath);
    end

    normalized = normalize_member( ...
        sourcePath, ...
        sourceMembers.SourceMemberPath(k), ...
        sourceMembers.FrequencyLabel(k), ...
        manifest);

    writetable(normalized, outputPath);

    fprintf("Wrote %d rows: %s\n", height(normalized), outputPath);
end

normalizedAtUTC = string(datetime( ...
    "now", ...
    TimeZone="UTC", ...
    Format="yyyy-MM-dd'T'HH:mm:ss'Z'"));

normalizationManifest = struct( ...
    "provider_id", string(manifest.provider_id), ...
    "dataset_id", string(manifest.dataset_id), ...
    "source_datalist_id", "10578", ...
    "source_datalist_title", "banks weekly", ...
    "source_url", string(manifest.source_url), ...
    "raw_file_path", string(manifest.raw_file_path), ...
    "raw_file_bytes", double(manifest.raw_file_bytes), ...
    "raw_file_sha256", string(manifest.raw_file_sha256), ...
    "staging_directory", string(stagingDir), ...
    "normalizer", "normalize_fred_datalist_zip", ...
    "normalized_at_utc", normalizedAtUTC, ...
    "source_members", table2struct(sourceMembers));

manifestPath = fullfile(stagingDir, "normalization_manifest.json");

if isfile(manifestPath)
    error("Refusing to overwrite normalization manifest: %s", manifestPath);
end

fid = fopen(manifestPath, "w");
assert(fid >= 0, ...
    "Could not open normalization manifest for writing: %s", manifestPath);

cleanup = onCleanup(@() fclose(fid));
fprintf(fid, "%s", jsonencode(normalizationManifest, PrettyPrint=true));

result = struct( ...
    "staging_directory", string(stagingDir), ...
    "source_members", sourceMembers, ...
    "normalization_manifest_path", string(manifestPath));
end

function normalized = normalize_member( ...
    sourcePath, sourceMemberPath, frequencyLabel, manifest)

opts = detectImportOptions(sourcePath, "TextType", "string");

assert(ismember("observation_date", string(opts.VariableNames)), ...
    "Source member has no observation_date column: %s", sourcePath);

opts = setvartype(opts, "observation_date", "datetime");
opts = setvaropts(opts, "observation_date", ...
    "InputFormat", "yyyy-MM-dd");

source = readtable(sourcePath, opts);

observationDate = source.observation_date;
columnNames = string(source.Properties.VariableNames);
dataColumns = columnNames(columnNames ~= "observation_date");

suffixes = ["_CCA", "_CCH", "_CH1", "_CHG", ...
            "_LOG", "_PC1", "_PCA", "_PCH"];

seriesIDs = dataColumns;
transformCodes = repmat("LEVEL", size(dataColumns));

for k = 1:numel(suffixes)
    hit = endsWith(dataColumns, suffixes(k));
    seriesIDs(hit) = extractBefore(dataColumns(hit), suffixes(k));
    transformCodes(hit) = extractAfter(suffixes(k), "_");
end

nDates = numel(observationDate);
nColumns = numel(dataColumns);
nRows = nDates * nColumns;

providerID = repmat(string(manifest.provider_id), nRows, 1);
datasetID = repmat(string(manifest.dataset_id), nRows, 1);
rawArchiveSHA256 = repmat(string(manifest.raw_file_sha256), nRows, 1);
memberPath = repmat(string(sourceMemberPath), nRows, 1);
frequency = repmat(string(frequencyLabel), nRows, 1);

observationDateLong = repmat(observationDate, nColumns, 1);
seriesIDLong = repelem(seriesIDs(:), nDates, 1);
transformLong = repelem(transformCodes(:), nDates, 1);
rawColumnLong = repelem(dataColumns(:), nDates, 1);

values = NaN(nRows, 1);

for k = 1:nColumns
    columnValue = source.(dataColumns(k));

    if iscell(columnValue)
        columnValue = string(columnValue);
    end

    if isstring(columnValue)
        columnValue = str2double(columnValue);
    end

    rowRange = (k - 1) * nDates + (1:nDates);
    values(rowRange) = double(columnValue);
end

normalizationTime = string(datetime( ...
    "now", ...
    TimeZone="UTC", ...
    Format="yyyy-MM-dd'T'HH:mm:ss'Z'"));

normalizedAtUTC = repmat(normalizationTime, nRows, 1);

normalized = table( ...
    providerID, ...
    datasetID, ...
    rawArchiveSHA256, ...
    memberPath, ...
    frequency, ...
    observationDateLong, ...
    seriesIDLong, ...
    transformLong, ...
    rawColumnLong, ...
    values, ...
    isnan(values), ...
    normalizedAtUTC, ...
    VariableNames=[ ...
        "provider_id"
        "dataset_id"
        "raw_archive_sha256"
        "source_member_path"
        "frequency_label"
        "observation_date"
        "series_id"
        "transformation_code"
        "raw_column_name"
        "value"
        "is_missing"
        "normalized_at_utc"]);
end
