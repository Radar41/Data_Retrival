# Track C: are the series being pulled together

Branch `claude/ra-common-mode-9bf224`, cut from `3eb8984`. Brief: `docs/WORK_PACKAGES.md`, Track C. Nothing is pushed or merged.

## State

| Package | Stage | State |
|---|---|---|
| C1 | `common_mode` | built, tested, committed |
| C2 | `signatures` (consolidation only) | not built: a draft module exists outside the repository (see Next), untested and not wired |

Tests: 322 pass, 1 expected failure (baseline 268 + 1). Spec 0 builds in 28 s (baseline 10 s); `common_mode` adds 17 s, nearly all of it 4.05 million 14 × 14 eigenvalue solves for the surrogates.

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

Checked: a second implementation (pandas correlation, scipy's solver, `numpy.roll`, a hand-written quantile) recomputed all 4,050 defined cells of spec 0; 43 planted bugs were all caught by the tests.

## Shared files touched (for the merge)

- `src/rattractor/build.py`: one block after compare's writes, inside the `try`. It imports its own stages and ends with `track_c = {...}`, the manifest entries in stage order. In the manifest literal: `**track_c,` after `"compare": compare_info,` and `*track_c` at the end of `stages_passed` (the form Track A's notes describe for `track_a`).
- `src/rattractor/config.py`: one block before `return cfg` in `validate_config`.
- `configs/default.yaml`: one block after `surrogates.scope`. `schemas/config.yaml`: one block at the end.
- `tests/stages/test_build.py`: the `stages_passed` list in `test_fixture_build_and_manifest` and the lines right after it.
- `tests/stages/test_grid.py`: one assertion that read the last two entries of `stages_passed` now reads entries 8 and 9. Every track that adds a stage breaks the old form.
- Not touched: `README.md`, the plan, `cli.py`, the docstring at the top of `build.py`.

## Next

C2 `signatures`: the consolidation flag from `common_mode_month` (λ1 above its band and absorption rising, held `signatures.persistence_months`), behind `signatures.kinds`. Collapse and collusion are not to be built.

The session that built C1 stopped here (usage limit). Left for C2:

- A draft of `src/rattractor/stages/signatures.py` is in the shared notes folder, `track_c/signatures_draft.py`. It has never been run. Its design: one table `signatures_flag` keyed (k, t, mode, i) with `components` as a JSON string, `available`, `held_months`, `flagged`; "rising" read as higher than the month before; requirement names `lambda1_above_band`, `absorption_rising`.
- Still to write: `schemas/signatures_flag.yaml`, the config keys (`signatures.kinds`, `signatures.consolidation_requires`, `signatures.persistence_months`) with their rules in `config.py`, `tests/stages/test_signatures.py`, the build wiring (add to the Track C block and to `track_c`), the expected stage list in `test_build.py`.
- Still to do for the whole track: an independent recomputation of the signatures output, planted bugs for signatures, and the section 8 report (how much rests on the AR rows and on April 2020; the questions for Adrian).
- Open questions noted so far, each with the default used: turnover as the angle between sign-fixed vectors (0 to π) or between axes (0 to π/2); null rows for one series; linear-interpolated quantile for the band.
- The same notes folder holds the second implementation (`recompute_common_mode.py`), the planted-bug harness and list (`harness.py`, `c1.py`) and the spec 0 view script (`view_spec0.py`).

## Run

```
PY=/home/radar-41-0/Documents/Data_Retrival/residual-attractor/.venv/bin/python
PYTHONPATH=$PWD/src $PY -m pytest
PYTHONPATH=$PWD/src $PY -m rattractor.cli build spec0_spring_adan7406.yaml --root <a scratch folder>
```
