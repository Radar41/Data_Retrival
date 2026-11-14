function [A, mon] = field(ctx, rel, var, T)
%FIELD  A (k, i, t) table as a K x N x P array over grid/month (NaN where absent).
%   [A, mon] = field(ctx, 'grid/resid', 'resid')         reads the table
%   [A, mon] = field(ctx, [], 'loading', T)              uses table T already read
mon = sort(raplot.util.readp(ctx, 'grid/month').t);
if nargin < 4, T = raplot.util.readp(ctx, rel, {'k', 'i', 't', var}); end
[ok, tt] = ismember(T.t, mon);
A = nan(ctx.L.K, ctx.L.N, numel(mon));
A(sub2ind(size(A), double(T.k(ok)) + 1, double(T.i(ok)) + 1, tt(ok))) = T.(var)(ok);
end
