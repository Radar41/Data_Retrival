function sql = fred_series_sql(seriesId, options)
%FRED_SERIES_SQL SQL for one series' observations as known on a vintage date.
%   SQL = FRED_SERIES_SQL(ID) selects the values current today.
%   Options:
%     Vintage  datetime  the value current on that day: the same rule as the
%                        SQL function value_as_of (vintage BETWEEN
%                        realtime_start AND realtime_end). Default today.
%              "latest"  rows whose window is still open (realtime_end =
%                        9999-12-31); equal to Vintage = today.
%              "first"   the first-published value of each period: DISTINCT
%                        ON (observation_date), smallest realtime_start.
%     Range    [start end] datetime bounds on observation_date; NaT is open.
%
%   The series id must be an identifier (letters, digits, _ . -) so it can be
%   placed in the statement as a literal; anything else is an error. Pure
%   function: no database access, so it is unit-tested without one.
%
%   See also fred_series, fred_pg_query.
arguments
    seriesId (1,1) string {mustBeSeriesId}
    options.Vintage = datetime("today")
    options.Range (1,2) datetime = [NaT NaT]
end

cols = "observation_date, value, realtime_start, realtime_end";
where = "series_id = '" + seriesId + "'";
r = options.Range;
if ~isnat(r(1)), where = where + " AND observation_date >= DATE '" + string(r(1), "yyyy-MM-dd") + "'"; end
if ~isnat(r(2)), where = where + " AND observation_date <= DATE '" + string(r(2), "yyyy-MM-dd") + "'"; end

v = options.Vintage;
if isstring(v) || ischar(v)
    switch lower(string(v))
        case "latest"
            sql = "SELECT " + cols + " FROM observation WHERE " + where + ...
                " AND realtime_end = DATE '9999-12-31' ORDER BY observation_date";
        case "first"
            sql = "SELECT DISTINCT ON (observation_date) " + cols + " FROM observation WHERE " + where + ...
                " ORDER BY observation_date, realtime_start";
        otherwise
            error("fred_series_sql:vintage", ...
                "Vintage must be a datetime, ""latest"" or ""first"", not ""%s"".", string(v));
    end
else
    assert(isdatetime(v) && isscalar(v) && ~isnat(v), "fred_series_sql:vintage", ...
        "Vintage must be a datetime scalar, ""latest"" or ""first"".");
    sql = "SELECT " + cols + " FROM observation WHERE " + where + ...
        " AND DATE '" + string(v, "yyyy-MM-dd") + "' BETWEEN realtime_start AND realtime_end" + ...
        " ORDER BY observation_date";
end
end


function mustBeSeriesId(id)
if isempty(regexp(id, "^[A-Za-z0-9_.\-]{1,40}$", "once"))
    error("fred_series_sql:seriesId", ...
        "A FRED series id is letters, digits, underscore, dot or hyphen (at most 40), not ""%s"".", id);
end
end
