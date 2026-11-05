classdef NaiveAdapterPayloadTest < matlab.unittest.TestCase
    %NAIVEADAPTERPAYLOADTEST The fit payload of the naive random-walk adapter
    % carries the full uncertainty contract.
    %
    % Regression test: commit ab38d13 spliced two assignments into one line
    % (`parameter_covariance_refefitPayload.parameter_covariance = []`), so
    % the payload silently lost parameter_covariance and
    % parameter_covariance_reference while every end-to-end test still
    % passed. The contract is now checked field by field.

    properties (Constant)
        UncertaintyFields = [ ...
            "parameter_covariance", "parameter_covariance_status", ...
            "parameter_covariance_reference", ...
            "parameter_standard_error", "parameter_standard_error_status", ...
            "parameter_standard_error_reference"]
    end

    methods (TestClassSetup)
        function addSource(testCase)
            import matlab.unittest.fixtures.PathFixture
            root = fileparts(fileparts(fileparts(mfilename("fullpath"))));
            testCase.applyFixture(PathFixture(fullfile(root, "src")));
        end
    end

    methods (Test)

        function fitPayloadHasEveryUncertaintyField(testCase)
            adapter = gdss.AnalyticalNaiveRandomWalkAdapter(struct("adapter_id", "analytical.naive_random_walk"));
            trainingData = struct("target_values", (1:10)', ...
                "target_times", datetime(2020, 1, 1) + caldays(0:9)');
            payload = adapter.fit(trainingData, struct());

            for f = testCase.UncertaintyFields
                testCase.verifyTrue(isfield(payload, f), "Missing payload field: " + f);
            end

            testCase.verifyEqual(payload.parameter_covariance_status, "NOT_AVAILABLE");
            testCase.verifyEqual(payload.parameter_standard_error_status, "NOT_AVAILABLE");
            testCase.verifyEqual(payload.parameter_covariance_reference, "");
            testCase.verifyEqual(payload.parameter_standard_error_reference, "");
            testCase.verifyEmpty(payload.parameter_covariance);
            testCase.verifyEmpty(payload.parameter_standard_error);

            % No field name may carry the splice: a nested struct where a
            % value belongs is exactly what the garbled line produced.
            testCase.verifyFalse(any(contains(fieldnames(payload), "refefitPayload")));
        end

    end

end
