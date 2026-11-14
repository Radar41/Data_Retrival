# Work packages: the cross-series analyses, split into sessions

Written 2026-11-13 at the end of the chat that built stages 1–10 (see [`REPORT_2026-11-13.md`](REPORT_2026-11-13.md)). Each track below is one session in its own git worktree and branch. A session needs nothing from that chat: everything it needs is in this file, the files it points to, and the code.

Paths are relative to `residual-attractor/` unless they start with `/` or `docs/PLAN`.

## 1. Read first, in this order

1. Sections 2–4 of this file, then your track in section 5.
2. `README.md`: what every stage does and the choices made.
3. `docs/PLAN_residuals_to_relationship_graph.md` (repository root), sections 0 and 5: the rules and the rdiag rework.
4. `src/rattractor/stages/compare.py`, `tests/stages/test_compare.py` and the compare block in `src/rattractor/build.py`: the pattern for a stage that reads the grid.
5. rdiag's text for your stage (section 4 says where it is and how to read it).

## 2. Rules for every session

**The archive rule (Adrian, binding).** Every configuration's residuals for every series are kept one by one. Nothing fuses, pools, averages or weights across configurations. For these stages that means:

- The configuration index `k` is in every key of every table. An analysis runs on configuration k's rows alone.
- Cross-series work (a pair of series, a correlation matrix over series) happens inside one configuration.
- No table holds a value computed from more than one configuration, and no stage picks a "best" configuration. Views for a person come afterwards and are not artifacts.
- Twins (Holt with β = 0 and SES) are ordinary configurations here: analyse each one. They only need marking where two configurations meet in one test.
- Test it: changing configuration k′'s residuals must leave every row with k ≠ k′ bit-identical.

**The machinery rules** (plan section 0).

- Indices, not names. No stage reads `grid_names`, and none branches on a method name or a series id.
- Nothing depends on counts. Adding a series or a configuration must not change the rows of the others. The fixture has one series: a cross-series stage must write valid empty or null output there, not fail.
- Every tunable number is a config key: `configs/default.yaml`, typed in `schemas/config.yaml`, cross-key rules in `src/rattractor/config.py`. No defaults in code. Take key names and values from rdiag's `config/params.yaml` (`wavelet.omega0`, `common_mode.window`, ...).
- Randomness comes only from `rattractor.common.seeds.stream(cfg, stage, *keys)`.
- Surrogates come only from `rattractor.common.surrogates`: `offsets(cfg, purpose, P, n_draws, k, *unit)`, `shift(x, offset)`, `n_distinct(cfg, P)`. On spec 0 (P = 98, minimum offset 12) only 75 different offsets exist, so a test that shifts one row has at most 75 different surrogates. Say what that does to your p-values; enumerating every offset is exact and cheaper than drawing 1,000.

**Inference.** Store every raw p-value with the keys of the unit it tests. Where a stage's own rule needs a decision (adjacency's edge rule), decide within one configuration and say so in a column. The false-discovery stage comes later and reads your tables; do not build a registry.

**Scope.**

- Do not change stages 1–10 or their artifacts. If you find a bug there, fix it in its own commit with a test that fails without the fix, and say so in your report.
- No new dependencies. Installed: numpy, scipy, pandas, pyarrow, pyyaml, psycopg. Not installed: pywt, statsmodels, sklearn, torch, duckdb, networkx, ripser, gudhi.
- Touch only `residual-attractor/`. Do not edit `README.md`'s State section or the plan: write `docs/progress/track_<letter>.md` instead and the merge folds it in.
- Commit on your own branch after each package. Never push, never merge, never run `git add -A`.
- rdiag is a downloaded archive: read it as text, never import or run it.
- The FRED key is not needed (the data is in PostgreSQL). Never search for it or print it.

**What the data will do to you.** Run spec 0 reads every series in levels, and on levels the 29 AR configurations carry drift, not shocks (two thirds of their standardized residuals lie beyond 2σ). April 2020 is the largest loss on a fifth of all configuration-series rows (a quarter in first differences). Do not correct for either: build the method as specified, then say in your report how much of what you see sits on the AR rows and on April 2020.

## 3. How a stage is built here

- **Module** `src/rattractor/stages/<stage>.py`. The docstring states the formulas, what is read and written, the rdiag source and every departure from it. `run(...)` returns `(frames, info)`: a dict of data frames and a dict for the manifest. `check(...)` raises `AcceptanceError(stage, message, rows)` with the failing rows.
- **Schemas** `schemas/<stage>_<table>.yaml`, written to `builds/<id>/<stage>/<table>.parquet`. Build frames only with `contracts.from_columns(columns, artifact)`. Dtypes: int8, int16, int32, float32, float64, string, bool, boolean, category, Int16, datetime64[ns], list[float32] (one length per artifact), list[int16], list[string].
- **Keys** `k` (int32), `i` (int32), `t` (month start, datetime64[ns]), exactly as in `grid_resid`.
- **Build wiring** in `src/rattractor/build.py`, one block after compare: set `stage`, run, write each frame, add `info` to the manifest, add the stage name to `stages_passed` (and to the expected list in `tests/stages/test_build.py`). Keep every edit to a shared file in one contiguous block; the tracks merge one after another and these are the only places they meet.
- **Tests** `tests/stages/test_<stage>.py`:
  - known answers on synthetic input with planted structure (each track lists its minimum);
  - one test per acceptance rule, failing when its bug is planted;
  - the archive-rule and count-independence tests from section 2;
  - a multi-series build (`tests/stages/test_grid.py` has `three_series`) and the one-series fixture build.
