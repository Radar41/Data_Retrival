function U = units(ctx, kind)
%UNITS  The units one stage draws, from ctx.rows (empty = every row). All indices 0-based.
%   'row'   U.k, U.i      every selected (k, i)
%   'k'     U.k           every configuration with a selected row
%   'i'     U.i           every series with a selected row
%   'byi'   U.i, U.ks{n}  series, and the configurations selected for each (row stages that read per series)
%   'byk'   U.k, U.is{n}  configurations, and the series selected for each
L = ctx.L;
R = ctx.rows;
if isempty(R)
    [kk, ii] = ndgrid(0:L.K-1, 0:L.N-1);
    R = [kk(:), ii(:)];
end
R = unique(R, 'rows');
switch kind
    case 'row', U.k = R(:, 1); U.i = R(:, 2);
    case 'k',   U.k = unique(R(:, 1));
    case 'i',   U.i = unique(R(:, 2));
    case 'byi'
        U.i = unique(R(:, 2));
        U.ks = arrayfun(@(i) R(R(:, 2) == i, 1), U.i, 'UniformOutput', false);
    case 'byk'
        U.k = unique(R(:, 1));
        U.is = arrayfun(@(k) R(R(:, 1) == k, 2), U.k, 'UniformOutput', false);
end
end
