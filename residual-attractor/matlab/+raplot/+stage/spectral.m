function spectral(ctx)
%SPECTRAL  Per row: the global wavelet spectrum against its red-noise threshold with the row's bands
% shaded; each band's scale-averaged power over time against its threshold; the dominant period over time.
% Overview: number of bands per row. Check: bands sit where the spectrum clears the threshold.
L = ctx.L;
GL = raplot.util.readp(ctx, 'spectral/global');
BD = raplot.util.readp(ctx, 'spectral/bands');
BP = raplot.util.readp(ctx, 'spectral/band_power');
DM = raplot.util.readp(ctx, 'spectral/dominant');
BC = raplot.util.readp(ctx, 'spectral/band_count');
S = sortrows(raplot.util.readp(ctx, 'wavelet/scale'), 'j');
mon = sort(raplot.util.readp(ctx, 'grid/month').t);
P = numel(mon);

M = nan(L.K, L.N);
M(sub2ind(size(M), double(BC.k) + 1, double(BC.i) + 1)) = BC.band_count;
[f, tl] = raplot.util.newfig(900, 1300, 1, 1, sprintf('spectral: band count, every row (%d bands in all)', height(BD)), ctx);
raplot.util.kxn(nexttile(tl), ctx, M, 'bands per row', [-0.5 max(M(:)) + 0.5], parula(max(M(:)) + 1));
raplot.util.savefig(f, ctx, '00_overview.png');

U = raplot.util.units(ctx, 'row');
parfor (n = 1:numel(U.k), ctx.M)
    k = U.k(n); i = U.i(n);
    g = sortrows(GL(GL.k == k & GL.i == i, :), 'j');
    b = BD(BD.k == k & BD.i == i, :);
    bp = BP(BP.k == k & BP.i == i, :);
    dm = DM(DM.k == k & DM.i == i, :);
    per = S.period(double(g.j) + 1);
    [file, ttl] = raplot.util.names(ctx, k, i, 'spectral');
    [f, tl] = raplot.util.newfig(1300, 1000, 3, 1, ttl, ctx);
    ax = nexttile(tl); hold(ax, 'on');
    yl = [min([g.gws; g.threshold]) / 2, max([g.gws; g.threshold]) * 2];
    for q = 1:height(b)
        patch(ax, [b.period_lo(q) b.period_hi(q) b.period_hi(q) b.period_lo(q)], yl([1 1 2 2]), [.95 .85 .4], ...
            'EdgeColor', 'none', 'FaceAlpha', 0.5, 'HandleVisibility', 'off');
    end
    plot(ax, per, g.gws, 'k.-'); plot(ax, per, g.threshold, 'r--');
    plot(ax, per(g.above), g.gws(g.above), 'ko', 'MarkerFaceColor', 'k');
    set(ax, 'XScale', 'log', 'YScale', 'log'); ylim(ax, yl); xlim(ax, [min(per) max(per)]);
    xlabel(ax, 'period (months)');
    legend(ax, {'global spectrum', 'red-noise threshold', 'above'}, 'Location', 'best');
    title(ax, sprintf('global wavelet spectrum; %d band(s) shaded', height(b))); grid(ax, 'on');
    ax = nexttile(tl); hold(ax, 'on');
    cols = lines(max(1, height(b)));
    for q = 1:height(b)
        r = sortrows(bp(bp.band == b.band(q), :), 't');
        [~, tt] = ismember(r.t, mon);
        plot(ax, tt, r.sap, '-', 'Color', cols(q, :));
        yline(ax, b.sap_threshold(q), '--', 'Color', cols(q, :), 'HandleVisibility', 'off');
    end
    ax.XTick = 1:6:P; ax.XTickLabel = string(mon(1:6:end), 'yyyy-MM'); xlim(ax, [1 P]);
    title(ax, 'scale-averaged power of each band (dashed: its threshold)'); grid(ax, 'on');
    if height(b) > 0
        legend(ax, compose("band %d: %.1f-%.1f mo", double(b.band), b.period_lo, b.period_hi), 'Location', 'best');
    end
    ax = nexttile(tl);
    dm = sortrows(dm, 't'); [~, tt] = ismember(dm.t, mon);
    plot(ax, tt, dm.period, 'k.-'); set(ax, 'YScale', 'log');
    ax.XTick = 1:6:P; ax.XTickLabel = string(mon(1:6:end), 'yyyy-MM'); xlim(ax, [1 P]);
    ylabel(ax, 'months'); title(ax, 'dominant period by month'); grid(ax, 'on');
    raplot.util.savefig(f, ctx, file);
end
end
