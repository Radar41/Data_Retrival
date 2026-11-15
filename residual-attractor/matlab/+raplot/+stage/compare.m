function compare(ctx)
%COMPARE  Stage 10. Per series: configuration x configuration matrices of the pairwise (DM / CW) p,
% the CPA p and the fluctuation-test reject; the MCS p of every configuration; the loss over time.
% Overview: per series, how many pairs differ under each test and the MCS size.
L = ctx.L;
PW = raplot.util.readp(ctx, 'compare/pairwise', {'i', 'k_a', 'k_b', 'test', 'p_value'});
CP = raplot.util.readp(ctx, 'compare/cpa', {'i', 'k_a', 'k_b', 'p_value'});
FS = raplot.util.readp(ctx, 'compare/fluctuation_sup', {'i', 'k_a', 'k_b', 'reject'});
MC = raplot.util.readp(ctx, 'compare/mcs');
[LO, mon] = raplot.util.field(ctx, 'compare/loss', 'loss');
c = ctx.man.compare;

cnt = zeros(L.N, 4);
for i = 0:L.N-1
    cnt(i+1, :) = [sum(PW.p_value(PW.i == i) < 0.05), sum(CP.p_value(CP.i == i) < 0.05), ...
                   sum(double(FS.reject(FS.i == i)), 'omitnan'), sum(MC.in_set(MC.i == i))];
end
[f, tl] = raplot.util.newfig(1500, 750, 1, 1, sprintf('compare: %d pairs per series, MCS over %d models (alpha %.2g)', ...
    c.pairs_per_series, c.mcs.models_per_series, c.mcs.alpha), ctx);
ax = nexttile(tl);
bar(ax, 0:L.N-1, cnt);
ax.XTick = 0:L.N-1; ax.XTickLabel = L.sid; ax.XTickLabelRotation = 60;
legend(ax, {sprintf('DM/CW p < 0.05 (total %d)', sum(cnt(:, 1))), sprintf('CPA p < 0.05 (total %d)', sum(cnt(:, 2))), ...
    sprintf('fluctuation rejects (total %d)', sum(cnt(:, 3))), sprintf('in MCS (total %d)', sum(cnt(:, 4)))}, 'Location', 'best');
title(ax, 'counts per series'); grid(ax, 'on');
raplot.util.savefig(f, ctx, '00_overview.png');

U = raplot.util.units(ctx, 'i');
for i = U.i'
    [file, ttl] = raplot.util.names(ctx, [], i, 'compare');
    [f, tl] = raplot.util.newfig(1900, 1250, 2, 3, ttl, ctx);
    mat(nexttile(tl), ctx, PW(PW.i == i, :), 'p_value', @(p) -log10(p), [0 4], 'pairwise DM / CW: -log10 p');
    mat(nexttile(tl), ctx, CP(CP.i == i, :), 'p_value', @(p) -log10(p), [0 4], 'CPA: -log10 p');
    mat(nexttile(tl), ctx, FS(FS.i == i, :), 'reject', @double, [0 1], sprintf('fluctuation sup reject (critical %.3f)', c.fluctuation.critical_value));
    ax = nexttile(tl);
    m = sortrows(MC(MC.i == i, :), 'k');
    b = bar(ax, m.k, m.mcs_p_value, 'FaceColor', 'flat');
    b.CData = repmat([.6 .6 .6], height(m), 1); b.CData(m.in_set, :) = repmat([.2 .6 .3], sum(m.in_set), 1);
    yline(ax, c.mcs.alpha, 'k--', 'alpha');
    rep = m.represented_by ~= m.k & m.represented_by >= 0;
    hold(ax, 'on'); plot(ax, m.k(rep), zeros(sum(rep), 1), 'rx');
    ax.XTick = 0:L.K-1; ax.XTickLabel = compose('%02d', 0:L.K-1); ax.XTickLabelRotation = 90; ax.FontSize = 6;
    title(ax, sprintf('MCS p by configuration (green in set: %d; red x represented by a twin)', sum(m.in_set)));
    ax = nexttile(tl, [1 2]);
    Z = log10(squeeze(LO(:, i+1, :)));
    im = imagesc(ax, 1:numel(mon), 0:L.K-1, Z); set(im, 'AlphaData', isfinite(Z)); ax.Color = [.82 .82 .82];
    colorbar(ax);
    ax.YTick = 0:L.K-1; ax.YTickLabel = L.kshort; ax.FontSize = 6;
    ax.XTick = 1:6:numel(mon); ax.XTickLabel = string(mon(1:6:end), 'yyyy-MM'); ax.XTickLabelRotation = 60;
    title(ax, sprintf('log10 loss (%s) by configuration and month', c.loss));
    raplot.util.savefig(f, ctx, file);
end
end

function mat(ax, ctx, T, var, tf, lims, ttl)
K = ctx.L.K;
M = nan(K);
v = tf(double(T.(var)));
M(sub2ind([K K], double(T.k_a) + 1, double(T.k_b) + 1)) = v;
M(sub2ind([K K], double(T.k_b) + 1, double(T.k_a) + 1)) = v;
im = imagesc(ax, 0:K-1, 0:K-1, M); set(im, 'AlphaData', ~isnan(M)); ax.Color = [.82 .82 .82];
clim(ax, lims); colorbar(ax); axis(ax, 'square');
ax.XTick = 0:K-1; ax.YTick = 0:K-1; ax.XTickLabel = compose('%02d', 0:K-1); ax.YTickLabel = ctx.L.kshort;
ax.FontSize = 5; ax.XTickLabelRotation = 90;
title(ax, sprintf('%s (%d pairs)', ttl, height(T)), 'FontSize', 8);
end
