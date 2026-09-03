 function manifest = register_raw_dataset(rawFile, options)
%REGISTER_RAW_DATASET Register a downloaded raw dataset with provenance.
%
% manifest = register_raw_dataset(rawFile, Name=Value)
%
% Example:
% manifest = register_raw_dataset( ...
%     fullfile(userpath, "fred_datalist_11923.csv"), ...
%     ProviderID = "fred", ...
%     DatasetID = "fred_datalist_11923", ...
%     SourceURL = "https://fredaccount.stlouisfed.org/public/datalist/11923", ...
%     Notes = "Published FRED data list download; raw file unchanged.");
%
% The function copies the supplied source file into data/raw/<provider>/,
% calculates a SHA-256 digest, and writes an auditable JSON manifest.

arguments
    rawFile (1,1) string {mustBeFile}

    options.ProviderID (1,1) string = "manual"
    options.DatasetID (1,1) string {mustBeNonempty} = "unnamed_dataset"
    options.SourceURL (1,1) string = missing
    options.Notes (1,1) string = ""
    options.CopyIntoProject (1,1) logical = true
end

root = currentProject().RootFolder;

providerID = lower(regexprep(options.ProviderID, "[^a-zA-Z0-9_-]", "_"));
datasetID = regexprep(options.DatasetID, "[^a-zA-Z0-9_-]", "_");

rawDirectory = fullfile(root, "data", "raw", providerID);
manifestDirectory = fullfile(root, "data", "manifests", "incoming");

if ~isfolder(rawDirectory)
    mkdir(rawDirectory);
end

if ~isfolder(manifestDirectory)
    mkdir(manifestDirectory);
end

[~, originalBaseName, originalExtension] = fileparts(rawFile);

registeredAt = datetime("now", TimeZone="UTC");
timestamp = string(registeredAt, "yyyy-MM-dd'T'HHmmss'Z'");

destinationFileName = ...
    timestamp + "_" + datasetID + "_" + originalBaseName + originalExtension;

destinationFile = fullfile(rawDirectory, destinationFileName);

if options.CopyIntoProject
    copyfile(rawFile, destinationFile, "f");
else
    destinationFile = rawFile;
end

fileInfo = dir(destinationFile);

sha256 = compute_sha256(destinationFile);

manifest = struct( ...
    "provider_id", providerID, ...
    "dataset_id", datasetID, ...
    "source_url", options.SourceURL, ...
    "notes", options.Notes, ...
    "registered_at_utc", string(registeredAt), ...
    "original_file_name", string(originalBaseName + originalExtension), ...
    "raw_file_name", string(destinationFileName), ...
    "raw_file_path", string(destinationFile), ...
    "raw_file_bytes", fileInfo.bytes, ...
    "raw_file_sha256", sha256, ...
    "copy_into_project", options.CopyIntoProject, ...
    "ingestion_status", "registered");

manifestFileName = timestamp + "_" + datasetID + ".json";
manifestFile = fullfile(manifestDirectory, manifestFileName);

write_text_file( ...
    manifestFile, ...
    jsonencode(manifest, PrettyPrint=true));

fprintf("Raw dataset registered.\n");
fprintf("Provider: %s\n", providerID);
fprintf("Dataset ID: %s\n", datasetID);
fprintf("Raw file: %s\n", destinationFile);
fprintf("Manifest: %s\n", manifestFile);
fprintf("SHA-256: %s\n", sha256);

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