# Track C: are the series being pulled together

Branch `claude/ra-common-mode-9bf224`, cut from `3eb8984`. Brief: `docs/WORK_PACKAGES.md`, Track C. Nothing is pushed or merged.

## State

| Package | Stage | State |
|---|---|---|
| C1 | `common_mode` | built, tested, committed (`de95c25`) |
| C2 | `signatures` (consolidation only) | built, tested, committed (`eca8e9e`) |

Both packages of the track are done. Tests: 351 pass, 1 expected failure (baseline 268 + 1), in 29 s (baseline 21 s). Spec 0 builds in 29 s (baseline 10 s) with both stages in `stages_passed`; `common_mode` adds 18 s, nearly all of it 4.05 million 14 × 14 eigenvalue solves for the surrogates, and `signatures` adds under a second.

## C1: `common_mode`

Code: `src/rattractor/stages/common_mode.py`, `src/rattractor/common/linalg.py`. Tests: `tests/stages/test_common_mode.py`, `tests/unit/test_linalg.py`. The module docstring holds the formulas and every departure from rdiag.

Reads the grid only. For each configuration k on its own, and each month t with a full trailing window of `common_mode.window` months:

| Artifact | Key | Columns | Rows on spec 0 |
|---|---|---|---|
| `common_mode/month.parquet` | k, t | lambda1, lambda1_q, p_value, n_surrogates, mp_edge, absorption_ratio, vector_turnover | 5,292 |
| `common_mode/eigen.parquet` | k, t, r | eigenvalue | 74,088 |
| `common_mode/vector.parquet` | k, t, i | loading | 74,088 |

Every month of the grid has rows; 4,050 of the 5,292 (k, t) are defined on spec 0 (75 months × 54 configurations).

