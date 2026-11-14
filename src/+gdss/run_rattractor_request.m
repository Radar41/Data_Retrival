function summary = run_rattractor_request(requestDir, opts)
%RUN_RATTRACTOR_REQUEST  Run the GDSS adapters for one residual-attractor request and write the forecast cube.
%
%   gdss.run_rattractor_request('residual-attractor/external/<request_id>')
%   gdss.run_rattractor_request(dir, workers=8, series=["DGORDER","STLFSI4"])
%
% Reads <dir>/request.json (written by `rattractor build` when a config holds estimated families)
% and <dir>/series.parquet (exactly the series ingest produced: series_id, t, y). For every
% (series, configuration) it walks the issuances i = i0 .. N-1 (0-based, i is the last observed
% index) on an expanding window:
%   refit    at i0 and every refit_every issuances after it: adapter.fit on y(0..i)
%   filter   in between: the last fitted payload with training_values = y(0..i) (and, for the naive
%            adapter, state_at_origin = y(i)), so parameters come from data through fit_through <= i
%   forecast adapter.forecast for h = 1..H+1 from every issuance
% A failed refit keeps the previous parameters; an issuance before any successful fit has no forecast.
% Statuses come from what happened (caught errors, warnings captured with lastwarn), never constants.
%
% Writes, all under <dir>:
%   cube/<series>.parquet   one row per (config_id, issuance): fit_through, status, yhat_01..yhat_HH,
%                           sd_01..sd_HH (the model's own forecast sd; NaN where the adapter has none)
%   fit_status.parquet      one row per refit attempt: params, log likelihood, warnings, seconds
%   done.json               counts, leakage checks, wall time, MATLAB version; written last
% The adapters are used as they are (gdss.create_model_adapter).

arguments
    requestDir (1,:) char
    opts.workers double = NaN
    opts.series string = string.empty
    opts.methods string = string.empty   % only these families (smoke runs; a full run takes every one)
end

t0 = tic;
req = jsondecode(fileread(fullfile(requestDir, 'request.json')));
S = parquetread(fullfile(requestDir, 'series.parquet'));
H1 = double(req.horizon) + 1;
cfgs = req.configurations;
if ~iscell(cfgs), cfgs = num2cell(cfgs); end
if ~isempty(opts.methods), cfgs = cfgs(cellfun(@(c) ismember(string(c.method), opts.methods), cfgs)); end
sids = unique(S.series_id, 'stable');
if ~isempty(opts.series), sids = sids(ismember(sids, opts.series)); end
cubeDir = fullfile(requestDir, 'cube');
if ~isfolder(cubeDir), mkdir(cubeDir); end

workers = opts.workers;
if isnan(workers)
    w = str2double(getenv('SLURM_CPUS_PER_TASK'));
    if isnan(w), w = 1; end
    workers = w;
end
M = 0;
if workers > 1
    p = gcp('nocreate');
    if isempty(p) || p.NumWorkers ~= workers
        delete(p);
        parpool('Processes', workers);
    end
    M = workers;
end

% one task per (series, configuration)
[si, ci] = ndgrid(1:numel(sids), 1:numel(cfgs));
si = si(:); ci = ci(:);
Y = cell(numel(sids), 1);
for n = 1:numel(sids)
    s = sortrows(S(S.series_id == sids(n), :), 't');
    assert(isequal(s.t, (0:height(s)-1)'), 'gdss:rattractor:t', '%s: t is not 0..N-1', sids(n));
    Y{n} = s.y;
end
cubes = cell(numel(si), 1);
fits = cell(numel(si), 1);
fprintf('request %s: %d series x %d configurations, H+1 = %d, %d workers\n', req.request_id, numel(sids), numel(cfgs), H1, workers);
parfor (n = 1:numel(si), M)
    c = cfgs{ci(n)};
    [cubes{n}, fits{n}] = walk(Y{si(n)}, c, H1, sids(si(n)));
end

% leakage: per configuration, on the first series, change y after a cut and redo the walk up to it
lk = cell(numel(cfgs), 1);
parfor (n = 1:numel(cfgs), M)
    lk{n} = leakage(Y{1}, cfgs{n}, H1, sids(1));
end
leak = [lk{:}];
assert(all([leak.identical]), 'gdss:rattractor:leakage', 'forecasts at or before the cut changed: %s', ...
    strjoin(string({leak(~[leak.identical]).config_id}), ', '));

for n = 1:numel(sids)
    T = vertcat(cubes{si == n});
    parquetwrite(fullfile(cubeDir, sids(n) + ".parquet"), T);
end
F = vertcat(fits{:});
parquetwrite(fullfile(requestDir, 'fit_status.parquet'), F);

allc = vertcat(cubes{:});
summary = struct();
summary.request_id = req.request_id;
summary.series = cellstr(sids);
summary.configurations = numel(cfgs);
summary.cube_rows = height(allc);
summary.issuances_without_forecast = sum(allc.status == "NO_FIT" | allc.status == "FORECAST_FAILED");
summary.refits = height(F);
summary.refits_failed = sum(F.status ~= "COMPLETE");
summary.refits_with_warnings = sum(strlength(F.warnings) > 0);
summary.leakage = leak;
summary.wall_seconds = toc(t0);
summary.workers = workers;
summary.matlab_version = version;
summary.created = char(datetime('now', 'TimeZone', 'UTC', 'Format', "yyyy-MM-dd'T'HH:mm:ss'Z'"));
fid = fopen(fullfile(requestDir, 'done.json'), 'w');
fprintf(fid, '%s\n', jsonencode(summary, 'PrettyPrint', true));
fclose(fid);
fprintf('done: %d cube rows, %d refits (%d failed, %d with warnings), %.0fs\n', summary.cube_rows, ...
    summary.refits, summary.refits_failed, summary.refits_with_warnings, summary.wall_seconds);
end


function [T, F, i0] = walk(y, c, H1, sid, last)
%WALK  Every issuance of one (series, configuration); stop after issuance `last` when given.
mc = gdss.rattractor_model_config(c);
adapter = gdss.create_model_adapter(mc);
N = numel(y);
if nargin < 5, last = N - 1; end
p = c.params;
R = double(p.refit_every);
minTrain = double(p.min_train);
v = adapter.validate(struct('target_dimension', 1, 'training_observation_count', N));
need = minTrain;
if isfield(v, 'required_minimum_training_observations')
    need = max(need, double(v.required_minimum_training_observations));
end
i0 = need - 1;                                   % first issuance: y(0..i0) holds `need` points
iss = (i0:last)';
valid = string(v.status) == "VALID";
n = numel(iss);
yh = nan(n, H1); sd = nan(n, H1);
status = strings(n, 1); through = -ones(n, 1, 'int32');
fitRows = {};
fp = []; ft = -1;
if ~valid
    status(:) = "NO_FIT";
    fitRows{1} = fit_row(c, sid, i0, -1, "INVALID", string(v.status) + ": " + string(v.status_reason), "", NaN, "", 0);
end
for r = 1:n * valid
    i = iss(r);
    ytr = y(1:i+1);
    if mod(i - i0, R) == 0
        [fpNew, row] = try_fit(adapter, ytr, i, c, sid);
        fitRows{end+1, 1} = row; %#ok<AGROW>
        if ~isempty(fpNew)
            fp = fpNew; ft = i; status(r) = "REFIT";
        elseif isempty(fp)
            status(r) = "NO_FIT";
            continue
        else
            status(r) = "REFIT_FAILED";
        end
    else
        if isempty(fp), status(r) = "NO_FIT"; continue; end
        status(r) = "FILTERED";
    end
    q = fp;
    q.training_values = ytr;
    if string(c.adapter_id) == "analytical.naive_random_walk", q.state_at_origin = ytr(end); end  % the one adapter that forecasts from it
    try
        fc = adapter.forecast(q, struct('horizon', (1:H1)', 'origin_index', i + 1));
        yh(r, :) = fc.point_forecast(:)';
        sd(r, :) = fc.forecast_standard_deviation(:)';
        through(r) = ft;
    catch err
        status(r) = "FORECAST_FAILED";
        through(r) = ft;
        fitRows{end+1, 1} = fit_row(c, sid, i, ft, "FORECAST_FAILED", err.message, "", NaN, "", 0); %#ok<AGROW>
    end
end
T = table(repmat(string(sid), n, 1), repmat(string(c.config_id), n, 1), int32(iss), through, status, ...
    'VariableNames', {'series_id', 'config_id', 'issuance', 'fit_through', 'status'});
for h = 1:H1
    T.(sprintf('yhat_%02d', h)) = yh(:, h);
end
for h = 1:H1
    T.(sprintf('sd_%02d', h)) = sd(:, h);
end
if isempty(fitRows)
    F = fit_row(c, sid, -1, -1, "NO_REFIT", "no issuance", "", NaN, "", 0);
    F = F([], :);
else
    F = vertcat(fitRows{:});
end
end


function [fp, row] = try_fit(adapter, ytr, i, c, sid)
fp = [];
lastwarn('');
t = tic;
try
    out = evalc('fpOut = adapter.fit(struct(''target_values'', ytr), struct(''origin_index'', i + 1, ''training_start_index'', 1, ''training_end_index'', i + 1, ''training_observation_count'', numel(ytr)));'); %#ok<NASGU>
    [wmsg, ~] = lastwarn;
    fp = fpOut;
    ll = NaN;
    if isfield(fp, 'log_likelihood'), ll = double(fp.log_likelihood); end
    st = "COMPLETE";
    if isfield(fp, 'status'), st = string(fp.status); end
    conv = "";
    if isfield(fp, 'convergence_status'), conv = string(fp.convergence_status); end
    row = fit_row(c, sid, i, i, st, "", string(wmsg), ll, params_json(fp), toc(t));
    row.convergence_status = conv;
    if st ~= "COMPLETE", fp = []; end
catch err
    [wmsg, ~] = lastwarn;
    row = fit_row(c, sid, i, -1, "FIT_FAILED", string(err.message), string(wmsg), NaN, "", toc(t));
    row.convergence_status = "";
end
end


function row = fit_row(c, sid, i, through, status, reason, warns, ll, params, secs)
row = table(string(sid), string(c.config_id), int32(i), int32(through), string(status), string(reason), ...
    string(warns), double(ll), string(params), double(secs), "", ...
    'VariableNames', {'series_id', 'config_id', 'issuance', 'fit_through', 'status', 'reason', 'warnings', ...
                      'log_likelihood', 'params_json', 'seconds', 'convergence_status'});
end


function s = params_json(fp)
s = "";
try
    if isfield(fp, 'parameter_name') && isfield(fp, 'parameter_value')
        s = string(jsonencode(cell2struct(num2cell(double(fp.parameter_value(:))), ...
            cellstr(matlab.lang.makeValidName(string(fp.parameter_name(:)))), 1)));
    elseif isfield(fp, 'parameter_table') && istable(fp.parameter_table) && height(fp.parameter_table) > 0
        s = string(jsonencode(fp.parameter_table));
    end
catch
    s = "";
end
end


function out = leakage(y, c, H1, sid)
%LEAKAGE  Forecasts issued at or before a cut must not change when y after the cut changes.
N = numel(y);
R = double(c.params.refit_every);
[~, ~, i0] = walk(y, c, H1, sid, -1);           % first issuance only
cut = min(N - 2, i0 + 2 * R + 1);
y2 = y;
y2(cut + 2:end) = y2(cut + 2:end) + 10 * (std(y) + 1) * sin(1:numel(y2) - cut - 1)';
a = walk(y, c, H1, sid, cut);
b = walk(y2, c, H1, sid, cut);
cols = startsWith(a.Properties.VariableNames, 'yhat_') | startsWith(a.Properties.VariableNames, 'sd_');
A = a{:, cols}; B = b{:, cols};
out = struct('config_id', char(c.config_id), 'cut', cut, 'issuances_compared', height(a), ...
    'identical', isequaln(A, B) && isequal(a.fit_through, b.fit_through));
end
