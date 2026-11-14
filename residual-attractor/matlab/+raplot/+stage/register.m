function register(ctx)
%REGISTER  Stage 2. Overview only: every registered configuration on its method's grid,
% admissible or not, with ell and its status. Check: which configurations exist and why some are out.
R = raplot.util.readp(ctx, 'registry');
L = ctx.L;
methods = unique(R.method, 'stable');
[f, tl] = raplot.util.newfig(1500, 950, 2, numel(methods), ...
    sprintf('register: %d configurations, %d admissible', height(R), sum(R.admissible)), ctx);
for m = 1:numel(methods)
    r = R(R.method == methods(m), :);
    ax = nexttile(tl, m);
    hold(ax, 'on');
    ok = r.admissible;
    scatter(ax, r.grid_i(ok), r.grid_j(ok), 140, [.2 .6 .3], 'filled', 's');
    scatter(ax, r.grid_i(~ok), r.grid_j(~ok), 140, [.85 .2 .2], 'filled', 's');
    for n = 1:height(r)
        k = find(L.cid == r.config_id(n)) - 1;
        lab = r.params(n);
        if ~isempty(k), lab = sprintf('k%02d\n%s', k, lab); end
        text(ax, double(r.grid_i(n)), double(r.grid_j(n)) + 0.32, lab, 'FontSize', 6, 'HorizontalAlignment', 'center');
    end
    ax.XLim = [min(r.grid_i) - 0.7, max(r.grid_i) + 0.7]; ax.YLim = [min(r.grid_j) - 0.7, max(r.grid_j) + 1];
    xlabel(ax, 'grid_i'); ylabel(ax, 'grid_j');
    title(ax, sprintf('%s  axes %s: %d admissible (green), %d not (red)', methods(m), r.grid_axes(1), sum(ok), sum(~ok)));
    box(ax, 'on');

    ax = nexttile(tl, numel(methods) + m);
    [g, st] = findgroups(r.ell_status);
    hold(ax, 'on');
    cols = lines(numel(st));
    for q = 1:numel(st)
        sel = g == q;
        scatter(ax, find(sel), r.ell(sel), 30, cols(q, :), 'filled');
    end
    legend(ax, cellstr(string(st)), 'Location', 'best');
    xlabel(ax, 'registry row (this method)'); ylabel(ax, 'ell');
    title(ax, sprintf('%s: ell by row, coloured by ell_status', methods(m)));
    grid(ax, 'on');
end
raplot.util.savefig(f, ctx, '00_overview.png');
end
