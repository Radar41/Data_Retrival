# Track B progress: who leads, by events

Branch `claude/ra-tails-coincidence-4bf46d` (worktree `ra-tails-coincidence-4bf46d`), from `3eb8984`. Brief: `docs/WORK_PACKAGES.md`, Track B. Nothing is pushed or merged.

## State

| Package | Stage | State |
|---|---|---|
| B1 | `tails` | built, tested, in the build |
| B2 | `events` | next |
| B3 | `coincidence` | after B2 |

## B1 `tails` (rdiag s2d, every configuration's row on its own)

Files: `src/rattractor/stages/tails.py`, `schemas/tails_{hill_curve,mean_excess,rolling_hill,thresholds}.yaml`, `tests/stages/test_tails.py`, config keys `tails.*`, one block each in `build.py`, `config.py`, `test_build.py`. Written to `builds/<id>/tails/`.

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
7. `tests/stages/test_grid.py` line 167 asserted that compare is the last stage; it now reads positions 8:10, so later stages can follow. One line, no stage 1-10 code touched.

On spec 0 (54 x 14 rows, P = 98): 11,340 + 21,924 + 74,088 + 756 rows, 1.9 s. 600 of 756 rows take the lowest grid quantile (0.70), so their threshold is the 70th percentile of |resid| and 30 of 98 months exceed it; the rule has too few exceedances to move. 5,324 of 21,168 fits sit on the shape bound.

Shared helpers other test files import from `tests/stages/test_tails.py`: `grid_frames(R)` (grid tables for a synthetic field), `three_series_grid(cfg)`, `fixture_build(cfg)` (one cached build of the one-series fixture).

## Environment

From the worktree's `residual-attractor/`: `PY=/home/radar-41-0/Documents/Data_Retrival/residual-attractor/.venv/bin/python`, `PYTHONPATH=$PWD/src $PY -m pytest`, and `PYTHONPATH=$PWD/src $PY -m rattractor.cli build spec0_spring_adan7406.yaml --root <scratch dir>` (a worktree has no `builds/`).

## Next

B2 `events`: `events.kinds: [residual]`, table `events_flags` (k, kind, i, t): event = |resid| > u_star of the row, sign, defined. Then B3 `coincidence`: precursor rate per ordered pair and window inside each configuration, `coincidence.windows`, circular-shift p-value.
