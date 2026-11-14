# Track A progress: who leads, by phase

Branch `claude/ra-wavelet-coherence-1ef86c` (worktree), cut from `3eb8984`. Brief: `docs/WORK_PACKAGES.md`, Track A. Nothing is pushed or merged.

## State

| Package | Stage | State |
|---|---|---|
| A1 | `wavelet` | built, tested, committed |
| A2 | `spectral` | built, tested, committed |
| A3 | `coherence` | built, tested, committed |
| A4 | `adjacency` | not started |

Tests: 391 pass, 1 expected failure (268 + 34 wavelet + 37 spectral + 52 coherence). Spec 0 builds in 70 s (10.5 s before coherence, 9 s before Track A) with `wavelet`, `spectral`, `coherence` in `stages_passed`.

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

## A3, `coherence`

Files: `src/rattractor/stages/coherence.py`, the smoothing kernels in `common/wavelets.py`, `schemas/coherence_{cells,scope}.yaml`, `tests/stages/test_coherence.py`, keys `coherence.*` and `surrogates.n_coherence`.

| Artifact | Key | Rows on spec 0 |
|---|---|---|
| `coherence/cells.parquet` | k, i_a, i_b, j, t | 15,891,876 (397 MB): r2, phase, r2_q, in_coi, significant |
| `coherence/scope.parquet` | k, i_a, i_b, band_a, band_b | 5,704: 4,914 all-scales rows and 790 band overlaps, each with its raw p-value and lag in months |

`coherence.run` takes 43 s on spec 0 (4,914 pairs x 76 fields), peak memory 4.3 GB.

Choices (each is in the module docstring):

- Surrogates shift only the higher-indexed row. 1000 draws are asked for but only 75 offsets exist at P = 98, so each is used once; p-values step by 1/76.
- `r2_q` is the r-th largest surrogate value, r = floor((1 - quantile)(n + 1)) = 3 of 75, not an interpolated quantile.
- The (pair, band) test rdiag names without a statistic: mean r2 over the scope's in-cone cells against the same on every shift. Scopes: all scales (band_a = band_b = -1), plus each overlap of the two rows' own bands.
- Lag in months = phase x period / 2 pi, per scope (circular mean phase and geometric mean period of the significant cells). Positive: i_a leads.
- The cross-spectrum is formed so that taking a pair the other way round gives the same r2 and the negated phase, bit for bit.
- A shared deterministic cycle is coherent under every shift, so it is not significant (tested as a property).

Finding to report (measured, pinned by two tests): rdiag's minimum shift of 12 months makes the null too easy to beat on unrelated rows. On independent AR(1) rows (14 series, P = 98): 7.7% of in-cone cells are significant (5% at the shortest periods, 12 to 15% at the longest) against the rule's 3.9%, and the smallest p-value (1/76) turns up for 7% of pairs. With every nonzero shift in the null (min offset 1) the same code gives 4.2% against 4.1% and 1.1% against 1.0%, so the code is exact and the cause is the excluded neighbourhood. Nothing corrects for it. Question for Adrian; default used: rdiag's 12.

Spec 0, first look: all-scales share of significant cells averages 0.157 (0.077 on unrelated rows); 33% of pairs sit at the smallest p-value (7% on unrelated rows). By method: AR 0.146, Holt 0.169, SES 0.171.

## A4, `adjacency`: not started. Design, revised after measuring

- Reads `coherence_scope` (+ `wavelet_scale`). weight = n_significant / n_cells; expected = 1 - coherence.quantile.
- Effective n: the Kish count of smoothing footprints, n_eff = max(1, n_cells^2 / (sqrt(2 pi) x min(width x voices, scales in scope) x sum over scope scales of n_a(j) s_j)), n_a(j) the in-cone months at scale j. A cell at scale j stands for a block sqrt(2 pi) s_j months long (the Gaussian's equivalent width) and min(4.8, scales in scope) scales wide. One scale gives n_a / (sqrt(2 pi) s).
- Do NOT use the earlier plan (scales / 4.8 x mean of per-scale counts): on unrelated rows it gave p <= 0.05 for 15% of pairs and at least one edge in 51% of pure-noise configurations. The Kish form gave 6.4% and 4.2% (target at most 10%), and is conservative for narrow scopes. Measured variance-matching n for all scales: 34.9; Kish: 23.6.
- p = I_expected(x, n_eff - x + 1), x = weight x n_eff (scipy.special.betainc; the binomial upper tail for real n); p = 1 at weight 0.
- Benjamini-Yekutieli in `common/fdr.py`, within one configuration, two families (all-scales rows; band rows), named in a `family` column, with `family_size`, `q_value`, `edge` = q_value <= inference.q. `adjacency.per_band: false` keeps only the all-scales rows.
- Keys still to add: `adjacency.edge_weight`, `adjacency.edge_rule`, `adjacency.per_band`, `inference.cooccurrence_family_method`, `inference.q`.
- Tests to write: BY known answers, the p-value against scipy's binomial at integer n, unrelated rows (share of pure-noise configurations with an edge), the planted delay gets its edge (`delayed_field` in `tests/stages/test_coherence.py`), check rules, archive rule, count independence (weight and p_value do not depend on counts; q_value and edge are family decisions inside one configuration), fixture.

After A4: second independent implementation on a sample of spec 0, planted bugs, the AR-rows and April 2020 shares, then the section 8 report. None of that has been done. Track C left a mutation harness worth copying in the shared notes folder (`track_c/harness.py`).

## For the merge

- `src/rattractor/build.py`: one block after compare (it imports its stages itself), plus two adjacent lines in the manifest: `**track_a,` and `*track_a` at the end of `stages_passed`.
- `src/rattractor/config.py`: one block before `return cfg` in `validate_config`.
- `configs/default.yaml`, `schemas/config.yaml`: one block at the end.
- `tests/stages/test_build.py`: the expected `stages_passed` list.
- `tests/stages/test_grid.py` line 167: `[-2:]` became `[8:10]`, because stages now follow compare. Tracks B and C need the same one-line change.

## How to continue

Environment: `docs/WORK_PACKAGES.md` section 4. The test helpers every Track A test module shares are at the top of `tests/stages/test_wavelet.py` (`make_grid`, `subgrid`, `ar1_rows`, `assert_other_configurations_identical`, `assert_frames_equal_under_reindexing`, `fixture_build`, `three_series_grid`).
