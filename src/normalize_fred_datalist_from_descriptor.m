function result = normalize_fred_datalist_from_descriptor(descriptor, options)
%NORMALIZE_FRED_DATALIST_FROM_DESCRIPTOR Plan or normalize FRED CSV members.
%
% result = normalize_fred_datalist_from_descriptor(descriptor)
% performs a dry run and writes no files.
%
% result = normalize_fred_datalist_from_descriptor(descriptor, ...
%     DryRun=false)
% normalizes discovered source CSV files into the descriptor staging folder.

arguments
    descriptor (1,1) struct
    options.DryRun (1,1) logical = true
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

stagingDir = string(descriptor.staging_directory);

assert(isfolder(stagingDir), ...
    "Descriptor staging directory does not exist: %s", stagingDir);

[sourceMembers, sourcePaths] = discover_source_csv_members(stagingDir);

assert(~isempty(sourceMembers), ...
    "No source CSV members were found in: %s", stagingDir);

nMembers = numel(sourceMembers);

memberPath = strings(nMembers, 1);
outputFileName = strings(nMembers, 1);
outputPath = strings(nMembers, 1);
observationDateColumn = strings(nMembers, 1);
dataColumnCount = zeros(nMembers, 1);
baseSeriesCount = zeros(nMembers, 1);
variantColumnCount = zeros(nMembers, 1);
transformationCodes = strings(nMembers, 1);

for k = 1:nMembers
    opts = detectImportOptions(sourcePaths(k), "TextType", "string");
    variableNames = string(opts.VariableNames);

    assert(~isempty(variableNames), ...
        "Source member has no columns: %s", sourcePaths(k));

    assert(variableNames(1) == "observation_date", ...
        "First column must be observation_date: %s", sourcePaths(k));

    dataColumns = variableNames(2:end);

    [seriesIDs, transformCodes] = parse_fred_export_columns(dataColumns);

    memberPath(k) = sourceMembers(k);
    outputFileName(k) = "normalized_" + sanitize_member_name(sourceMembers(k));
    outputPath(k) = fullfile(stagingDir, outputFileName(k));
    observationDateColumn(k) = variableNames(1);
    dataColumnCount(k) = numel(dataColumns);
    baseSeriesCount(k) = numel(unique(seriesIDs));
    variantColumnCount(k) = numel(dataColumns);
    transformationCodes(k) = strjoin(unique(transformCodes), ", ");

    if ~options.DryRun && isfile(outputPath(k))
        error("Refusing to overwrite normalized output: %s", outputPath(k));
    end
end

memberPlan = table( ...
    memberPath, ...
    outputFileName, ...
    outputPath, ...
    observationDateColumn, ...
    dataColumnCount, ...
    baseSeriesCount, ...
    variantColumnCount, ...
    transformationCodes, ...
    VariableNames=[ ...
        "source_member_path"
        "normalized_file_name"
        "normalized_file_path"
        "observation_date_column"
        "data_column_count"
        "base_series_count"
        "variant_column_count"
        "transformation_codes"]);

result = struct( ...
    "provider_id", string(descriptor.provider_id), ...
    "dataset_id", string(descriptor.dataset_id), ...
    "raw_archive_sha256", string(descriptor.raw_file_sha256), ...
    "staging_key", string(descriptor.staging_key), ...
    "staging_directory", stagingDir, ...
    "dry_run", options.DryRun, ...
    "source_member_count", nMembers, ...
    "source_member_plan", memberPlan);

if options.DryRun
    fprintf("Dry-run normalization plan.\n");
    fprintf("  Staging directory: %s\n", stagingDir);
    fprintf("  Source CSV members: %d\n", nMembers);
    disp(memberPlan)
    return
end

error([ ...
    "Write mode is intentionally not implemented yet. " + ...
    "Validate the dry-run plan before adding a new write path."]);
end

function [sourceMembers, sourcePaths] = discover_source_csv_members(stagingDir)

files = dir(fullfile(stagingDir, "*.csv"));

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
sourcePaths = fullfile(stagingDir, sourceMembers);
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

function outputName = sanitize_member_name(memberName)

memberName = string(memberName);

[~, baseName, ~] = fileparts(memberName);

baseName = lower(baseName);
baseName = regexprep(baseName, "[^a-zA-Z0-9]+", "_");
baseName = regexprep(baseName, "^_+|_+$", "");

outputName = baseName + ".csv";
end
