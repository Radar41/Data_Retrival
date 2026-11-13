"""Stage 10, compare: rdiag's Stage 1 under input contract v2, configuration against configuration.

Reads the grid (stage 9) and the registry; there is no fused reference (the archive rule).
Every analysis runs per series i on the configurations' own residuals resid[k, i, t]:

    loss          L[k, i, t] = resid^2 (or |resid|), each configuration on its own
    pairwise      every unordered pair k_a < k_b: Diebold-Mariano with the Harvey-Leybourne-Newbold
                  correction (two-sided, Student t, n - 1 df) on d = L_a - L_b, or Clark-West
                  (one-sided, normal) when one configuration nests the other (same core_spec_id,
                  exog set a strict subset); long-run variance Newey-West (Bartlett), lag
                  floor(4 (n / 100)^(2/9))
    mcs           Hansen-Lunde-Nason model confidence set, T_max statistic, stationary bootstrap
    fluctuation   Giacomini-Rossi: sqrt(m) x mean(d over the m months ending t) / sigma_HAC(d, full
                  sample), against the two-sided critical value of their Table 1 interpolated in m / P
    cpa           Giacomini-White conditional predictive ability on d with instruments h(t - 1),
                  Wald statistic with HAC covariance, chi-square with df = number of instruments
Twins (configurations that forecast identically through a method face, registry.twin_groups)
agree exactly or to rounding, so they never reach a test: their pairwise, fluctuation and CPA rows
are marked twin with no statistic, and the MCS runs on one representative per group (the smallest
k), whose result every member carries. Clark-West runs on the unscaled one-step errors (raw), not
the standardized residuals, so its adjustment is the squared forecast difference in one unit.
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
from scipy import stats

from .. import contracts
from ..registry import twin_groups
from . import AcceptanceError

# Giacomini and Rossi (2010), Table I: two-sided critical values of the fluctuation test, by mu = m / P.
GR_MU = np.array([0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9])
GR_TABLE = {
    0.05: np.array([3.393, 3.179, 3.012, 2.890, 2.779, 2.634, 2.560, 2.433, 2.248]),
    0.10: np.array([3.170, 2.948, 2.766, 2.626, 2.500, 2.356, 2.252, 2.130, 1.950]),
}
TINY = np.finfo(np.float64).tiny  # p-values are reported in (0, 1]


def hac_lag(n: int) -> int:
    return int(np.floor(4 * (n / 100) ** (2 / 9)))


def long_run_variance(d: np.ndarray) -> tuple[np.ndarray, int]:
    """Newey-West (Bartlett) long-run variance of each row of d, with the lag rule above."""
    n = d.shape[-1]
    q = hac_lag(n)
    x = d - d.mean(axis=-1, keepdims=True)
    lrv = (x * x).sum(axis=-1) / n
    for j in range(1, q + 1):
        lrv = lrv + 2.0 * (1.0 - j / (q + 1)) * (x[..., j:] * x[..., :-j]).sum(axis=-1) / n
    return lrv, q


def dm_hln(d: np.ndarray, horizon: int = 1) -> tuple[np.ndarray, np.ndarray, int]:
    """(statistic, two-sided p-value, lag) for each row of d."""
    n = d.shape[-1]
    lrv, q = long_run_variance(d)
    dm = d.mean(axis=-1) / np.sqrt(lrv / n)
    stat = dm * np.sqrt((n + 1 - 2 * horizon + horizon * (horizon - 1) / n) / n)
    return stat, np.clip(2.0 * stats.t.sf(np.abs(stat), df=n - 1), TINY, 1.0), q


def clark_west(e_small: np.ndarray, e_large: np.ndarray) -> tuple[np.ndarray, np.ndarray, int]:
    """(statistic, one-sided p-value, lag): MSPE-adjusted, positive when the larger model forecasts better.

    yhat_small - yhat_large = e_large - e_small, so the adjustment is computed from the residuals.
    """
    f = e_small**2 - (e_large**2 - (e_large - e_small) ** 2)
    n = f.shape[-1]
    lrv, q = long_run_variance(f)
    stat = f.mean(axis=-1) / np.sqrt(lrv / n)
    return stat, np.clip(stats.norm.sf(stat), TINY, 1.0), q


def stationary_bootstrap_weights(P: int, n_boot: int, block: float, rng: np.random.Generator) -> np.ndarray:
    """(n_boot, P) weights, each row the share of a Politis-Romano stationary-bootstrap resample at each t."""
    idx = np.empty((n_boot, P), dtype=np.int64)
    idx[:, 0] = rng.integers(0, P, n_boot)
    jump = rng.random((n_boot, P)) < 1.0 / block
    start = rng.integers(0, P, (n_boot, P))
    for t in range(1, P):
        idx[:, t] = np.where(jump[:, t], start[:, t], (idx[:, t - 1] + 1) % P)
    w = np.zeros((n_boot, P))
    np.add.at(w, (np.repeat(np.arange(n_boot), P), idx.reshape(-1)), 1.0)
    return w / P


def mcs(L: np.ndarray, alpha: float, weights: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Model confidence set over the rows of L (m models x P), T_max statistic.

    Returns (mcs_p_value, in_set, elimination_order) per model: the full elimination sequence is
    run, the p-value of the model eliminated at step s is the max of the step p-values so far, the
    last model gets 1, in_set = p >= alpha, and the order is 0 for the set and 1, 2, ... for the
    models eliminated before it.
    """
    m = L.shape[0]
    Lbar, Lstar = L.mean(axis=1), weights @ L.T  # (m,), (B, m)
    alive, pvals, order = list(range(m)), [], []
    while len(alive) > 1:
        a = np.array(alive)
        dbar = Lbar[a] - Lbar[a].mean()
        dstar = Lstar[:, a] - Lstar[:, a].mean(axis=1, keepdims=True)
        sd = np.sqrt(((dstar - dbar) ** 2).mean(axis=0))
        sd = np.where(sd > 0, sd, np.inf)  # a model that never differs from the set mean cannot be eliminated by it
        t = dbar / sd
        tstar = ((dstar - dbar) / sd).max(axis=1)
        pvals.append(float((tstar >= t.max()).mean()))
        e = int(a[np.argmax(t)])
        order.append(e)
        alive.remove(e)
    p = np.ones(m)
    running = 0.0
    for e, pv in zip(order, pvals):
        running = max(running, pv)
        p[e] = running
    in_set = p >= alpha
    elim = np.zeros(m, dtype=np.int64)
    step = 0
    for e in order:
        if not in_set[e]:
            step += 1
            elim[e] = step
    return p, in_set, elim