Config keys: `common_mode.window` 24, `common_mode.absorption_top_fraction` 0.2, `common_mode.quantile` 0.95, `surrogates.n_common_mode` 1000 (rdiag's names and values).

Choices made:

- **Null, not a number, where nothing can be correlated**: before the first full window, with one series (the fixture), and where a row is flat over the window. A surrogate draw that brings a flat stretch into the window is left out, and `n_surrogates` says how many draws were counted.
- **The test sits in the table.** `lambda1`, `p_value` and `n_surrogates` are stored beside rdiag's `lambda1_q`, keyed (k, t). p = (1 + #{surrogate λ1 ≥ λ1}) / (1 + n). No registry is written.
- **Band**: `numpy.quantile`, linear interpolation.
- **Turnover** is the angle between the sign-fixed vectors, 0 to π, as rdiag's table has it. A value above π/2 is the sign rule turning over a vector whose loadings nearly cancel; the axis moved by π minus the value.
- **`mp_edge`** is a constant column of the month table (rdiag: a one-row attributes table). It is never used in a rule.
- **Top count** ceil(N × fraction) is computed on the decimal the config states, so 100 × 0.07 gives 7, not 8.
- **Eigenvalues** come from `eigvalsh` for the configuration and for its surrogates alike, so a draw that reproduces the configuration's windows ties with it exactly; `eigh` gives the vector.
- `common/linalg.py` has `corr`, `eigh_desc` (with the sign rule), `mp_edge` and `angle`. rdiag's `principal_angles` is not built: nothing reads it yet.
- **Surrogates and p-values.** Each row has 75 offsets on spec 0, but the 14 rows are shifted independently, so the 1,000 draws of a configuration are all different arrangements and the smallest p is 1/1001. Cost grows with N³ per solve; for N above the window length the w × w product of the same windows has the same leading eigenvalue and would be cheaper (not built).

## C2: `signatures`

Code: `src/rattractor/stages/signatures.py`. Tests: `tests/stages/test_signatures.py`. Reads `common_mode_month` only.

| Artifact | Key | Columns | Rows on spec 0 |
|---|---|---|---|
| `signatures/flag.parquet` | k, t, mode, i | components, available, held_months, flagged | 5,292 |

Config keys: `signatures.kinds` [consolidation], `signatures.consolidation_requires` [lambda1_above_band, absorption_rising], `signatures.persistence_months` 6.

Choices made:

- **Consolidation only.** `signatures.kinds` may hold `consolidation` or nothing; the config refuses `collapse` and `collusion`, which are Adrian's to decide (report decisions 6 and 7).
- **Rising** means higher than the month before. With the persistence rule a flag needs λ1 above its band and the absorption ratio up, six months in a row. rdiag's "rising over persistence_months" could also be read as higher than six months before. Under that reading one shock month that lifts the ratio once keeps the rule true for six months by itself, which the persistence rule exists to prevent; on spec 0 it would flag 245 rows in 41 configurations, against 68 in 26.
- **One table**, rdiag's shape plus k. `components` is a JSON object in a string column (rdiag: a map), with null for an undefined metric. `held_months` is added so the persistence rule can be read and checked from the table. `i` is -1 (all series together).
- **Not available** where a metric the rule reads is undefined: before the first full window, the first defined month (no month before to rise from), one series, a flat row. Such a month ends a run.
- The requirement rdiag names `lambda1_above_q95` is `lambda1_above_band` here, because the band's level is `common_mode.quantile`.
- No registry: a flagged span is a run of flagged months in the table.

## Checked

- **Second implementations**, written apart from the stages. Common mode: pandas correlation, scipy's solver, `numpy.roll`, a hand-written quantile, on all 4,050 defined cells of spec 0: eigenvalues, loadings, absorption and the band agree to 3e-14, turnover to 1e-13, p-values exactly. Signatures: a plain loop over each configuration's months, all 5,292 rows: no mismatch.
- **Planted bugs**: 47 in `common_mode` and `linalg`, 29 in `signatures`, the build wiring and the config rules, one at a time in a scratch copy. The tests caught all 76.
- The scripts are in the shared notes folder of the session group, under `track_c/`.

## What spec 0 shows (views for a person, not artifacts)

Build `5c3be362e7eaa4e6` at `eca8e9e`; 4,050 defined (k, t) cells.

- **Overall.** λ1 is above its band on 1,966 cells (48.5%); 942 of them sit at the smallest p there is, 1/1001.
- **AR rows** (29 of 54 configurations, 2,175 cells). Their λ1 is the largest (median 7.3 of 14), but their band is higher still (median 8.3), because drifting rows correlate at any alignment: they are above the band on 34.9% of cells, against 70.2% for SES and 61.2% for Holt. The Marchenko-Pastur edge (3.11) would call 99.3% of AR cells a common mode. AR rows hold 38.6% of the above-band cells and 13 of the 68 flagged rows.
- **Windows that contain April 2020** (24 of the 75 months, 2020-04 to 2022-03). SES and Holt are above the band on 596 of 600 cells there (median λ1 6.5 against a band of 3.4) and on 612 of 1,275 elsewhere (48.0%). AR shows no difference (34.2% and 35.2%). 42.4% of all above-band cells are in those windows.
- **The one month.** With each row's April 2020 residual replaced by that row's median (a scratch rerun), above-band cells in those 24 months go from 834 to 642 (AR 238 to 84, SES and Holt 596 to 558), and flagged rows from 68 to 27.
- **Consolidation.** 68 flagged rows in 26 configurations (Holt 14, SES 7, AR 5), in 28 runs. 65 of the 68 are in windows that contain April 2020: 18 runs begin in February or April 2020 and are flagged from July or September to October 2020. Three runs are flagged in February 2025.
- **The leading vector** is a contrast far more often than a pull in one direction: every loading has one sign on 4.5% of cells. 136 of 3,996 turnover values exceed π/2, each a sign flip.

## Shared files touched (for the merge)

- `src/rattractor/build.py`: one block after compare's writes, inside the `try`. It imports its own stages and ends with `track_c = {...}`, the manifest entries in stage order. In the manifest literal: `**track_c,` after `"compare": compare_info,` and `*track_c` at the end of `stages_passed` (the form Track A's notes describe for `track_a`).
- `src/rattractor/config.py`: one block before `return cfg` in `validate_config`.
- `configs/default.yaml`: one block after `surrogates.scope`. `schemas/config.yaml`: one block at the end.
- `tests/stages/test_build.py`: the `stages_passed` list in `test_fixture_build_and_manifest` and the lines right after it.
- `tests/stages/test_grid.py`: one assertion that read the last two entries of `stages_passed` now reads entries 8 and 9 (the same wording as Track A).
- Not touched: `README.md`, the plan, `cli.py`, the docstring at the top of `build.py`.

## Next

Nothing in this track. Waiting on Adrian (wave 2): collapse and collusion, the Bai-Ng split, the false-discovery stage that reads `common_mode_month.p_value`, replay.

## Run

```
PY=/home/radar-41-0/Documents/Data_Retrival/residual-attractor/.venv/bin/python
PYTHONPATH=$PWD/src $PY -m pytest
PYTHONPATH=$PWD/src $PY -m rattractor.cli build spec0_spring_adan7406.yaml --root <a scratch folder>
```
