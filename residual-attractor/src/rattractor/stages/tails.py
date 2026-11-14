"""Stage tails: rdiag's Stage 2d under input contract v2, every configuration's row on its own.

Reads the grid (stage 9). Each row a = |resid[k, i, :]| (P months) is analysed alone; no value here
is computed from two rows, so nothing crosses configurations or series.

    hill_curve    gamma(n_tail) = mean(ln a_(0), ..., ln a_(n_tail - 1)) - ln a_(n_tail), with
                  a_(0) >= a_(1) >= ... the row sorted descending, for every n_tail on
                  tails.n_tail_grid; se = gamma / sqrt(n_tail). `star` marks n_tail_star: the middle of
                  the tails.n_tail_stability_width consecutive n_tail whose gammas vary least
                  (tails.n_tail_rule: hill_stability).
    mean_excess   on the thresholds u_j = the q_j quantile of a (linear interpolation), q_j on
                  tails.threshold_grid_quantiles [first, last, step]: n_exceed = #{a > u},
                  e(u) = mean(a - u | a > u), and the generalized Pareto fit to the excesses y = a - u,
                      l(xi, sigma) = -n ln sigma - (1 + 1 / xi) sum ln(1 + xi y / sigma):
                  gpd_shape = the xi >= tails.gpd_shape_min that maximizes the profile
                  l_p(xi) = max over sigma of l, and [gpd_ci_lo, gpd_ci_hi] = the range of such xi with
                  2 (l_p(gpd_shape) - l_p(xi)) <= the tails.gpd_ci_level quantile of chi-square(1).
                  `stable` is true where the threshold's shape lies inside the interval of every
                  higher fitted threshold.
    rolling_hill  gamma and se with tails.rolling_n_tail upper order statistics over the
                  tails.rolling_window months ending at t; null before the first full window.
    thresholds    u_star = the row's lowest stable threshold (tails.threshold_rule:
                  gpd_shape_stability), u its index on the quantile grid, n_exceed = #{a > u_star}.
                  Stage events reads this table; no fixed sigma cutoff exists anywhere.

Source: rdiag s2_transforms/tails.py, schemas/20_stage2.yaml (s2d.*), params tails.*.
Departures from rdiag, and the choices it leaves open:
  - k is in every key: rdiag ran on the fused row, here every configuration's row runs on its own.
  - rdiag calls the number of upper order statistics k. Here k is the configuration, so the count is
    n_tail in every column and config key (k_grid, k_rule, k_stability_width, rolling_k), and rdiag's
    k_star is the `star` flag on the curve.
  - n_tail_star: rdiag gives the rule (minimum variance of gamma over a sliding range) but not which
    n_tail of the chosen range. Here the middle one (the lower middle when the width is even), and
    the lowest range on a tie.
  - The generalized Pareto fit. rdiag asks for maximum likelihood "with a fixed starting point" and for
    "confidence intervals", naming neither a bound nor the interval. The likelihood is unbounded for
    xi < -1 and has no regular optimum below -1/2, so the estimate here is the maximum over
    xi >= tails.gpd_shape_min, found by a search that needs no starting point. The interval is the
    profile-likelihood interval (tails.gpd_ci), cut at the same bound, not estimate +/- z x asymptotic
    standard error: a row here has 3 to 30 exceedances, and on exponential excesses the latter covers
    the true shape 29% of the time at 5 exceedances, 51% at 10 and 76% at 30 (nominal 95%), the
    profile interval 99%, 96% and 91% (tests/stages/test_tails.py simulates both).
  - A threshold with fewer than tails.min_exceed exceedances carries no fit and takes no part in the
    stability rule. rdiag fits at every grid quantile, which at P = 98 fits two points at q = 0.98;
    its postcondition n_exceed >= 3 is the value of that key, so the highest fitted threshold is
    always stable and every chosen threshold has at least that many exceedances.
  - Rows that cannot be measured get nulls instead of stopping the run (rdiag raises): gamma is null
    where a_(n_tail) = 0 (no logarithm), no star where no full range is defined, and u_star is null
    where no threshold has tails.min_exceed exceedances (the row then has no events).
  - mean_excess also carries n_exceed and stable, and thresholds carries u, so the rule can be read
    and checked from the tables.
"""

