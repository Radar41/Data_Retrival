function coincidence(ctx)
%COINCIDENCE  Per configuration: one leader x follower tile per window [delta_min, delta_max]: colour =
% rate (share of the leader's eligible events followed by a follower event), white dot p <= 0.05, black
% ring p at the surrogate floor. Overview: tests at p <= 0.05 and at the floor per configuration.
L = ctx.L;
T = raplot.util.readp(ctx, 'coincidence/precursor');
c = ctx.man.coincidence;
pf = c.null.smallest_p_value;
atf = abs(T.p_value - pf) < 1e-12;
a05 = accumarray(double(T.k) + 1, double(T.p_value <= 0.05), [L.K 1]);
afl = accumarray(double(T.k) + 1, double(atf), [L.K 1]);
[f, tl] = raplot.util.newfig(1000, 1300, 1, 1, sprintf('coincidence: %d tests, %d at p <= 0.05, %d at the floor %.4f', ...
    height(T), sum(a05), sum(afl), pf), ctx);
ax = nexttile(tl);
barh(ax, 0:L.K-1, [a05 afl]);
ax.YTick = 0:L.K-1; ax.YTickLabel = L.kshort; ax.YDir = 'reverse'; ax.FontSize = 6;
legend(ax, {'p <= 0.05', 'p at floor'}, 'Location', 'best'); grid(ax, 'on');
title(ax, sprintf('per configuration (%d tests each)', height(T) / L.K));
raplot.util.savefig(f, ctx, '00_overview.png');

W = c.windows;
nw = size(W, 1);
N = L.N;
U = raplot.util.units(ctx, 'k');
parfor (n = 1:numel(U.k), ctx.M)
    k = U.k(n);
    t = T(T.k == k, :);
    [file, ttl] = raplot.util.names(ctx, k, [], 'coincidence');
    cols = ceil(nw / 3);
    [f, tl] = raplot.util.newfig(2400, 1500, 3, cols, ttl + "   rows: leader i_a, columns: follower i_b", ctx);
    for w = 1:nw
        s = t(t.delta_min == W(w, 1) & t.delta_max == W(w, 2), :);
        a = double(s.i_a) + 1; b = double(s.i_b) + 1;
        Z = nan(N); Z(sub2ind([N N], a, b)) = s.rate;
        ax = nexttile(tl);
        im = imagesc(ax, 0:N-1, 0:N-1, Z); set(im, 'AlphaData', ~isnan(Z)); ax.Color = [.82 .82 .82];
        clim(ax, [0 1]); axis(ax, 'square'); hold(ax, 'on');
        sig = s.p_value <= 0.05;
        fl = abs(s.p_value - pf) < 1e-12;
        plot(ax, b(sig) - 1, a(sig) - 1, 'wo', 'MarkerFaceColor', 'w', 'MarkerSize', 3);
        plot(ax, b(fl) - 1, a(fl) - 1, 'ko', 'MarkerSize', 6);
        ax.XTick = 0:N-1; ax.YTick = 0:N-1; ax.FontSize = 6;
        if w > nw - cols, ax.XTickLabel = L.sid; ax.XTickLabelRotation = 90; else, ax.XTickLabel = compose('%d', 0:N-1); end
        if mod(w - 1, cols) == 0, ax.YTickLabel = L.sid; else, ax.YTickLabel = compose('%d', 0:N-1); end
        title(ax, sprintf('window [%d, %d]: %d at p <= 0.05, %d at floor', W(w, 1), W(w, 2), sum(sig), sum(fl)), 'FontSize', 8);
        if w == nw, cb = colorbar(ax); cb.Layout.Tile = 'east'; cb.Label.String = 'rate'; end
    end
    raplot.util.savefig(f, ctx, file);
end
end
