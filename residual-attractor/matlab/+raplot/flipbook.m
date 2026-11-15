function flipbook(buildDir, opts)
%FLIPBOOK  Per series, one page per configuration in grid order along each parameter path, every scale
% fixed, so flipping pages shows only how the residuals move as the configuration moves one grid step.
%
%   raplot.flipbook('builds/de655b9a42895179')
%   raplot.flipbook(B, series={'WPU1197'}, workers=4, out='/scratch/flip')
%
% Writes only <build>/figures/flipbook/ (or opts.out):
%   i06_WPU1197/00_map.png                         grid neighbours, edge colour = rms of the step
%   i06_WPU1197/<path>/00_path.png                 pages x months of R, and of the step
%   i06_WPU1197/<path>/p01_k10_<cid>.png ...       left: state of k; right: k minus previous page
% The previous page is used only when it is the true grid neighbour (grid index exactly one less).
% Every number comes from one row or one neighbour pair; nothing is pooled across configurations.

arguments
    buildDir (1,:) char
    opts.series cell = {}
    opts.workers double = 1
    opts.out char = ''
end

% Fixed scales: the same on every page, path and series. No autoscaling anywhere.
SC.resid  = [-6 6];   SC.dresid = [-3 3];    % R row, and its step
SC.fiber  = [-4 4];   SC.dfiber = [-2 2];    % fiber X_k, and its step
SC.wave   = [-6 4];   SC.dwave  = [-3 3];    % log2(power / variance), and its step
SC.strip  = [-4 4];   SC.dstrip = [-2 2];    % path strip: R, and its step
SC.edge   = [0 2];                           % series map: rms of the step
SC.nan    = [.82 .82 .82];                   % NaN cells
SC.prev   = [.72 .72 .72];                   % previous page's row behind the state
SC.W = 1800; SC.H = 1200;                    % page size in pixels (pages and path strips)
SC.mapW = 1800; SC.mapH = 760;
SC.none = 'no neighbour on this path';

B = char(java.io.File(buildDir).getCanonicalPath());
man = jsondecode(fileread(fullfile(B, 'manifest.json')));
ctx.B = B;
ctx.man = man;
ctx.id = man.build_id;
ctx.L = raplot.util.labels(ctx);
ctx.rows = zeros(0, 2);
ctx.M = 0;
L = ctx.L;
root = opts.out;
if isempty(root), root = fullfile(B, 'figures', 'flipbook'); end
if isempty(opts.series)
    is = 0:L.N-1;
else
    [ok, loc] = ismember(string(opts.series), L.sid);
    assert(all(ok), 'raplot:flipbook', 'unknown series: %s', strjoin(string(opts.series(~ok)), ', '));
    is = loc(:)' - 1;
end
if opts.workers > 1
    p = gcp('nocreate');
    if isempty(p) || p.NumWorkers ~= opts.workers
        delete(p);
        parpool('Processes', opts.workers);
    end
    ctx.M = opts.workers;
end