from __future__ import annotations

import re

import numpy as np
import pandas as pd
from scipy import stats

from .. import contracts
from . import AcceptanceError

COUNT_RULE = re.compile(r"floor\(P / ([1-9][0-9]*)\)")  # the one rule a count may follow instead of being an integer
THRESHOLD_RULES = ("gpd_shape_stability",)
N_TAIL_RULES = ("hill_stability",)
GOLDEN = (np.sqrt(5.0) - 1.0) / 2.0
GRID, GOLDEN_STEPS, BISECTIONS = 65, 32, 40  # sizes of the likelihood search: numerics, not statistics
POLISH = 1e-6                                 # half-width in s of the bracket the maximum is refined in after the golden section
TINY = 1e-290                                 # guards a logarithm of the smallest excess relative to the largest
CHUNK = 4096                                  # rows of the field fitted at a time (memory only)


def resolve_count(spec, P: int) -> int:
    """A count from the config: an integer, or the text 'floor(P / d)'."""
    if isinstance(spec, str):
        return P // int(COUNT_RULE.fullmatch(spec).group(1))
    return int(spec)


def n_tail_grid(cfg: dict, P: int) -> np.ndarray:
    lo, hi = (resolve_count(x, P) for x in cfg["tails.n_tail_grid"])
    return np.arange(lo, hi + 1)


def quantile_grid(cfg: dict) -> np.ndarray:
    first, last, step = cfg["tails.threshold_grid_quantiles"]
    return np.round(first + step * np.arange(int(np.floor((last - first) / step + 1e-9)) + 1), 12)


def dense(frames: dict[str, pd.DataFrame], stage: str = "tails") -> tuple[np.ndarray, np.ndarray]:
    """(resid as a (K, N, P) array, the months in order)."""
    r = frames["grid_resid"]
    months = np.sort(frames["grid_month"]["t"].to_numpy())
    R = np.full((len(frames["grid_config"]), len(frames["grid_series"]), months.size), np.nan)
    R[r["k"].to_numpy(), r["i"].to_numpy(), np.searchsorted(months, r["t"].to_numpy())] = r["resid"].to_numpy()
    if np.isnan(R).any():
        raise AcceptanceError(stage, "the grid does not hold one finite residual per (k, i, t)")
    return R, months


def hill(a_desc: np.ndarray, n_tail: np.ndarray) -> np.ndarray:
    """Hill's gamma at each n_tail for each row of a_desc (sorted descending along the last axis).

    NaN where the (n_tail + 1)-th largest value is 0: its logarithm does not exist.
    """
    with np.errstate(divide="ignore", invalid="ignore"):
        ln = np.log(a_desc)
        g = np.cumsum(ln, axis=-1)[..., n_tail - 1] / n_tail - ln[..., n_tail]
    return np.where(a_desc[..., n_tail] > 0, g, np.nan)


def hill_star(gamma: np.ndarray, width: int) -> np.ndarray:
    """Position on the n_tail grid of each row's n_tail_star, -1 where no range of `width` is fully defined."""
    rows, n = gamma.shape
    star = np.full(rows, -1)
    if rows == 0 or width > n:
        return star
    var = np.lib.stride_tricks.sliding_window_view(gamma, width, axis=1).var(axis=2)  # NaN where a gamma is null
    ok = ~np.isnan(var)
    has = ok.any(axis=1)
    star[has] = np.where(ok, var, np.inf).argmin(axis=1)[has] + (width - 1) // 2
    return star


def rolling_hill(a: np.ndarray, window: int, n_tail: int) -> np.ndarray:
    """Hill's gamma over the `window` values ending at each t, for each row of a; NaN before the first full window."""
    out = np.full(a.shape, np.nan)
    if window <= a.shape[-1]:
        top = -np.sort(-np.lib.stride_tricks.sliding_window_view(a, window, axis=-1), axis=-1)[..., : n_tail + 1]
        out[..., window - 1 :] = hill(top, np.array([n_tail]))[..., 0]
    return out


