function common_mode(ctx)
%COMMON_MODE  Per configuration: lambda1 against its surrogate band and the Marchenko-Pastur edge; its p;
% absorption ratio and turnover of the leading vector; the leading loadings by series and month; every
% eigenvalue. Overview: defined months per configuration, and lambda1 over its band, configuration x month.
L = ctx.L;
M = raplot.util.readp(ctx, 'common_mode/month');
V = raplot.util.readp(ctx, 'common_mode/vector');
E = raplot.util.readp(ctx, 'common_mode/eigen');
mon = sort(raplot.util.readp(ctx, 'grid/month').t);
P = numel(mon);
[~, tt] = ismember(M.t, mon);
def = ~isnan(M.lambda1);
dk = accumarray(double(M.k) + 1, double(def), [L.K 1]);
X = nan(L.K, P); X(sub2ind(size(X), double(M.k) + 1, tt)) = M.lambda1 ./ M.lambda1_q;
[f, tl] = raplot.util.newfig(2000, 1300, 1, 2, sprintf('common_mode: %d defined months (window %d)', sum(dk), ctx.man.common_mode.window), ctx);
ax = nexttile(tl);
barh(ax, 0:L.K-1, dk); ax.YTick = 0:L.K-1; ax.YTickLabel = L.kshort; ax.YDir = 'reverse'; ax.FontSize = 6;
title(ax, 'defined months per configuration'); grid(ax, 'on');
ax = nexttile(tl);
im = imagesc(ax, 1:P, 0:L.K-1, X); set(im, 'AlphaData', ~isnan(X)); ax.Color = [.82 .82 .82];
clim(ax, [0.5 1.5]); colormap(ax, raplot.util.rdbu()); colorbar(ax);
ax.YTick = 0:L.K-1; ax.YTickLabel = L.kshort; ax.FontSize = 6;
ax.XTick = 1:6:P; ax.XTickLabel = string(mon(1:6:end), 'yyyy-MM'); ax.XTickLabelRotation = 60;
title(ax, sprintf('lambda1 / lambda1_q (red: above the band); %d months above', sum(M.lambda1 > M.lambda1_q)));
raplot.util.savefig(f, ctx, '00_overview.png');

[LD, ~] = raplot.util.field(ctx, [], 'loading', V);
N = L.N;
mp = ctx.man.common_mode.mp_edge.value;
U = raplot.util.units(ctx, 'k');
parfor (n = 1:numel(U.k), ctx.M)
    k = U.k(n);
    m = sortrows(M(M.k == k, :), 't'); [~, tm] = ismember(m.t, mon);
    e = E(E.k == k, :); [~, te] = ismember(e.t, mon);
    EV = nan(N, P); EV(sub2ind([N P], double(e.r) + 1, te)) = e.eigenvalue;
    [file, ttl] = raplot.util.names(ctx, k, [], 'common_mode');
    [f, tl] = raplot.util.newfig(1500, 1500, 5, 1, ttl, ctx);
    xt = @(ax) set(ax, 'XTick', 1:6:P, 'XTickLabel', string(mon(1:6:end), 'yyyy-MM'), 'XLim', [0.5 P + 0.5]);
    ax = nexttile(tl);
    plot(ax, tm, m.lambda1, 'k.-', tm, m.lambda1_q, 'r--'); yline(ax, mp, ':', 'MP edge');
    xt(ax); legend(ax, {'lambda1', 'lambda1_q (surrogate band)'}, 'Location', 'best');
    title(ax, sprintf('leading eigenvalue; %d defined months, %d above the band', sum(~isnan(m.lambda1)), sum(m.lambda1 > m.lambda1_q))); grid(ax, 'on');
    ax = nexttile(tl);
    plot(ax, tm, -log10(m.p_value), 'k.-'); yline(ax, -log10(0.05), 'r--', 'p 0.05'); xt(ax);
    title(ax, '-log10 p of lambda1 (raw)'); grid(ax, 'on');
    ax = nexttile(tl);
    yyaxis(ax, 'left'); plot(ax, tm, m.absorption_ratio, '.-'); ylabel(ax, 'absorption ratio');
    yyaxis(ax, 'right'); plot(ax, tm, m.vector_turnover, '.-'); ylabel(ax, 'turnover (rad)');
    xt(ax); title(ax, 'absorption ratio and turnover of the leading vector'); grid(ax, 'on');
    ax = nexttile(tl);
    Z = squeeze(LD(k+1, :, :));
    im = imagesc(ax, 1:P, 0:N-1, Z); set(im, 'AlphaData', ~isnan(Z)); ax.Color = [.82 .82 .82];
    clim(ax, [-1 1]); colormap(ax, raplot.util.rdbu()); colorbar(ax);
    ax.YTick = 0:N-1; ax.YTickLabel = L.sid; xt(ax);
    title(ax, 'leading loadings by series');
    ax = nexttile(tl);
    plot(ax, 1:P, EV', '-'); xt(ax); set(ax, 'YScale', 'log');
    title(ax, 'all eigenvalues of the trailing correlation matrix'); grid(ax, 'on');
    raplot.util.savefig(f, ctx, file);
end
end
