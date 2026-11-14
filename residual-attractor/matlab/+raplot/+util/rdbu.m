function c = rdbu(n)
%RDBU  Diverging blue-white-red colormap, n rows (default 129): negative blue, zero white, positive red.
if nargin < 1, n = 129; end
x = linspace(-1, 1, n)';
b = [0.13 0.40 0.67]; r = [0.70 0.09 0.17]; w = [1 1 1];
c = (x < 0) .* (w + (-x) .* (b - w)) + (x >= 0) .* (w + x .* (r - w));
end
