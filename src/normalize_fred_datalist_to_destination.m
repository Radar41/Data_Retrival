function result = normalize_fred_datalist_to_destination(descriptor, options)
%NORMALIZE_FRED_DATALIST_TO_DESTINATION Normalize FRED CSV members safely.
%
% result = normalize_fred_datalist_to_destination(descriptor, ...
%     DestinationDirectory=destinationDirectory)
%
% Source files remain untouched. DestinationDirectory must not exist or
% must exist and be empty. The function refuses to overwrite any file.

arguments
    descriptor (1,1) struct
    options.DestinationDirectory (1,1) string {mustBeNonempty}
end

requiredFields = [ ...
    "provider_id"
    "dataset_id"
    "raw_file_sha256"
    "staging_key"
    "staging_directory"];

for k = 1:numel(requiredFields)
    assert(isfield(descriptor, requiredFields(k)), ...
        "Descriptor is missing required field: %s", requiredFields(k));
end

assert(string(descriptor.provider_id) == "fred", ...
    "This normalizer requires descriptor.provider_id = 'fred'.");

sourceDirectory = string(descriptor.staging_directory);

assert(isfolder(sourceDirectory), ...
    "Descriptor staging directory does not exist: %s", sourceDirectory);

destinationDirectory = string(options.DestinationDirectory);

assert(sourceDirectory ~= destinationDirectory, ...
    "DestinationDirectory must differ from descriptor.staging_directory.");

prepare_empty_destination(destinationDirectory);

[sourceMembers, sourcePaths] = discover_source_csv_members(sourceDirectory);

assert(~isempty(sourceMembers), ...
    "No source CSV members were found in: %s", sourceDirectory);

nMembers = numel(sourceMembers);

outputFileNames = strings(nMembers, 1);
outputPaths = strings(nMembers, 1);
sourceBytes = zeros(nMembers, 1);
sourceSHA256 = strings(nMembers, 1);
inputRowCounts = zeros(nMembers, 1);
dataColumnCounts = zeros(nMembers, 1);
baseSeriesCounts = zeros(nMembers, 1);
variantColumnCounts = zeros(nMembers, 1);
outputRowCounts = zeros(nMembers, 1);
outputSHA256 = strings(nMembers, 1);
transformationCodes = strings(nMembers, 1);

for k = 1:nMembers
    sourcePath = sourcePaths(k);
    sourceMember = sourceMembers(k);

    outputFileNames(k) = "normalized_" + sanitize_member_name(sourceMember);
    outputPaths(k) = fullfile(destinationDirectory, outputFileNames(k));

    assert(~isfile(outputPaths(k)), ...
        "Refusing to overwrite normalized output: %s", outputPaths(k));

    sourceInfo = dir(sourcePath);
    sourceBytes(k) = sourceInfo.bytes;
    sourceSHA256(k) = compute_sha256(sourcePath);

    sourceTable = readtable( ...
        sourcePath, ...
        TextType="string", ...
        VariableNamingRule="preserve");

    variableNames = string(sourceTable.Properties.VariableNames);

    assert(~isempty(variableNames), ...
        "Source member has no columns: %s", sourcePath);

    assert(variableNames(1) == "observation_date", ...
        "First column must be observation_date: %s", sourcePath);

    observationDates = string(sourceTable{:, 1});
    dataColumns = variableNames(2:end);

    [seriesIDs, transformCodes] = parse_fred_export_columns(dataColumns);

    inputRowCounts(k) = height(sourceTable);
    dataColumnCounts(k) = numel(dataColumns);
    baseSeriesCounts(k) = numel(unique(seriesIDs));
    variantColumnCounts(k) = numel(dataColumns);
    transformationCodes(k) = strjoin(unique(transformCodes), ", ");

    normalizedTable = make_long_table( ...
        sourceTable, ...
        observationDates, ...
        dataColumns, ...
        seriesIDs, ...
        transformCodes, ...
        sourceMember);

    writetable(normalizedTable, outputPaths(k));

    outputRowCounts(k) = height(normalizedTable);
    outputSHA256(k) = compute_sha256(outputPaths(k));
end

memberManifest = table( ...
    sourceMembers, ...
    sourcePaths, ...
    sourceBytes, ...
    sourceSHA256, ...
    outputFileNames, ...
    outputPaths, ...
    inputRowCounts, ...
    dataColumnCounts, ...
    baseSeriesCounts, ...
    variantColumnCounts, ...
    outputRowCounts, ...
    outputSHA256, ...
    transformationCodes, ...
    VariableNames=[ ...
        "source_member"
        "source_path"
        "source_bytes"
        "source_sha256"
        "normalized_file_name"
        "normalized_file_path"
        "input_row_count"
        "data_column_count"
        "base_series_count"
        "variant_column_count"
        "normalized_row_count"
        "normalized_file_sha256"
        "transformation_codes"]);

manifest = struct( ...
    "provider_id", string(descriptor.provider_id), ...
    "dataset_id", string(descriptor.dataset_id), ...
    "source_datalist_id", get_optional_string(descriptor, "source_datalist_id"), ...
    "raw_archive_sha256", string(descriptor.raw_file_sha256), ...
    "staging_key", string(descriptor.staging_key), ...
    "source_staging_directory", sourceDirectory, ...
    "normalization_destination_directory", destinationDirectory, ...
    "normalized_at_utc", string(datetime( ...
        "now", ...
        TimeZone="UTC", ...
        Format="yyyy-MM-dd'T'HH:mm:ss'Z'")), ...
    "normalization_status", "completed", ...
    "member_count", nMembers, ...
    "members", table2struct(memberManifest));

