function events(ctx)
%EVENTS  Per configuration: series x month raster of events, red above / blue below, grey where the row
% is undefined, with each row's threshold and count. Overview: events per row.
% Check: events fire on the row's own threshold (|resid| > u_star), never a fixed sigma.
L = ctx.L;
F = raplot.util.readp(ctx, 'events/flags');
TH = raplot.util.readp(ctx, 'tails/thresholds', {'k', 'i', 'u_star'});
[R, mon] = raplot.util.field(ctx, 'grid/resid', 'resid');
P = numel(mon);
F.v = double(F.sign) .* double(F.event);
F.v(~F.defined) = NaN;
[V, ~] = raplot.util.field(ctx, [], 'v', F);
U_ = nan(L.K, L.N); U_(sub2ind(size(U_), double(TH.k) + 1, double(TH.i) + 1)) = TH.u_star;
cnt = sum(abs(V), 3, 'omitnan');
mis = squeeze(sum(xor(abs(R) > U_, abs(V) == 1) & ~isnan(V), 3));
[f, tl] = raplot.util.newfig(900, 1300, 1, 1, sprintf('events: %d events (manifest %d); months where event differs from |resid| > u_star: %d', ...
    sum(cnt(:)), ctx.man.events.rows.residual.events, sum(mis(:))), ctx);
raplot.util.kxn(nexttile(tl), ctx, cnt, 'events per row');
raplot.util.savefig(f, ctx, '00_overview.png');

U = raplot.util.units(ctx, 'k');
parfor (n = 1:numel(U.k), ctx.M)
    k = U.k(n);
    Z = squeeze(V(k+1, :, :));
    [file, ttl] = raplot.util.names(ctx, k, [], 'events');
    [f, tl] = raplot.util.newfig(1500, 650, 1, 1, ttl, ctx);
    ax = nexttile(tl);
    im = imagesc(ax, 1:P, 0:L.N-1, Z); set(im, 'AlphaData', ~isnan(Z)); ax.Color = [.82 .82 .82];
    clim(ax, [-1 1]); colormap(ax, [0.13 0.40 0.67; 1 1 1; 0.70 0.09 0.17]);
    ax.YTick = 0:L.N-1;
    ax.YTickLabel = compose("%02d %s  u* %.2f  n %d", (0:L.N-1)', L.sid, U_(k+1, :)', cnt(k+1, :)');
    ax.XTick = 1:6:P; ax.XTickLabel = string(mon(1:6:end), 'yyyy-MM'); ax.XTickLabelRotation = 60;
    title(ax, sprintf('residual events: red resid > u*, blue resid < -u*; %d events', sum(cnt(k+1, :))));
    raplot.util.savefig(f, ctx, file);
end
end