def fluctuation_critical_value(mu: float, alpha: float) -> float:
    if alpha not in GR_TABLE:
        raise AcceptanceError("compare", f"fluctuation alpha {alpha} has no column in the Giacomini-Rossi table (0.05, 0.10)")
    if not GR_MU[0] <= mu <= GR_MU[-1]:
        raise AcceptanceError("compare", f"fluctuation mu = m / P = {mu:.3f} lies outside the table's 0.1..0.9")
    return float(np.interp(mu, GR_MU, GR_TABLE[alpha]))


def fluctuation(d: np.ndarray, m: int) -> np.ndarray:
    """fstat for each row of d at every t; NaN for t < m - 1."""
    P = d.shape[-1]
    lrv, _ = long_run_variance(d)
    c = np.concatenate([np.zeros(d.shape[:-1] + (1,)), np.cumsum(d, axis=-1)], axis=-1)
    out = np.full(d.shape, np.nan)
    out[..., m - 1 :] = np.sqrt(m) * ((c[..., m:] - c[..., : P - m + 1]) / m) / np.sqrt(lrv)[..., None]
    return out


def cpa(d: np.ndarray, instruments: list[str]) -> tuple[np.ndarray, np.ndarray, int]:
    """(Wald statistic, p-value, n) of Giacomini-White for each row of d, instruments at t - 1."""
    y = d[..., 1:]
    named = {"const": np.ones_like(y), "d_lag1": d[..., :-1]}
    H = np.stack([named[nm] for nm in instruments], axis=-2)   # (..., q, n)
    Z = H * y[..., None, :]
    n, q = y.shape[-1], len(instruments)
    Zbar = Z.mean(axis=-1)
    lag = hac_lag(n)
    omega = np.einsum("...it,...jt->...ij", Z, Z) / n
    for j in range(1, lag + 1):
        g = np.einsum("...it,...jt->...ij", Z[..., j:], Z[..., :-j]) / n
        omega = omega + (1.0 - j / (lag + 1)) * (g + np.swapaxes(g, -1, -2))
    ok = np.linalg.matrix_rank(omega) == q  # a constant d leaves omega singular: no statistic, the check reports it
    stat = np.full(omega.shape[:-2], np.nan)
    if ok.any():
        stat[ok] = n * np.einsum("...i,...i->...", Zbar[ok], np.linalg.solve(omega[ok], Zbar[ok][..., None])[..., 0])
    return stat, np.where(ok, np.clip(stats.chi2.sf(stat, q), TINY, 1.0), np.nan), n


