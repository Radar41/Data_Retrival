function D = sdates(ctx)
%SDATES  Per-series period dates: D.(series_id)(t+1) is the datetime of base index t (calendar.parquet).
C = raplot.util.readp(ctx, 'calendar', {'series_id', 't', 'period'});
D = struct();
for s = unique(C.series_id)'
    c = sortrows(C(C.series_id == s, :), 't');
    d = NaT(max(c.t) + 1, 1);
    d(c.t + 1) = datetime(c.period, 'InputFormat', 'yyyy-MM-dd');
    D.(char(s)) = d;
end
end
