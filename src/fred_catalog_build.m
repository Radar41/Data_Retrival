function catalog = fred_catalog_build()
%FRED_CATALOG_BUILD Build a reproducible FRED root-category catalog snapshot.
%
% catalog = fred_catalog_build()
%
% Dependencies:
%   fred_api_request.m
%
% The function:
%   1. Retrieves FRED root categories from category/children, category_id=0.
%   2. Preserves the unmodified API response as JSON.
%   3. Writes a normalized CSV suitable for Neo4j LOAD CSV.
%   4. Writes metadata describing the retrieval.
%
% This initial version intentionally imports only root categories.
% Recursive category ingestion is the next catalog-development step.

proj = currentProject;
root = proj.RootFolder;

retrievedAtUTC = datetime("now", "TimeZone", "UTC");
snapshotID = string(retrievedAtUTC, "yyyy-MM-dd'T'HH-mm-ss'Z'");

snapshotDirectory = fullfile( ...
    root, "data", "catalog", "fred", "snapshots", char(snapshotID));

neo4jImportDirectory = fullfile( ...
    root, "data", "catalog", "neo4j-import");

if ~isfolder(snapshotDirectory)
    mkdir(snapshotDirectory);
end

if ~isfolder(neo4jImportDirectory)
    mkdir(neo4jImportDirectory);
end

requestParameters = struct("category_id", 0);

response = fred_api_request( ...
    "category/children", ...
    requestParameters);

if ~isfield(response, "categories")
    error("Data_Retrival:FRED:CatalogResponseInvalid", ...
        "FRED category response did not contain a categories field.");
end

categories = response.categories;
n = numel(categories);

providerID = repmat("fred", n, 1);
categoryID = string(reshape([categories.id], [], 1));
categoryName = string(reshape({categories.name}, [], 1));
parentID = string(reshape([categories.parent_id], [], 1));

categoriesTable = table( ...
    providerID, ...
    categoryID, ...
    categoryName, ...
    parentID, ...
    VariableNames = ["provider_id", "category_id", "name", "parent_id"]);

rawResponseFile = fullfile( ...
    snapshotDirectory, "response.json");

localWriteJson(rawResponseFile, response);

categoriesSnapshotFile = fullfile( ...
    snapshotDirectory, "fred_root_categories.csv");

writetable(categoriesTable, categoriesSnapshotFile);

neo4jCategoriesFile = fullfile( ...
    neo4jImportDirectory, "fred_root_categories.csv");

writetable(categoriesTable, neo4jCategoriesFile);

manifest = struct;
manifest.provider_id = "fred";
manifest.provider_name = "Federal Reserve Economic Data";
manifest.snapshot_id = snapshotID;
manifest.retrieved_at_utc = string(retrievedAtUTC, ...
    "yyyy-MM-dd'T'HH:mm:ss'Z'");
manifest.endpoint = "category/children";
manifest.request_parameters = requestParameters;
manifest.category_count = n;
manifest.raw_response_file = "response.json";
manifest.normalized_categories_file = "fred_root_categories.csv";
manifest.neo4j_import_file = string(neo4jCategoriesFile);
manifest.matlab_version = version;
manifest.project_root = string(root);

manifestFile = fullfile( ...
    snapshotDirectory, "catalog_manifest.json");

localWriteJson(manifestFile, manifest);

catalog = struct;
catalog.ProviderID = "fred";
catalog.SnapshotID = snapshotID;
catalog.RetrievedAtUTC = retrievedAtUTC;
catalog.SnapshotDirectory = string(snapshotDirectory);
catalog.RawResponseFile = string(rawResponseFile);
catalog.ManifestFile = string(manifestFile);
catalog.Neo4jImportFile = string(neo4jCategoriesFile);
catalog.RootCategories = categoriesTable;

fprintf("FRED catalog snapshot created.\n");
fprintf("Snapshot ID: %s\n", snapshotID);
fprintf("Categories: %d\n", n);
fprintf("Snapshot: %s\n", snapshotDirectory);
fprintf("Neo4j CSV: %s\n", neo4jCategoriesFile);

end

function localWriteJson(filename, value)
fid = fopen(filename, "w");

if fid == -1
    error("Data_Retrival:FileWriteFailed", ...
        "Could not open '%s' for writing.", filename);
end

cleanup = onCleanup(@() fclose(fid));
fwrite(fid, jsonencode(value, PrettyPrint = true), "char");
end