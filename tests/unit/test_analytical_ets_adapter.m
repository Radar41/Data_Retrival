classdef test_analytical_ets_adapter < matlab.unittest.TestCase
    %TEST_ANALYTICAL_ETS_ADAPTER The ETS adapter validates its class and
    % data, fits by maximum likelihood with statuses taken from the
    % optimizer, and forecasts by re-running the state recursion from the
    % fitted initial states over fitPayload.training_values.

    methods (TestClassSetup)
        function addSource(testCase)
            import matlab.unittest.fixtures.PathFixture
            root = fileparts(fileparts(fileparts(mfilename("fullpath"))));
            testCase.applyFixture(PathFixture(fullfile(root, "src")));
        end
    end

    methods (Static)

        function config = baseConfig(errorType, trendType, seasonType, varargin)
            config = struct( ...
                "adapter_id", "analytical.ets", ...
                "target_transform", "identity", ...
                "forecast_strategy", "recursive", ...
                "forecast_scale", "LEVEL", ...
                "prediction_interval_levels", [0.80 0.95], ...
                "ets_error", errorType, ...
                "ets_trend", trendType, ...
                "ets_season", seasonType);
            for i = 1:2:numel(varargin)
                config.(varargin{i}) = varargin{i + 1};
            end
        end

        function dataContext = dataContext(n, varargin)
            dataContext = struct( ...
                "target_dimension", 1, ...
                "training_observation_count", n);
            for i = 1:2:numel(varargin)
                dataContext.(varargin{i}) = varargin{i + 1};
            end
        end

        function y = localLevelSeries(n, seed)
            stream = RandStream("mt19937ar", "Seed", seed);
            y = 50 + cumsum(0.5 * randn(stream, n, 1)) + randn(stream, n, 1);
        end

        function y = trendSeries(n, seed)
            stream = RandStream("mt19937ar", "Seed", seed);
            t = (1:n)';
            y = 20 + 0.3 * t + cumsum(0.2 * randn(stream, n, 1)) + ...
                0.5 * randn(stream, n, 1);
        end

        function [y, shape] = seasonalSeries(n, seed)
            stream = RandStream("mt19937ar", "Seed", seed);
            t = (1:n)';
            shape = 10 * sin(2 * pi * (1:12)' / 12) + 4 * cos(4 * pi * (1:12)' / 12);
            shape = shape - mean(shape);
            y = 100 + 0.4 * t + shape(mod(t - 1, 12) + 1) + randn(stream, n, 1);
        end

        function y = positiveSeasonalSeries(n, seed)
            stream = RandStream("mt19937ar", "Seed", seed);
            t = (1:n)';
            factor = 1 + 0.15 * sin(2 * pi * (1:12)' / 12);
            y = (200 + 0.8 * t) .* factor(mod(t - 1, 12) + 1) .* ...
                (1 + 0.01 * randn(stream, n, 1));
        end

        function f = aanObjective(q, y)
            alpha = q(1);
            beta = q(2);
            if alpha < 1e-4 || alpha > 0.9999 || beta < 1e-4 || beta > alpha
                f = 1e10;
                return
            end
            level = q(3);
            slope = q(4);
            sse = 0;
            for t = 1:numel(y)
                e = y(t) - (level + slope);
                sse = sse + e ^ 2;
                level = level + slope + alpha * e;
                slope = slope + beta * e;
            end
            f = log(sse / numel(y));
        end

        function payload = fitSeries(adapter, y)
            payload = adapter.fit(struct("target_values", y), struct());
        end

        function payload = forecastHorizons(adapter, fitPayload, n)
            payload = adapter.forecast(fitPayload, struct("horizon", (1:n)'));
        end

    end

    methods (Test)

        function validateAcceptsEveryClass(testCase)
            errors = ["A", "M"];
            trends = ["N", "A", "Ad"];
            seasons = ["N", "A", "M"];
            for e = errors
                for tr = trends
                    for s = seasons
                        adapter = gdss.AnalyticalEtsAdapter( ...
                            test_analytical_ets_adapter.baseConfig(e, tr, s));
                        validation = adapter.validate( ...
                            test_analytical_ets_adapter.dataContext(300, ...
                            "training_minimum_value", 1));
                        testCase.verifyEqual(validation.status, "VALID", ...
                            "ETS(" + e + "," + tr + "," + s + ")");
                        testCase.verifyEqual(validation.adapter_id, "analytical.ets");
                    end
                end
            end
        end

        function validateRejectsBadConfiguration(testCase)
            adapter = gdss.AnalyticalEtsAdapter( ...
                test_analytical_ets_adapter.baseConfig("X", "N", "N"));
            validation = adapter.validate(test_analytical_ets_adapter.dataContext(100));
            testCase.verifyEqual(validation.status, "INVALID_CONFIGURATION");

            adapter = gdss.AnalyticalEtsAdapter( ...
                test_analytical_ets_adapter.baseConfig("A", "M", "N"));
            validation = adapter.validate(test_analytical_ets_adapter.dataContext(100));
            testCase.verifyEqual(validation.status, "INVALID_CONFIGURATION");

            adapter = gdss.AnalyticalEtsAdapter( ...
                test_analytical_ets_adapter.baseConfig("A", "N", "A", "season_period", 1));
            validation = adapter.validate(test_analytical_ets_adapter.dataContext(100));
            testCase.verifyEqual(validation.status, "INVALID_CONFIGURATION");

            adapter = gdss.AnalyticalEtsAdapter( ...
                test_analytical_ets_adapter.baseConfig("A", "N", "N", ...
                "target_transform", "log"));
            validation = adapter.validate(test_analytical_ets_adapter.dataContext(100));
            testCase.verifyEqual(validation.status, "UNSUPPORTED_TARGET_TRANSFORM");

            adapter = gdss.AnalyticalEtsAdapter( ...
                test_analytical_ets_adapter.baseConfig("A", "N", "N"));
            validation = adapter.validate(struct("target_dimension", 2, ...
                "training_observation_count", 100));
            testCase.verifyEqual(validation.status, "INVALID_CONFIGURATION");
        end

        function validateRequiresTwoSeasonsPlusTwo(testCase)
            adapter = gdss.AnalyticalEtsAdapter( ...
                test_analytical_ets_adapter.baseConfig("A", "A", "A"));

            shortValidation = adapter.validate(test_analytical_ets_adapter.dataContext(25));
            testCase.verifyEqual(shortValidation.status, "INSUFFICIENT_TRAINING_DATA");

            enoughValidation = adapter.validate(test_analytical_ets_adapter.dataContext(26));
            testCase.verifyEqual(enoughValidation.status, "VALID");
            testCase.verifyEqual(enoughValidation.required_minimum_training_observations, 26);

            % season_period defaults to 12 and can be set.
            quarterly = gdss.AnalyticalEtsAdapter( ...
                test_analytical_ets_adapter.baseConfig("A", "N", "A", "season_period", 4));
            testCase.verifyEqual(quarterly.validate( ...
                test_analytical_ets_adapter.dataContext(10)).status, "INSUFFICIENT_TRAINING_DATA");
        end

        function multiplicativeRefusedOnDataWithZero(testCase)
            y = test_analytical_ets_adapter.positiveSeasonalSeries(60, 3);
            y(17) = 0;

            for classes = {["M", "N", "N"], ["A", "A", "M"], ["M", "Ad", "M"]}
                c = classes{1};
                adapter = gdss.AnalyticalEtsAdapter( ...
                    test_analytical_ets_adapter.baseConfig(c(1), c(2), c(3)));

                validation = adapter.validate(test_analytical_ets_adapter.dataContext( ...
                    numel(y), "training_minimum_value", min(y)));
                testCase.verifyEqual(validation.status, "INVALID_CONFIGURATION");

                validation = adapter.validate(test_analytical_ets_adapter.dataContext( ...
                    numel(y), "training_values", y));
                testCase.verifyEqual(validation.status, "INVALID_CONFIGURATION");

                % No positivity in dataContext: validation warns, fit refuses.
                validation = adapter.validate(test_analytical_ets_adapter.dataContext(numel(y)));
                testCase.verifyEqual(validation.status, "VALID");
                testCase.verifyNotEmpty(validation.warnings);

                testCase.verifyError(@() test_analytical_ets_adapter.fitSeries(adapter, y), ...
                    "gdss:AnalyticalEtsAdapter:NonpositiveData");
            end

            % The additive classes accept the same data.
            additive = gdss.AnalyticalEtsAdapter( ...
                test_analytical_ets_adapter.baseConfig("A", "N", "N"));
            testCase.verifyEqual(additive.validate(test_analytical_ets_adapter.dataContext( ...
                numel(y), "training_minimum_value", 0)).status, "VALID");
        end

        function annForecastIsSimpleExponentialSmoothingLevel(testCase)
            y = test_analytical_ets_adapter.localLevelSeries(150, 11);
            adapter = gdss.AnalyticalEtsAdapter( ...
                test_analytical_ets_adapter.baseConfig("A", "N", "N"));

            payload = test_analytical_ets_adapter.fitSeries(adapter, y);
            testCase.verifyEqual(payload.status, "COMPLETE");
            testCase.verifyEqual(payload.training_values, y);

            alpha = payload.ets_parameters.alpha;
            level = payload.ets_parameters.initial_level;
            squaredErrors = 0;
            for t = 1:numel(y)
                squaredErrors = squaredErrors + (y(t) - level) ^ 2;
                level = level + alpha * (y(t) - level);
            end

            forecastPayload = test_analytical_ets_adapter.forecastHorizons(adapter, payload, 8);

            testCase.verifyEqual(forecastPayload.point_forecast, repmat(level, 8, 1), ...
                "RelTol", 1e-12);
            testCase.verifyEqual(payload.ets_parameters.innovation_variance, ...
                squaredErrors / numel(y), "RelTol", 1e-10);

            % Class 1 variance: sigma^2 (1 + (h - 1) alpha^2).
            sigma2 = payload.ets_parameters.innovation_variance;
            testCase.verifyEqual(forecastPayload.forecast_variance, ...
                sigma2 * (1 + ((1:8)' - 1) * alpha ^ 2), "RelTol", 1e-12);
            testCase.verifyEqual(forecastPayload.forecast_distribution_family, ...
                repmat("normal", 8, 1));

            z95 = norminv(0.975);
            testCase.verifyEqual(forecastPayload.interval_upper(:, 2), ...
                level + z95 * sqrt(forecastPayload.forecast_variance), "RelTol", 1e-12);
            testCase.verifySize(forecastPayload.interval_lower, [8 2]);
        end

        function aanPointForecastsAreLinearInHorizon(testCase)
            y = test_analytical_ets_adapter.trendSeries(120, 5);
            adapter = gdss.AnalyticalEtsAdapter( ...
                test_analytical_ets_adapter.baseConfig("A", "A", "N"));

            payload = test_analytical_ets_adapter.fitSeries(adapter, y);
            forecastPayload = test_analytical_ets_adapter.forecastHorizons(adapter, payload, 24);

            steps = diff(forecastPayload.point_forecast);
            testCase.verifyEqual(steps, repmat(forecastPayload.state_at_forecast_origin.slope, ...
                23, 1), "AbsTol", 1e-9);
            testCase.verifyEqual(forecastPayload.point_forecast(1), ...
                forecastPayload.state_at_forecast_origin.level + ...
                forecastPayload.state_at_forecast_origin.slope, "AbsTol", 1e-9);

            parameters = payload.ets_parameters;
            testCase.verifyLessThanOrEqual(parameters.beta, parameters.alpha);
            testCase.verifyGreaterThan(parameters.beta, 0);
            testCase.verifyGreaterThan(forecastPayload.state_at_forecast_origin.slope, 0);
        end

        function extendedTrainingValuesFilterForwardWithFixedParameters(testCase)
            y = test_analytical_ets_adapter.trendSeries(260, 8);
            adapter = gdss.AnalyticalEtsAdapter( ...
                test_analytical_ets_adapter.baseConfig("A", "Ad", "N"));

            payload = test_analytical_ets_adapter.fitSeries(adapter, y(1:200));
            parametersBefore = payload.ets_parameters;

            extended = payload;
            extended.training_values = y;

            forecastPayload = test_analytical_ets_adapter.forecastHorizons(adapter, extended, 12);
            testCase.verifyEqual(extended.ets_parameters, parametersBefore);
            testCase.verifyEqual(forecastPayload.filtered_observation_count, 260);

            p = parametersBefore;
            testCase.verifyGreaterThanOrEqual(p.phi, 0.8);
            testCase.verifyLessThanOrEqual(p.phi, 0.98);

            level = p.initial_level;
            slope = p.initial_slope;
            for t = 1:numel(y)
                e = y(t) - (level + p.phi * slope);
                level = level + p.phi * slope + p.alpha * e;
                slope = p.phi * slope + p.beta * e;
            end

            expected = level + cumsum(p.phi .^ (1:12)') * slope;
            testCase.verifyEqual(forecastPayload.point_forecast, expected, "RelTol", 1e-12);

            % The fit-time origin is the same recursion stopped at 200.
            original = test_analytical_ets_adapter.forecastHorizons(adapter, payload, 12);
            testCase.verifyEqual(original.state_at_forecast_origin.level, ...
                payload.state_at_origin.level, "RelTol", 1e-12);
            testCase.verifyNotEqual(original.point_forecast, forecastPayload.point_forecast);
        end

        function seasonalAaaRecoversSeasonShape(testCase)
            [y, shape] = test_analytical_ets_adapter.seasonalSeries(144, 21);
            adapter = gdss.AnalyticalEtsAdapter( ...
                test_analytical_ets_adapter.baseConfig("A", "A", "A"));

            payload = test_analytical_ets_adapter.fitSeries(adapter, y);
            testCase.verifyEqual(payload.status, "COMPLETE");

            season = payload.ets_parameters.initial_season;
            testCase.verifySize(season, [12 1]);
            testCase.verifyEqual(sum(season), 0, "AbsTol", 1e-6);

            correlation = corr(season, shape);
            testCase.verifyGreaterThan(correlation, 0.98);
            testCase.verifyLessThan(max(abs(season - shape)), 2.5);

            % Forecast seasonality follows the calendar position.
            forecastPayload = test_analytical_ets_adapter.forecastHorizons(adapter, payload, 24);
            state = forecastPayload.state_at_forecast_origin;
            detrended = forecastPayload.point_forecast - (state.level + (1:24)' * state.slope);
            positions = mod(numel(y) + (1:24)' - 1, 12) + 1;
            testCase.verifyEqual(detrended, state.season_by_position(positions), "AbsTol", 1e-9);
            testCase.verifyGreaterThan(corr(detrended(1:12), shape(positions(1:12))), 0.95);

            % Class 1 variance has the seasonal jump at h = m + 1.
            sigma2 = payload.ets_parameters.innovation_variance;
            testCase.verifyEqual(forecastPayload.forecast_variance(1), sigma2, "RelTol", 1e-12);
        end

        function multiplicativeClassUsesSeededSimulation(testCase)
            y = test_analytical_ets_adapter.positiveSeasonalSeries(120, 4);
            adapter = gdss.AnalyticalEtsAdapter( ...
                test_analytical_ets_adapter.baseConfig("M", "A", "M", ...
                "simulation_path_count", 500));

            payload = test_analytical_ets_adapter.fitSeries(adapter, y);
            testCase.verifyEqual(payload.status, "COMPLETE");
            testCase.verifyEqual(sum(payload.ets_parameters.initial_season), 12, "AbsTol", 1e-6);

            rng(12345, "twister");
            globalBefore = rng;

            first = test_analytical_ets_adapter.forecastHorizons(adapter, payload, 18);
            second = test_analytical_ets_adapter.forecastHorizons(adapter, payload, 18);

            testCase.verifyEqual(rng, globalBefore);
            testCase.verifyEqual(second.forecast_variance, first.forecast_variance);
            testCase.verifyEqual(second.interval_lower, first.interval_lower);

            testCase.verifyEqual(first.forecast_distribution_method, ...
                repmat("ets_seeded_simulation_500_paths", 18, 1));
            testCase.verifyEqual(first.prediction_interval_method, ...
                repmat("simulation_quantile", 18, 1));
            testCase.verifyTrue(all(first.forecast_variance > 0));
            testCase.verifyTrue(all(first.interval_lower(:, 2) < first.point_forecast));
            testCase.verifyTrue(all(first.interval_upper(:, 2) > first.point_forecast));
            testCase.verifyTrue(all(first.interval_lower(:, 2) <= first.interval_lower(:, 1)));
        end

        function statusesComeFromOptimizer(testCase)
            y = test_analytical_ets_adapter.localLevelSeries(100, 2);
            adapter = gdss.AnalyticalEtsAdapter( ...
                test_analytical_ets_adapter.baseConfig("M", "N", "N"));

            payload = test_analytical_ets_adapter.fitSeries(adapter, y);

            exitFlag = payload.optimizer_exit_flag;
            warned = strlength(payload.optimizer_warning_message) > 0;
            if exitFlag > 0 && ~warned
                expected = "CONVERGED";
            elseif exitFlag > 0
                expected = "CONVERGED_WITH_WARNINGS";
            elseif exitFlag == 0
                expected = "ITERATION_LIMIT_REACHED";
            else
                expected = "FAILED";
            end
            testCase.verifyEqual(payload.convergence_status, expected);
            testCase.verifyTrue(startsWith(payload.convergence_message, ...
                "fmincon exit flag " + string(exitFlag)));
            testCase.verifyEqual(payload.iterations, payload.estimation_output.iterations);
            testCase.verifyEqual(payload.function_evaluations, ...
                payload.estimation_output.funcCount);

            parameterTable = payload.parameter_table;
            testCase.verifyEqual(parameterTable.parameter_name, ...
                ["smoothing_alpha_level"; "initial_level"; "innovation_variance"]);
            testCase.verifySize(payload.parameter_covariance, [3 3]);
            testCase.verifySize(payload.parameter_standard_error, [3 1]);
            testCase.verifyTrue(ismember(payload.parameter_covariance_status, ...
                ["AVAILABLE", "UNRELIABLE", "NOT_AVAILABLE"]));
            if any(parameterTable.at_bound) && payload.parameter_covariance_status ~= "NOT_AVAILABLE"
                testCase.verifyEqual(payload.parameter_covariance_status, "UNRELIABLE");
            end
            testCase.verifyEqual(payload.parameter_standard_error_status, ...
                payload.parameter_covariance_status);

            for f = ["parameter_covariance_reference", "parameter_standard_error_reference", ...
                    "log_likelihood", "aic", "aicc", "bic", "runtime_seconds"]
                testCase.verifyTrue(isfield(payload, f), "Missing payload field: " + f);
            end
            testCase.verifyTrue(isfinite(payload.log_likelihood));
            testCase.verifyEqual(payload.aic, -2 * payload.log_likelihood + 2 * 3, ...
                "RelTol", 1e-12);
        end

        function fitReachesIndependentOptimum(testCase)
            % A slope smoothing pinned at its lower bound is a local
            % optimum on this series; the fit must reach the better one an
            % independent Nelder-Mead search finds.
            stream = RandStream("mt19937ar", "Seed", 3);
            t = (1:300)';
            factor = 1 + 0.1 * sin(2 * pi * (1:12)' / 12);
            y = (500 + cumsum(2 * randn(stream, 300, 1)) + 0.5 * t) .* ...
                factor(mod(t - 1, 12) + 1) .* (1 + 0.005 * randn(stream, 300, 1));

            adapter = gdss.AnalyticalEtsAdapter( ...
                test_analytical_ets_adapter.baseConfig("A", "A", "N"));
            payload = test_analytical_ets_adapter.fitSeries(adapter, y);

            objective = @(q) test_analytical_ets_adapter.aanObjective(q, y);
            settings = optimset("MaxFunEvals", 8000, "MaxIter", 8000, ...
                "TolX", 1e-10, "TolFun", 1e-12);
            best = Inf;
            for alpha = [0.5 0.9]
                q0 = [alpha; 0.5 * alpha; y(1); y(2) - y(1)];
                [~, value] = fminsearch(objective, q0, settings);
                best = min(best, value);
            end

            testCase.verifyLessThanOrEqual(payload.objective_value, best + 1e-6);
            testCase.verifyGreaterThan(payload.optimizer_start_count, 1);
        end

        function fitIsDeterministic(testCase)
            [y, ~] = test_analytical_ets_adapter.seasonalSeries(80, 9);
            adapter = gdss.AnalyticalEtsAdapter( ...
                test_analytical_ets_adapter.baseConfig("A", "Ad", "A"));

            rng(7, "twister");
            globalBefore = rng;
            first = test_analytical_ets_adapter.fitSeries(adapter, y);
            second = test_analytical_ets_adapter.fitSeries(adapter, y);
            testCase.verifyEqual(rng, globalBefore);

            testCase.verifyEqual(second.ets_parameters, first.ets_parameters);
            testCase.verifyEqual(second.parameter_table.estimated_value, ...
                first.parameter_table.estimated_value);
            testCase.verifyEqual(height(first.parameter_table), 4 + 2 + 12 + 1);
        end

    end

end
