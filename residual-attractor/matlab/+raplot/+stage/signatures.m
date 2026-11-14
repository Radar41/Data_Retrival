function signatures(ctx)
%SIGNATURES  Per configuration: lambda1 against its band with flagged months shaded; a strip of the
% rule's parts month by month (available, lambda1 above band, absorption rising, flagged) and the months
% held. Overview: flagged configuration x month. Check: a flag only where both parts hold long enough.
L = ctx.L;
S = raplot.util.readp(ctx, 'signatures/flag');
mon = sort(raplot.util.readp(ctx, 'grid/month').t);
P = numel(mon);
[~, tt] = ismember(S.t, mon);
X = zeros(L.K, P); X(sub2ind(size(X), double(S.k) + 1, tt)) = double(S.flagged);
X(sub2ind(size(X), double(S.k(~S.available)) + 1, tt(~S.available))) = NaN;
sg = ctx.man.signatures.consolidation;
[f, tl] = raplot.util.newfig(1600, 1300, 1, 1, sprintf('signatures: %d flagged months in %d configurations (persistence %d)', ...
    sum(S.flagged), numel(unique(S.k(S.flagged))), sg.persistence_months), ctx);
ax = nexttile(tl);
im = imagesc(ax, 1:P, 0:L.K-1, X); set(im, 'AlphaData', ~isnan(X)); ax.Color = [.82 .82 .82];
colormap(ax, [1 1 1; .8 .1 .1]); clim(ax, [0 1]);
ax.YTick = 0:L.K-1; ax.YTickLabel = L.kshort; ax.FontSize = 6;
ax.XTick = 1:6:P; ax.XTickLabel = string(mon(1:6:end), 'yyyy-MM'); ax.XTickLabelRotation = 60;
title(ax, 'consolidation flagged (red); grey = not available');
raplot.util.savefig(f, ctx, '00_overview.png');

U = raplot.util.units(ctx, 'k');
parfor (n = 1:numel(U.k), ctx.M)
    k = U.k(n);
    s = sortrows(S(S.k == k, :), 't'); [~, ts] = ismember(s.t, mon);
    c = cellfun(@jsondecode, cellstr(s.components), 'UniformOutput', false);
    g = @(fn) cellfun(@(x) num(x, fn), c);
    l1 = g('lambda1'); lq = g('lambda1_q'); ar = g('absorption_ratio'); ap = g('absorption_ratio_prev');
    above = l1 > lq; rising = ar > ap;
    [file, ttl] = raplot.util.names(ctx, k, [], 'signatures');
    [f, tl] = raplot.util.newfig(1500, 950, 3, 1, ttl, ctx);
    xt = @(ax) set(ax, 'XTick', 1:6:P, 'XTickLabel', string(mon(1:6:end), 'yyyy-MM'), 'XLim', [0.5 P + 0.5]);
    ax = nexttile(tl); hold(ax, 'on');
    yl = [0, max([l1; lq; 1], [], 'omitnan') * 1.1];
    for q = find(s.flagged)'
        patch(ax, ts(q) + [-0.5 0.5 0.5 -0.5], yl([1 1 2 2]), [1 .8 .8], 'EdgeColor', 'none', 'HandleVisibility', 'off');
    end
    plot(ax, ts, l1, 'k.-', ts, lq, 'r--'); ylim(ax, yl); xt(ax);
    legend(ax, {'lambda1 (as the rule read it)', 'lambda1_q'}, 'Location', 'best');
    title(ax, sprintf('%d flagged months (shaded); rule: %s for %d months', sum(s.flagged), strjoin(string(sg.requires), ' and '), sg.persistence_months));
    grid(ax, 'on');
    ax = nexttile(tl);
    Z = double([s.available'; above'; rising'; s.flagged']);
    imagesc(ax, ts, 1:4, Z); colormap(ax, [1 1 1; .2 .5 .3]); clim(ax, [0 1]);
    ax.YTick = 1:4; ax.YTickLabel = {'available', 'lambda1 > lambda1_q', 'absorption rising', 'flagged'}; xt(ax);
    title(ax, 'parts of the rule by month (green = holds)');
    ax = nexttile(tl);
    bar(ax, ts, s.held_months); yline(ax, sg.persistence_months, 'r--', 'persistence'); xt(ax);
    title(ax, 'held_months'); grid(ax, 'on');
    raplot.util.savefig(f, ctx, file);
end
end

function v = num(x, fn)
% one number from a decoded components object; JSON null (or a missing key) is NaN
v = NaN;
if isfield(x, fn) && ~isempty(x.(fn)), v = double(x.(fn)); end
end
