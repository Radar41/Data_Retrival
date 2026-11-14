function tails(ctx)
%TAILS  Per row: the Hill plot with its chosen n_tail; mean excess and GPD shape (with its interval)
% across the threshold grid, with the chosen threshold u_star; the rolling Hill estimate over time.
% Overview: which quantile of the grid each row's threshold sits at, and how many rows sit at each.
% Check: the threshold rule (Track B: most rows at the grid's floor).
L = ctx.L;
HC = raplot.util.readp(ctx, 'tails/hill_curve');
ME = raplot.util.readp(ctx, 'tails/mean_excess');
TH = raplot.util.readp(ctx, 'tails/thresholds');
RH = raplot.util.readp(ctx, 'tails/rolling_hill');
qs = ctx.man.tails.threshold_quantiles;
mon = sort(raplot.util.readp(ctx, 'grid/month').t);
P = numel(mon);

Q = nan(L.K, L.N);
Q(sub2ind(size(Q), double(TH.k) + 1, double(TH.i) + 1)) = qs(double(TH.u) + 1);
[f, tl] = raplot.util.newfig(1600, 1300, 1, 2, 'tails: chosen threshold of every row', ctx);
raplot.util.kxn(nexttile(tl), ctx, Q, 'quantile of u_star on the threshold grid', [min(qs) max(qs)]);
ax = nexttile(tl);
histogram(ax, Q(:), [qs(:) - 0.005; qs(end) + 0.005]);
xlabel(ax, 'threshold quantile'); ylabel(ax, 'rows');
title(ax, sprintf('rows by threshold quantile: %d of %d at the floor %.2f', sum(Q(:) == min(qs)), sum(~isnan(Q(:))), min(qs)));
grid(ax, 'on');
raplot.util.savefig(f, ctx, '00_overview.png');

U = raplot.util.units(ctx, 'row');
parfor (n = 1:numel(U.k), ctx.M)
    k = U.k(n); i = U.i(n);
    h = sortrows(HC(HC.k == k & HC.i == i, :), 'n_tail');
    m = sortrows(ME(ME.k == k & ME.i == i, :), 'u');
    t = TH(TH.k == k & TH.i == i, :);
    r = RH(RH.k == k & RH.i == i, :);
    [file, ttl] = raplot.util.names(ctx, k, i, 'tails');
    [f, tl] = raplot.util.newfig(1400, 950, 2, 2, ttl, ctx);
    ax = nexttile(tl);
    errorbar(ax, h.n_tail, h.gamma, h.se, 'k.-'); hold(ax, 'on');
    s = h(h.star, :);
    plot(ax, s.n_tail, s.gamma, 'rp', 'MarkerSize', 12, 'MarkerFaceColor', 'r');
    xlabel(ax, 'n_tail'); ylabel(ax, 'gamma');
    title(ax, sprintf('Hill plot; star n_tail %s', strjoin(string(s.n_tail), ','))); grid(ax, 'on');
    ax = nexttile(tl);
    plot(ax, m.threshold, m.mean_excess, 'k.-'); hold(ax, 'on');
    if height(t) == 1, xline(ax, t.u_star, 'r-', sprintf('u_star %.2f (q %.2f, %d exceed)', t.u_star, qs(t.u + 1), t.n_exceed), 'Interpreter', 'none'); end
    xlabel(ax, 'threshold on |resid|'); ylabel(ax, 'mean excess');
    title(ax, 'mean excess over the threshold grid'); grid(ax, 'on');
    ax = nexttile(tl);
    ok = ~isnan(m.gpd_shape);
    errorbar(ax, m.threshold(ok), m.gpd_shape(ok), m.gpd_shape(ok) - m.gpd_ci_lo(ok), m.gpd_ci_hi(ok) - m.gpd_shape(ok), 'k.'); hold(ax, 'on');
    plot(ax, m.threshold(m.stable), m.gpd_shape(m.stable), 'go', 'MarkerSize', 7);
    if height(t) == 1, xline(ax, t.u_star, 'r-'); end
    xlabel(ax, 'threshold on |resid|'); ylabel(ax, 'GPD shape');
    title(ax, 'GPD shape and profile-likelihood interval (green: stable)'); grid(ax, 'on');
    ax = nexttile(tl);
    r = sortrows(r, 't'); [~, tt] = ismember(r.t, mon);
    fill(ax, [tt; flipud(tt)], [r.gamma - r.se; flipud(r.gamma + r.se)], [.8 .85 .95], 'EdgeColor', 'none'); hold(ax, 'on');
    plot(ax, tt, r.gamma, 'k-');
    ax.XTick = 1:6:P; ax.XTickLabel = string(mon(1:6:end), 'yyyy-MM'); xlim(ax, [1 P]); ax.XTickLabelRotation = 60;
    title(ax, sprintf('rolling Hill gamma +- se (window %d, n_tail %d)', ctx.man.config.tails_rolling_window, ctx.man.config.tails_rolling_n_tail));
    grid(ax, 'on');
    raplot.util.savefig(f, ctx, file);
end
end
