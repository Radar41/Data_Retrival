function P = gridpaths(ctx)
%GRIDPATHS  The paths along each method's parameter grid, admissible configurations only.
%   P(n).method  ses / ar / holt          P(n).axis   the moving parameter
%   P(n).fixed   e.g. 'phi2 -0.3' ('' for a one-axis method)
%   P(n).folder  e.g. 'ar_along_phi1_phi2_-0.3'
%   P(n).k       0-based k per page, in grid order
%   P(n).val     the moving parameter's value per page
%   P(n).gidx    grid index along the moving axis per page (a gap means no grid neighbour)
% One-axis method: one path over grid_i. Two-axis method: one path along axis 1 for each grid_j and
% one along axis 2 for each grid_i. Paths with fewer than 2 pages are dropped.
L = ctx.L;
G = raplot.util.readp(ctx, 'registry', {'config_id', 'method', 'params', 'grid_axes', 'grid_i', 'grid_j', 'admissible'});
G = G(G.admissible, :);
[ok, kk] = ismember(string(G.config_id), L.cid);
assert(all(ok), 'raplot:gridpaths', 'admissible registry rows missing from grid/names');
G.k = kk - 1;
P = struct('method', {}, 'axis', {}, 'fixed', {}, 'folder', {}, 'k', {}, 'val', {}, 'gidx', {});
for m = unique(string(G.method), 'stable')'
    r = G(string(G.method) == m, :);
    ax = string(jsondecode(char(r.grid_axes(1))));
    prm = arrayfun(@(s) jsondecode(char(s)), string(r.params));
    gi = double([r.grid_i, r.grid_j]);
    for a = 1:numel(ax)
        if numel(ax) == 1
            groups = 0; other = [];
        else
            other = 3 - a;
            groups = unique(gi(:, other))';
        end
        for g = groups
            if isempty(other), sel = true(height(r), 1); else, sel = gi(:, other) == g; end
            idx = find(sel);
            [~, o] = sort(gi(idx, a)); idx = idx(o);
            if numel(idx) < 2, continue; end
            p.method = char(m);
            p.axis = char(ax(a));
            if isempty(other)
                p.fixed = '';
                p.folder = sprintf('%s_along_%s', m, ax(a));
            else
                fv = prm(idx(1)).(ax(other));
                p.fixed = sprintf('%s %g', ax(other), fv);
                p.folder = sprintf('%s_along_%s_%s_%g', m, ax(a), ax(other), fv);
            end
            p.k = r.k(idx)';
            p.val = arrayfun(@(q) prm(q).(ax(a)), idx)';
            p.gidx = gi(idx, a)';
            P(end+1) = p; %#ok<AGROW>
        end
    end
end
end