def _nested(config: pd.DataFrame, ka: np.ndarray, kb: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """(nested, a_is_small) for each pair: same core_spec_id and one exog set a strict subset of the other."""
    core = config.set_index("k")["core_spec_id"]
    ex = {int(k): set(v) for k, v in zip(config["k"], config["exog_set"])}
    nested, a_small = np.zeros(ka.size, bool), np.zeros(ka.size, bool)
    for j, (a, b) in enumerate(zip(ka, kb)):
        if core[a] == core[b]:
            if ex[a] < ex[b]:
                nested[j], a_small[j] = True, True
            elif ex[b] < ex[a]:
                nested[j] = True
    return nested, a_small


def _scatter(values: np.ndarray, mask: np.ndarray, fill=np.nan) -> np.ndarray:
    """Full-length array holding values where mask is true and fill elsewhere."""
    out = np.full(mask.shape + values.shape[1:], fill, dtype=np.result_type(values, np.float64))
    out[mask] = values
    return out


def run(frames: dict[str, pd.DataFrame], registry: pd.DataFrame, index: pd.DataFrame, cfg: dict,
        raw: np.ndarray | None = None) -> tuple[dict[str, pd.DataFrame], dict]:
    """raw: the unscaled one-step errors (K, N, P) in grid order, needed only when a pair is nested (Clark-West)."""
    r, config, months = frames["grid_resid"], frames["grid_config"], np.sort(frames["grid_month"]["t"].to_numpy())
    K, N, P = len(config), len(frames["grid_series"]), months.size
    cid_k = dict(zip(index["config_id"], index["k"].astype(int)))
    # A grid may hold only some configurations; a twin group counts only the members it holds.
    twins = [g for g in ([cid_k[c] for c in grp if c in cid_k] for grp in twin_groups(registry, cfg)) if len(g) > 1]
    rep = np.arange(K)
    for g in twins:
        rep[g] = min(g)
    R = np.empty((K, N, P))
    key = (r["k"].to_numpy(), r["i"].to_numpy(), np.searchsorted(months, r["t"].to_numpy()))
    R[key] = r["resid"].to_numpy()
    L = R**2 if cfg["compare.loss"] == "squared" else np.abs(R)

    ka, kb = np.triu_indices(K, 1)
    is_twin = rep[ka] == rep[kb]
    tested = ~is_twin
    nested, a_small = _nested(config, ka, kb)
    if (nested & tested).any() and raw is None:
        raise AcceptanceError("compare", "a nested pair needs Clark-West on the unscaled errors, and none were given")
    m = cfg["compare.fluctuation_window"]
    crit = fluctuation_critical_value(m / P, cfg["compare.fluctuation_alpha"])
    instruments = list(cfg["compare.cpa_instruments"])
    reps = np.unique(rep)
    cw = nested & tested

    out = {name: [] for name in ("loss", "pairwise", "mcs", "fluct", "fsup", "cpa")}
    for i in range(N):
        out["loss"].append(pd.DataFrame({"k": np.repeat(np.arange(K), P), "i": i, "t": np.tile(months, K), "loss": L[:, i, :].reshape(-1)}))
        # Twins never reach a test: identical models can make d exactly zero and every variance singular.
        d = L[ka[tested], i, :] - L[kb[tested], i, :]
        st, pv, q = dm_hln(d)
        stat, p = _scatter(st, tested), _scatter(pv, tested)
        if cw.any():
            e = raw[:, i, :]
            small = np.where(a_small[cw], ka[cw], kb[cw])
            large = np.where(a_small[cw], kb[cw], ka[cw])
            stat[cw], p[cw], _ = clark_west(e[small], e[large])
        test = np.where(nested, "CW", "DM_HLN").astype(object)
        test[is_twin] = "twin"
        out["pairwise"].append(pd.DataFrame({"i": i, "k_a": ka, "k_b": kb, "test": test, "nested": nested,
                                             "statistic": stat, "p_value": p, "hac_lag": q, "n": P}))
        f = _scatter(fluctuation(d, m), tested)
        sup = _scatter(np.nanmax(np.abs(f[tested]), axis=1), tested)
        out["fluct"].append(pd.DataFrame({"i": i, "k_a": np.repeat(ka, P), "k_b": np.repeat(kb, P), "t": np.tile(months, ka.size),
                                          "fstat": f.reshape(-1), "outside_band": (np.abs(np.nan_to_num(f, nan=0.0)) > crit).reshape(-1)}))
        out["fsup"].append(pd.DataFrame({"i": i, "k_a": ka, "k_b": kb, "sup_abs_fstat": sup, "critical_value": crit,
                                         "reject": pd.array(np.where(is_twin, None, sup > crit), dtype="boolean")}))
        cs, cp, cn = cpa(d, instruments)
        out["cpa"].append(pd.DataFrame({"i": i, "k_a": ka, "k_b": kb, "statistic": _scatter(cs, tested),
                                        "df": len(instruments), "p_value": _scatter(cp, tested), "n": cn,
                                        "instruments": [instruments] * ka.size}))
        rng = np.random.default_rng([cfg["seed"], 10, i])
        w = stationary_bootstrap_weights(P, cfg["compare.mcs_n_boot"], cfg["compare.mcs_block_length"], rng)
        pr, ins, elim = mcs(L[reps, i, :], cfg["compare.mcs_alpha"], w)
        pos = np.searchsorted(reps, rep)
        out["mcs"].append(pd.DataFrame({"i": i, "k": np.arange(K), "mcs_p_value": pr[pos], "in_set": ins[pos],
                                        "elimination_order": elim[pos], "represented_by": rep}))

    cat = lambda xs: pd.concat(xs, ignore_index=True)
    built = {}
    for name, artifact in (("loss", "compare_loss"), ("pairwise", "compare_pairwise"), ("mcs", "compare_mcs"),
                           ("fluct", "compare_fluctuation"), ("fsup", "compare_fluctuation_sup"), ("cpa", "compare_cpa")):
        f = cat(out[name])
        built[artifact] = contracts.from_columns({c: (f[c].tolist() if c in ("instruments", "reject") else f[c].to_numpy()) for c in f.columns}, artifact)
    check(built, frames, cfg, crit, int(is_twin.sum()))
    info = {
        "loss": cfg["compare.loss"], "hac": "Newey-West Bartlett, lag floor(4 (n / 100)^(2/9))", "hac_lag": hac_lag(P),
        "pairs_per_series": int(ka.size), "twin_pairs_per_series": int(is_twin.sum()),
        "twin_groups": [[int(k) for k in g] for g in twins], "nested_pairs_per_series": int(nested.sum()),
        "mcs": {"alpha": cfg["compare.mcs_alpha"], "statistic": "T_max", "n_boot": cfg["compare.mcs_n_boot"],
                "block_length": cfg["compare.mcs_block_length"], "models_per_series": int(reps.size)},
        "fluctuation": {"m": m, "mu": m / P, "alpha": cfg["compare.fluctuation_alpha"], "critical_value": crit, "sigma_scope": "full_sample"},
        "cpa": {"instruments": instruments, "lag": "instruments at t - 1"},
        "clark_west": "on the unscaled one-step errors, so its adjustment is the squared forecast difference in series units",
        "not_built": "Bai-Ng factor decomposition (a cross-configuration split; see the plan, section 5)",
    }
    return built, info


def check(b: dict[str, pd.DataFrame], frames: dict[str, pd.DataFrame], cfg: dict, crit: float, n_twin_pairs: int) -> None:
    """Stage 10 acceptance: rdiag's Stage 1 invariants in their v2 form; a failure carries the failing rows."""
    K, N, P = len(frames["grid_config"]), len(frames["grid_series"]), len(frames["grid_month"])
    pairs = K * (K - 1) // 2
    pw, mc, fl, fs, cp, ls = (b[x] for x in ("compare_pairwise", "compare_mcs", "compare_fluctuation", "compare_fluctuation_sup", "compare_cpa", "compare_loss"))
    problems, frames_out = [], []
    counts = {"compare_loss": K * N * P, "compare_pairwise": pairs * N, "compare_cpa": pairs * N, "compare_fluctuation_sup": pairs * N,
              "compare_fluctuation": pairs * N * P, "compare_mcs": K * N}
    for name, want in counts.items():
        if len(b[name]) != want:
            problems.append(f"{name} has {len(b[name])} rows, expected {want}")
    lm = ls.merge(frames["grid_resid"], on=["k", "i", "t"], how="left")
    want_loss = lm["resid"] ** 2 if cfg["compare.loss"] == "squared" else lm["resid"].abs()
    twin = (pw["test"] == "twin").to_numpy()
    p = pw["p_value"].to_numpy()
    nested, _ = _nested(frames["grid_config"], pw["k_a"].to_numpy(), pw["k_b"].to_numpy())
    rules = [
        ("compare_loss", ls, (lm["loss"] != want_loss).to_numpy(), "loss equals L(resid) exactly"),
        ("compare_pairwise", pw, ~twin & ~((p > 0) & (p <= 1) & np.isfinite(pw["statistic"].to_numpy())), "tested pairs carry a finite statistic and a p-value in (0, 1]"),
        ("compare_pairwise", pw, twin & (pw["statistic"].notna() | pw["p_value"].notna()).to_numpy(), "twin pairs carry no test"),
        ("compare_pairwise", pw, (pw["nested"].to_numpy() != nested) | (~twin & ((pw["test"] == "CW").to_numpy() != nested)), "test is CW exactly when the pair is nested"),
        ("compare_mcs", mc, mc["in_set"].to_numpy() != (mc["mcs_p_value"].to_numpy() >= cfg["compare.mcs_alpha"]), "in_set equals mcs_p_value >= alpha"),
        ("compare_mcs", mc, mc["in_set"].to_numpy() & (mc["elimination_order"].to_numpy() != 0), "set members have elimination order 0"),
        ("compare_cpa", cp, ~(cp["p_value"].isna().to_numpy() == (pw["test"] == "twin").to_numpy()) | (cp["p_value"].notna() & ~((cp["p_value"] > 0) & (cp["p_value"] <= 1))).to_numpy(),
         "cpa p-values in (0, 1] for tested pairs, null exactly for twins"),
        ("compare_fluctuation_sup", fs, (fs["critical_value"] != crit).to_numpy(), "critical value from the configured alpha and m / P"),
    ]
    month_pos = fl.groupby(["i", "k_a", "k_b"]).cumcount().to_numpy()
    fl_twin = fl.merge(pw[["i", "k_a", "k_b", "test"]], on=["i", "k_a", "k_b"], how="left")["test"].to_numpy() == "twin"
    m = cfg["compare.fluctuation_window"]
    rules += [
        ("compare_fluctuation", fl, fl["fstat"].isna().to_numpy() != (fl_twin | (month_pos < m - 1)), "fstat null exactly for the first m - 1 months and for twins"),
        ("compare_fluctuation", fl, fl["outside_band"].to_numpy() != (fl["fstat"].abs() > crit).fillna(False).to_numpy(), "outside_band equals |fstat| > critical value"),
    ]
    for artifact, frame, mask, rule in rules:
        if mask.any():
            problems.append(f"{artifact}: {rule} ({int(mask.sum())} rows)")
            keys = [c for c in ("i", "k", "k_a", "k_b", "t") if c in frame.columns]
            frames_out.append(frame.loc[mask, keys].assign(artifact=artifact, problem=rule))
    if int(twin.sum()) != n_twin_pairs * N:
        problems.append(f"{int(twin.sum())} twin pair rows, expected {n_twin_pairs * N}")
    if not mc.groupby("i")["in_set"].any().all():
        problems.append("every series needs at least one configuration in its model confidence set")
    if problems:
        raise AcceptanceError("compare", "; ".join(problems), pd.concat(frames_out, ignore_index=True) if frames_out else None)
