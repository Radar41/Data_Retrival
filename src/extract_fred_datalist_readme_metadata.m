function result = extract_fred_datalist_readme_metadata(manifest)
%EXTRACT_FRED_DATALIST_README_METADATA Parse fixed-width FRED list README.

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
    "This extractor requires provider_id = 'fred'.");
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

readmePath = fullfile(stagingDir, "README.txt");
csvPath = fullfile(stagingDir, "series_metadata.csv");
jsonPath = fullfile(stagingDir, "series_metadata.json");

assert(isfile(readmePath), ...
    "Expected staged README does not exist: %s", readmePath);

if isfile(csvPath)
    error("Refusing to overwrite existing metadata CSV: %s", csvPath);
end

if isfile(jsonPath)
    error("Refusing to overwrite existing metadata JSON: %s", jsonPath);
end

readmeText = fileread(readmePath);
readmeText = replace(readmeText, sprintf("\r\n"), sprintf("\n"));
readmeText = replace(readmeText, sprintf("\r"), sprintf("\n"));
lines = splitlines(string(readmeText));

headerRows = find(~cellfun(@isempty, regexp(cellstr(lines), ...
    '^Series ID\s+Real Time Start\s+Period End\s*$', 'once')));

assert(~isempty(headerRows), ...
    "No fixed-width FRED series headers found in README: %s", readmePath);

recordRows = headerRows + 1;
recordRows = recordRows(recordRows <= numel(lines));

nSeries = numel(recordRows);

seriesID = strings(nSeries, 1);
realTimeStart = strings(nSeries, 1);
periodEnd = strings(nSeries, 1);
title = strings(nSeries, 1);
source = strings(nSeries, 1);
release = strings(nSeries, 1);
unitsLevel = strings(nSeries, 1);
unitsCHG = strings(nSeries, 1);
unitsCH1 = strings(nSeries, 1);
unitsPCH = strings(nSeries, 1);
unitsPC1 = strings(nSeries, 1);
unitsPCA = strings(nSeries, 1);
unitsCCH = strings(nSeries, 1);
unitsCCA = strings(nSeries, 1);
unitsLOG = strings(nSeries, 1);
frequency = strings(nSeries, 1);
seasonalAdjustment = strings(nSeries, 1);
notes = strings(nSeries, 1);

fieldLabels = [ ...
    "Title"
    "Source"
    "Release"
    "Units"
    "Units (Columns matching *_CHG*)"
    "Units (Columns matching *_CH1*)"
    "Units (Columns matching *_PCH*)"
    "Units (Columns matching *_PC1*)"
    "Units (Columns matching *_PCA*)"
    "Units (Columns matching *_CCH*)"
    "Units (Columns matching *_CCA*)"
    "Units (Columns matching *_LOG*)"
    "Frequency"
    "Seasonal Adjustment"
    "Notes"];

for k = 1:nSeries
    if k < nSeries
        blockEnd = headerRows(k + 1) - 1;
    else
        blockEnd = numel(lines);
    end

    blockLines = lines(recordRows(k):blockEnd);

    [seriesID(k), realTimeStart(k), periodEnd(k)] = ...
        parse_record_header(blockLines(1));

    title(k) = extract_report_field(blockLines, "Title", fieldLabels);
    source(k) = extract_report_field(blockLines, "Source", fieldLabels);
    release(k) = extract_report_field(blockLines, "Release", fieldLabels);
    unitsLevel(k) = extract_report_field(blockLines, "Units", fieldLabels);
    unitsCHG(k) = extract_report_field( ...
        blockLines, "Units (Columns matching *_CHG*)", fieldLabels);
    unitsCH1(k) = extract_report_field( ...
        blockLines, "Units (Columns matching *_CH1*)", fieldLabels);
    unitsPCH(k) = extract_report_field( ...
        blockLines, "Units (Columns matching *_PCH*)", fieldLabels);
    unitsPC1(k) = extract_report_field( ...
        blockLines, "Units (Columns matching *_PC1*)", fieldLabels);
    unitsPCA(k) = extract_report_field( ...
        blockLines, "Units (Columns matching *_PCA*)", fieldLabels);
    unitsCCH(k) = extract_report_field( ...
        blockLines, "Units (Columns matching *_CCH*)", fieldLabels);
    unitsCCA(k) = extract_report_field( ...
        blockLines, "Units (Columns matching *_CCA*)", fieldLabels);
    unitsLOG(k) = extract_report_field( ...
        blockLines, "Units (Columns matching *_LOG*)", fieldLabels);
    frequency(k) = extract_report_field( ...
        blockLines, "Frequency", fieldLabels);
    seasonalAdjustment(k) = extract_report_field( ...
        blockLines, "Seasonal Adjustment", fieldLabels);
    notes(k) = extract_report_field(blockLines, "Notes", fieldLabels);
end

