function adjacency(ctx)
%ADJACENCY  Per configuration: the all-scales weight of every pair with its edges marked, the edges as a
% graph, and band-scope edges per pair. Overview: edges per configuration, all-scales and band.
% Check: which pairs pass the BY decision inside their configuration and family.
L = ctx.L;
E = raplot.util.readp(ctx, 'adjacency/edges');
fam = ctx.man.adjacency.families;
isall = E.family == "all";
ea = accumarray(double(E.k(isall)) + 1, double(E.edge(isall)), [L.K 1]);
eb = accumarray(double(E.k(~isall)) + 1, double(E.edge(~isall)), [L.K 1]);
[f, tl] = raplot.util.newfig(1000, 1300, 1, 1, sprintf('adjacency: %d of %d all-scales edges, %d of %d band edges (manifest %d, %d)', ...
    sum(ea), sum(isall), sum(eb), sum(~isall), fam.all.edges, fam.band.edges), ctx);
ax = nexttile(tl);
barh(ax, 0:L.K-1, [ea eb], 'stacked');
ax.YTick = 0:L.K-1; ax.YTickLabel = L.kshort; ax.YDir = 'reverse'; ax.FontSize = 6;
legend(ax, {'all-scales edges (of 91 pairs)', 'band edges'}, 'Location', 'best'); grid(ax, 'on');
title(ax, 'edges per configuration');
raplot.util.savefig(f, ctx, '00_overview.png');

U = raplot.util.units(ctx, 'k');
N = L.N;
parfor (n = 1:numel(U.k), ctx.M)
    k = U.k(n);
    e = E(E.k == k, :);
    a = e(e.family == "all", :);
    b = e(e.family ~= "all", :);
    W = nan(N); A = false(N);
    ia = double(a.i_a) + 1; ib = double(a.i_b) + 1;
    W(sub2ind([N N], ia, ib)) = a.weight; W(sub2ind([N N], ib, ia)) = a.weight;
    A(sub2ind([N N], ia, ib)) = a.edge; A(sub2ind([N N], ib, ia)) = a.edge;
    BE = accumarray([double(b.i_a) + 1, double(b.i_b) + 1], double(b.edge), [N N]);
    BT = accumarray([double(b.i_a) + 1, double(b.i_b) + 1], 1, [N N]);
    [file, ttl] = raplot.util.names(ctx, k, [], 'adjacency');
    [f, tl] = raplot.util.newfig(2000, 760, 1, 3, ttl, ctx);
    ax = nexttile(tl);
    im = imagesc(ax, 0:N-1, 0:N-1, W); set(im, 'AlphaData', ~isnan(W)); ax.Color = [.82 .82 .82];
    clim(ax, [0 1]); colorbar(ax); axis(ax, 'square'); hold(ax, 'on');
    [r, c] = find(A); plot(ax, c - 1, r - 1, 'k*', 'MarkerSize', 5);
    ax.XTick = 0:N-1; ax.YTick = 0:N-1; ax.XTickLabel = L.sid; ax.YTickLabel = L.sid; ax.XTickLabelRotation = 60;
    title(ax, sprintf('all-scales weight (share of significant in-cone cells); * edge: %d of %d pairs', sum(a.edge), height(a)));
    ax = nexttile(tl);
    Wz = W; Wz(isnan(Wz) | ~A) = 0;
    G = graph(Wz, cellstr(L.sid), 'upper', 'omitselfloops');
    if numedges(G) > 0
        plot(ax, G, 'Layout', 'circle', 'LineWidth', 0.5 + 4 * G.Edges.Weight, 'NodeColor', [.2 .3 .6], 'EdgeColor', [.85 .33 .1], 'Interpreter', 'none');
    else
        plot(ax, G, 'Layout', 'circle', 'Interpreter', 'none');
    end
    axis(ax, 'off'); axis(ax, 'square');
    title(ax, 'all-scales edges (width = weight)');
    ax = nexttile(tl);
    Z = BE; Z(BT == 0) = NaN;
    im = imagesc(ax, 0:N-1, 0:N-1, Z); set(im, 'AlphaData', ~isnan(Z)); ax.Color = [.82 .82 .82];
    colorbar(ax); axis(ax, 'square');
    for q = find(BT)'
        [r, c] = ind2sub([N N], q);
        text(ax, c - 1, r - 1, sprintf('%d/%d', BE(q), BT(q)), 'HorizontalAlignment', 'center', 'FontSize', 6);
    end
    ax.XTick = 0:N-1; ax.YTick = 0:N-1; ax.XTickLabel = L.sid; ax.YTickLabel = L.sid; ax.XTickLabelRotation = 60;
    title(ax, sprintf('band scopes: edges / tests per pair (%d of %d; grey = no shared band)', sum(b.edge), height(b)));
    raplot.util.savefig(f, ctx, file);
end
end
