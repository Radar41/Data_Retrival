function forecast(ctx)
%FORECAST  Stage 4. Per row: every forward ladder's yhat path against y; the failure scale r_g by
% origin x h; median r, r_h, r_g by h. Overview: median r_g at h = 1 and at h = H.
% Check: ladders start at their origin and land on the right months; the scale grows with h.
L = ctx.L;
D = raplot.util.sdates(ctx);
S = raplot.util.readp(ctx, 'series', {'series_id', 't', 'y'});
H = ctx.man.config.horizon_H;
vars = {'config_id', 'origin', 'ladder', 'h', 't_target', 'yhat', 'y', 'r', 'r_h', 'r_g'};

M1 = nan(L.K, L.N); MH = nan(L.K, L.N);
U = raplot.util.units(ctx, 'byi');
for i = 0:L.N-1
    T = raplot.util.readp(ctx, "steps/" + L.sid(i+1), {'config_id', 'ladder', 'h', 'r_g'});
    T = T(T.ladder == "forward", :);
    [g, cid] = findgroups(T.config_id);
    [~, kk] = ismember(cid, L.cid);
    m1 = splitapply(@(r, h) median(r(h == 1), 'omitnan'), T.r_g, T.h, g);
    mH = splitapply(@(r, h) median(r(h == max(h)), 'omitnan'), T.r_g, T.h, g);
    M1(kk, i+1) = m1; MH(kk, i+1) = mH;
end
[f, tl] = raplot.util.newfig(1500, 1300, 1, 2, 'forecast: median failure scale r_g of the forward ladders, every row', ctx);
raplot.util.kxn(nexttile(tl), ctx, M1, 'median r_g at h = 1', [0 3]);
raplot.util.kxn(nexttile(tl), ctx, MH, sprintf('median r_g at h = %d', H), [0 3]);
raplot.util.savefig(f, ctx, '00_overview.png');

parfor (n = 1:numel(U.i), ctx.M)
    sid = L.sid(U.i(n) + 1);
    T = raplot.util.readp(ctx, "steps/" + sid, vars);
    s = sortrows(S(S.series_id == sid, :), 't');
    for k = U.ks{n}'
        draw(ctx, k, U.i(n), T(T.config_id == L.cid(k+1), :), s, D.(char(sid)), H);
    end
end
end

function draw(ctx, k, i, T, s, d, H)
fw = sortrows(T(T.ladder == "forward", :), {'origin', 'h'});
[file, ttl] = raplot.util.names(ctx, k, i, 'forecast');
[f, tl] = raplot.util.newfig(1400, 1000, 2, 2, ttl, ctx);

ax = nexttile(tl, [1 2]);
o0 = min(fw.origin);
keep = s.t >= o0 - 24;
plot(ax, d(s.t(keep) + 1), s.y(keep), 'k-', 'LineWidth', 1.2); hold(ax, 'on');
% one NaN-separated line holds every origin's ladder, starting from y at the origin
[uo, ~, g] = unique(fw.origin);
xs = NaT(0, 1); ys = zeros(0, 1);
for q = 1:numel(uo)
    r = fw(g == q, :);
    xs = [xs; d(uo(q) + 1); d(r.t_target + 1); NaT]; %#ok<AGROW>
    ys = [ys; s.y(s.t == uo(q)); r.yhat; NaN]; %#ok<AGROW>
end
plot(ax, xs, ys, '-', 'Color', [.85 .33 .1 .25]);
xline(ax, d(o0 + 1), 'k--', 'first origin');
legend(ax, {'y', sprintf('forward ladders yhat (h 1..%d), %d origins', H, numel(uo))}, 'Location', 'best');
title(ax, 'forward ladders against y'); grid(ax, 'on'); axis(ax, 'tight');

ax = nexttile(tl);
G = accumarray([g, double(fw.h)], double(fw.r_g), [numel(uo), H], @mean, NaN);
im = imagesc(ax, 1:H, 1:numel(uo), G); set(im, 'AlphaData', ~isnan(G)); ax.Color = [.82 .82 .82];
clim(ax, [0 4]); colorbar(ax);
step = max(1, round(numel(uo) / 12));
ax.YTick = 1:step:numel(uo); ax.YTickLabel = string(d(uo(1:step:end) + 1), 'yyyy-MM');
xlabel(ax, 'h'); ylabel(ax, 'origin');
title(ax, 'failure scale r_g = |e| / sigma_g, forward ladders (2 = fail level)');

ax = nexttile(tl);
hh = (1:H)';
med = @(v) accumarray(double(fw.h), double(v), [H 1], @(x) median(x, 'omitnan'), NaN);
plot(ax, hh, med(fw.r), 'o-', hh, med(fw.r_h), 's-', hh, med(fw.r_g), 'd-'); hold(ax, 'on');
p90 = accumarray(double(fw.h), double(fw.r_g), [H 1], @(x) prctile(x, 90), NaN);
plot(ax, hh, p90, ':', 'Color', [.5 .5 .5]);
yline(ax, 2, 'k--', 'fail level');
legend(ax, {'median r = |e|/sigma', 'median r_h = |e|/sigma_h', 'median r_g = |e|/sigma_g', '90th pct r_g'}, 'Location', 'best');
xlabel(ax, 'h'); title(ax, 'scales by horizon'); grid(ax, 'on');
raplot.util.savefig(f, ctx, file);
end
