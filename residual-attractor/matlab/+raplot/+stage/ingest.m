function ingest(ctx)
%INGEST  Stage 1. Per series: y over its kept run, train/test split, imputed months, first-release lag.
% Overview: all series as small multiples. Check: gaps, the transform, the split at test_start.
S = raplot.util.readp(ctx, 'series');
C = raplot.util.readp(ctx, 'calendar');
L = ctx.L;
cat = ctx.man.run_spec.catalog;
note = sprintf('transform %s, %s, as_of %s, test_start %s', cat.transform, cat.frequency, cat.as_of, cat.test_start);

[f, tl] = raplot.util.newfig(1500, 1000, 4, 4, "ingest: every series (" + note + ")", ctx);
for i = 0:L.N-1
    [d, y, tr, imp] = one_series(S, C, L.sid(i+1));
    ax = nexttile(tl);
    plot(ax, d(tr), y(tr), '-', 'Color', [.25 .45 .7]); hold(ax, 'on');
    plot(ax, d(~tr), y(~tr), '-', 'Color', [.85 .35 .1]);
    plot(ax, d(imp), y(imp), 'o', 'Color', [.8 0 0], 'MarkerSize', 3);
    title(ax, sprintf('i%02d %s  (n %d, test %d)', i, L.sid(i+1), numel(y), sum(~tr)));
    axis(ax, 'tight');
end
raplot.util.savefig(f, ctx, '00_overview.png');

U = raplot.util.units(ctx, 'i');
for i = U.i'
    [file, ttl] = raplot.util.names(ctx, [], i, 'ingest');
    [d, y, tr, imp, rel] = one_series(S, C, L.sid(i+1));
    [f, tl] = raplot.util.newfig(1200, 750, 2, 1, ttl + "   (" + note + ")", ctx);
    ax = nexttile(tl);
    plot(ax, d(tr), y(tr), '-', 'Color', [.25 .45 .7], 'LineWidth', 0.9); hold(ax, 'on');
    plot(ax, d(~tr), y(~tr), '-', 'Color', [.85 .35 .1], 'LineWidth', 0.9);
    plot(ax, d(imp), y(imp), 'o', 'Color', [.8 0 0], 'MarkerSize', 4);
    if any(~tr), xline(ax, d(find(~tr, 1)), 'k--', 'test start'); end
    legend(ax, {'train', 'test', sprintf('imputed (%d)', sum(imp))}, 'Location', 'best');
    title(ax, sprintf('y as ingested: %d months %s .. %s', numel(y), string(d(1), 'yyyy-MM'), string(d(end), 'yyyy-MM')));
    grid(ax, 'on'); axis(ax, 'tight');
    ax = nexttile(tl);
    lag = days(rel - d);
    plot(ax, d, lag, '.', 'Color', [.3 .3 .3]);
    title(ax, sprintf('first release minus period (days); %d months without a release', sum(isnat(rel))));
    grid(ax, 'on'); axis(ax, 'tight');
    raplot.util.savefig(f, ctx, file);
end
end

function [d, y, tr, imp, rel] = one_series(S, C, sid)
s = sortrows(S(S.series_id == sid, :), 't');
c = sortrows(C(C.series_id == sid, :), 't');
[~, ia, ib] = intersect(s.t, c.t);
s = s(ia, :); c = c(ib, :);
d = datetime(c.period, 'InputFormat', 'yyyy-MM-dd');
y = s.y;
tr = s.split == "train";
imp = c.imputed;
rel = NaT(size(d));
ok = strlength(c.first_release) > 0 & ~ismissing(c.first_release);
rel(ok) = datetime(c.first_release(ok), 'InputFormat', 'yyyy-MM-dd');
end