manifestPath = fullfile(destinationDirectory, "normalization_manifest.json");

assert(~isfile(manifestPath), ...
    "Refusing to overwrite normalization manifest: %s", manifestPath);

write_text_file(manifestPath, jsonencode(manifest, PrettyPrint=true));

result = struct( ...
    "provider_id", string(descriptor.provider_id), ...
    "dataset_id", string(descriptor.dataset_id), ...
    "raw_archive_sha256", string(descriptor.raw_file_sha256), ...
    "source_staging_directory", sourceDirectory, ...
    "normalization_destination_directory", destinationDirectory, ...
    "normalization_manifest_path", string(manifestPath), ...
    "normalization_status", "completed", ...
    "source_member_count", nMembers, ...
    "members", memberManifest);

fprintf("FRED normalization completed.\n");
fprintf("  Source directory: %s\n", sourceDirectory);
fprintf("  Destination directory: %s\n", destinationDirectory);
fprintf("  Normalized members: %d\n", nMembers);
fprintf("  Manifest: %s\n", manifestPath);
end

function prepare_empty_destination(destinationDirectory)

if ~isfolder(destinationDirectory)
    [wasCreated, message] = mkdir(destinationDirectory);

    assert(wasCreated, ...
        "Could not create destination directory: %s", message);

    return
end

entries = dir(destinationDirectory);
entries = entries(~ismember({entries.name}, {".", ".."}));

assert(isempty(entries), ...
    "DestinationDirectory already exists and is not empty: %s", ...
    destinationDirectory);
end

function [sourceMembers, sourcePaths] = discover_source_csv_members(sourceDirectory)

files = dir(fullfile(sourceDirectory, "*.csv"));

if isempty(files)
    sourceMembers = strings(0, 1);
    sourcePaths = strings(0, 1);
    return
end

allNames = string({files.name})';

generatedPrefixes = [ ...
    "normalized_"
    "series_metadata"
    "archive_inventory"
    "source_members"
    "providers"
    "datasets"
    "raw_artifacts"
    "series_variants"];

isGenerated = false(size(allNames));

for k = 1:numel(generatedPrefixes)
    isGenerated = isGenerated | startsWith( ...
        lower(allNames), lower(generatedPrefixes(k)));
end

sourceMembers = sort(allNames(~isGenerated));
sourcePaths = fullfile(sourceDirectory, sourceMembers);
end

function [seriesIDs, transformCodes] = parse_fred_export_columns(dataColumns)

dataColumns = string(dataColumns);

suffixes = ["_CCA", "_CCH", "_CH1", "_CHG", ...
            "_LOG", "_PC1", "_PCA", "_PCH"];

seriesIDs = dataColumns;
transformCodes = repmat("LEVEL", size(dataColumns));

for k = 1:numel(suffixes)
    hit = endsWith(dataColumns, suffixes(k));

    seriesIDs(hit) = extractBefore(dataColumns(hit), suffixes(k));
    transformCodes(hit) = extractAfter(suffixes(k), "_");
end
end

function normalizedTable = make_long_table( ...
    sourceTable, observationDates, dataColumns, ...
    seriesIDs, transformCodes, sourceMember)

nRows = height(sourceTable);
nColumns = numel(dataColumns);
nOutputRows = nRows * nColumns;

observationDate = repelem(observationDates, nColumns, 1);
seriesID = repmat(seriesIDs(:), nRows, 1);
transformationCode = repmat(transformCodes(:), nRows, 1);
sourceColumn = repmat(dataColumns(:), nRows, 1);
sourceMemberColumn = repmat(string(sourceMember), nOutputRows, 1);

valueMatrix = sourceTable{:, 2:end};

assert(isnumeric(valueMatrix), ...
    "Data columns must import as numeric values: %s", sourceMember);

value = reshape(valueMatrix.', [], 1);

normalizedTable = table( ...
    observationDate, ...
    seriesID, ...
    transformationCode, ...
    value, ...
    sourceMemberColumn, ...
    sourceColumn, ...
    VariableNames=[ ...
        "observation_date"
        "series_id"
        "transformation_code"
        "value"
        "source_member"
        "source_column"]);
end

function outputName = sanitize_member_name(memberName)

memberName = string(memberName);

[~, baseName, ~] = fileparts(memberName);

baseName = lower(baseName);
baseName = regexprep(baseName, "[^a-zA-Z0-9]+", "_");
baseName = regexprep(baseName, "^_+|_+$", "");

outputName = baseName + ".csv";
end

function value = get_optional_string(structure, fieldName)

if isfield(structure, fieldName)
    value = string(structure.(fieldName));
else
    value = missing;
end
end

function hash = compute_sha256(filename)

import java.security.MessageDigest
import java.io.FileInputStream
import java.io.BufferedInputStream

digest = MessageDigest.getInstance("SHA-256");

inputStream = BufferedInputStream(FileInputStream(char(filename)));
cleanup = onCleanup(@() inputStream.close());

buffer = zeros(1, 8192, "int8");

while true
    bytesRead = inputStream.read(buffer, 0, numel(buffer));

    if bytesRead == -1
        break
    end

    digest.update(buffer(1:bytesRead));
end

hashBytes = typecast(digest.digest(), "uint8");
hash = lower(reshape(dec2hex(hashBytes, 2).', 1, []));
end

function write_text_file(filename, text)

fileID = fopen(filename, "w");

if fileID == -1
    error("Data_Retrival:FileWriteFailed", ...
        "Could not open file for writing: %s", filename);
end

cleanup = onCleanup(@() fclose(fileID));
fprintf(fileID, "%s", text);
end