- **Check your own work** before reporting: recompute a sample of spec 0's output with a second, independently written implementation, and plant bugs in the stage to see that the tests catch them.
- **Baseline** at the commit this file arrived in: 268 tests pass plus 1 expected failure, in about 20 seconds; spec 0 builds in 9 seconds. Report the time your stage adds. If it adds more than a few minutes, say so and name the exact cheaper form; never cut draws silently.

## 4. Environment

A worktree has no `.venv`, no `builds/` and no `downloads/` (all untracked). From the worktree's `residual-attractor/`:

```
PY=/home/radar-41-0/Documents/Data_Retrival/residual-attractor/.venv/bin/python
PYTHONPATH=$PWD/src $PY -c "import rattractor; print(rattractor.__file__)"   # must print a path inside the worktree
PYTHONPATH=$PWD/src $PY -m pytest
PYTHONPATH=$PWD/src $PY -m rattractor.cli build fixture_six_regime.yaml
PYTHONPATH=$PWD/src $PY -m rattractor.cli build spec0_spring_adan7406.yaml   # needs PostgreSQL `fred` over the local socket
```

- **rdiag as text:** `unzip -p /home/radar-41-0/Documents/Data_Retrival/downloads/residual_diagnostic.zip residual_diagnostic/<path>`. Useful paths: `config/params.yaml`, `schemas/20_stage2.yaml`, `schemas/30_stage3.yaml`, `schemas/40_inference.yaml`, `contracts/conventions.md`, `db/RECONCILIATION.md`, `WHY.md`, and each stub's docstring under `src/rdiag/` (`s2_transforms/`, `s3_cooccurrence/`, `common/`). The stubs raise `NotImplementedError`; their docstrings are the specification.
- **rdiag under v2:** wherever rdiag says "fused row", read "each configuration's own row", and add `k` to the key.
- **A finished build to read** (read-only): `/home/radar-41-0/Documents/Data_Retrival/residual-attractor/builds/171464ad5372997a/`. The input field is `grid/resid.parquet` (k, i, t, resid): 54 × 14 × 98.

## 5. Wave 1: three tracks, started together

Each track's packages run in order. After each package: tests green, spec 0 builds, commit, and update `docs/progress/track_<letter>.md` (what is built, choices made, what is next), so a fresh session could continue from the file alone.

### Track A: who leads, by phase (branch slug `ra-wavelet-coherence`)

Plan section 5, step 2. The first cross-series lead-lag evidence.

| Package | Stage name | rdiag source | Writes, per configuration |
|---|---|---|---|
| A1 | `wavelet` | `s2a.cwt`, `s2a.complex`; `common/wavelets.py`; params `wavelet` | Morlet transform of each (k, i) row: power, cone of influence, red-noise significance, amplitude and phase |
| A2 | `spectral` | `s2b.global_spectrum`, `s2b.bands`, `s2b.band_power`, `s2b.dominant_period`; params `spectral_summary` | global spectrum, data-driven bands, band power, dominant period |
| A3 | `coherence` | `s3_cooccurrence/coherence.py`; params `coherence`, `surrogates.n_coherence` | wavelet coherence and relative phase for every pair of series (91 pairs × 54 configurations on spec 0), with surrogate significance; lead-lag in months = phase × period / 2π |
| A4 | `adjacency` | `s3_cooccurrence/adjacency.py`; params `adjacency`, `inference` | per band: edge weight, binomial p-value, edge decision within the configuration |

- Shared code: `src/rattractor/common/wavelets.py`, and `common/fdr.py` (Benjamini-Yekutieli) for A4. Surrogate purpose: `"coherence"`, unit `(i_a, i_b)` with i_a < i_b, shifting only the higher-indexed row.
- Bands: if rdiag derives one band set from several rows, derive one per configuration from that configuration's rows. Never across configurations.
- Known answers, at least:
  - a sinusoid of period p puts its power peak at the scale whose Fourier period is p; white noise has mean normalized power 1 at every scale;
  - two series sharing a cycle, the second L months behind the first, plus independent noise: coherence near 1 in that band, the phase returns L with the stated sign, and swapping the series flips the sign;
  - independent red-noise rows: about 5% of cells flagged at the 0.95 level, and edges kept at about the nominal rate;
  - cells inside the cone of influence are flagged and never counted.

### Track B: who leads, by events (branch slug `ra-tails-coincidence`)

Plan section 5, step 3. The second kind of co-movement evidence: events in one series followed by events in another.

