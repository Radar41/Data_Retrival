function cadence(ctx)
%CADENCE  Stage 5. Per row: the horizons h1..h4 at which each origin's forward ladder first crosses
% the thresholds 1..4 on the failure scale, and each origin's label. Overview: share labelled Holds,
% the most common label, and label totals by series. Check: h1 <= h2 <= h3 <= h4 and the labels follow.
L = ctx.L;
D = raplot.util.sdates(ctx);
labs = string(ctx.man.cadence.labels);
cols = lines(numel(labs));
sc = string(ctx.man.cadence.scale);

holds = nan(L.K, L.N); modal = nan(L.K, L.N); counts = zeros(L.N, numel(labs));
for i = 0:L.N-1
    C = raplot.util.readp(ctx, "cadence/" + L.sid(i+1), {'config_id', 'label'});
    lab = categorical(string(C.label), labs);
    counts(i+1, :) = countcats(lab)';
    for k = 0:L.K-1
        l = lab(C.config_id == L.cid(k+1));
        holds(k+1, i+1) = mean(l == "Holds");
        [~, modal(k+1, i+1)] = max(countcats(l));
    end
end
[f, tl] = raplot.util.newfig(1900, 1300, 1, 3, "cadence on " + sc + ": every row", ctx);
raplot.util.kxn(nexttile(tl), ctx, holds, 'share of origins labelled Holds', [0 1]);
ax = raplot.util.kxn(nexttile(tl), ctx, modal, 'most common label', [0.5 numel(labs) + 0.5], cols);
cb = ax.Colorbar; cb.Ticks = 1:numel(labs); cb.TickLabels = labs;
ax = nexttile(tl);
b = barh(ax, 0:L.N-1, counts, 'stacked');
for q = 1:numel(b), b(q).FaceColor = cols(q, :); end
ax.YTick = 0:L.N-1; ax.YTickLabel = L.sid; ax.YDir = 'reverse';
legend(ax, labs, 'Location', 'southoutside', 'NumColumns', 3); title(ax, 'labels by series (all configurations)');
raplot.util.savefig(f, ctx, '00_overview.png');

U = raplot.util.units(ctx, 'byi');
parfor (n = 1:numel(U.i), ctx.M)
    sid = L.sid(U.i(n) + 1);
    C = raplot.util.readp(ctx, "cadence/" + sid);
    d = D.(char(sid));
    for k = U.ks{n}'
        c = sortrows(C(C.config_id == L.cid(k+1), :), 'origin');
        [file, ttl] = raplot.util.names(ctx, k, U.i(n), 'cadence');
        [f, tl] = raplot.util.newfig(1300, 800, 3, 1, ttl, ctx);
        tl.TileIndexing = 'rowmajor';
        ax = nexttile(tl, [2 1]);
        x = d(c.origin + 1);
        hold(ax, 'on');
        mk = {'o', 's', 'd', '^'};
        for q = 1:4
            plot(ax, x, c.(sprintf('h%d', q)), mk{q}, 'MarkerSize', 4);
        end
        ylabel(ax, 'h of first crossing'); ylim(ax, [0 ctx.man.config.horizon_H + 1]);
        legend(ax, compose('h%d: %s >= %d', (1:4)', sc, (1:4)'), 'Location', 'best');
        bad = sum(c.h1 > c.h2 | c.h2 > c.h3 | c.h3 > c.h4, 'omitnan');
        title(ax, sprintf('threshold crossings by origin (blank = not reached within H); out-of-order rows: %d', bad));
        grid(ax, 'on');
        ax = nexttile(tl);
        lab = double(categorical(string(c.label), labs));
        image(ax, 1:height(c), 1, reshape(cols(lab, :), 1, [], 3));
        ax.YTick = [];
        step = max(1, round(height(c) / 15));
        ax.XTick = 1:step:height(c); ax.XTickLabel = string(x(1:step:end), 'yyyy-MM');
        present = unique(lab);
        hold(ax, 'on');
        for q = present'
            patch(ax, NaN, NaN, cols(q, :));
        end
        legend(ax, labs(present), 'Location', 'southoutside', 'NumColumns', numel(present));
        title(ax, 'label of each origin');
        raplot.util.savefig(f, ctx, file);
    end
end
end
