function hash = file_sha256(filename)
%FILE_SHA256 SHA-256 digest of a file's bytes, as 64 lowercase hex characters.
%
% hash = file_sha256(filename)
%
% The file is read in MATLAB with fread, in 8 MiB chunks, and each chunk is
% passed to java.security.MessageDigest.
%
% Do not read through a Java InputStream into a MATLAB buffer instead:
% MATLAB passes arrays to Java by value, so InputStream.read(buffer, ...)
% fills a copy and the MATLAB buffer stays all zeros. The digest is then the
% SHA-256 of N zero bytes, where N is the file size. register_raw_dataset
% and normalize_fred_datalist_to_destination had exactly that bug until
% 2026-11-12, so manifests written before then record zero-buffer digests
% (for example bfaf1597... for the 2,589,365-byte banks_weekly.zip, whose
% real SHA-256 is 3b2f1c70...).

arguments
    filename (1,1) string {mustBeFile}
end

fileID = fopen(filename, "r");

if fileID == -1
    error("Data_Retrival:FileReadFailed", ...
        "Could not open file for reading: %s", filename);
end

cleanup = onCleanup(@() fclose(fileID));

digest = java.security.MessageDigest.getInstance("SHA-256");
chunkBytes = 8 * 1024 * 1024;

while true
    chunk = fread(fileID, chunkBytes, "*uint8");

    if isempty(chunk)
        break
    end

    digest.update(typecast(chunk.', "int8"));
end

hashBytes = typecast(digest.digest(), "uint8");
hash = lower(reshape(dec2hex(hashBytes, 2).', 1, []));
end
