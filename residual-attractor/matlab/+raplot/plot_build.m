function plot_build(buildDir, opts)
%PLOT_BUILD  Draw every stage of one residual-attractor build as PNGs, for spot checks by eye.
%
%   raplot.plot_build('builds/de655b9a42895179')
%   raplot.plot_build(B, stages={'grid','tails'}, rows=[0 0; 26 6], workers=1, out='/tmp/x')
%
% Reads the build's parquet tables only; writes nothing inside the build except <build>/figures/
% (or opts.out). One folder per stage, NN_<stage>/, each with 00_overview.png (all rows at once)
% and one PNG per unit:
%   row stages     fit forecast cadence lagcorr wavelet spectral tails   k00_i00_<series>_<config>.png
%   config stages  grid coherence adjacency events coincidence common_mode signatures   k00_<config>.png
%   series stages  ingest fibers compare   <series>.png
%   overview only  register bundle_summary
% k and i are the build's own 0-based indices (grid/names, fiber_index). rows = [k i; ...] limits
% every stage to those rows (and to their configurations and series); empty means every row.

arguments
    buildDir (1,:) char
    opts.stages cell = {}
    opts.rows double = zeros(0, 2)
    opts.workers double = 1
    opts.out char = ''
end

STAGES = {'ingest','register','fit','forecast','fibers','cadence','lagcorr','bundle_summary','grid', ...
          'compare','wavelet','spectral','coherence','adjacency','tails','events','coincidence', ...
          'common_mode','signatures'};

B = char(java.io.File(buildDir).getCanonicalPath());
man = jsondecode(fileread(fullfile(B, 'manifest.json')));
ctx.B = B;
ctx.man = man;
ctx.id = man.build_id;
ctx.L = raplot.util.labels(ctx);
ctx.rows = opts.rows;
ctx.M = 0;
root = opts.out;
if isempty(root), root = fullfile(B, 'figures'); end

want = STAGES;
if ~isempty(opts.stages), want = STAGES(ismember(STAGES, opts.stages)); end
passed = cellstr(man.stages_passed);
skipped = want(~ismember(want, passed));
want = want(ismember(want, passed));
for s = skipped, fprintf('skip %s: not in stages_passed\n', s{1}); end

if opts.workers > 1
    p = gcp('nocreate');
    if isempty(p) || p.NumWorkers ~= opts.workers
        delete(p);
        parpool('Processes', opts.workers);
    end
    ctx.M = opts.workers;
end

fprintf('build %s: %d configurations, %d series, %d stages -> %s\n', ctx.id, ctx.L.K, ctx.L.N, numel(want), root);
failed = {};
t0 = tic;
for s = want
    n = find(strcmp(STAGES, s{1}));
    ctx.out = fullfile(root, sprintf('%02d_%s', n, s{1}));
    if ~isfolder(ctx.out), mkdir(ctx.out); end
    t1 = tic;
    try
        feval(['raplot.stage.' s{1}], ctx);
        d = dir(fullfile(ctx.out, '*.png'));
        fprintf('  %-15s %5d png  %6.1fs\n', s{1}, numel(d), toc(t1));
    catch err
        failed{end+1} = s{1}; %#ok<AGROW>
        fprintf(2, '  %-15s FAILED after %.1fs: %s\n', s{1}, toc(t1), err.message);
        for f = err.stack(1:min(4, end))', fprintf(2, '      at %s line %d\n', f.name, f.line); end
    end
end
fprintf('done in %.1fs\n', toc(t0));
if ~isempty(failed)
    error('raplot:failed', 'stages failed: %s', strjoin(failed, ', '));
end
end
