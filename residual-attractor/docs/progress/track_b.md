# Track B progress: who leads, by events

Branch `claude/ra-tails-coincidence-4bf46d` (worktree `ra-tails-coincidence-4bf46d`), from `3eb8984`. Brief: `docs/WORK_PACKAGES.md`, Track B. Nothing is pushed or merged.

## State

| Package | Stage | State |
|---|---|---|
| B1 | `tails` | built, tested, in the build (commit `35e9e0a`) |
| B2 | `events` | built, tested, in the build |
| B3 | `coincidence` | **not started**; design below |

Suite at B2: 341 passed, 1 expected failure (268 baseline + 53 tails + 20 events). Spec 0 builds with `tails` and `events` in `stages_passed`.

Still to do after B3: the second, independently written recomputation of a sample of spec 0; planted bugs against the tests; the baseline build time for "time added"; the section 8 report.

## B1 `tails` (rdiag s2d, every configuration's row on its own)

Files: `src/rattractor/stages/tails.py`, `schemas/tails_{hill_curve,mean_excess,rolling_hill,thresholds}.yaml`, `tests/stages/test_tails.py`, config keys `tails.*`, blocks in `build.py`, `config.py`, `test_build.py`. Written to `builds/<id>/tails/`.

Each row a = |resid[k, i, :]| is analysed alone. Tables and keys:

- `tails_hill_curve` (k, i, n_tail): gamma, se, `star` (rdiag's k_star).
- `tails_mean_excess` (k, i, u): threshold, n_exceed, mean_excess, gpd_shape, gpd_ci_lo, gpd_ci_hi, `stable`.
- `tails_rolling_hill` (k, i, t): gamma, se.
- `tails_thresholds` (k, i): u, u_star, n_exceed. Stage `events` reads u_star.

Choices (each is in the module docstring):

1. rdiag's k (count of upper order statistics) is `n_tail` everywhere: columns and the keys `tails.n_tail_grid`, `tails.n_tail_rule`, `tails.n_tail_stability_width`, `tails.rolling_n_tail`.
2. n_tail_star is the middle of the steadiest range of `tails.n_tail_stability_width` counts (rdiag does not say which count of the range).
3. Generalized Pareto fit: maximum likelihood over shape >= `tails.gpd_shape_min` (-0.5), by a search with no starting point. rdiag names neither a bound nor a method, and below -1 the likelihood is unbounded.
4. The interval the stability rule reads is the profile-likelihood interval (`tails.gpd_ci`), not estimate +/- z se: at 5, 10 and 30 exceedances the latter covers the true shape 29%, 51% and 76% of the time, the profile interval 99%, 96% and 91% (simulated in the tests).
5. A threshold with fewer than `tails.min_exceed` (3, rdiag's n_exceed >= 3) exceedances is not fitted and takes no part in the rule. At P = 98 that is the 0.98 quantile (2 exceedances).
6. Rows that cannot be measured get nulls and do not stop the build (rdiag raises): gamma where the (n_tail + 1)-th largest value is 0, u_star where no threshold has enough exceedances.
7. `tests/stages/test_grid.py` line 167 asserted that compare is the last stage; it now reads positions 8:10, so later stages can follow. One line, no stage 1-10 code touched. The other tracks will meet the same line.

On spec 0 (54 x 14 rows, P = 98): 11,340 + 21,924 + 74,088 + 756 rows, 1.9 s. 600 of 756 rows take the lowest grid quantile (0.70), so their threshold is the 70th percentile of |resid| and 30 of 98 months exceed it; the rule has too few exceedances to move. 5,324 of 21,168 fits sit on the shape bound. Question for Adrian (default: rdiag's grid from 0.70): raise the grid's floor?

Shared helpers other test files import from `tests/stages/test_tails.py`: `grid_frames(R)` (grid tables for a synthetic field), `three_series_grid(cfg)`, `fixture_build(cfg)` (one cached build of the one-series fixture), `changed(frames, k, factor)`.

## B2 `events` (rdiag s3.events)

Files: `src/rattractor/stages/events.py`, `schemas/events_flags.yaml`, `tests/stages/test_events.py`, keys `events.kinds: [residual]` and `events.residual: tails_threshold`. Written to `builds/<id>/events/flags.parquet`.

- `events_flags` (k, kind, i, t): event = |resid| > the row's own u_star (strict), sign = sign of resid at every month, defined = the row has a threshold.
- Only `residual` can be named in `events.kinds`; `band_power` and `persistence` are refused by the config until their sources exist. The schema's `kind` category already lists all three.
- rdiag's coordinate f is the column `kind`.

On spec 0: 74,088 rows, 21,526 events, 7 to 30 per row (median 30), every row defined.

## B3 `coincidence`: design, nothing written yet

- Table `coincidence_precursor`, key (k, kind_a, i_a, kind_b, i_b, delta_min, delta_max); columns n_events_a, n_eligible_a, rate, n_surrogates, p_value. File `coincidence/precursor.parquet`.
- Keys: `coincidence.windows` (list of [delta_min, delta_max]; default [0,0]..[12,12] plus [0,2]), `coincidence.direction: precursor`, `coincidence.null: enumerate | draw`, `surrogates.n_coincidence: 1000`.
- Rate: share of a's eligible events at t with at least one b event in [t + delta_min, t + delta_max]. An a-event is eligible when the whole window lies inside the sample and b is defined on all of it (rdiag's "counting only t where b is defined", extended to the sample end because windows now reach 12 months). Rows only where n_eligible_a > 0.
- Null: b's (event, defined) series circularly shifted, `surrogates.shift`. Default `enumerate`: every admissible offset once (m + arange(`surrogates.n_distinct`)), p = (1 + #{rate_o >= rate}) / (1 + D), compared as integers (hits_o x n >= hits x n_o). `draw` weights each offset by its count among `surrogates.offsets(cfg, "coincidence", P, B, k, i_b)`.
- Why enumerate: on spec 0 only 75 offsets exist, so the smallest honest p is 1/76 = 0.0132; 1,000 draws would report 1/1001. At 0.0132 no Benjamini-Yekutieli family larger than 3 tests can yield a discovery at q = 0.10. To report.
- Per k: stack E shifted by every offset, cumulative sums give window counts, one matrix product per window gives hits and eligible counts for all ordered pairs. Do not edit `common/surrogates.py`.
- Tests to write: planted lag L (rate 1 at [L, L], p = 1/(1 + D), reverse not significant, other lags near the base rate); independent series reject at about the nominal rate; a brute-force loop version on a small case; draw mode against `surrogates.offsets` and `shift`; undefined months; archive rule; added series leave existing pairs unchanged; one-series input gives a valid empty table; check rules.

## Environment

From the worktree's `residual-attractor/`: `PY=/home/radar-41-0/Documents/Data_Retrival/residual-attractor/.venv/bin/python`, `PYTHONPATH=$PWD/src $PY -m pytest`, and `PYTHONPATH=$PWD/src $PY -m rattractor.cli build spec0_spring_adan7406.yaml --root <scratch dir>` (a worktree has no `builds/`).