def gpd_fit(Y: np.ndarray, n: np.ndarray, shape_min: float, level: float) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """(shape, ci_lo, ci_hi) of the generalized Pareto fit to the first n[f] values (all > 0) of each row of Y.

    With tau = xi / sigma, the sigma that maximizes l at a given xi satisfies mean(1 / (1 + tau y)) = 1 / (1 + xi),
    so tau alone traces the profile: xi(tau) = 1 / w - 1 with w = mean(1 / (1 + tau y)), increasing in tau, and
        l_p / n = -ln(xi(tau) / tau) - mean(ln(1 + tau y)) / (1 - w).
    l_p rises where mean(ln(1 + tau y)) > xi(tau) and falls where it is smaller.
    The search runs in s = ln(1 + tau max(y)): a fixed grid from the point where xi = shape_min to a bound past
    which l_p only falls, golden-section refinement around the best grid point, bisection on the sign of the
    slope to settle the maximum, and bisection for the two ends of the interval (the outermost crossings of l_p
    with its maximum less chi-square / 2 that the grid separates).
    shape_min is the estimate when no xi above it does better, and the lower end when l_p there is still inside.
    """
    F, M = Y.shape
    valid = np.arange(M)[None, :] < n[:, None]
    z = np.where(valid, Y / np.where(valid, Y, 0.0).max(axis=1)[:, None], 0.0)  # excesses over the largest, in (0, 1]
    top = valid & (z == 1.0)
    zmin = np.maximum(np.where(valid, z, 1.0).min(axis=1), TINY)

    def curve(s: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """(l_p / n + ln max(y), xi, a value with the sign of the slope of l_p) at s, one of each per fit."""
        th = np.expm1(s)[:, None]
        with np.errstate(divide="ignore", invalid="ignore", over="ignore"):
            den = np.where(top, np.exp(s)[:, None], 1.0 + th * z)  # 1 + tau y; exactly e^s for the largest excess
            w = np.where(valid, 1.0 / den, 0.0).sum(axis=1) / n
            v = np.where(valid, z / den, 0.0).sum(axis=1) / n      # (1 - w) / theta, without the cancellation
            m = np.where(valid, np.where(top, s[:, None], np.log1p(th * z)), 0.0).sum(axis=1) / n
            th = th[:, 0]
            xi = th * v / w
            return -np.log(v / w) - np.where(th == 0.0, 1.0, m / (th * v)), xi, m - xi

    def bisect(inside: np.ndarray, outside: np.ndarray, is_inside) -> np.ndarray:
        for _ in range(BISECTIONS):
            mid = 0.5 * (inside + outside)
            keep = is_inside(mid)
            inside, outside = np.where(keep, mid, inside), np.where(keep, outside, mid)
        return inside

    w_max = 1.0 / (1.0 + shape_min)                       # w at xi = shape_min
    s_lo = bisect(np.full(F, -np.log(w_max)), -np.log(n * w_max), lambda s: curve(s)[1] >= shape_min)
    big = -np.log(zmin)
    s_hi = np.log1p((2.0 * big + 2.0) / zmin)             # l_p falls for every s beyond this

    step = (s_hi - s_lo) / (GRID - 1)
    values = np.stack([curve(s_lo + step * j)[0] for j in range(GRID)])   # (GRID, F)
    j_best = values.argmax(axis=0)
    a, b = s_lo + step * np.maximum(j_best - 1, 0), s_lo + step * np.minimum(j_best + 1, GRID - 1)
    c, d = b - GOLDEN * (b - a), a + GOLDEN * (b - a)
    fc, fd = curve(c)[0], curve(d)[0]
    for _ in range(GOLDEN_STEPS):
        left = fc > fd
        a, b = np.where(left, a, c), np.where(left, d, b)
        c_new, d_new = np.where(left, b - GOLDEN * (b - a), d), np.where(left, c, a + GOLDEN * (b - a))
        f_new = curve(np.where(left, c_new, d_new))[0]
        fc, fd = np.where(left, f_new, fd), np.where(left, fc, f_new)
        c, d = c_new, d_new
    s_star = 0.5 * (a + b)
    l_lo = curve(s_lo)[0]
    at_min = l_lo >= curve(s_star)[0]                     # nothing above shape_min does better
    a, b = np.maximum(s_star - POLISH, s_lo), np.minimum(s_star + POLISH, s_hi)
    settle = ~at_min & (curve(a)[2] > 0) & (curve(b)[2] < 0)   # the slope changes sign around the golden-section point
    s_star = np.where(settle, bisect(a, b, lambda s: curve(s)[2] > 0), s_star)
    l_star, shape, _ = curve(s_star)
    s_star, l_star, shape = np.where(at_min, s_lo, s_star), np.where(at_min, l_lo, l_star), np.where(at_min, shape_min, shape)

    target = l_star - stats.chi2.ppf(level, 1) / (2.0 * n)
    inside = lambda s: curve(s)[0] >= target
    grid_s = s_lo[None, :] + step[None, :] * np.arange(GRID)[:, None]
    ok = values >= target[None, :]
    cols = np.arange(F)
    # lower end: the leftmost grid point inside at or below s_star (s_star itself when there is none), against the grid point before it
    left_ok = ok & (grid_s <= s_star[None, :])
    j_in = np.where(left_ok.any(axis=0), left_ok.argmax(axis=0), -1)
    s_in = np.where(j_in >= 0, grid_s[np.maximum(j_in, 0), cols], s_star)
    j_out = np.where(j_in >= 0, j_in - 1, np.floor((s_star - s_lo) / np.where(step > 0, step, 1.0)).astype(int))
    j_out = np.where((j_in < 0) & (grid_s[np.clip(j_out, 0, GRID - 1), cols] >= s_star), j_out - 1, j_out)
    open_left = (j_out < 0) | (l_lo >= target)            # the bound cuts the interval
    s_left = bisect(s_in, grid_s[np.clip(j_out, 0, GRID - 1), cols], inside)
    ci_lo = np.where(open_left, shape_min, curve(s_left)[1])
    # upper end: the rightmost grid point inside at or above s_star, against the next one, or the far bound past s_hi
    right_ok = ok & (grid_s >= s_star[None, :])
    j_in = np.where(right_ok.any(axis=0), GRID - 1 - right_ok[::-1].argmax(axis=0), -1)
    s_in = np.where(j_in >= 0, grid_s[np.maximum(j_in, 0), cols], s_star)
    j_out = np.where(j_in >= 0, j_in + 1, np.ceil((s_star - s_lo) / np.where(step > 0, step, 1.0)).astype(int))
    j_out = np.where((j_in < 0) & (grid_s[np.clip(j_out, 0, GRID - 1), cols] <= s_star), j_out + 1, j_out)
    with np.errstate(over="ignore"):
        s_far = np.maximum(np.log1p(np.expm1(np.clip(big - target, 0.0, 600.0)) / zmin), s_hi)  # l_p < target beyond
    s_out = np.where(j_out > GRID - 1, s_far, grid_s[np.clip(j_out, 0, GRID - 1), cols])
    ci_hi = curve(bisect(s_in, s_out, inside))[1]
    return shape, np.minimum(ci_lo, shape), np.maximum(ci_hi, shape)


def stable_thresholds(shape: np.ndarray, lo: np.ndarray, hi: np.ndarray) -> np.ndarray:
    """Along the last axis (thresholds ascending, NaN = not fitted): shape[j] lies inside [lo[m], hi[m]] for every fitted m > j."""
    fitted = ~np.isnan(shape)
    lo_f, hi_f = np.where(fitted, lo, -np.inf), np.where(fitted, hi, np.inf)
    end = np.full(shape.shape[:-1] + (1,), np.inf)
    lo_above = np.concatenate([np.maximum.accumulate(lo_f[..., ::-1], axis=-1)[..., ::-1][..., 1:], -end], axis=-1)
    hi_above = np.concatenate([np.minimum.accumulate(hi_f[..., ::-1], axis=-1)[..., ::-1][..., 1:], end], axis=-1)
    with np.errstate(invalid="ignore"):
        return fitted & (shape >= lo_above) & (shape <= hi_above)


def excesses(a_desc: np.ndarray, U: np.ndarray, width: int) -> tuple[np.ndarray, np.ndarray]:
    """(n_exceed (rows, G), Y (rows, G, width)): the first n_exceed entries of Y[r, j] are the excesses of row r over U[r, j]."""
    n_exc = np.stack([(a_desc > U[:, j : j + 1]).sum(axis=1) for j in range(U.shape[1])], axis=1) if U.shape[1] else np.zeros(U.shape, int)
    if n_exc.size and n_exc.max() > width:
        raise AcceptanceError("tails", f"{int(n_exc.max())} values exceed a threshold, more than the {width} the lowest quantile allows")
    return n_exc, a_desc[:, None, :width] - U[:, :, None]


def run(frames: dict[str, pd.DataFrame], cfg: dict) -> tuple[dict[str, pd.DataFrame], dict]:
    R, months = dense(frames)
    K, N, P = R.shape
    rows = K * N
    a = np.abs(R).reshape(rows, P)
    kk, ii = np.repeat(np.arange(K), N), np.tile(np.arange(N), K)
    a_desc = -np.sort(-a, axis=1)

    n_grid = n_tail_grid(cfg, P)
    if n_grid.size and (n_grid[0] < 1 or n_grid[-1] > P - 1):
        raise AcceptanceError("tails", f"tails.n_tail_grid gives n_tail {n_grid[0]}..{n_grid[-1]} at P = {P}; Hill needs 1 <= n_tail <= P - 1")
    gamma = hill(a_desc, n_grid)
    star = hill_star(gamma, cfg["tails.n_tail_stability_width"])
    is_star = np.arange(n_grid.size)[None, :] == star[:, None]

    q = quantile_grid(cfg)
    G = q.size
    U = np.quantile(a, q, axis=1).T
    width = P - int(np.floor((P - 1) * q[0]))  # no more values than this can lie above the lowest threshold, whatever the row
    n_exc, mean_exc = np.empty((rows, G), dtype=np.int64), np.empty((rows, G))
    shape, ci_lo, ci_hi = (np.full((rows, G), np.nan) for _ in range(3))
    for r0 in range(0, rows, CHUNK):
        sl = slice(r0, r0 + CHUNK)
        n_c, Y = excesses(a_desc[sl], U[sl], width)
        valid = np.arange(width)[None, None, :] < n_c[:, :, None]
        with np.errstate(invalid="ignore", divide="ignore"):
            mean_exc[sl] = np.where(n_c > 0, np.where(valid, Y, 0.0).sum(axis=2) / n_c, np.nan)
        n_exc[sl] = n_c
        fit = n_c >= cfg["tails.min_exceed"]
        if fit.any():
            est = gpd_fit(Y[fit], n_c[fit], cfg["tails.gpd_shape_min"], cfg["tails.gpd_ci_level"])
            for out, values in zip((shape, ci_lo, ci_hi), est):
                out[sl][fit] = values
    stable = stable_thresholds(shape, ci_lo, ci_hi)
    has = stable.any(axis=1)
    u = np.where(has, stable.argmax(axis=1), -1)
    pick = np.maximum(u, 0)
    u_star = np.where(has, U[np.arange(rows), pick], np.nan)
    n_star = np.where(has, n_exc[np.arange(rows), pick], 0)

    rolled = rolling_hill(a, cfg["tails.rolling_window"], cfg["tails.rolling_n_tail"])
    built = {
        "tails_hill_curve": contracts.from_columns({
            "k": np.repeat(kk, n_grid.size), "i": np.repeat(ii, n_grid.size), "n_tail": np.tile(n_grid, rows),
            "gamma": gamma.reshape(-1), "se": (gamma / np.sqrt(n_grid)[None, :]).reshape(-1), "star": is_star.reshape(-1),
        }, "tails_hill_curve"),
        "tails_mean_excess": contracts.from_columns({
            "k": np.repeat(kk, G), "i": np.repeat(ii, G), "u": np.tile(np.arange(G), rows), "threshold": U.reshape(-1),
            "n_exceed": n_exc.reshape(-1), "mean_excess": mean_exc.reshape(-1), "gpd_shape": shape.reshape(-1),
            "gpd_ci_lo": ci_lo.reshape(-1), "gpd_ci_hi": ci_hi.reshape(-1), "stable": stable.reshape(-1),
        }, "tails_mean_excess"),
        "tails_rolling_hill": contracts.from_columns({
            "k": np.repeat(kk, P), "i": np.repeat(ii, P), "t": np.tile(months, rows),
            "gamma": rolled.reshape(-1), "se": (rolled / np.sqrt(cfg["tails.rolling_n_tail"])).reshape(-1),
        }, "tails_rolling_hill"),
        "tails_thresholds": contracts.from_columns({
            "k": kk, "i": ii, "u": [int(x) if x >= 0 else None for x in u], "u_star": u_star, "n_exceed": n_star,
        }, "tails_thresholds"),
    }
    check(built, frames, cfg)
    fitted = ~np.isnan(shape)
    info = {
        "rdiag": "s2d.hill_curve, s2d.mean_excess, s2d.rolling_hill, s2d.thresholds, one row of the field at a time",
        "rows": rows,
        "n_tail_grid": [int(n_grid[0]), int(n_grid[-1])] if n_grid.size else [],
        "n_tail_rule": f"{cfg['tails.n_tail_rule']}: middle of the {cfg['tails.n_tail_stability_width']} consecutive n_tail with the least variance of gamma",
        "rows_without_star": int((star < 0).sum()),
        "threshold_quantiles": [float(x) for x in q],
        "threshold_rule": f"{cfg['tails.threshold_rule']}: the lowest threshold whose shape lies inside the interval of every higher fitted one",
        "gpd": {"estimate": f"maximum likelihood over shape >= {cfg['tails.gpd_shape_min']}", "interval": cfg["tails.gpd_ci"],
                "level": cfg["tails.gpd_ci_level"], "min_exceed": cfg["tails.min_exceed"],
                "fits": int(fitted.sum()), "fits_at_shape_min": int((shape[fitted] <= cfg["tails.gpd_shape_min"]).sum())},
        "rows_without_threshold": int((~has).sum()),
        "rows_at_lowest_quantile": int((u == 0).sum()),
        "n_exceed_at_u_star": {"min": int(n_star[has].min()), "median": float(np.median(n_star[has])), "max": int(n_star[has].max())} if has.any() else {},
        "rolling": {"window": cfg["tails.rolling_window"], "n_tail": cfg["tails.rolling_n_tail"]},
    }
    return built, info


def check(b: dict[str, pd.DataFrame], frames: dict[str, pd.DataFrame], cfg: dict) -> None:
    """Stage tails acceptance: rdiag's s2d invariants in their v2 form; a failure carries the failing rows."""
    R, months = dense(frames)
    K, N, P = R.shape
    a = np.abs(R)
    hc, me, rh, th = (b[x] for x in ("tails_hill_curve", "tails_mean_excess", "tails_rolling_hill", "tails_thresholds"))
    n_grid, q = n_tail_grid(cfg, P), quantile_grid(cfg)
    min_exceed, window, n_roll = cfg["tails.min_exceed"], cfg["tails.rolling_window"], cfg["tails.rolling_n_tail"]
    problems, failing = [], []
    counts = {"tails_hill_curve": K * N * n_grid.size, "tails_mean_excess": K * N * q.size, "tails_rolling_hill": K * N * P, "tails_thresholds": K * N}
    for name, want in counts.items():
        if len(b[name]) != want:
            problems.append(f"{name} has {len(b[name])} rows, expected {want}")
    if problems:
        raise AcceptanceError("tails", "; ".join(problems))

    def same(x, y):  # equal, nulls matching nulls
        x, y = np.asarray(x, dtype=np.float64), np.asarray(y, dtype=np.float64)
        return (x == y) | (np.isnan(x) & np.isnan(y))

    a_desc = -np.sort(-a, axis=2)
    g, se = hc["gamma"].to_numpy(), hc["se"].to_numpy()
    hk, hi_, hn = hc["k"].to_numpy(), hc["i"].to_numpy(), hc["n_tail"].to_numpy()
    stars = hc.groupby(["k", "i"], sort=False)["star"].transform("sum").to_numpy()
    fit = (me["n_exceed"] >= min_exceed).to_numpy()
    xi, lo, hi = (me[c].to_numpy() for c in ("gpd_shape", "gpd_ci_lo", "gpd_ci_hi"))
    count = (a[me["k"].to_numpy(), me["i"].to_numpy(), :] > me["threshold"].to_numpy()[:, None]).sum(axis=1)
    G = q.size
    want_stable = stable_thresholds(xi.reshape(-1, G), lo.reshape(-1, G), hi.reshape(-1, G)).reshape(-1)
    pos = np.searchsorted(months, rh["t"].to_numpy())
    rg = rh["gamma"].to_numpy()
    flat = np.zeros(len(rh), dtype=bool)  # windows whose (n_tail + 1)-th largest value is 0
    if window <= P:
        nth = -np.sort(-np.lib.stride_tricks.sliding_window_view(a, window, axis=2), axis=3)[..., n_roll]
        full = pos >= window - 1
        flat[full] = nth[rh["k"].to_numpy()[full], rh["i"].to_numpy()[full], pos[full] - (window - 1)] <= 0
    first = me[me["stable"]].groupby(["k", "i"], sort=False)["u"].min().rename("first_stable")
    tm = th.merge(first, left_on=["k", "i"], right_index=True, how="left")
    tm = tm.merge(me[["k", "i", "u", "threshold"]].rename(columns={"u": "first_stable"}), on=["k", "i", "first_stable"], how="left")
    u_star = th["u_star"].to_numpy()
    with np.errstate(invalid="ignore"):
        star_count = (a[th["k"].to_numpy(), th["i"].to_numpy(), :] > u_star[:, None]).sum(axis=1)
        rules = [
            ("tails_hill_curve", hc, ~same(se, g / np.sqrt(hn)), "se equals gamma / sqrt(n_tail)"),
            ("tails_hill_curve", hc, np.isnan(g) != (a_desc[hk, hi_, hn] <= 0), "gamma is null exactly where the (n_tail + 1)-th largest |resid| is 0"),
            ("tails_hill_curve", hc, (stars > 1) | (hc["star"].to_numpy() & np.isnan(g)), "at most one star per row, on a defined gamma"),
            ("tails_mean_excess", me, me["n_exceed"].to_numpy() != count, "n_exceed counts |resid| above the threshold"),
            ("tails_mean_excess", me, me["mean_excess"].isna().to_numpy() != (count == 0), "mean_excess is null exactly where nothing exceeds the threshold"),
            ("tails_mean_excess", me, (me["mean_excess"] <= 0).to_numpy() | (me["threshold"] < 0).to_numpy(), "thresholds are not negative and mean excesses are positive"),
            ("tails_mean_excess", me, (np.isnan(xi) == fit) | (np.isnan(lo) == fit) | (np.isnan(hi) == fit), "a generalized Pareto fit exactly where n_exceed >= tails.min_exceed"),
            ("tails_mean_excess", me, fit & ~((lo <= xi) & (xi <= hi) & (lo >= cfg["tails.gpd_shape_min"])), "tails.gpd_shape_min <= gpd_ci_lo <= gpd_shape <= gpd_ci_hi"),
            ("tails_mean_excess", me, me["stable"].to_numpy() != want_stable, "stable means the shape lies inside the interval of every higher fitted threshold"),
            ("tails_rolling_hill", rh, np.isnan(rg) != ((pos < window - 1) | flat), "rolling gamma is null exactly before the first full window (and where the window's (n_tail + 1)-th largest |resid| is 0)"),
            ("tails_rolling_hill", rh, ~same(rh["se"].to_numpy(), rg / np.sqrt(n_roll)), "rolling se equals gamma / sqrt(tails.rolling_n_tail)"),
            ("tails_thresholds", th, ~same(tm["first_stable"].to_numpy(dtype=np.float64, na_value=np.nan), th["u"].to_numpy(dtype=np.float64, na_value=np.nan))
             | ~same(tm["threshold"].to_numpy(), u_star), "u_star is the row's lowest stable threshold"),
            ("tails_thresholds", th, th["n_exceed"].to_numpy() != star_count, "n_exceed counts |resid| above u_star"),
            ("tails_thresholds", th, ~np.isnan(u_star) & (th["n_exceed"].to_numpy() < min_exceed), "a chosen threshold has at least tails.min_exceed exceedances"),
        ]
    for artifact, frame, mask, rule in rules:
        if mask.any():
            problems.append(f"{artifact}: {rule} ({int(mask.sum())} rows)")
            keys = [c for c in ("k", "i", "t", "n_tail", "u") if c in frame.columns]
            failing.append(frame.loc[mask, keys].assign(artifact=artifact, problem=rule))
    if problems:
        raise AcceptanceError("tails", "; ".join(problems), pd.concat(failing, ignore_index=True))
