# Track B progress: who leads, by events

Branch `claude/ra-tails-coincidence-4bf46d` (worktree `ra-tails-coincidence-4bf46d`), from `3eb8984`. Brief: `docs/WORK_PACKAGES.md`, Track B. Nothing is pushed or merged.

## State

| Package | Stage | State |
|---|---|---|
| B1 | `tails` | built, tested, in the build (`35e9e0a`) |
| B2 | `events` | built, tested, in the build (`ed90503`) |
| B3 | `coincidence` | built, tested, in the build |

Suite: 384 passed, 1 expected failure (268 baseline + 53 tails + 20 events + 43 coincidence). Spec 0 builds with `tails`, `events`, `coincidence` in `stages_passed` (build `85d595e8961b566c` from `da76690`); 87 of the 88 earlier artifacts are byte-identical to build `171464ad5372997a` (the other is provenance, which holds the build id), and the six new artifacts repeat byte for byte across two builds.

Checked so far:

- **Planted bugs**, in a scratch copy (scripts in the notes folder, `track_b/`): 112 planted (88, then 24 subtler ones and weakened acceptance rules), 110 caught. With each stage's own acceptance check switched off inside `run()`, the tests alone still caught all 82 stage bugs of the first batch. The two not caught: an estimate exactly on an interval's upper end (a test case now covers it), and the branch of `gpd_fit` that looks for the interval's upper end past the search grid's last point, which no test reaches and which 80,000 simulated fits and six extreme ones never reached either. That branch is an untested safeguard.
- **Degenerate and short inputs** run clean with warnings as errors: all-zero rows, heavy ties, values over 16 decades, P from 25 to 60.

**Not done** (the session hit its usage limit twice):

1. The second, independently written recomputation of a sample of spec 0. An agent was writing it from the module docstrings alone; its unfinished scripts are in the session scratchpad under `recompute/` (`tails_own.py`) and nothing from it has been compared yet.
2. The baseline build time. Measured alone on spec 0: tails 1.9 to 2.1 s, events 0.02 s, coincidence 0.4 s; the whole build took about 12 s against the 9 s the brief states, not yet timed back to back with the base commit.
3. The section 8 report. The views behind it are `view_spec0.py` and `view_april.py` in the notes folder; their numbers are below.

Views on spec 0 (for a person, not artifacts):

- Coincidence: 16,705 of 137,592 tests have p <= 0.05 (12.1%) and 11,965 sit on the floor 1/76 (8.7%; chance is at most 1.3%).
- AR rows: the 29 AR configurations are 53.7% of the tests and hold 80.6% of those on the floor (13.0% of AR tests against 3.7% for Holt and 3.5% for SES), flat from lag 0 to lag 12: drift puts every AR row's events in the same years.
- SES and Holt: the share on the floor falls with the lag, 9.2% at lag 0, 6.3%, 5.7%, 3.9% at lags 1 to 3, and about 1% (chance) from lag 8 on.
- April 2020 is an event in 379 of 756 rows (72% of SES, 70% of Holt, 32% of AR rows). Without its events, 70% of the SES and Holt tests on the floor stay there (98.8% for AR); without March to June 2020, about half.
- The floor: with 75 shifts no p is below 0.0132. Benjamini-Yekutieli at q = 0.10 finds nothing when the family is all tests, one configuration, or one configuration and window; it finds 8,678 tests when the family is one ordered pair's 14 windows inside one configuration. The family decides everything.
- The four twin configurations (38, 42, 46, 50) repeat the rows of 1, 3, 5, 7 exactly.

## Shared files, as the three tracks agreed in the notes folder

- `build.py`: one block after compare's writes, inside the `try`, with its own `from .stages import coincidence, events, tails` and ending in `track_b = {...}`; `**track_b,` after `"compare": compare_info,` and `*track_b` inside `stages_passed`. Tracks A and C use `track_a` and `track_c` the same way.
- `config.py`: one block right before `return cfg`.
- `configs/default.yaml`: one block after `surrogates.scope` (Track C's is at the same place, Track A's at the end). `schemas/config.yaml`: one block at the end.
- `tests/stages/test_build.py`: the expected stage list, and three lines on the artifacts.
- `tests/stages/test_grid.py` line 167: `[-2:]` became `[8:10]`, the same wording as Tracks A and C, so that line merges without a conflict.

