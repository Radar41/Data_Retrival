classdef test_run_rattractor_request < matlab.unittest.TestCase
    %TEST_RUN_RATTRACTOR_REQUEST The residual-attractor bridge: one request with the naive, local-level and
    % ARIMA(1,1,0) adapters on two short series. Every issuance from the first one with enough data has a
    % forecast from parameters fitted at or before it, the naive forecast is y at the issuance, and the
    % driver's own cut test passes.

    properties
        Dir
    end

    methods (TestClassSetup)
        function addSource(testCase)
            import matlab.unittest.fixtures.PathFixture
            root = fileparts(fileparts(fileparts(mfilename("fullpath"))));
            testCase.applyFixture(PathFixture(fullfile(root, "src")));
        end
    end

    methods (TestMethodSetup)
        function writeRequest(testCase)
            import matlab.unittest.fixtures.TemporaryFolderFixture
            f = testCase.applyFixture(TemporaryFolderFixture);
            testCase.Dir = f.Folder;
            stream = RandStream("mt19937ar", "Seed", 7);
            n = 90;
            y1 = 50 + cumsum(randn(stream, n, 1));
            y2 = 10 + 0.1 * (1:n)' + randn(stream, n, 1);
            S = table([repmat("A", n, 1); repmat("B", n, 1)], int32([0:n-1, 0:n-1]'), [y1; y2], ...
                'VariableNames', {'series_id', 't', 'y'});
            parquetwrite(fullfile(testCase.Dir, "series.parquet"), S);
            pol = struct("refit_every", 12, "window", "expanding", "min_train", 24);
            c(1) = struct("config_id", "naive0000000000a", "method", "gdss.naive", ...
                "adapter_id", "analytical.naive_random_walk", "params", pol);
            c(2) = struct("config_id", "locallevel00000b", "method", "gdss.local_level", ...
                "adapter_id", "matlab.ssm.local_level", "params", pol);
            p3 = pol; p3.arima_p = 1; p3.arima_d = 1; p3.arima_q = 0;
            c3 = struct("config_id", "arima110000000c", "method", "gdss.arima", "adapter_id", "matlab.arima", "params", p3);
            req = struct("request_id", "testrequest0001", "horizon", 3, "series_sha256", "x", ...
                "configurations", {{c(1), c(2), c3}});
            fid = fopen(fullfile(testCase.Dir, "request.json"), "w");
            fprintf(fid, "%s", jsonencode(req));
            fclose(fid);
        end
    end

    methods (Test)
        function cubeIsCompleteAndCausal(testCase)
            s = gdss.run_rattractor_request(testCase.Dir, workers=1);
            testCase.verifyTrue(isfile(fullfile(testCase.Dir, "done.json")));
            testCase.verifyTrue(all([s.leakage.identical]));
            testCase.verifyEqual(numel(s.leakage), 3);
            for sid = ["A", "B"]
                C = parquetread(fullfile(testCase.Dir, "cube", sid + ".parquet"));
                testCase.verifyEqual(numel(unique(C.config_id)), 3);
                for cid = unique(C.config_id)'
                    r = sortrows(C(C.config_id == cid, :), 'issuance');
                    testCase.verifyEqual(double(r.issuance), (23:89)');            % min_train 24 -> first issuance 23
                    testCase.verifyTrue(all(r.fit_through <= r.issuance & r.fit_through >= 0));
                    testCase.verifyEqual(double(r.fit_through), 23 + 12 * floor((double(r.issuance) - 23) / 12));
                    testCase.verifyTrue(all(isfinite([r.yhat_01, r.yhat_02, r.yhat_03, r.yhat_04]), 'all'));
                end
            end
            S = parquetread(fullfile(testCase.Dir, "series.parquet"));
            C = parquetread(fullfile(testCase.Dir, "cube", "A.parquet"));
            nv = sortrows(C(C.config_id == "naive0000000000a", :), 'issuance');
            yA = S.y(S.series_id == "A");
            testCase.verifyEqual(nv.yhat_04, yA(nv.issuance + 1));               % naive: y at the issuance, every h
            testCase.verifyTrue(all(isnan(nv.sd_01)));                             % the naive adapter gives no sd
            ll = sortrows(C(C.config_id == "locallevel00000b", :), 'issuance');
            testCase.verifyTrue(all(ll.sd_02 >= ll.sd_01 - 1e-12));               % local level: sd grows with h
            F = parquetread(fullfile(testCase.Dir, "fit_status.parquet"));
            testCase.verifyEqual(height(F), 2 * 3 * 6);                            % refits at 23, 35, ..., 83
        end

        function filteringUsesNewDataButOldParameters(testCase)
            gdss.run_rattractor_request(testCase.Dir, workers=1);
            C = parquetread(fullfile(testCase.Dir, "cube", "A.parquet"));
            a = sortrows(C(C.config_id == "arima110000000c", :), 'issuance');
            % Between refits the forecast still moves with y (filtering), and the parameters stay put.
            testCase.verifyNotEqual(a.yhat_01(2), a.yhat_01(1));
            testCase.verifyEqual(a.fit_through(2), a.fit_through(1));
        end
    end
end
