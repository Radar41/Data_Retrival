function coherence(ctx)
%COHERENCE  Per configuration: all 91 pairs on one page. Upper triangle (row i_a, column i_b): the r2
% scalogram of the pair (month x period), outside-cone washed out, significant cells outlined. Lower
% triangle: the all-scales scope p and share of significant in-cone cells. Overview: the share of
% in-cone cells significant per configuration, and every pair's all-scales p.
L = ctx.L;
SC = raplot.util.readp(ctx, 'coherence/scope');
S = sortrows(raplot.util.readp(ctx, 'wavelet/scale'), 'j');
mon = sort(raplot.util.readp(ctx, 'grid/month').t);
J = height(S); P = numel(mon);
lp = log2(S.period);
q = ctx.man.config.coherence_quantile;
pfloor = ctx.man.coherence.surrogates.smallest_p_value;

C = raplot.util.readp(ctx, 'coherence/cells', {'k', 'in_coi', 'significant'});
share = splitapply(@(s, c) sum(s & c) / sum(c), C.significant, C.in_coi, double(C.k) + 1);
clear C
all_ = SC(SC.band_a == -1 & SC.band_b == -1, :);
[pr, ~, gp] = unique([all_.i_a, all_.i_b], 'rows');
PM = nan(L.K, size(pr, 1));
PM(sub2ind(size(PM), double(all_.k) + 1, gp)) = -log10(all_.p_value);
[f, tl] = raplot.util.newfig(2000, 1300, 1, 2, 'coherence: every configuration and pair', ctx);
ax = nexttile(tl);
barh(ax, 0:L.K-1, share); xline(ax, 1 - q, 'r--', sprintf('%.2f', 1 - q));
ax.YTick = 0:L.K-1; ax.YTickLabel = L.kshort; ax.YDir = 'reverse'; ax.FontSize = 6;
title(ax, 'share of in-cone cells significant, per configuration (all 91 pairs)'); grid(ax, 'on');
ax = nexttile(tl);
imagesc(ax, 1:size(pr, 1), 0:L.K-1, PM); colorbar(ax); clim(ax, [0 -log10(pfloor)]);
ax.YTick = 0:L.K-1; ax.YTickLabel = L.kshort; ax.FontSize = 6;
ax.XTick = 1:5:size(pr, 1); ax.XTickLabel = compose('%d-%d', pr(1:5:end, 1), pr(1:5:end, 2)); ax.XTickLabelRotation = 90;
title(ax, '-log10 p of the all-scales scope, configuration x pair (i_a-i_b); top of scale = surrogate floor ' + string(sprintf('%.4f', pfloor)));
raplot.util.savefig(f, ctx, '00_overview.png');

U = raplot.util.units(ctx, 'k');
parfor (n = 1:numel(U.k), ctx.M)
    k = U.k(n);
    Ck = raplot.util.readp(ctx, 'coherence/cells', {'k', 'i_a', 'i_b', 'j', 't', 'r2', 'in_coi', 'significant'}, rowfilter("k").k == k);
    sk = SC(SC.k == k & SC.band_a == -1 & SC.band_b == -1, :);
    [~, tt] = ismember(Ck.t, mon);
    [file, ttl] = raplot.util.names(ctx, k, [], 'coherence');
    [f, tl] = raplot.util.newfig(2600, 2500, L.N, L.N, ttl + "   upper: r2 (0..1) by month x period, black = significant; lower: all-scales p and share", ctx);
    tl.TileSpacing = 'tight';
    for a = 0:L.N-1
        for b = 0:L.N-1
            ax = nexttile(tl, a * L.N + b + 1);
            if a == b
                axis(ax, 'off'); text(ax, 0.5, 0.5, sprintf('%02d\n%s', a, L.sid(a+1)), 'HorizontalAlignment', 'center', 'FontSize', 9, 'FontWeight', 'bold');
            elseif a < b
                sel = Ck.i_a == a & Ck.i_b == b;
                Z = nan(J, P); Cc = false(J, P); G = false(J, P);
                idx = sub2ind([J P], double(Ck.j(sel)) + 1, tt(sel));
                Z(idx) = Ck.r2(sel); Cc(idx) = Ck.in_coi(sel); G(idx) = Ck.significant(sel);
                imagesc(ax, 1:P, lp, Z); clim(ax, [0 1]);
                raplot.util.coi(ax, 1:P, lp, Cc);
                if any(G(:)), contour(ax, 1:P, lp, double(G), [0.5 0.5], 'k-', 'LineWidth', 0.5); end
                ax.XTick = []; ax.YTick = [];
            else
                r = sk(sk.i_a == b & sk.i_b == a, :);
                axis(ax, 'off');
                if height(r) == 1
                    pv = r.p_value; sh = double(r.n_significant) / double(r.n_cells);
                    c = [1 1 1] - min(1, -log10(pv) / -log10(pfloor)) * [0 .6 .6];
                    patch(ax, [0 1 1 0], [0 0 1 1], c, 'EdgeColor', [.8 .8 .8]);
                    text(ax, 0.5, 0.5, sprintf('p %.3f\nshare %.2f\nlag %.1f mo', pv, sh, r.lag_months), 'HorizontalAlignment', 'center', 'FontSize', 7);
                    xlim(ax, [0 1]); ylim(ax, [0 1]);
                end
            end
        end
    end
    raplot.util.savefig(f, ctx, file);
end
end
