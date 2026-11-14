function grid(ctx)
%GRID  Stage 9. Per configuration: the archive R[k, i, t], series x holdout month.
% Overview: sd and max |resid| of every row, and the month each row's largest |resid| falls on.
% Check: rows standardized near unit scale; outlier months (April 2020) visible per configuration.
L = ctx.L;
[R, mon] = raplot.util.field(ctx, 'grid/resid', 'resid');
P = numel(mon);
sd = std(R, 0, 3, 'omitnan');
[mx, at] = max(abs(R), [], 3, 'omitnan');
[f, tl] = raplot.util.newfig(2100, 1300, 1, 3, sprintf('grid: R[k, i, t], K %d, N %d, P %d (%s .. %s)', L.K, L.N, P, ...
    string(mon(1), 'yyyy-MM'), string(mon(end), 'yyyy-MM')), ctx);
raplot.util.kxn(nexttile(tl), ctx, sd, 'sd of resid over the holdout');
raplot.util.kxn(nexttile(tl), ctx, mx, 'max |resid|');
ax = nexttile(tl);
c = accumarray(at(:), 1, [P 1]);
bar(ax, 1:P, c);
step = 6; ax.XTick = 1:step:P; ax.XTickLabel = string(mon(1:step:end), 'yyyy-MM'); ax.XTickLabelRotation = 60;
[~, top] = maxk(c, 4);
title(ax, "rows whose max |resid| is in that month; top: " + strjoin(string(mon(top), 'yyyy-MM') + " (" + c(top) + ")", ', '));
ax.XGrid = 'on'; ax.YGrid = 'on';
raplot.util.savefig(f, ctx, '00_overview.png');

U = raplot.util.units(ctx, 'k');
parfor (n = 1:numel(U.k), ctx.M)
    k = U.k(n);
    Z = squeeze(R(k+1, :, :));
    [file, ttl] = raplot.util.names(ctx, k, [], 'grid');
    [f, tl] = raplot.util.newfig(1500, 650, 1, 1, ttl, ctx);
    ax = nexttile(tl);
    im = imagesc(ax, 1:P, 0:L.N-1, Z); set(im, 'AlphaData', ~isnan(Z)); ax.Color = [.82 .82 .82];
    clim(ax, [-4 4]); colormap(ax, raplot.util.rdbu()); colorbar(ax);
    ax.YTick = 0:L.N-1; ax.YTickLabel = compose("%02d %s", (0:L.N-1)', L.sid);
    ax.XTick = 1:6:P; ax.XTickLabel = string(mon(1:6:end), 'yyyy-MM'); ax.XTickLabelRotation = 60;
    title(ax, sprintf('resid = e1 / sigma(t-1), clipped at +-4; NaN cells %d; max |resid| %.2f', sum(isnan(Z(:))), max(abs(Z(:)))));
    raplot.util.savefig(f, ctx, file);
end
end
