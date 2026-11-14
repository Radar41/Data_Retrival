classdef test_matlab_lsboost_adapter < matlab.unittest.TestCase
    %TEST_MATLAB_LSBOOST_ADAPTER The LSBoost lag-tree adapter fits
    % deterministically, forecasts recursively from the tail of
    % fitPayload.training_values, and leaves the global rng untouched.

    methods (TestClassSetup)
        function addSource(testCase)
            import matlab.unittest.fixtures.PathFixture
            root = fileparts(fileparts(fileparts(mfilename("fullpath"))));
            testCase.applyFixture(PathFixture(fullfile(root, "src")));
        end
    end

    methods (Static)

        function config = baseConfig(varargin)
            config = struct( ...
                "adapter_id", "matlab.ml.lsboost", ...
                "target_transform", "identity", ...
                "forecast_strategy", "recursive", ...
                "forecast_scale", "LEVEL", ...
                "prediction_interval_levels", [0.80 0.95]);
            for i = 1:2:numel(varargin)
                config.(varargin{i}) = varargin{i + 1};
            end
        end

        function y = randomWalk(n, seed)
            stream = RandStream("mt19937ar", "Seed", seed);
            y = 100 + cumsum(randn(stream, n, 1));
        end

        function payload = fitSeries(adapter, y)
            payload = adapter.fit(struct("target_values", y), struct());
        end

        function payload = forecastHorizons(adapter, fitPayload, n)
            payload = adapter.forecast(fitPayload, struct("horizon", (1:n)'));
        end

    end

    methods (Test)

        function refitIsDeterministic(testCase)
            y = test_matlab_lsboost_adapter.randomWalk(300, 1);
            adapter = gdss.MatlabLsboostAdapter(test_matlab_lsboost_adapter.baseConfig());

            first = test_matlab_lsboost_adapter.fitSeries(adapter, y);
            second = test_matlab_lsboost_adapter.fitSeries(adapter, y);

            testCase.verifyEqual(second.in_sample_fitted_values, first.in_sample_fitted_values);
            testCase.verifyEqual(second.in_sample_residuals, first.in_sample_residuals);

            probe = randn(RandStream("mt19937ar", "Seed", 2), 50, 12) + 100;
            testCase.verifyEqual(predict(second.estimated_model, probe), ...
                predict(first.estimated_model, probe));

            f1 = test_matlab_lsboost_adapter.forecastHorizons(adapter, first, 21);
            f2 = test_matlab_lsboost_adapter.forecastHorizons(adapter, second, 21);
            testCase.verifyEqual(f2.point_forecast, f1.point_forecast);
            testCase.verifyEqual(f2.forecast_variance, f1.forecast_variance);
            testCase.verifyEqual(f2.interval_lower, f1.interval_lower);
        end

        function fitPayloadReportsFixedHyperparameters(testCase)
            y = test_matlab_lsboost_adapter.randomWalk(300, 3);
            adapter = gdss.MatlabLsboostAdapter(test_matlab_lsboost_adapter.baseConfig());
            payload = test_matlab_lsboost_adapter.fitSeries(adapter, y);

            testCase.verifyEqual(payload.status, "COMPLETE");
            testCase.verifyEqual(payload.convergence_status, "BACKEND_OUTPUT_AVAILABLE");
            testCase.verifyTrue(all(payload.parameter_table.parameter_role == "fixed"));
            testCase.verifyEqual(payload.parameter_covariance_status, "NOT_AVAILABLE");
            testCase.verifyEqual(payload.parameter_standard_error_status, "NOT_AVAILABLE");
            testCase.verifyEmpty(payload.parameter_covariance);
            testCase.verifyEqual(payload.training_values, y);
            testCase.verifyEqual(numel(payload.in_sample_residuals), 300 - 12);
            testCase.verifyEqual(payload.iterations, 200);
        end

        function forecastHasRequestedContiguousLength(testCase)
            y = test_matlab_lsboost_adapter.randomWalk(300, 4);
            adapter = gdss.MatlabLsboostAdapter(test_matlab_lsboost_adapter.baseConfig());
            fitPayload = test_matlab_lsboost_adapter.fitSeries(adapter, y);

            payload = test_matlab_lsboost_adapter.forecastHorizons(adapter, fitPayload, 21);

            testCase.verifyEqual(payload.status, "COMPLETE");
            testCase.verifyEqual(payload.horizon, (1:21)');
            testCase.verifySize(payload.point_forecast, [21 1]);
            testCase.verifySize(payload.forecast_variance, [21 1]);
            testCase.verifySize(payload.interval_lower, [21 2]);
            testCase.verifySize(payload.interval_upper, [21 2]);
            testCase.verifyTrue(all(payload.point_forecast_status == "AVAILABLE"));
            testCase.verifyTrue(all(payload.forecast_distribution_status == "AVAILABLE"));
            testCase.verifyTrue(all(payload.prediction_interval_status == "AVAILABLE"));
            testCase.verifyTrue(all(payload.forecast_distribution_method == ...
                "residual_bootstrap_recursive"));
            testCase.verifyTrue(all(payload.interval_lower(:, 2) <= payload.interval_lower(:, 1)));
            testCase.verifyTrue(all(payload.interval_upper(:, 2) >= payload.interval_upper(:, 1)));

            testCase.verifyError(@() adapter.forecast(fitPayload, ...
                struct("horizon", [1; 3])), ?MException);
            testCase.verifyError(@() adapter.forecast(fitPayload, ...
                struct("horizon", (2:5)')), ?MException);
        end

        function forecastUsesTailOfTrainingValues(testCase)
            y = test_matlab_lsboost_adapter.randomWalk(320, 5);
            adapter = gdss.MatlabLsboostAdapter(test_matlab_lsboost_adapter.baseConfig());
            fitPayload = test_matlab_lsboost_adapter.fitSeries(adapter, y(1:300));

            base = test_matlab_lsboost_adapter.forecastHorizons(adapter, fitPayload, 21);

            % A later origin: the same ensemble, a longer y.
            extended = fitPayload;
            extended.training_values = y;
            later = test_matlab_lsboost_adapter.forecastHorizons(adapter, extended, 21);

            testCase.verifyEqual(extended.estimated_model, fitPayload.estimated_model);
            testCase.verifyNotEqual(later.point_forecast, base.point_forecast);

            % Its forecast equals a forecast from only the last boost_lags values.
            tailOnly = fitPayload;
            tailOnly.training_values = y((end - 11):end);
            fromTail = test_matlab_lsboost_adapter.forecastHorizons(adapter, tailOnly, 21);
            testCase.verifyEqual(fromTail.point_forecast, later.point_forecast);

            % Changing values older than the lag window changes nothing.
            olderChanged = extended;
            olderChanged.training_values(1:100) = 0;
            unchanged = test_matlab_lsboost_adapter.forecastHorizons(adapter, olderChanged, 21);
            testCase.verifyEqual(unchanged.point_forecast, later.point_forecast);

            % Changing the newest value changes the forecast.
            tailChanged = extended;
            tailChanged.training_values(end) = tailChanged.training_values(end) + 10;
            changed = test_matlab_lsboost_adapter.forecastHorizons(adapter, tailChanged, 21);
            testCase.verifyNotEqual(changed.point_forecast(1), later.point_forecast(1));
        end

        function oneStepErrorIsSmallOnNoiselessSeries(testCase)
            % Noiseless deterministic AR recursion (a sinusoid with a
            % non-integer period): the lags determine the next value.
            t = (1:300)';
            y = 50 + 10 * sin(2 * pi * t / 23.7);
            adapter = gdss.MatlabLsboostAdapter(test_matlab_lsboost_adapter.baseConfig());
            fitPayload = test_matlab_lsboost_adapter.fitSeries(adapter, y(1:299));

            payload = test_matlab_lsboost_adapter.forecastHorizons(adapter, fitPayload, 1);

            testCase.verifyLessThan(abs(payload.point_forecast - y(300)), 0.5);
        end

        function differenceTargetExtrapolatesLinearTrend(testCase)
            t = (1:200)';
            y = 2 + 0.5 * t;
            adapter = gdss.MatlabLsboostAdapter(test_matlab_lsboost_adapter.baseConfig( ...
                "boost_target", "difference"));
            fitPayload = test_matlab_lsboost_adapter.fitSeries(adapter, y);

            payload = test_matlab_lsboost_adapter.forecastHorizons(adapter, fitPayload, 21);

            testCase.verifyEqual(payload.point_forecast, y(end) + 0.5 * (1:21)', ...
                "AbsTol", 1e-8);

            % The level target cannot leave the range of the training values.
            levelAdapter = gdss.MatlabLsboostAdapter(test_matlab_lsboost_adapter.baseConfig());
            levelFit = test_matlab_lsboost_adapter.fitSeries(levelAdapter, y);
            levelForecast = test_matlab_lsboost_adapter.forecastHorizons(levelAdapter, levelFit, 21);
            testCase.verifyLessThanOrEqual(max(levelForecast.point_forecast), max(y));
        end

        function bootstrapVarianceGrowsOnRandomWalk(testCase)
            y = test_matlab_lsboost_adapter.randomWalk(300, 6);
            adapter = gdss.MatlabLsboostAdapter(test_matlab_lsboost_adapter.baseConfig( ...
                "boost_target", "difference"));
            fitPayload = test_matlab_lsboost_adapter.fitSeries(adapter, y);

            payload = test_matlab_lsboost_adapter.forecastHorizons(adapter, fitPayload, 21);
            v = payload.forecast_variance;

            testCase.verifyGreaterThan(v(1), 0);
            testCase.verifyGreaterThan(v(end), 5 * v(1));
            testCase.verifyGreaterThanOrEqual(mean(diff(v) >= 0), 0.8);
        end

        function globalRngStateIsRestored(testCase)
            y = test_matlab_lsboost_adapter.randomWalk(300, 7);
            adapter = gdss.MatlabLsboostAdapter(test_matlab_lsboost_adapter.baseConfig());
            fitPayload = test_matlab_lsboost_adapter.fitSeries(adapter, y);

            previous = rng;
            testCase.addTeardown(@() rng(previous));

            rng(12345, "twister");
            before = rng;
            first = test_matlab_lsboost_adapter.forecastHorizons(adapter, fitPayload, 21);
            testCase.verifyEqual(rng, before);

            % A different caller state gives the same seeded bootstrap.
            rng(999, "twister");
            second = test_matlab_lsboost_adapter.forecastHorizons(adapter, fitPayload, 21);
            testCase.verifyEqual(second.forecast_variance, first.forecast_variance);
        end

        function validateEnforcesMinimumTrainingLength(testCase)
            config = test_matlab_lsboost_adapter.baseConfig("boost_lags", 12);
            adapter = gdss.MatlabLsboostAdapter(config);
            minimum = 12 + max(30, 3 * 12);

            short = adapter.validate(struct("target_dimension", 1, ...
                "training_observation_count", minimum - 1));
            enough = adapter.validate(struct("target_dimension", 1, ...
                "training_observation_count", minimum));

            testCase.verifyEqual(short.status, "INSUFFICIENT_TRAINING_DATA");
            testCase.verifyEqual(enough.status, "VALID");
            testCase.verifyEqual(enough.required_minimum_training_observations, minimum);

            fewLags = gdss.MatlabLsboostAdapter(test_matlab_lsboost_adapter.baseConfig( ...
                "boost_lags", 4));
            testCase.verifyEqual(fewLags.validate(struct("target_dimension", 1, ...
                "training_observation_count", 34)).status, "VALID");
            testCase.verifyEqual(fewLags.validate(struct("target_dimension", 1, ...
                "training_observation_count", 33)).status, "INSUFFICIENT_TRAINING_DATA");

            bad = gdss.MatlabLsboostAdapter(test_matlab_lsboost_adapter.baseConfig( ...
                "boost_target", "log"));
            testCase.verifyEqual(bad.validate(struct("target_dimension", 1, ...
                "training_observation_count", 300)).status, "INVALID_CONFIGURATION");

            noStrategy = gdss.MatlabLsboostAdapter(rmfield(config, "forecast_strategy"));
            testCase.verifyEqual(noStrategy.validate(struct("target_dimension", 1, ...
                "training_observation_count", 300)).status, "UNSUPPORTED_FORECAST_STRATEGY");
        end

    end

end
