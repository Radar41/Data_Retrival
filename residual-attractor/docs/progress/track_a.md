# Track A progress: who leads, by phase

Branch `claude/ra-wavelet-coherence-1ef86c` (worktree), cut from `3eb8984`. Brief: `docs/WORK_PACKAGES.md`, Track A. Nothing is pushed or merged.

## State

| Package | Stage | State |
|---|---|---|
| A1 | `wavelet` | built, tested, committed |
| A2 | `spectral` | next |
| A3 | `coherence` | not started |
| A4 | `adjacency` | not started |

Tests: 302 pass, 1 expected failure (268 + 34 in `tests/stages/test_wavelet.py`). Spec 0 builds in 10 s (9 s before) with `wavelet` in `stages_passed`.

## A1, `wavelet`

Files: `src/rattractor/common/wavelets.py`, `src/rattractor/stages/wavelet.py`, `schemas/wavelet_{scale,series,red_noise,cwt}.yaml`, `tests/stages/test_wavelet.py`, nine `wavelet.*` config keys.

| Artifact | Key | Rows on spec 0 |
|---|---|---|
| `wavelet/scale.parquet` | j | 33 (periods 2 to 32 months, 8 per octave) |
| `wavelet/series.parquet` | k, i | 756 |
| `wavelet/red_noise.parquet` | k, i, j | 24,948 |
| `wavelet/cwt.parquet` | k, i, j, t | 2,444,904 (97 MB) |

Choices (each is in the module docstring):

- Every (k, i) row is transformed on its own, centred on its own mean.
- Torrence and Compo's Fourier-space algorithm, zero padded to a power of two at or above P + 6 e-folding times of the largest scale (512 at P = 98).
- Unit energy is exact on the discrete grid, so white noise has mean power 1 at every scale. Torrence and Compo's continuous factor gives 0.55 at period 2.
- `in_coi` keeps rdiag's meaning: true = at least √2 × scale from both ends. Cells where it is false are kept, flagged and never counted.
- `wavelet_scale` has no `k`: it follows from P and the config only.
- rdiag's `s2a.complex` is the holonomy cell complex (needs adjacency edges). Not built; the complex coefficients are `w_re`, `w_im`, with amplitude and phase beside them.
- A constant row stops the build with its (k, i).

## For the merge

- `src/rattractor/build.py`: one block after compare (it imports its stages itself), plus two adjacent lines in the manifest: `**track_a,` and `*track_a` at the end of `stages_passed`.
- `src/rattractor/config.py`: one block before `return cfg` in `validate_config`.
- `configs/default.yaml`, `schemas/config.yaml`: one block at the end.
- `tests/stages/test_build.py`: the expected `stages_passed` list.
- `tests/stages/test_grid.py` line 167: `[-2:]` became `[8:10]`, because stages now follow compare. Tracks B and C need the same one-line change.

## How to continue

Environment: `docs/WORK_PACKAGES.md` section 4. The test helpers every Track A test module shares are at the top of `tests/stages/test_wavelet.py` (`make_grid`, `subgrid`, `ar1_rows`, `assert_other_configurations_identical`, `assert_frames_equal_under_reindexing`, `fixture_build`, `three_series_grid`).
