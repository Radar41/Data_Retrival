classdef FileSha256Test < matlab.unittest.TestCase
    %FILESHA256TEST file_sha256 hashes the file's bytes.
    %
    % Regression test: until 2026-11-12, register_raw_dataset and
    % normalize_fred_datalist_to_destination read files through
    % java.io.InputStream.read into a MATLAB int8 buffer. MATLAB passes that
    % buffer to Java by value, so it stayed all zeros and every recorded
    % SHA-256 was the digest of N zero bytes (N = file size). Both functions
    % now call file_sha256.

    methods (TestClassSetup)
        function addSource(testCase)
            import matlab.unittest.fixtures.PathFixture
            root = fileparts(fileparts(fileparts(mfilename("fullpath"))));
            testCase.applyFixture(PathFixture(fullfile(root, "src")));
        end
    end

    methods (Test)

        function matchesPublishedTestVectors(testCase)
            % FIPS 180-2 vectors: "abc" and the empty message.
            testCase.verifyEqual(file_sha256(testCase.writeBytes(uint8('abc'))), ...
                'ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad');
            testCase.verifyEqual(file_sha256(testCase.writeBytes(zeros(1, 0, "uint8"))), ...
                'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855');
        end

        function dependsOnContentNotJustLength(testCase)
            % The old bug gave every file of the same size the same digest.
            counting = file_sha256(testCase.writeBytes(uint8(0:254)));
            zeroFilled = file_sha256(testCase.writeBytes(zeros(1, 255, "uint8")));
            testCase.verifyNotEqual(counting, zeroFilled);
        end

        function hashesAcrossReadChunks(testCase)
            % 8 MiB + 3 bytes spans two 8 MiB fread chunks. Bytes cycle 0..250;
            % the expected digest was computed independently with Python hashlib.
            n = 8 * 1024 * 1024 + 3;
            bytes = uint8(mod(0:(n - 1), 251));
            testCase.verifyEqual(file_sha256(testCase.writeBytes(bytes)), ...
                'ee63efa194650eff0863c7e4be539e27520ca99f4b63cda269c7c1509e90bcaa');
        end

    end

    methods (Access = private)
        function path = writeBytes(testCase, bytes)
            import matlab.unittest.fixtures.TemporaryFolderFixture
            folder = testCase.applyFixture(TemporaryFolderFixture);
            path = fullfile(folder.Folder, "bytes.bin");
            fileID = fopen(path, "w");
            testCase.assertNotEqual(fileID, -1, "Could not create " + path);
            fwrite(fileID, bytes, "uint8");
            fclose(fileID);
        end
    end

end
