function [file, ttl] = names(ctx, k, i, stage)
%NAMES  File name and title of one unit. k or i may be [] (configuration or series units).
L = ctx.L;
if ~isempty(k) && ~isempty(i)
    file = sprintf('k%02d_i%02d_%s_%s.png', k, i, L.sid(i+1), L.cid(k+1));
    ttl = sprintf('%s   k%02d %s (%s)   i%02d %s', stage, k, L.kname(k+1), L.cid(k+1), i, L.sid(i+1));
elseif ~isempty(k)
    file = sprintf('k%02d_%s.png', k, L.cid(k+1));
    ttl = sprintf('%s   k%02d %s (%s)', stage, k, L.kname(k+1), L.cid(k+1));
else
    file = sprintf('i%02d_%s.png', i, L.sid(i+1));
    ttl = sprintf('%s   i%02d %s', stage, i, L.sid(i+1));
end
end
