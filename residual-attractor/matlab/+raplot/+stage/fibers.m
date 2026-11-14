function fibers(ctx)
%FIBERS  Stage 4b. Per series: the fiber X_k at every base point (origin x h), every configuration k,
% one panel per ladder; and the spread of X across configurations at each point.
% Overview: median across-configuration sd of X by series and ladder. Check: the configurations' own
% standardized residuals side by side (points, never pooled).
L = ctx.L;
D = raplot.util.sdates(ctx);
med = nan(L.N, 2); agree = nan(L.N, 2);
lad = ["forward", "backward"];
for i = 0:L.N-1
    F = raplot.util.readp(ctx, "fibers/" + L.sid(i+1), {'ladder', 'x'});
    for q = 1:2
        X = cell2mat(cellfun(@(v) double(v(:))', F.x(F.ladder == lad(q)), 'UniformOutput', false));
        med(i+1, q) = median(std(X, 0, 2, 'omitnan'), 'omitnan');
        agree(i+1, q) = mean(all(X > 0, 2) | all(X < 0, 2));
    end
end
[f, tl] = raplot.util.newfig(1400, 700, 1, 2, 'fibers: spread of X_k across configurations, every series', ctx);
ax = nexttile(tl); bar(ax, 0:L.N-1, med); legend(ax, lad, 'Location', 'best');
ax.XTick = 0:L.N-1; ax.XTickLabel = L.sid; ax.XTickLabelRotation = 60;
title(ax, 'median over base points of sd_k(X_k)'); grid(ax, 'on');
ax = nexttile(tl); bar(ax, 0:L.N-1, agree); legend(ax, lad, 'Location', 'best');
ax.XTick = 0:L.N-1; ax.XTickLabel = L.sid; ax.XTickLabelRotation = 60;
title(ax, 'share of base points where every configuration has the same sign'); grid(ax, 'on');
raplot.util.savefig(f, ctx, '00_overview.png');

U = raplot.util.units(ctx, 'i');
parfor (n = 1:numel(U.i), ctx.M)
    i = U.i(n);
    sid = L.sid(i+1);
    F = raplot.util.readp(ctx, "fibers/" + sid, {'origin', 'ladder', 'h', 'step', 'x'});
    d = D.(char(sid));
    [file, ttl] = raplot.util.names(ctx, [], i, 'fibers');
    [f, tl] = raplot.util.newfig(1600, 1150, 2, 2, ttl, ctx);
    for q = 1:2
        G = sortrows(F(F.ladder == lad(q), :), {'origin', 'h'});
        X = cell2mat(cellfun(@(v) double(v(:))', G.x, 'UniformOutput', false));
        ax = nexttile(tl, q);
        imagesc(ax, 0:L.K-1, 1:height(G), X); clim(ax, [-4 4]); colormap(ax, raplot.util.rdbu()); colorbar(ax);
        ax.XTick = 0:L.K-1; ax.XTickLabel = compose('%02d', 0:L.K-1); ax.XTickLabelRotation = 90; ax.FontSize = 6;
        [uo, first] = unique(G.origin);
        step = max(1, round(numel(uo) / 15));
        ax.YTick = first(1:step:end); ax.YTickLabel = string(d(uo(1:step:end) + 1), 'yyyy-MM');
        xlabel(ax, 'configuration k'); ylabel(ax, 'base point (origin, then h)');
        title(ax, sprintf('%s ladder: X_k, %d base points x %d configurations', lad(q), height(G), size(X, 2)));
        ax = nexttile(tl, q + 2);
        sd = std(X, 0, 2, 'omitnan');
        mx = max(abs(X), [], 2);
        plot(ax, 1:height(G), sd, '-', 1:height(G), mx, '-');
        ax.XTick = first(1:step:end); ax.XTickLabel = string(d(uo(1:step:end) + 1), 'yyyy-MM');
        legend(ax, {'sd over configurations', 'max |X_k|'}, 'Location', 'best');
        title(ax, sprintf('%s ladder: spread at each base point', lad(q))); grid(ax, 'on'); axis(ax, 'tight');
    end
    raplot.util.savefig(f, ctx, file);
end
end
