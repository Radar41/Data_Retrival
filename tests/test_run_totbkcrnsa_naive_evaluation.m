function tests = test_run_totbkcrnsa_naive_evaluation
tests = functiontests(localfunctions);
end

function testCompleteEvaluationRun(testCase)

projectRoot = fileparts(fileparts(mfilename("fullpath")));

addpath(fullfile(projectRoot, "src"));

config = totbkcrnsa_naive_evaluation_config(string(projectRoot));

evaluationRun = run_totbkcrnsa_naive_evaluation(config);

verifyEqual(testCase, string(evaluationRun.record_type), ...
    "EVALUATION_RUN");

verifyEqual(testCase, string(evaluationRun.status), ...
    "COMPLETE");

verifyEqual(testCase, evaluationRun.origin_index, 2539);

verifyEqual(testCase, evaluationRun.origin_time, ...
    datetime(2021, 8, 25));

verifyEqual(testCase, evaluationRun.horizon_count, 260);

verifyEqual(testCase, evaluationRun.first_horizon, 1);

verifyEqual(testCase, evaluationRun.last_horizon, 260);

verifyEqual(testCase, numel(evaluationRun.forecast_leaves), 260);

verifyEqual(testCase, ...
    evaluationRun.forecast_realization.point_forecast, ...
    repmat(15753.887, 260, 1), ...
    "AbsTol", 1e-9);

verifyEqual(testCase, ...
    evaluationRun.forecast_scorecard.mean_absolute_error, ...
    2034.7961769230769, ...
    "AbsTol", 1e-9);

verifyEqual(testCase, ...
    evaluationRun.forecast_scorecard.root_mean_squared_error, ...
    2232.486026315147, ...
    "AbsTol", 1e-9);

leafErrors = [evaluationRun.forecast_leaves.forecast_error]';
leafAbsoluteErrors = [evaluationRun.forecast_leaves.absolute_error]';
leafSquaredErrors = [evaluationRun.forecast_leaves.squared_error]';

verifyEqual(testCase, ...
    evaluationRun.forecast_scorecard.mean_error, ...
    mean(leafErrors), ...
    "AbsTol", 1e-9);

verifyEqual(testCase, ...
    evaluationRun.forecast_scorecard.mean_absolute_error, ...
    mean(leafAbsoluteErrors), ...
    "AbsTol", 1e-9);

verifyEqual(testCase, ...
    evaluationRun.forecast_scorecard.root_mean_squared_error, ...
    sqrt(mean(leafSquaredErrors)), ...
    "AbsTol", 1e-9);

verifyTrue(testCase, all(leafErrors > 0));

verifyEqual(testCase, sum(leafErrors > 0), 260);

end

function testGenericEvaluatorMatchesNaiveReference(testCase)

projectRoot = fileparts(fileparts(mfilename("fullpath")));

addpath(fullfile(projectRoot, "src"));

config = totbkcrnsa_naive_evaluation_config(string(projectRoot));

referenceRun = run_totbkcrnsa_naive_evaluation(config);
genericRun = run_gdss_evaluation(config);

verifyEqual(testCase, ...
    string(genericRun.record_type), ...
    "EVALUATION_RUN");

verifyEqual(testCase, ...
    string(genericRun.status), ...
    "COMPLETE");

verifyEqual(testCase, ...
    genericRun.origin_index, ...
    referenceRun.origin_index);

verifyEqual(testCase, ...
    genericRun.origin_time, ...
    referenceRun.origin_time);

verifyEqual(testCase, ...
    genericRun.horizon_count, ...
    referenceRun.horizon_count);

verifyEqual(testCase, ...
    genericRun.first_horizon, ...
    referenceRun.first_horizon);

verifyEqual(testCase, ...
    genericRun.last_horizon, ...
    referenceRun.last_horizon);

verifyEqual(testCase, ...
    genericRun.forecast_realization.point_forecast, ...
    referenceRun.forecast_realization.point_forecast, ...
    "AbsTol", 1e-9);

verifyEqual(testCase, ...
    genericRun.forecast_scorecard.mean_absolute_error, ...
    referenceRun.forecast_scorecard.mean_absolute_error, ...
    "AbsTol", 1e-9);

verifyEqual(testCase, ...
    genericRun.forecast_scorecard.root_mean_squared_error, ...
    referenceRun.forecast_scorecard.root_mean_squared_error, ...
    "AbsTol", 1e-9);

verifyEqual(testCase, ...
    [genericRun.forecast_leaves.forecast_error]', ...
    [referenceRun.forecast_leaves.forecast_error]', ...
    "AbsTol", 1e-9);

end

function testRejectsOriginWithoutHoldout(testCase)

projectRoot = fileparts(fileparts(mfilename("fullpath")));

addpath(fullfile(projectRoot, "src"));

config = totbkcrnsa_naive_evaluation_config(string(projectRoot));

% The series has 2,799 rows, so index 2,799 leaves no holdout.
config.origin_index = 2799;

didThrow = false;
caughtMessage = "";

try
    run_totbkcrnsa_naive_evaluation(config);
catch ME
    didThrow = true;
    caughtMessage = string(ME.message);
end

verifyTrue(testCase, didThrow, ...
    "An origin with no held-out rows must be rejected.");

verifyTrue(testCase, contains(caughtMessage, ...
    "origin_index must leave at least one held-out observation"), ...
    "The rejection error did not identify the no-holdout origin condition.");

end

function testRejectsNonIdentityTransform(testCase)

projectRoot = fileparts(fileparts(mfilename("fullpath")));

addpath(fullfile(projectRoot, "src"));

config = totbkcrnsa_naive_evaluation_config(string(projectRoot));

% This function's baseline adapter is deliberately identity-only.
config.target_transform = "log";

didThrow = false;
caughtMessage = "";

try
    run_totbkcrnsa_naive_evaluation(config);
catch ME
    didThrow = true;
    caughtMessage = string(ME.message);
end

verifyTrue(testCase, didThrow, ...
    "A non-identity target transform must be rejected.");

verifyTrue(testCase, contains(caughtMessage, ...
    "This function requires the identity target transform."), ...
    "The rejection error did not identify the transform requirement.");

end

function testFactoryCreatesNaiveAdapter(testCase)
projectRoot = fileparts(fileparts(mfilename("fullpath")));
addpath(fullfile(projectRoot, "src"));

config = totbkcrnsa_naive_evaluation_config(string(projectRoot));
adapter = gdss.create_model_adapter(config);

verifyClass(testCase, adapter, ...
    "gdss.AnalyticalNaiveRandomWalkAdapter");
end