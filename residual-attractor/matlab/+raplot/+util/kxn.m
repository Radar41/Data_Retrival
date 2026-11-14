function ax = kxn(ax, ctx, M, ttl, lims, cmap)
%KXN  Heatmap of one value per (configuration k, series i): rows k (54), columns i (14).
% NaN cells are drawn grey. Every overview of a row stage uses this, so every row is one cell.
L = ctx.L;
im = imagesc(ax, 0:L.N-1, 0:L.K-1, M);
set(im, 'AlphaData', ~isnan(M));
ax.Color = [.82 .82 .82];
if nargin > 4 && ~isempty(lims), clim(ax, lims); end
if nargin > 5 && ~isempty(cmap), colormap(ax, cmap); end
colorbar(ax);
ax.YTick = 0:L.K-1; ax.YTickLabel = L.kshort; ax.FontSize = 6;
ax.XTick = 0:L.N-1; ax.XTickLabel = compose("%02d %s", (0:L.N-1)', L.sid); ax.XTickLabelRotation = 60;
title(ax, ttl, 'FontSize', 9);
end
