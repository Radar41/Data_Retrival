# Track A progress: who leads, by phase

Branch `claude/ra-wavelet-coherence-1ef86c` (worktree), cut from `3eb8984`. Brief: `docs/WORK_PACKAGES.md`, Track A. Nothing is pushed or merged.

## State

| Package | Stage | State |
|---|---|---|
| A1 | `wavelet` | built, tested, committed |
| A2 | `spectral` | built, tested, committed |
| A3 | `coherence` | DRAFT, uncommitted work saved as a WIP commit: module written, never run; no schemas, no stage tests, not wired |
| A4 | `adjacency` | not started |

Tests: 339 pass, 1 expected failure (268 + 34 wavelet + 37 spectral). Spec 0 builds in 10.5 s (9 s before) with `wavelet` and `spectral` in `stages_passed`.

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

## A2, `spectral`

Files: `src/rattractor/stages/spectral.py`, `schemas/spectral_{global,bands,band_count,band_power,dominant}.yaml`, `tests/stages/test_spectral.py`, five `spectral_summary.*` config keys.

| Artifact | Key | Rows on spec 0 |
|---|---|---|
| `spectral/global.parquet` | k, i, j | 24,948, each with its raw p-value |
| `spectral/bands.parquet` | k, i, band | 488 |
| `spectral/band_count.parquet` | k, i | 756 |
| `spectral/band_power.parquet` | k, i, band, t | 47,824 |
| `spectral/dominant.parquet` | k, i, t | 74,088 |

Choices:

- Bands are per (k, i) row, from that row's own spectrum against its own AR(1) reference. Never across configurations, never across series.
- `p_value` per (k, i, j) is stored raw (rdiag registers these tests in its registry).
- `spectral_summary.dj0_decorrelation` (0.60, Torrence and Compo's δj0) is a new key: rdiag cites their eq. 26 for the band-power level and leaves the factor implicit.
- On pure red noise about a third of rows get a band by chance (two adjacent scales at 5% each, and neighbouring scales are correlated). That is rdiag's rule; the false-discovery stage is what controls it.

## A3, `coherence`: where it stopped (session hit its usage limit on 2026-11-13)

Done: `coherence.*` and `surrogates.n_coherence` config keys; the smoothing kernels in `common/wavelets.py` (`smoother`, `smooth`, `scale_weights`) with one test in `tests/stages/test_coherence.py`; a full draft of `src/rattractor/stages/coherence.py` that has **never been run**.

Still to do, in order:

1. Schemas `schemas/coherence_cells.yaml` (k, i_a, i_b int32; j int16; t; r2, phase, r2_q float64; in_coi, significant bool; key k, i_a, i_b, j, t) and `schemas/coherence_scope.yaml` (k, i_a, i_b int32; band_a, band_b, j_lo, j_hi int16, with -1/-1 = all scales; n_cells, n_significant, n_surrogates int32; r2_mean, p_value, phase, period, lag_months nullable float64; key k, i_a, i_b, band_a, band_b).
2. Run the draft on a small grid, then on spec 0 (expected about a minute: 4,914 pairs x 76 fields; 15.9 M cell rows, roughly 400 MB).
3. Wire into `build.py` (`coherence.run(frames, wav, spec_frames, cfg)`, files under `coherence/`), add to `track_a` and to the expected list in `test_build.py`.
4. Tests: planted delay (sign, and the swap flips it), independent red noise (about 3.9% of in-cone cells at P = 98, never above 5%), cone, archive rule, count independence, every check rule, one-series fixture (empty tables), round trip, config validation.

Design decisions already taken (all in the draft's docstring):

- Surrogates shift only the higher-indexed row. When `surrogates.n_coherence` >= the offsets that exist (75 on spec 0) every offset is used once; p-values then step by 1/76.
- `r2_q` is the r-th largest surrogate value, r = floor((1 - quantile)(n + 1)), not an interpolated quantile, so a cell's null rate never exceeds 1 - quantile.
- The (pair, band) test rdiag names without a statistic: mean r2 over the scope's in-cone cells against the same on every surrogate. Scopes: all scales, plus each overlap of the two rows' own bands.
- Lag in months = phase x period / 2 pi, stored per scope (circular mean phase and geometric mean period of the significant cells). Positive: i_a leads.
- A shared deterministic cycle is coherent under every shift, so it is not significant: test significance with a shared stochastic component.

## A4, `adjacency`: not started. Planned design

- Reads `coherence_scope` (+ `wavelet_scale`). weight = n_significant / n_cells; expected = 1 - coherence.quantile.
- Effective n: (scales in scope / 4.8, at least 1) x mean over scales of (in-cone months / (sqrt(2 pi) x scale), at least 1). p = I_expected(x, n_eff - x + 1), x = weight x n_eff (the binomial tail for real n).
- Benjamini-Yekutieli in `common/fdr.py`, within one configuration, two families (all-scales rows; band rows), named in a `family` column, with `family_size`, `q_value`, `edge` = q_value <= inference.q.
- Keys still to add: `adjacency.edge_weight`, `adjacency.edge_rule`, `adjacency.per_band`, `inference.cooccurrence_family_method`, `inference.q`.

After A4: second independent implementation on a sample of spec 0, planted bugs, the AR-rows and April 2020 shares, then the section 8 report. None of that has been done.

## For the merge

- `src/rattractor/build.py`: one block after compare (it imports its stages itself), plus two adjacent lines in the manifest: `**track_a,` and `*track_a` at the end of `stages_passed`.
- `src/rattractor/config.py`: one block before `return cfg` in `validate_config`.
- `configs/default.yaml`, `schemas/config.yaml`: one block at the end.
- `tests/stages/test_build.py`: the expected `stages_passed` list.
- `tests/stages/test_grid.py` line 167: `[-2:]` became `[8:10]`, because stages now follow compare. Tracks B and C need the same one-line change.

## How to continue

Environment: `docs/WORK_PACKAGES.md` section 4. The test helpers every Track A test module shares are at the top of `tests/stages/test_wavelet.py` (`make_grid`, `subgrid`, `ar1_rows`, `assert_other_configurations_identical`, `assert_frames_equal_under_reindexing`, `fixture_build`, `three_series_grid`).
