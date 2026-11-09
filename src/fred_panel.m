function TT = fred_panel(seriesIds, options)
%FRED_PANEL Several catalog series side by side, as known on one vintage date.
%   TT = FRED_PANEL(["UNRATE" "CPIAUCSL"]) one column per series, named by id,
%   outer-joined on observation date; a period a series does not have is NaN.
%   Options Vintage and Range are those of fred_series and apply to every
%   column. Frequencies are not reconciled: a monthly and a quarterly series
%   give the union of their dates, so aggregate (retime) before regressing.
%   Per-series metadata is the table TT.Properties.CustomProperties.Series.
%
%   See also fred_series, retime, synchronize.
arguments
    seriesIds (1,:) string
    options.Vintage = datetime("today")
    options.Range (1,2) datetime = [NaT NaT]
end

n = numel(seriesIds);
parts = cell(1, n);
meta = table('Size', [n, 6], 'VariableTypes', repmat("string", 1, 6), ...
    'VariableNames', ["SeriesId", "Title", "Frequency", "Units", "SeasonalAdjustment", "Release"]);
for k = 1:n
    S = fred_series(seriesIds(k), Vintage=options.Vintage, Range=options.Range);
    % A fresh timetable, so none of the series' custom properties ride along.
    P = timetable(S.ObservationDate, S.Value, 'VariableNames', seriesIds(k));
    parts{k} = P;
    c = S.Properties.CustomProperties;
    meta(k, :) = {c.SeriesId, c.Title, c.Frequency, c.Units, c.SeasonalAdjustment, c.Release};
end
if n == 1
    TT = parts{1};
else
    TT = synchronize(parts{:}, "union", "fillwithmissing");
end
TT.Properties.DimensionNames{1} = 'ObservationDate';
TT = addprop(TT, ["Series", "Vintage"], ["table", "table"]);
TT.Properties.CustomProperties.Series = meta;
if isdatetime(options.Vintage)
    TT.Properties.CustomProperties.Vintage = options.Vintage;
else
    TT.Properties.CustomProperties.Vintage = string(options.Vintage);
end
end
