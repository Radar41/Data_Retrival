function result = fred_pull(seriesID, options)
%FRED_PULL Retrieve one FRED series and preserve retrieval provenance.
%
% result = fred_pull(seriesID)
% result = fred_pull(seriesID, options)
%
% Inputs
%   seriesID : FRED series identifier, for example "GDP", "CPIAUCSL",
%              "UNRATE", or "DEXUSEU".
%   options  : optional structure with fields:
%       StartDate  - datetime or string, optional
%       EndDate    - datetime or string, optional
%       ApiKey     - FRED API key. If omitted, reads FRED_API_KEY from
%                    the MATLAB environment.
%       SaveRaw    - logical; save raw response and metadata. Default true
%
% Output
%   result : structure containing:
%       SeriesID
%       RetrievedAtUTC
%       RequestURL
%       Observations
%       RawResponse
%       OutputDirectory
%
% This function is MATLAB-only. It is intentionally not a MATLAB Coder
% entry point because it performs HTTPS retrieval and persistent I/O.

arguments
    seriesID (1,1) string
    options.StartDate = ""
    options.EndDate = ""
    options.ApiKey (1,1) string = ""
    options.SaveRaw (1,1) logical = true
end

if strlength(seriesID) == 0
    error("Data_Retrival:FRED:MissingSeriesID", ...
        "seriesID must be a nonempty FRED series identifier.");
end

apiKey = options.ApiKey;

if strlength(apiKey) == 0
    apiKey = string(getenv("MYFREDKey"));
end

if strlength(apiKey) == 0
    error("Data_Retrival:FRED:MissingApiKey", ...
        ["No FRED API key was provided. Set the FRED_API_KEY environment ", ...
         "variable or pass options.ApiKey. Do not save API keys in source code."]);
end

baseURL = "https://api.stlouisfed.org/fred/series/observations";

query = struct;
query.series_id = char(seriesID);
query.api_key = char(apiKey);
query.file_type = "json";

if strlength(string(options.StartDate)) > 0
    query.observation_start = char(string(options.StartDate));
end

if strlength(string(options.EndDate)) > 0
    query.observation_end = char(string(options.EndDate));
end

requestURL = baseURL + "?" + localEncodeQuery(query);
requestOptions = weboptions( ...
    "ContentType", "json", ...
    "Timeout", 60);

try
    rawResponse = webread(requestURL, requestOptions);
catch exception
    throwAsCaller(MException("Data_Retrival:FRED:RequestFailed", ...
        "FRED request failed for series '%s': %s", ...
        seriesID, exception.message));
end

if ~isfield(rawResponse, "observations")
    error("Data_Retrival:FRED:UnexpectedResponse", ...
        "FRED returned no observations field for series '%s'.", seriesID);
end

observationData = rawResponse.observations;
n = numel(observationData);

dates = NaT(n, 1, "TimeZone", "UTC");
values = nan(n, 1);

for k = 1:n
    dates(k) = datetime(observationData(k).date, ...
        "InputFormat", "yyyy-MM-dd", ...
        "TimeZone", "UTC");

    valueText = string(observationData(k).value);

    if valueText ~= "."
        values(k) = str2double(valueText);
    end
end

observations = timetable(dates, values, ...
    "VariableNames", "Value");
observations.Properties.DimensionNames{1} = "Date";

retrievedAtUTC = datetime("now", "TimeZone", "UTC");
outputDirectory = "";

if options.SaveRaw
    proj = currentProject;
    root = proj.RootFolder;

    runID = replace(string(retrievedAtUTC, ...
        "yyyy-MM-dd'T'HH-mm-ss'Z'"), ":", "-");

    outputDirectory = fullfile( ...
        root, "data", "raw", "fred", char(seriesID), char(runID));

    mkdir(outputDirectory);

    writetimetable(observations, ...
        fullfile(outputDirectory, "observations.csv"));

    metadata = struct;
    metadata.series_id = seriesID;
    metadata.retrieved_at_utc = string(retrievedAtUTC, ...
        "yyyy-MM-dd'T'HH:mm:ss'Z'");
    metadata.request_url_without_api_key = ...
        localRedactedURL(seriesID, options);
    metadata.observation_count = height(observations);
    metadata.missing_value_count = sum(isnan(observations.Value));
    metadata.matlab_version = version;
    metadata.output_directory = string(outputDirectory);

    metadataFile = fullfile(outputDirectory, "metadata.json");
    fid = fopen(metadataFile, "w");
    cleanup = onCleanup(@() fclose(fid));

    if fid == -1
        error("Data_Retrival:FRED:MetadataWriteFailed", ...
            "Could not write metadata file: %s", metadataFile);
    end

    fwrite(fid, jsonencode(metadata, PrettyPrint = true), "char");
end

result = struct;
result.SeriesID = seriesID;
result.RetrievedAtUTC = retrievedAtUTC;
result.RequestURL = localRedactedURL(seriesID, options);
result.Observations = observations;
result.RawResponse = rawResponse;
result.OutputDirectory = string(outputDirectory);

end

function queryText = localEncodeQuery(query)
names = fieldnames(query);
parts = strings(numel(names), 1);

for k = 1:numel(names)
    name = string(names{k});
    value = string(query.(names{k}));
    parts(k) = urlencode(name) + "=" + urlencode(value);
end

queryText = strjoin(parts, "&");
end

function redactedURL = localRedactedURL(seriesID, options)
baseURL = "https://api.stlouisfed.org/fred/series/observations";

parts = [
    "series_id=" + urlencode(seriesID)
    "file_type=json"
];

if strlength(string(options.StartDate)) > 0
    parts(end + 1) = "observation_start=" + ...
        urlencode(string(options.StartDate));
end

if strlength(string(options.EndDate)) > 0
    parts(end + 1) = "observation_end=" + ...
        urlencode(string(options.EndDate));
end

parts(end + 1) = "api_key=REDACTED";

redactedURL = baseURL + "?" + strjoin(parts, "&");
end