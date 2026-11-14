function bundle_summary(ctx)
%BUNDLE_SUMMARY  Stage 7. Overview only: the stage has one row per (series, configuration), so each
% heatmap cell is one row: sign flips at lag -1 and +1, total rotation, closure at +1.
L = ctx.L;
F = nan(L.K, L.N, 3); Cl = strings(L.K, L.N);
for i = 0:L.N-1
    T = raplot.util.readp(ctx, "bundle_summary/" + L.sid(i+1));
    [~, kk] = ismember(T.config_id, L.cid);
    F(kk, i+1, 1) = T.flips_lag_m1;
    F(kk, i+1, 2) = T.flips_lag_p1;
    F(kk, i+1, 3) = T.total_rotation;
    Cl(kk, i+1) = string(T.closure_p1);
end
[uc, ~, g] = unique(Cl(:));
[f, tl] = raplot.util.newfig(2300, 1300, 1, 4, sprintf('bundle_summary: every row (base.closed %d)', ctx.man.config.base_closed), ctx);
raplot.util.kxn(nexttile(tl), ctx, F(:, :, 1), 'flips_lag_m1');
raplot.util.kxn(nexttile(tl), ctx, F(:, :, 2), 'flips_lag_p1');
raplot.util.kxn(nexttile(tl), ctx, F(:, :, 3), 'total_rotation');
ax = raplot.util.kxn(nexttile(tl), ctx, reshape(g, L.K, L.N), 'closure_p1', [0.5 numel(uc) + 0.5], lines(numel(uc)));
ax.Colorbar.Ticks = 1:numel(uc); ax.Colorbar.TickLabels = uc;
raplot.util.savefig(f, ctx, '00_overview.png');
end
