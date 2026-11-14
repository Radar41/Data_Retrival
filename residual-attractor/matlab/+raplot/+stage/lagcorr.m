function lagcorr(ctx)
%LAGCORR  Stage 6. Per row: rho(t, lag) of the one-step errors along the base, lags -K..K, and the
% number of pairs behind each value. Overview: mean rho at lag -1 and +1. Check: lead/lag sign along the base.
L = ctx.L;
D = raplot.util.sdates(ctx);
Km = nan(L.K, L.N); Kp = nan(L.K, L.N);
for i = 0:L.N-1
    T = raplot.util.readp(ctx, "lagcorr/" + L.sid(i+1), {'config_id', 'k', 'rho'});
    for k = 0:L.K-1
        r = T(T.config_id == L.cid(k+1), :);
        Km(k+1, i+1) = mean(r.rho(r.k == -1), 'omitnan');
        Kp(k+1, i+1) = mean(r.rho(r.k == 1), 'omitnan');
    end
end
[f, tl] = raplot.util.newfig(1500, 1300, 1, 2, 'lagcorr: mean rho of e1 along the base, every row', ctx);
raplot.util.kxn(nexttile(tl), ctx, Km, 'mean rho at lag -1 (trailing window)', [-1 1], raplot.util.rdbu());
raplot.util.kxn(nexttile(tl), ctx, Kp, 'mean rho at lag +1 (leading window)', [-1 1], raplot.util.rdbu());
raplot.util.savefig(f, ctx, '00_overview.png');

U = raplot.util.units(ctx, 'byi');
parfor (n = 1:numel(U.i), ctx.M)
    sid = L.sid(U.i(n) + 1);
    T = raplot.util.readp(ctx, "lagcorr/" + sid, {'config_id', 't', 'k', 'rho', 'n_pairs'});
    d = D.(char(sid));
    for k = U.ks{n}'
        r = T(T.config_id == L.cid(k+1), :);
        [ut, ~, gt] = unique(r.t);
        [ul, ~, gl] = unique(double(r.k));
        R = accumarray([gl, gt], double(r.rho), [numel(ul), numel(ut)], @mean, NaN);
        P = accumarray([gl, gt], double(r.n_pairs), [numel(ul), numel(ut)], @mean, NaN);
        [file, ttl] = raplot.util.names(ctx, k, U.i(n), 'lagcorr');
        [f, tl] = raplot.util.newfig(1300, 850, 2, 1, ttl, ctx);
        step = max(1, round(numel(ut) / 15));
        ax = nexttile(tl);
        im = imagesc(ax, 1:numel(ut), ul, R); set(im, 'AlphaData', ~isnan(R)); ax.Color = [.82 .82 .82];
        clim(ax, [-1 1]); colormap(ax, raplot.util.rdbu()); colorbar(ax);
        ax.XTick = 1:step:numel(ut); ax.XTickLabel = string(d(ut(1:step:end) + 1), 'yyyy-MM');
        ylabel(ax, 'lag k'); title(ax, sprintf('rho(t, k) of e1 (grey = no value); %d of %d cells defined', sum(~isnan(R(:))), numel(R)));
        ax = nexttile(tl);
        im = imagesc(ax, 1:numel(ut), ul, P); set(im, 'AlphaData', ~isnan(P)); ax.Color = [.82 .82 .82];
        colorbar(ax);
        ax.XTick = 1:step:numel(ut); ax.XTickLabel = string(d(ut(1:step:end) + 1), 'yyyy-MM');
        ylabel(ax, 'lag k'); title(ax, sprintf('n_pairs behind each rho (min_pairs %d)', ctx.man.config.lagcorr_min_pairs));
        raplot.util.savefig(f, ctx, file);
    end
end
end
