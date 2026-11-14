function fit(ctx)
%FIT  Stage 3. Per row: y with yhat1, the one-step error e1, and the two states s1, s2 over the whole series.
% Overview: RMSE(e1) on the test split over RMSE of the no-change forecast. Check: the recursion tracks y.
L = ctx.L;
S = raplot.util.readp(ctx, 'series');
T = raplot.util.readp(ctx, 'states');
R = raplot.util.readp(ctx, 'registry', {'config_id', 's1_name', 's2_name'});
D = raplot.util.sdates(ctx);

M = nan(L.K, L.N);
for i = 0:L.N-1
    s = sortrows(S(S.series_id == L.sid(i+1), :), 't');
    te = s.t(s.split == "test");
    naive = sqrt(mean(diff(s.y(s.split == "test")).^2));
    ti = T(T.series_id == L.sid(i+1) & ismember(T.t, te), {'config_id', 'e1'});
    for k = 0:L.K-1
        e = ti.e1(ti.config_id == L.cid(k+1));
        M(k+1, i+1) = sqrt(mean(e.^2, 'omitnan')) / naive;
    end
end
[f, tl] = raplot.util.newfig(900, 1300, 1, 1, 'fit: RMSE(e1) on test / RMSE(no-change), every row', ctx);
raplot.util.kxn(nexttile(tl), ctx, M, 'relative RMSE (1 = no-change forecast)', [0 2]);
raplot.util.savefig(f, ctx, '00_overview.png');

U = raplot.util.units(ctx, 'byi');
parts = cell(numel(U.i), 1);
for n = 1:numel(U.i)
    sid = L.sid(U.i(n) + 1);
    parts{n} = struct('s', sortrows(S(S.series_id == sid, :), 't'), 'st', T(T.series_id == sid, :), 'd', D.(char(sid)));
end
parfor (n = 1:numel(U.i), ctx.M)
    p = parts{n};
    for k = U.ks{n}'
        draw(ctx, k, U.i(n), p, R);
    end
end
end

function draw(ctx, k, i, p, R)
cid = ctx.L.cid(k+1);
st = sortrows(p.st(p.st.config_id == cid, :), 't');
r = R(R.config_id == cid, :);
d = p.d;
tb = d(p.s.t(find(p.s.split == "test", 1)) + 1);
[file, ttl] = raplot.util.names(ctx, k, i, 'fit');
[f, tl] = raplot.util.newfig(1200, 900, 3, 1, ttl, ctx);
ax = nexttile(tl);
plot(ax, d(p.s.t + 1), p.s.y, 'k-', 'LineWidth', 0.9); hold(ax, 'on');
plot(ax, d(st.t + 1), st.yhat1, '-', 'Color', [.85 .33 .1], 'LineWidth', 0.8);
xline(ax, tb, 'k--', 'test start');
legend(ax, {'y', 'yhat1 (as stored at t)'}, 'Location', 'best');
title(ax, 'y and the one-step forecast'); grid(ax, 'on'); axis(ax, 'tight');
ax = nexttile(tl);
plot(ax, d(st.t + 1), st.e1, '-', 'Color', [.3 .3 .3]); hold(ax, 'on'); yline(ax, 0, 'k:');
xline(ax, tb, 'k--');
title(ax, sprintf('e1 = y - yhat1   (test RMSE %.4g, train RMSE %.4g)', ...
    sqrt(mean(st.e1(st.t >= p.s.t(find(p.s.split == "test", 1))).^2, 'omitnan')), ...
    sqrt(mean(st.e1(st.t < p.s.t(find(p.s.split == "test", 1))).^2, 'omitnan'))));
grid(ax, 'on'); axis(ax, 'tight');
ax = nexttile(tl);
yyaxis(ax, 'left'); plot(ax, d(st.t + 1), st.s1, '-'); ylabel(ax, "s1 " + r.s1_name);
yyaxis(ax, 'right'); plot(ax, d(st.t + 1), st.s2, '-'); ylabel(ax, "s2 " + r.s2_name);
xline(ax, tb, 'k--');
title(ax, sprintf('states: s1 = %s, s2 = %s', r.s1_name, r.s2_name)); grid(ax, 'on');
raplot.util.savefig(f, ctx, file);
end
