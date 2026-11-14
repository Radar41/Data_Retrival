function wavelet(ctx)
%WAVELET  Per row: the residual row, and its Morlet power (over the row's variance) by month and period,
% outside-cone cells washed out, red-noise-significant cells outlined. Overview: share of in-cone cells
% that are significant (red-noise test at the stated level) and the row's lag-1 autocorrelation.
L = ctx.L;
[R, mon] = raplot.util.field(ctx, 'grid/resid', 'resid');
W = raplot.util.readp(ctx, 'wavelet/cwt', {'k', 'i', 'j', 't', 'power', 'in_coi', 'significant'});
S = sortrows(raplot.util.readp(ctx, 'wavelet/scale'), 'j');
WS = raplot.util.readp(ctx, 'wavelet/series');
J = height(S); P = numel(mon);
lev = ctx.man.wavelet.red_noise.significance;

share = nan(L.K, L.N); ar1 = nan(L.K, L.N);
[g, kk, ii] = findgroups(W.k, W.i);
s = splitapply(@(sig, c) sum(sig & c) / sum(c), W.significant, W.in_coi, g);
share(sub2ind(size(share), double(kk) + 1, double(ii) + 1)) = s;
ar1(sub2ind(size(ar1), double(WS.k) + 1, double(WS.i) + 1)) = WS.ar1;
[f, tl] = raplot.util.newfig(1500, 1300, 1, 2, sprintf('wavelet: Morlet, %d scales, every row', J), ctx);
raplot.util.kxn(nexttile(tl), ctx, share, sprintf('share of in-cone cells significant (expect about %.2f under the null)', 1 - lev), [0 0.3]);
raplot.util.kxn(nexttile(tl), ctx, ar1, 'lag-1 autocorrelation of the row (its red-noise reference)', [-1 1], raplot.util.rdbu());
raplot.util.savefig(f, ctx, '00_overview.png');

U = raplot.util.units(ctx, 'byk');
part = cell(numel(U.k), 1);
for n = 1:numel(U.k), part{n} = W(W.k == U.k(n), :); end
clear W
lp = log2(S.period);
parfor (n = 1:numel(U.k), ctx.M)
    k = U.k(n);
    Wk = part{n};
    for i = U.is{n}'
        w = Wk(Wk.i == i, :);
        [~, tt] = ismember(w.t, mon);
        Z = nan(J, P); C = false(J, P); G = false(J, P);
        idx = sub2ind([J P], double(w.j) + 1, tt);
        Z(idx) = w.power; C(idx) = w.in_coi; G(idx) = w.significant;
        v = WS.variance(WS.k == k & WS.i == i);
        [file, ttl] = raplot.util.names(ctx, k, i, 'wavelet');
        [f, tl] = raplot.util.newfig(1300, 900, 3, 1, ttl, ctx);
        ax = nexttile(tl);
        plot(ax, 1:P, squeeze(R(k+1, i+1, :)), 'k-'); yline(ax, 0, ':');
        ax.XTick = 1:6:P; ax.XTickLabel = string(mon(1:6:end), 'yyyy-MM'); xlim(ax, [1 P]);
        title(ax, sprintf('resid row (variance %.3g, ar1 %.2f)', v, WS.ar1(WS.k == k & WS.i == i))); grid(ax, 'on');
        ax = nexttile(tl, [2 1]);
        imagesc(ax, 1:P, lp, log2(Z / v)); colorbar(ax); clim(ax, [-6 4]);
        raplot.util.coi(ax, 1:P, lp, C);
        if any(G(:)), contour(ax, 1:P, lp, double(G), [0.5 0.5], 'k-', 'LineWidth', 0.9); end
        ax.YTick = 1:5; ax.YTickLabel = string(2.^(1:5)); ylabel(ax, 'period (months)');
        ax.XTick = 1:6:P; ax.XTickLabel = string(mon(1:6:end), 'yyyy-MM'); ax.XTickLabelRotation = 60;
        title(ax, sprintf('log2 power / variance; black = significant at %.2f (%d of %d in-cone cells); white wash = outside the cone', ...
            lev, sum(G(:) & C(:)), sum(C(:))));
        raplot.util.savefig(f, ctx, file);
    end
end
end
