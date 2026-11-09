classdef (TestTags = {'Live'}) LiveSeriesReaderTest < matlab.unittest.TestCase
    % The MATLAB readers against the live PostgreSQL catalog: whatever
    % fred_series returns for a vintage must be what SQL returns for the same
    % vintage, and a panel must be the outer join of its series. Skips itself
    % when PostgreSQL is not reachable or UNRATE has no observations loaded.

    properties (Constant)
        Id = "UNRATE"
    end

    methods (TestClassSetup)
        function requirePostgres(testCase)
            [status, ~] = system("pg_isready -q -h localhost -p 5432");
            testCase.assumeEqual(status, 0, "PostgreSQL is not reachable on localhost:5432.");
            n = fred_pg_query("SELECT count(*) AS n FROM observation WHERE series_id = '" + testCase.Id + "'");
            testCase.assumeGreaterThan(n.n, 0, testCase.Id + " has no observations loaded.");
        end
    end

    methods (Test)

        function currentValuesAreTheOpenWindows(testCase)
            n = fred_pg_query("SELECT count(*) AS n FROM observation WHERE series_id = '" + testCase.Id + ...
                "' AND realtime_end = DATE '9999-12-31'");
            latest = fred_series(testCase.Id, Vintage="latest");
            today = fred_series(testCase.Id);
            testCase.verifyEqual(height(latest), n.n);
            testCase.verifyEqual(height(today), height(latest), "Vintage = today must equal ""latest"".");
            testCase.verifyEqual(today.Value, latest.Value);
            testCase.verifyTrue(issorted(today.ObservationDate, "strictascend"));
        end

        function asOfValueEqualsTheSqlFunction(testCase)
            % A vintage halfway through the loaded history, and a period a year before it.
            w = fred_pg_query("SELECT min(realtime_start) AS lo, max(realtime_start) AS hi FROM observation " + ...
                "WHERE series_id = '" + testCase.Id + "' AND realtime_end <> DATE '9999-12-31'");
            testCase.assumeFalse(isempty(w) || isnat(w.lo(1)), "No revised windows loaded for " + testCase.Id);
            vintage = w.lo(1) + (w.hi(1) - w.lo(1)) / 2;
            TT = fred_series(testCase.Id, Vintage=vintage);
            testCase.assumeGreaterThan(height(TT), 0);
            period = TT.ObservationDate(max(1, height(TT) - 12));
            sqlValue = fred_pg_query("SELECT value_as_of('" + testCase.Id + "', DATE '" + ...
                string(period, "yyyy-MM-dd") + "', DATE '" + string(vintage, "yyyy-MM-dd") + "') AS v");
            testCase.verifyEqual(TT.Value(TT.ObservationDate == period), double(sqlValue.v(1)), "AbsTol", 1e-9);
            testCase.verifyTrue(all(TT.RealtimeStart <= vintage & vintage <= TT.RealtimeEnd), ...
                "Every row's window must contain the vintage date.");
        end

        function firstPublishedValuesCoverEveryPeriodOnce(testCase)
            n = fred_pg_query("SELECT count(DISTINCT observation_date) AS n FROM observation WHERE series_id = '" + ...
                testCase.Id + "'");
            first = fred_series(testCase.Id, Vintage="first");
            testCase.verifyEqual(height(first), n.n);
            lo = fred_pg_query("SELECT observation_date, min(realtime_start) AS rs FROM observation WHERE series_id = '" + ...
                testCase.Id + "' GROUP BY observation_date ORDER BY observation_date");
            testCase.verifyEqual(first.RealtimeStart, lo.rs);
        end

        function metadataComesFromTheSeriesRow(testCase)
            row = fred_pg_query("SELECT s.title, u.units_name, f.frequency_name FROM series s " + ...
                "JOIN units u USING (units_code) JOIN frequency f USING (frequency_code) WHERE s.series_id = '" + ...
                testCase.Id + "'");
            TT = fred_series(testCase.Id, Range=[datetime(2019, 1, 1), datetime(2019, 12, 31)]);
            c = TT.Properties.CustomProperties;
            testCase.verifyEqual(c.SeriesId, testCase.Id);
            testCase.verifyEqual(c.Title, string(row.title(1)));
            testCase.verifyEqual(c.Units, string(row.units_name(1)));
            testCase.verifyEqual(c.Frequency, string(row.frequency_name(1)));
            testCase.verifyEqual(string(TT.Properties.VariableUnits{1}), string(row.units_name(1)));
            testCase.verifyEqual(height(TT), 12, "A monthly series has twelve periods in 2019.");
        end

        function panelIsTheOuterJoinOfItsSeries(testCase)
            ids = [testCase.Id, "PAYEMS"];
            n = fred_pg_query("SELECT count(*) AS n FROM series WHERE series_id IN ('" + join(ids, "','") + "')");
            testCase.assumeEqual(n.n, numel(ids), "Both panel series must be in the catalog.");
            range = [datetime(2019, 1, 1), datetime(2019, 12, 31)];
            TT = fred_panel(ids, Range=range);
            testCase.verifyEqual(string(TT.Properties.VariableNames), ids);
            a = fred_series(ids(1), Range=range);
            b = fred_series(ids(2), Range=range);
            testCase.verifyEqual(height(TT), numel(union(a.ObservationDate, b.ObservationDate)));
            testCase.verifyEqual(TT.(ids(1))(ismember(TT.ObservationDate, a.ObservationDate)), a.Value);
            testCase.verifyEqual(height(TT.Properties.CustomProperties.Series), numel(ids));
        end

        function unknownSeriesIsAnError(testCase)
            testCase.verifyError(@() fred_series("NOT_A_SERIES_ID_X"), "fred_series:unknown");
        end

    end
end
