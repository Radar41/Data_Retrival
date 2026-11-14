function L = labels(ctx)
%LABELS  Index maps of one build: k -> configuration, i -> series (both 0-based, as stored).
%   L.cid(k+1)   config_id          L.kname(k+1)  "method params" (short, for axes)
%   L.method(k+1) ses / ar / holt   L.sid(i+1)    series_id
% Checks grid/names against fiber_index so the two orders cannot drift apart.
N = raplot.util.readp(ctx, 'grid/names');
kk = sortrows(N(N.axis == "k", :), 'idx');
ii = sortrows(N(N.axis == "i", :), 'idx');
parts = split(kk.name, " ", 2);            % "<config_id> <method> <params json>"
L.cid = parts(:, 1);
L.method = parts(:, 2);
L.kname = strip(extractAfter(kk.name, L.cid + " "));
L.sid = ii.name;
L.K = height(kk);
L.N = height(ii);
FI = sortrows(raplot.util.readp(ctx, 'fiber_index'), 'k');
assert(isequal(FI.config_id, L.cid), 'raplot:labels', 'grid/names k order differs from fiber_index');
L.kshort = compose("%02d %s", (0:L.K-1)', L.kname);
end