t0 = tic;
[R, mon] = raplot.util.field(ctx, 'grid/resid', 'resid');
P = numel(mon);
S = sortrows(raplot.util.readp(ctx, 'wavelet/scale'), 'j');
J = height(S);
WS = raplot.util.readp(ctx, 'wavelet/series', {'k', 'i', 'variance'});
V = nan(L.K, L.N);
V(sub2ind(size(V), double(WS.k) + 1, double(WS.i) + 1)) = WS.variance;
W = raplot.util.readp(ctx, 'wavelet/cwt', {'k', 'i', 'j', 't', 'power', 'in_coi'});
[ok, tt] = ismember(W.t, mon);
Z = nan(L.K, L.N, J, P); C = false(L.K, L.N, J, P);
idx = sub2ind(size(Z), double(W.k(ok)) + 1, double(W.i(ok)) + 1, double(W.j(ok)) + 1, tt(ok));
Z(idx) = W.power(ok); C(idx) = W.in_coi(ok);
clear W idx tt ok
Z = log2(Z ./ V);
Pth = raplot.util.gridpaths(ctx);
G = raplot.util.readp(ctx, 'registry', {'config_id', 'grid_i', 'grid_j', 'admissible'});
G = G(G.admissible, :);
[~, kk] = ismember(string(G.config_id), L.cid);
pos = nan(L.K, 2);
pos(kk, :) = double([G.grid_i, G.grid_j]);
D = raplot.util.sdates(ctx);
twins = man.compare.twin_groups;
if iscell(twins), twins = cell2mat(cellfun(@(v) v(:)', twins, 'UniformOutput', false)); end
fprintf('flipbook %s: %d series, %d paths, %d pages per series, read in %.1fs -> %s\n', ...
    ctx.id, numel(is), numel(Pth), numel([Pth.k]), toc(t0), root);

for i = is
    t1 = tic;
    sid = L.sid(i+1);
    d.i = i; d.sid = sid;
    d.tag = sprintf('i%02d %s', i, sid);
    d.mon = mon; d.P = P;
    d.lp = log2(S.period);
    d.R = reshape(R(:, i+1, :), L.K, P);
    d.Z = reshape(Z(:, i+1, :, :), L.K, J, P);
    d.C = reshape(C(:, i+1, :, :), L.K, J, P);
    F = raplot.util.readp(ctx, "fibers/" + sid, {'origin', 'ladder', 'h', 'x'});
    F = F(string(F.ladder) == "forward", :);
    X = cell2mat(cellfun(@(v) double(v(:))', F.x, 'UniformOutput', false));
    d.uo = unique(F.origin); d.uh = unique(F.h);
    [~, oo] = ismember(F.origin, d.uo); [~, hh] = ismember(F.h, d.uh);
    lin = sub2ind([numel(d.uh) numel(d.uo)], hh, oo);
    d.X = nan(numel(d.uh), numel(d.uo), L.K);
    for k = 1:L.K
        x = nan(numel(d.uh), numel(d.uo)); x(lin) = X(:, k); d.X(:, :, k) = x;
    end
    dd = D.(char(sid));
    d.odate = dd(d.uo + 1);
    sdir = fullfile(root, sprintf('i%02d_%s', i, sid));
    if ~isfolder(sdir), mkdir(sdir); end
    drawmap(d, Pth, pos, twins, SC, ctx, fullfile(sdir, '00_map.png'));
    parfor (n = 1:numel(Pth), ctx.M)
        drawpath(Pth(n), d, SC, ctx, fullfile(sdir, Pth(n).folder));
    end
    fprintf('  %-22s %4d png  %6.1fs\n', sprintf('i%02d_%s', i, sid), ...
        numel(dir(fullfile(sdir, '**', '*.png'))), toc(t1));
end
fprintf('done in %.1fs\n', toc(t0));
end

% ---------------------------------------------------------------------------------------------------
function drawpath(p, d, SC, ctx, pdir)
if ~isfolder(pdir), mkdir(pdir); end
np = numel(p.k);
for q = 1:np
    k = p.k(q);
    kp = [];
    if q > 1 && p.gidx(q) - p.gidx(q-1) == 1, kp = p.k(q-1); end
    drawpage(p, q, k, kp, d, SC, ctx, fullfile(pdir, sprintf('p%02d_k%02d_%s.png', q, k, ctx.L.cid(k+1))));
end
drawstrip(p, d, SC, ctx, fullfile(pdir, '00_path.png'));
end

function [f, tl] = pagefig(w, h, rows, cols, ttl, ctx)
% newfig, then the size set in inches at 96 px/inch: pool workers report 72 px/inch and the client 96,
% so a size in pixels would export at different sizes; in inches every page is w x h at 96 dpi.
[f, tl] = raplot.util.newfig(w, h, rows, cols, ttl, ctx);
f.Units = 'inches';
f.Position = [0 0 w h] / 96;
end

function s = at(p)
s = '';
if ~isempty(p.fixed), s = [' at ' p.fixed]; end
end

function r = rmsv(x)
r = sqrt(mean(x(:) .^ 2, 'omitnan'));
end

function drawpage(p, q, k, kp, d, SC, ctx, file)
L = ctx.L; P = d.P; np = numel(p.k);
has = ~isempty(kp);
if has
    ttl = sprintf('flipbook  %s  %s  %s %g -> %g%s  page %d of %d  k%02d -> k%02d', d.tag, p.method, ...
        p.axis, p.val(q-1), p.val(q), at(p), q, np, kp, k);
else
    ttl = sprintf('flipbook  %s  %s  %s %g%s  page %d of %d  k%02d', d.tag, p.method, ...
        p.axis, p.val(q), at(p), q, np, k);
end
[f, tl] = pagefig(SC.W, SC.H, 3, 2, ttl, ctx);
r = d.R(k+1, :);
yard = rmsv(diff(r));

% row 1: residual row
ax = nexttile(tl, 1); hold(ax, 'on');
lab = '';
if has
    plot(ax, 1:P, d.R(kp+1, :), '-', 'Color', SC.prev, 'LineWidth', 1.4);
    lab = sprintf('  (grey: k%02d)', kp);
end
plot(ax, 1:P, r, 'k-', 'LineWidth', 1);
clipmarks(ax, 1:P, r, SC.resid, [0 0 0]);
monthaxis(ax, d, SC.resid);
title(ax, sprintf('state  R[k%02d, i%02d, t]  %s  %s%s', k, d.i, L.kname(k+1), L.cid(k+1), lab));
ax = nexttile(tl, 2); hold(ax, 'on');
if has
    s = r - d.R(kp+1, :);
    plot(ax, 1:P, s, '-', 'Color', [.55 .1 .1], 'LineWidth', 1);
    clipmarks(ax, 1:P, s, SC.dresid, [.55 .1 .1]);
    title(ax, sprintf('step  R[k%02d] - R[k%02d]:  rms %.3f over %d months   |   rms month-to-month change of R[k%02d]: %.3f', ...
        k, kp, rmsv(s), sum(~isnan(s)), k, yard));
else
    none(ax);
    title(ax, sprintf('step:  %s   |   rms month-to-month change of R[k%02d]: %.3f', SC.none, k, yard));
end
monthaxis(ax, d, SC.dresid);

% row 2: fiber, forward ladder
ax = nexttile(tl, 3);
heat(ax, d.X(:, :, k+1), SC.fiber, raplot.util.rdbu(), SC);
fiberaxis(ax, d);
title(ax, sprintf('fiber X_k%02d, forward ladder (origin x h)', k));
ax = nexttile(tl, 4);
if has
    heat(ax, d.X(:, :, k+1) - d.X(:, :, kp+1), SC.dfiber, raplot.util.rdbu(), SC);
    title(ax, sprintf('step  X_k%02d - X_k%02d', k, kp));
else
    heat(ax, nan(size(d.X, 1), size(d.X, 2)), SC.dfiber, raplot.util.rdbu(), SC); none(ax);
    title(ax, sprintf('step:  %s', SC.none));
end
fiberaxis(ax, d);

% row 3: wavelet power over the row's variance
Zk = reshape(d.Z(k+1, :, :), [], P); Ck = reshape(d.C(k+1, :, :), [], P);
ax = nexttile(tl, 5);
heat(ax, Zk, SC.wave, parula(256), SC, 1:P, d.lp);
raplot.util.coi(ax, 1:P, d.lp, Ck);
waveaxis(ax, d);
title(ax, sprintf('log2 power / variance, k%02d; white wash = outside the cone', k));
ax = nexttile(tl, 6);
if has
    Zp = reshape(d.Z(kp+1, :, :), [], P); Cp = reshape(d.C(kp+1, :, :), [], P);
    heat(ax, Zk - Zp, SC.dwave, raplot.util.rdbu(), SC, 1:P, d.lp);
    raplot.util.coi(ax, 1:P, d.lp, Ck & Cp);
    title(ax, sprintf('step  log2 map k%02d - k%02d; wash where either is outside the cone', k, kp));
else
    heat(ax, nan(size(Zk)), SC.dwave, raplot.util.rdbu(), SC, 1:P, d.lp); none(ax);
    title(ax, sprintf('step:  %s', SC.none));
end
waveaxis(ax, d);
raplot.util.savepage(f, file);
end

function drawstrip(p, d, SC, ctx, file)
P = d.P; np = numel(p.k);
[f, tl] = pagefig(SC.W, SC.H, 2, 1, sprintf('flipbook  %s  %s  path along %s%s  (%d pages)', ...
    d.tag, p.method, p.axis, at(p), np), ctx);
A = d.R(p.k + 1, :);
Dm = nan(np, P); lab = strings(np, 1); rr = nan(np, 1);
for q = 1:np
    lab(q) = sprintf('%s %g  k%02d', p.axis, p.val(q), p.k(q));
    if q > 1 && p.gidx(q) - p.gidx(q-1) == 1
        Dm(q, :) = A(q, :) - A(q-1, :);
        rr(q) = rmsv(Dm(q, :));
    end
end
ax = nexttile(tl);
heat(ax, A, SC.strip, raplot.util.rdbu(), SC, 1:P, 1:np);
ax.YTick = 1:np; ax.YTickLabel = lab;
monthticks(ax, d);
title(ax, 'R[k, i, t] per page (rows in grid order)');
ax = nexttile(tl);
heat(ax, Dm, SC.dstrip, raplot.util.rdbu(), SC, 1:P, 1:np);
slab = strings(np, 1);
for q = 1:np
    if isnan(rr(q))
        slab(q) = sprintf('k%02d', p.k(q));
        text(ax, P, q, [SC.none ' '], 'FontSize', 9, 'HorizontalAlignment', 'right', 'Color', [.3 .3 .3]);
    else
        slab(q) = sprintf('k%02d - k%02d', p.k(q), p.k(q-1));
        text(ax, P, q, sprintf('rms %.3f ', rr(q)), 'FontSize', 9, 'HorizontalAlignment', 'right', ...
            'BackgroundColor', 'w', 'Margin', 1);
    end
end
ax.YTick = 1:np; ax.YTickLabel = slab;
monthticks(ax, d);
title(ax, 'step R[k] - R[k_prev] from the previous grid neighbour; grey = no neighbour');
raplot.util.savepage(f, file);
end

function drawmap(d, Pth, pos, twins, SC, ctx, file)
tw = strings(1, size(twins, 1));
for n = 1:size(twins, 1)
    a = twins(n, 1); b = twins(n, 2);
    tw(n) = sprintf('k%02d/k%02d %.2g', a, b, rmsv(d.R(a+1, :) - d.R(b+1, :)));
end
[f, tl] = pagefig(SC.mapW, SC.mapH, 1, 3, sprintf('flipbook map  %s   twin pairs, rms of R[a] - R[b] (expect 0):  %s', ...
    d.tag, strjoin(tw, ',  ')), ctx);
cm = parula(256);
for m = ["ses", "ar", "holt"]
    ax = nexttile(tl); hold(ax, 'on');
    pm = Pth(strcmp({Pth.method}, m));
    ks = unique([pm.k]);
    for p = pm
        for q = 2:numel(p.k)
            if p.gidx(q) - p.gidx(q-1) ~= 1, continue; end
            a = p.k(q-1); b = p.k(q);
            v = rmsv(d.R(b+1, :) - d.R(a+1, :));
            c = cm(1 + round(min(max((v - SC.edge(1)) / diff(SC.edge), 0), 1) * 255), :);
            xy = [pos(a+1, :); pos(b+1, :)];
            plot(ax, xy(:, 1), xy(:, 2), '-', 'Color', c, 'LineWidth', 4);
            text(ax, mean(xy(:, 1)), mean(xy(:, 2)), sprintf('%.2f', v), 'FontSize', 7, ...
                'HorizontalAlignment', 'center', 'BackgroundColor', 'w', 'Margin', 0.5);
        end
    end
    scatter(ax, pos(ks+1, 1), pos(ks+1, 2), 60, 'k', 'filled', 's');
    for k = ks
        text(ax, pos(k+1, 1) - 0.06, pos(k+1, 2) - 0.06, sprintf('k%02d', k), 'FontSize', 7, 'FontWeight', 'bold', ...
            'HorizontalAlignment', 'right', 'VerticalAlignment', 'top');
    end
    colormap(ax, cm); clim(ax, SC.edge); cb = colorbar(ax); cb.Label.String = 'rms over months of the step';
    xl = [min(pos(ks+1, 1)) - 0.7, max(pos(ks+1, 1)) + 0.7];
    yl = [min(pos(ks+1, 2)) - 0.9, max(pos(ks+1, 2)) + 0.5];
    xlim(ax, xl); ylim(ax, yl);
    ax.XTick = unique(pos(ks+1, 1)); ax.YTick = unique(pos(ks+1, 2));
    ax.XTickLabel = gridlabels(pm, 1, ax.XTick); ax.YTickLabel = gridlabels(pm, 2, ax.YTick);
    box(ax, 'on');
    title(ax, sprintf('%s: %d configurations (k on nodes, parameter values on axes); edge = rms of the step, colour fixed %g..%g', ...
        m, numel(ks), SC.edge));
end
raplot.util.savepage(f, file);
end

function lab = gridlabels(pm, a, ticks)
% tick labels "<axis> <value>" for grid axis a (1 = grid_i, 2 = grid_j) of one method's paths
lab = repmat("", size(ticks));
for p = pm
    if pathaxis(pm, p) ~= a, continue; end
    for q = 1:numel(p.k)
        lab(ticks == p.gidx(q)) = sprintf('%s %g', p.axis, p.val(q));
    end
end
end

function a = pathaxis(pm, p)
% axis number of the moving parameter: the first method path's axis is axis 1
a = 1 + ~strcmp(p.axis, pm(1).axis);
end

function heat(ax, A, lim, cmap, SC, x, y)
if nargin < 6, x = 1:size(A, 2); y = 1:size(A, 1); end
im = imagesc(ax, x, y, A);
set(im, 'AlphaData', double(~isnan(A)));
ax.Color = SC.nan;
clim(ax, lim); colormap(ax, cmap); colorbar(ax);
end

function none(ax)
text(ax, 0.5, 0.5, 'no neighbour on this path', 'Units', 'normalized', 'FontSize', 14, ...
    'HorizontalAlignment', 'center', 'Color', [.35 .35 .35]);
end

function clipmarks(ax, x, y, lim, col)
hi = y > lim(2); lo = y < lim(1);
if any(hi), plot(ax, x(hi), repmat(lim(2), 1, sum(hi)), '^', 'MarkerFaceColor', col, 'MarkerEdgeColor', col, 'MarkerSize', 5, 'Clipping', 'off'); end
if any(lo), plot(ax, x(lo), repmat(lim(1), 1, sum(lo)), 'v', 'MarkerFaceColor', col, 'MarkerEdgeColor', col, 'MarkerSize', 5, 'Clipping', 'off'); end
end

function monthticks(ax, d)
ax.XTick = 1:12:d.P; ax.XTickLabel = string(d.mon(1:12:end), 'yyyy-MM');
xlim(ax, [0.5 d.P + 0.5]);
end

function monthaxis(ax, d, lim)
yline(ax, 0, ':');
ylim(ax, lim); monthticks(ax, d); grid(ax, 'on'); box(ax, 'on');
end

function fiberaxis(ax, d)
ax.YDir = 'normal';
O = numel(d.uo); st = max(1, round(O / 10));
ax.XTick = 1:st:O; ax.XTickLabel = string(d.odate(1:st:O), 'yyyy-MM');
xlim(ax, [0.5 O + 0.5]); ylim(ax, [0.5 numel(d.uh) + 0.5]);
ax.YTick = 1:numel(d.uh); ax.YTickLabel = string(d.uh); ylabel(ax, 'h'); xlabel(ax, 'origin');
ax.FontSize = 7;
end

function waveaxis(ax, d)
ax.YTick = 1:5; ax.YTickLabel = string(2.^(1:5)); ylabel(ax, 'period (months)');
ax.YLim = [min(d.lp) max(d.lp)] + [-1 1] * (d.lp(2) - d.lp(1)) / 2;
monthticks(ax, d);
end
