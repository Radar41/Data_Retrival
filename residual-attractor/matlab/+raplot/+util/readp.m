function T = readp(ctx, rel, vars, filt)
%READP  parquetread of <build>/<rel>.parquet, optionally only some columns and rows.
%   T = readp(ctx, 'coherence/cells', {'k','i_a','r2'}, rowfilter("k").k == 5)
% vars must include every column the filter uses (parquetread requires it).
args = {};
if nargin > 2 && ~isempty(vars)
    args = [args, {'SelectedVariableNames', vars}];
end
if nargin > 3 && ~isempty(filt)
    args = [args, {'RowFilter', filt}];
end
T = parquetread(fullfile(ctx.B, [char(rel) '.parquet']), args{:});
end