| Package | Stage name | rdiag source | Writes, per configuration |
|---|---|---|---|
| B1 | `tails` | `s2d.hill_curve`, `s2d.mean_excess`, `s2d.rolling_hill`, `s2d.thresholds`; params `tails` | tail index curves and each (k, i) row's own threshold |
| B2 | `events` | `s3_cooccurrence/events.py`; params `events` | residual events: months where \|resid\| exceeds the row's threshold |
| B3 | `coincidence` | `s3_cooccurrence/coincidence.py`; params `coincidence`, `surrogates.n_coincidence` | precursor rate and p-value for every ordered pair of series and every scanned window |

- **Name clash:** rdiag's tails use `k` for the number of upper order statistics. Here `k` is the configuration. Rename the count (`n_tail`) everywhere.
- **Event kinds:** rdiag has three (residual, band power, persistence). Build `residual` only, behind a config list `events.kinds`; the other two wait for their sources.
- **The plan's required change:** `coincidence.delta_max` = 2 is too short for supply-chain pass-through. Replace it with a config list of windows `[delta_min, delta_max]`, scanned one by one, each stored as its own test row. Default: the single lags `[0, 0]` to `[12, 12]`, plus rdiag's `[0, 2]`.
- Surrogate purpose: `"coincidence"`, unit `(i,)`, every row its own offset per draw.
- Known answers, at least:
  - exact Pareto samples return their tail index within sampling error; the mean excess of an exponential is flat;
  - events are exactly the months beyond the row's own threshold;
  - events planted L months after another series' events: the precursor rate at `[L, L]` is 1 with the smallest attainable p, the reverse direction is not significant, and other lags sit near the base rate;
  - independent event series reject at about the nominal rate; rows exist only where the leading series has events; 0 < p ≤ 1.

### Track C: are the series being pulled together (branch slug `ra-common-mode`)

Plan section 5, step 4, the part that needs no decision from Adrian. It is the "condensing" measurement.

| Package | Stage name | rdiag source | Writes, per configuration |
|---|---|---|---|
| C1 | `common_mode` | `s3_cooccurrence/common_mode.py`; params `common_mode`, `surrogates.n_common_mode` | per month: eigenvalues of the trailing-window correlation across series, leading eigenvalue with its surrogate band and p-value, Marchenko-Pastur edge as reference, absorption ratio, leading vector and its turnover |
| C2 | `signatures` | `s3_cooccurrence/signatures.py`; params `signatures` | the consolidation flag only: leading eigenvalue above its band and absorption rising, held for `persistence_months` |

- `common/linalg.py` holds the sign rule (leading vector with sum ≥ 0).
- Surrogate purpose: `"common_mode"`, unit `(i,)`, every row shifted independently.
- Build only `consolidation`, behind a config list `signatures.kinds`. Collapse needs ensemble spread, which has no source; collusion needs the Bai-Ng split. Both are Adrian's to decide.
- Known answers, at least:
  - independent rows: the leading eigenvalue leaves its band at about the nominal rate, and eigenvalues sum to N at every defined month;
  - a common factor switched on mid-sample: the leading eigenvalue approaches 1 + (N − 1)ρ, the leading vector loads on the planted series, absorption rises, and consolidation flags after `persistence_months` and not before;
  - turnover is 0 for a fixed structure and near 90° when the factor moves to a disjoint set of series;
  - every per-month value is null before the first full window.

## 6. Wave 2: not started

| Package | Needs first | Waits on Adrian for |
|---|---|---|
| `fdr`: one registry over every p-value table (stage 10's included), Benjamini-Yekutieli per family | tracks A, B, C merged | the family: per configuration or across all (report decision 4) |
| `holonomy` (rdiag `s2a.holonomy`) | track A | nothing; off the relationship path |
| `persistence` (rdiag `s2c`), then the band-power and persistence event kinds | track A for band power | nothing; needs its own Vietoris-Rips code |
| `factors` (Bai-Ng), collapse and collusion signatures | track C | report decisions 6 and 7 |
| Cutoff ladder and `replay` | tracks A, B, C merged | report decision 8 |
| GDSS families and configurations with inputs (plan 1.3, 1.4) | nothing | report decision 2 |
| The relationship graph (plan section 6) | A, B and `fdr` | report decision 9, and Adrian's definitional edges |
| Lag history (plan section 7) | replay and the graph | — |
| The spec's stage 8 (e3nn export) and views | nothing | a torch install |

## 7. Bringing the tracks together

- Nothing merges without Adrian's word. The main session does it, on `fred-catalog-adit2200`, in the order A, B, C.
- After a track merges, the next track's session rebases onto the new tip, resolves the shared-file blocks (keep both sides, in the order compare, wavelet, spectral, coherence, adjacency, tails, events, coincidence, common_mode, signatures), and re-runs the tests and the spec 0 build before it merges.
- The merge then updates `README.md` and the plan from the `docs/progress/` files.

## 8. What a session reports when it finishes

- Commits, one line each.
- Each stage's artifacts and row counts on spec 0, and the build time added.
- Test count, and what the second implementation and the planted bugs showed.
- Every departure from rdiag and why.
- How much of what the stage finds sits on the AR rows and on April 2020.
- Questions for Adrian, each with the default you used.
