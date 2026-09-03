function response = fred_api_request(endpoint, parameters)
%FRED_API_REQUEST Perform a validated FRED API Version 1 JSON request.
%
% response = fred_api_request(endpoint)
% response = fred_api_request(endpoint, parameters)
%
% endpoint   : API path without the leading slash, for example:
%              "category/children"
%              "releases"
%              "series/search"
%              "series/observations"
%
% parameters : optional scalar structure containing API query parameters.
%
% API credentials are read only from the FRED_API_KEY environment variable.
% No API key is written to output files or returned in this response.

arguments
    endpoint (1,1) string
    parameters (1,1) struct = struct
end

apiKey = string(getenv("FRED_API_KEY"));

apiKey = getSecret("MyFREDKey");

if strlength(apiKey) == 0
    error("Data_Retrival:FRED:MissingApiKey", ...
        "The MATLAB vault secret 'MyFREDKey' is unavailable.");
end

endpoint = strip(endpoint, "/");

if strlength(endpoint) == 0
    error("Data_Retrival:FRED:MissingEndpoint", ...
        "A FRED API endpoint is required.");
end

parameters.api_key = char(apiKey);
parameters.file_type = "json";

baseURL = "https://api.stlouisfed.org/fred/";
requestURL = baseURL + endpoint + "?" + localEncodeQuery(parameters);

requestOptions = weboptions( ...
    "ContentType", "json", ...
    "Timeout", 60);

try
    response = webread(requestURL, requestOptions);
catch exception
    throwAsCaller(MException( ...
        "Data_Retrival:FRED:RequestFailed", ...
        "FRED request failed for endpoint '%s': %s", ...
        endpoint, exception.message));
end

if isstruct(response) && isfield(response, "error_code")
    error("Data_Retrival:FRED:ApiError", ...
        "FRED API error at '%s': %s", ...
        endpoint, string(response.error_message));
end

end

function queryText = localEncodeQuery(parameters)
names = fieldnames(parameters);
parts = strings(numel(names), 1);

for k = 1:numel(names)
    name = string(names{k});
    value = string(parameters.(names{k}));

    parts(k) = localEncode(name) + "=" + localEncode(value);
end

queryText = strjoin(parts, "&");
end

function encoded = localEncode(value)
encoded = replace(string(value), "%", "%25");
encoded = replace(encoded, " ", "%20");
encoded = replace(encoded, "+", "%2B");
encoded = replace(encoded, "&", "%26");
encoded = replace(encoded, "=", "%3D");
encoded = replace(encoded, "/", "%2F");
encoded = replace(encoded, ":", "%3A");
encoded = replace(encoded, ",", "%2C");
end