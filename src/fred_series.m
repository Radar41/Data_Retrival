function TT = fred_series(seriesId, options)
%FRED_SERIES One catalog series as a timetable, as known on a vintage date.
%   TT = FRED_SERIES("UNRATE")                           values current today
%   TT = FRED_SERIES("UNRATE", Vintage=datetime(2020,3,6)) as known on 6 Mar 2020
%   TT = FRED_SERIES("UNRATE", Vintage="first")          first-published value per period
%   TT = FRED_SERIES("UNRATE", Range=[datetime(2000,1,1) NaT])
%
%   Row times are the observation dates. Variables: Value (double; NaN where
%   FRED reports "."), RealtimeStart and RealtimeEnd (the window in which that
%   value was the current one). The series row's metadata is on the timetable:
%   TT.Properties.CustomProperties.SeriesId, Title, Frequency, Units,
%   SeasonalAdjustment, Release, LastUpdated and Vintage, and
%   TT.Properties.VariableUnits for Value.
%
%   Reads PostgreSQL through fred_pg_query. The as-of rule is the one the SQL
%   function value_as_of applies, so a MATLAB result and a SQL result for the
%   same vintage can never disagree.
%
%   See also fred_panel, fred_series_sql, fred_pg_query.
arguments
    seriesId (1,1) string
    options.Vintage = datetime("today")
    options.Range (1,2) datetime = [NaT NaT]
end

meta = fred_pg_query("SELECT s.series_id, s.title, s.frequency_code, f.frequency_name, " + ...
    "s.units_code, u.units_name, s.sa_code, sa.sa_name, r.release_name, s.last_updated " + ...
    "FROM series s LEFT JOIN frequency f USING (frequency_code) LEFT JOIN units u USING (units_code) " + ...
    "LEFT JOIN seasonal_adjustment sa USING (sa_code) LEFT JOIN release r USING (release_id) " + ...
    "WHERE s.series_id = '" + validId(seriesId) + "'");
if height(meta) == 0
    error("fred_series:unknown", "%s is not in the catalog: not in the series table.", seriesId);
end

T = fred_pg_query(fred_series_sql(seriesId, Vintage=options.Vintage, Range=options.Range));
obsDate = toDatetime(T.observation_date);
value = toDouble(T.value);
TT = timetable(obsDate, value, toDatetime(T.realtime_start), toDatetime(T.realtime_end), ...
    'VariableNames', ["Value", "RealtimeStart", "RealtimeEnd"]);
TT.Properties.DimensionNames{1} = 'ObservationDate';

% One value per period is the contract. Real-time windows of one period are
% disjoint in FRED, but keep the most recently published row if they ever overlap.
if height(TT) > numel(unique(TT.ObservationDate))
    warning("fred_series:overlap", "%s: overlapping real-time windows; keeping the latest per period.", seriesId);
    TT = sortrows(TT, ["ObservationDate", "RealtimeStart"]);
    [~, last] = unique(TT.ObservationDate, "last");
    TT = TT(last, :);
end

units = string(meta.units_name(1));
TT.Properties.VariableUnits = [units, "", ""];
TT.Properties.Description = string(meta.title(1));
names = ["SeriesId", "Title", "Frequency", "Units", "SeasonalAdjustment", "Release", "LastUpdated", "Vintage"];
TT = addprop(TT, names, repmat("table", 1, numel(names)));
TT.Properties.CustomProperties.SeriesId = string(meta.series_id(1));
TT.Properties.CustomProperties.Title = string(meta.title(1));
TT.Properties.CustomProperties.Frequency = string(meta.frequency_name(1));
TT.Properties.CustomProperties.Units = units;
TT.Properties.CustomProperties.SeasonalAdjustment = string(meta.sa_name(1));
TT.Properties.CustomProperties.Release = string(meta.release_name(1));
TT.Properties.CustomProperties.LastUpdated = toDatetime(meta.last_updated(1));
if isdatetime(options.Vintage)
    TT.Properties.CustomProperties.Vintage = options.Vintage;
else
    TT.Properties.CustomProperties.Vintage = string(options.Vintage);
end
end


function id = validId(id)
% Same rule as fred_series_sql, applied before the metadata query.
fred_series_sql(id);
end


function d = toDatetime(x)
if isdatetime(x)
    d = x;
elseif isempty(x)
    d = datetime.empty(0, 1);
else
    d = datetime(string(x), "InputFormat", "yyyy-MM-dd' 'HH:mm:ss", "Format", "default");
    bad = isnat(d) & strlength(string(x)) > 0;
    if any(bad), d(bad) = datetime(string(x(bad)), "InputFormat", "yyyy-MM-dd"); end
end
d = reshape(d, [], 1);
end


function v = toDouble(x)
if isnumeric(x)
    v = double(x);
else
    v = str2double(string(x));
end
v = reshape(v, [], 1);
end