providerID = repmat("fred", nSeries, 1);
datasetID = repmat(string(manifest.dataset_id), nSeries, 1);
sourceDataListID = repmat("10578", nSeries, 1);
sourceDataListTitle = repmat("banks weekly", nSeries, 1);
sourceURL = repmat(string(manifest.source_url), nSeries, 1);
rawArchiveSHA256 = repmat(string(manifest.raw_file_sha256), nSeries, 1);
readmeMemberPath = repmat("README.txt", nSeries, 1);
metadataExtractedAtUTC = repmat(string(datetime( ...
    "now", ...
    TimeZone="UTC", ...
    Format="yyyy-MM-dd'T'HH:mm:ss'Z'")), nSeries, 1);

seriesMetadata = table( ...
    providerID, datasetID, sourceDataListID, sourceDataListTitle, ...
    sourceURL, rawArchiveSHA256, readmeMemberPath, ...
    seriesID, realTimeStart, periodEnd, title, source, release, ...
    unitsLevel, unitsCHG, unitsCH1, unitsPCH, unitsPC1, unitsPCA, ...
    unitsCCH, unitsCCA, unitsLOG, frequency, seasonalAdjustment, ...
    notes, metadataExtractedAtUTC, ...
    VariableNames=[ ...
        "provider_id"
        "dataset_id"
        "source_datalist_id"
        "source_datalist_title"
        "source_url"
        "raw_archive_sha256"
        "source_member_path"
        "series_id"
        "real_time_start"
        "period_end"
        "title"
        "source"
        "release"
        "units_level"
        "units_chg"
        "units_ch1"
        "units_pch"
        "units_pc1"
        "units_pca"
        "units_cch"
        "units_cca"
        "units_log"
        "frequency"
        "seasonal_adjustment"
        "notes"
        "metadata_extracted_at_utc"]);

assert(all(strlength(seriesMetadata.series_id) > 0), ...
    "At least one metadata row has an empty series_id.");

assert(numel(unique(seriesMetadata.series_id)) == height(seriesMetadata), ...
    "Duplicate series IDs found in parsed README metadata.");

assert(all(strlength(seriesMetadata.title) > 0), ...
    "At least one metadata row has an empty title.");

assert(all(strlength(seriesMetadata.frequency) > 0), ...
    "At least one metadata row has an empty frequency.");

writetable(seriesMetadata, csvPath);

jsonRecords = table2struct(seriesMetadata);
fid = fopen(jsonPath, "w");
assert(fid >= 0, "Could not open metadata JSON for writing: %s", jsonPath);
cleanup = onCleanup(@() fclose(fid));
fprintf(fid, "%s", jsonencode(jsonRecords, PrettyPrint=true));

fprintf("Parsed %d unique base-series metadata records.\n", ...
    height(seriesMetadata));
fprintf("Wrote: %s\n", csvPath);
fprintf("Wrote: %s\n", jsonPath);

result = struct( ...
    "staging_directory", string(stagingDir), ...
    "readme_path", string(readmePath), ...
    "series_metadata_path", string(csvPath), ...
    "series_metadata_json_path", string(jsonPath), ...
    "series_count", height(seriesMetadata));
end

function [seriesID, realTimeStart, periodEnd] = parse_record_header(line)

line = strtrim(line);

tokens = regexp(line, ...
    '^([A-Z0-9]+)\s+(\d{4}-\d{2}-\d{2})\s+(.+?)\s*$', ...
    'tokens', 'once');

assert(~isempty(tokens), ...
    "Could not parse FRED series record header: %s", line);

seriesID = string(tokens{1});
realTimeStart = string(tokens{2});
periodEnd = strtrim(string(tokens{3}));
end

function value = extract_report_field(blockLines, fieldLabel, allFieldLabels)

blockLines = string(blockLines);
fieldLabel = string(fieldLabel);
allFieldLabels = string(allFieldLabels);

trimmedLines = strtrim(blockLines);
fieldIndex = find(trimmedLines == fieldLabel, 1, "first");

if isempty(fieldIndex)
    value = "";
    return
end

nextFieldIndex = numel(blockLines) + 1;

for k = fieldIndex + 1:numel(blockLines)
    if any(trimmedLines(k) == allFieldLabels)
        nextFieldIndex = k;
        break
    end
end

valueLines = blockLines(fieldIndex + 1:nextFieldIndex - 1);
valueLines = strip_trailing_report_columns(valueLines);
valueLines = strtrim(valueLines);
valueLines = valueLines(valueLines ~= "");

value = strjoin(valueLines, " ");
value = regexprep(value, "\s+", " ");
value = strtrim(value);
end

function cleaned = strip_trailing_report_columns(lines)

cleaned = string(lines);

for k = 1:numel(cleaned)
    line = cleaned(k);

    line = regexprep(line, ...
        '\s+\d{4}-\d{2}-\d{2}\s+(Current|\d{4}-\d{2}-\d{2})\s*$', '');

    cleaned(k) = strtrim(line);
end
end
