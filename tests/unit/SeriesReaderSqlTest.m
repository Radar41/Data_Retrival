classdef SeriesReaderSqlTest < matlab.unittest.TestCase
    % The SQL that fred_series sends, checked without a database: the as-of
    % rule must be the one value_as_of applies, and the series id must be
    % placed in the statement only when it is an identifier.

    methods (Test)

        function asOfUsesTheValueAsOfRule(testCase)
            sql = fred_series_sql("UNRATE", Vintage=datetime(2020, 3, 6));
            testCase.verifySubstring(sql, "series_id = 'UNRATE'");
            testCase.verifySubstring(sql, "DATE '2020-03-06' BETWEEN realtime_start AND realtime_end");
            testCase.verifySubstring(sql, "ORDER BY observation_date");
        end

        function firstPublishedValueUsesDistinctOnTheSmallestWindow(testCase)
            sql = fred_series_sql("UNRATE", Vintage="first");
            testCase.verifySubstring(sql, "DISTINCT ON (observation_date)");
            testCase.verifySubstring(sql, "ORDER BY observation_date, realtime_start");
        end

        function latestSelectsOpenWindows(testCase)
            sql = fred_series_sql("UNRATE", Vintage="latest");
            testCase.verifySubstring(sql, "realtime_end = DATE '9999-12-31'");
        end

        function rangeBoundsTheObservationDate(testCase)
            sql = fred_series_sql("GDPC1", Range=[datetime(2000, 1, 1), datetime(2009, 12, 31)]);
            testCase.verifySubstring(sql, "observation_date >= DATE '2000-01-01'");
            testCase.verifySubstring(sql, "observation_date <= DATE '2009-12-31'");
            open = fred_series_sql("GDPC1", Range=[datetime(2000, 1, 1), NaT]);
            testCase.verifyFalse(contains(open, "observation_date <="));
        end

        function defaultVintageIsToday(testCase)
            sql = fred_series_sql("UNRATE");
            testCase.verifySubstring(sql, "DATE '" + string(datetime("today"), "yyyy-MM-dd") + "' BETWEEN");
        end

        function onlyIdentifiersReachTheStatement(testCase)
            testCase.verifyError(@() fred_series_sql("UNRATE'; DROP TABLE observation; --"), ?MException);
            testCase.verifyError(@() fred_series_sql(""), ?MException);
            testCase.verifyError(@() fred_series_sql("A B"), ?MException);
            testCase.verifyWarningFree(@() fred_series_sql("CUUR0000SA0L1E"));
            testCase.verifyWarningFree(@() fred_series_sql("DGS10-DGS2"));
        end

        function unknownVintageWordsAreRefused(testCase)
            testCase.verifyError(@() fred_series_sql("UNRATE", Vintage="newest"), "fred_series_sql:vintage");
            testCase.verifyError(@() fred_series_sql("UNRATE", Vintage=NaT), "fred_series_sql:vintage");
        end

    end
end