## B1 `tails` (rdiag s2d, every configuration's row on its own)

Files: `src/rattractor/stages/tails.py`, `schemas/tails_{hill_curve,mean_excess,rolling_hill,thresholds}.yaml`, `tests/stages/test_tails.py`, config keys `tails.*`. Written to `builds/<id>/tails/`.

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

On spec 0 (54 x 14 rows, P = 98): 11,340 + 21,924 + 74,088 + 756 rows, about 2 s. 600 of 756 rows take the lowest grid quantile (0.70), so their threshold is the 70th percentile of |resid| and 30 of 98 months exceed it; the rule has too few exceedances to move. 5,324 of 21,168 fits sit on the shape bound.

Shared helpers other test files import from `tests/stages/test_tails.py`: `grid_frames(R)` (grid tables for a synthetic field), `three_series_grid(cfg)`, `fixture_build(cfg)` (one cached build of the one-series fixture), `changed(frames, k, factor)`.

## B2 `events` (rdiag s3.events)

Files: `src/rattractor/stages/events.py`, `schemas/events_flags.yaml`, `tests/stages/test_events.py`, keys `events.kinds: [residual]` and `events.residual: tails_threshold`. Written to `builds/<id>/events/flags.parquet`.

- `events_flags` (k, kind, i, t): event = |resid| > the row's own u_star (strict), sign = sign of resid at every month, defined = the row has a threshold.
- Only `residual` can be named in `events.kinds`; `band_power` and `persistence` are refused by the config until their sources exist. The schema's `kind` category already lists all three.
- rdiag's coordinate f is the column `kind`.

On spec 0: 74,088 rows, 21,526 events, 7 to 30 per row (median 30), every row defined.

## B3 `coincidence` (rdiag s3.coincidence, inside each configuration)

Files: `src/rattractor/stages/coincidence.py`, `schemas/coincidence_precursor.yaml`, `tests/stages/test_coincidence.py`, keys `coincidence.windows`, `coincidence.direction`, `surrogates.n_coincidence`. Written to `builds/<id>/coincidence/precursor.parquet`.

- `coincidence_precursor` (k, kind_a, i_a, kind_b, i_b, delta_min, delta_max): n_events_a, n_eligible_a, rate, n_surrogates, p_value. One row per ordered pair of event series of one configuration and per window; each window is its own test with its raw p-value.
- `coincidence.windows` replaces rdiag's `delta_min` / `delta_max`: the single lags [0, 0] to [12, 12] and rdiag's [0, 2].
- Eligibility: an event of a counts when its whole window lies inside the sample and b is defined on all of it. rdiag says "counting only t where b is defined" and nothing about the sample's end; with windows up to a year that decides the rate. Rows exist where n_eligible_a > 0.
- Null: b's events and defined, shifted together by `surrogates.shift`. When `surrogates.n_coincidence` (1000) is at least the number of offsets that exist, every offset is used once; otherwise that many are drawn per follower row by `surrogates.offsets(cfg, "coincidence", P, n, k, i_b)`. Track A's coherence uses the same rule with `surrogates.n_coherence`.
- p = (1 + #{surrogate rate >= rate}) / (1 + n_surrogates), rates compared as whole numbers. A surrogate under which a has no eligible event is not counted.
- `common/surrogates.py` is untouched: the list of offsets is `min_offset + arange(n_distinct)`.

On spec 0: 137,592 rows (54 x 182 ordered pairs x 14 windows, every test possible), 0.4 s. All 75 offsets enumerated, so p moves in steps of 1/76 and is never below 0.0132.

## Environment

From the worktree's `residual-attractor/`: `PY=/home/radar-41-0/Documents/Data_Retrival/residual-attractor/.venv/bin/python`, `PYTHONPATH=$PWD/src $PY -m pytest`, and `PYTHONPATH=$PWD/src $PY -m rattractor.cli build spec0_spring_adan7406.yaml --root <scratch dir>` (a worktree has no `builds/`).
