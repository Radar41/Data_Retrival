# Track A progress: who leads, by phase

Branch `claude/ra-wavelet-coherence-1ef86c` (worktree), cut from `3eb8984`. Brief: `docs/WORK_PACKAGES.md`, Track A. Nothing is pushed or merged.

## State

| Package | Stage | State |
|---|---|---|
| A1 | `wavelet` | built, tested, committed |
| A2 | `spectral` | built, tested, committed |
| A3 | `coherence` | built, tested, committed |
| A4 | `adjacency` | built, tested, committed |

All four stages and the track-level checks are done; the report is the last section of this file. Tests: 427 passed, 1 expected failure. Spec 0 builds in 63 s with all four stages in `stages_passed`.

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

## A4, `adjacency`

Files: `src/rattractor/stages/adjacency.py`, `src/rattractor/common/fdr.py`, `schemas/adjacency_edges.yaml`, `tests/stages/test_adjacency.py`, keys `adjacency.*`, `inference.cooccurrence_family_method`, `inference.q`.

`adjacency/edges.parquet` (k, i_a, i_b, band_a, band_b): 5,704 rows on spec 0, one per coherence scope: weight, expected, n_eff, p_value, family, family_size, q_value, edge. 1,273 of 4,914 all-scales pairs and 76 of 790 band overlaps are edges. Formulas and choices are in the module docstring (Kish effective n of smoothing footprints; binomial tail for real n; Benjamini-Yekutieli within one configuration and family).

## For the merge

- `src/rattractor/build.py`: one block after compare (it imports its stages itself), plus two adjacent lines in the manifest: `**track_a,` and `*track_a` at the end of `stages_passed`.
- `src/rattractor/config.py`: one block before `return cfg` in `validate_config`.
- `configs/default.yaml`, `schemas/config.yaml`: one block at the end.
- `tests/stages/test_build.py`: the expected `stages_passed` list.
- `tests/stages/test_grid.py` line 167: `[-2:]` became `[8:10]`, because stages now follow compare. Tracks B and C need the same one-line change.

## How to continue

Environment: `docs/WORK_PACKAGES.md` section 4. The test helpers every Track A test module shares are at the top of `tests/stages/test_wavelet.py` (`make_grid`, `subgrid`, `ar1_rows`, `assert_other_configurations_identical`, `assert_frames_equal_under_reindexing`, `fixture_build`, `three_series_grid`).

## Report (WORK_PACKAGES section 8)

### Commits (branch `claude/ra-wavelet-coherence-1ef86c`, not pushed, not merged)

- `3f9ae96` A1 wavelet: the Morlet transform of every configuration's own row
- `8698746` A2 spectral: global spectrum, data-driven bands, band power, dominant period
- `d3bf738` A3 coherence: work in progress (superseded by the next)
- `71bed2b` A3 coherence: coherence, phase and circular-shift significance for every pair inside one configuration
- `5ef9829` A4 adjacency: edge weight, binomial p-value, edge decision within one configuration
- `9ea7428` A3 coherence: a surrogate equal to the observed field up to rounding is a tie (found by a planted bug)

No bug was found in stages 1 to 10. The one change outside Track A's files is `tests/stages/test_grid.py` line 167 (`[-2:]` to `[8:10]`), needed by every track because stages now follow compare.

### Artifacts on spec 0 (K 54, N 14, P 98, J 33)

| Stage | Artifact | Rows |
|---|---|---|
| wavelet | scale / series / red_noise / cwt | 33 / 756 / 24,948 / 2,444,904 |
| spectral | global / bands / band_count / band_power / dominant | 24,948 / 488 / 756 / 47,824 / 74,088 |
| coherence | cells / scope | 15,891,876 / 5,704 |
| adjacency | edges | 5,704 (1,273 all-scales edges of 4,914 pairs; 76 band edges of 790) |

Build time: 9 s before Track A, 63 s after (wavelet 0.5 s, spectral 0.3 s, coherence 43 s, adjacency under 1 s, the rest writing). The build directory grows by about 480 MB, 397 MB of it the coherence cell table. The cell table is dense (rdiag's design) and grows as N squared: about 860 M rows at 100 series.

### Tests and checks

- 427 passed, 1 expected failure (baseline 268). Track A: 34 wavelet, 37 spectral, 54 coherence, 34 adjacency. Each stage has the archive-rule test (changing one configuration leaves every other row bit-identical), count independence, one test per acceptance rule, the one-series fixture build (empty or null output) and known answers. Planted lags of 2, -3 and 0 months come back as 1.96, -2.85 and -0.06; swapping the series gives the same r2 and the negated phase, bit for bit.
- Second implementation (`recompute_track_a.py` in the session scratchpad; explicit DFT matrix instead of the FFT, its own daughter normalization, Gaussian and boxcar matrices, loops for bands, scopes, the order statistic and Benjamini-Yekutieli): 8 spec 0 configurations across all three methods, 112 rows, 96 pairs, every column of the four stages. Worst difference 1e-12 relative, no cell with a different significance flag, q-values to 2e-16.
- Planted bugs: 22, one at a time, in a scratch copy (Track C's harness). 21 caught at once. The miss, `>` for `>=` in the scope p-value, led to `9ea7428`. After it, both p-value mutants are caught. The one survivor (`> stat - 1e-12`) is equivalent to the original.

### Departures from rdiag, and why

- `k` in every key, every stage on each configuration's own rows, the false-discovery decision inside one configuration: the archive rule.
- `s2a.complex` (rdiag's holonomy cell complex, which needs adjacency edges) is not built. The complex coefficients `w_re`, `w_im` are stored, with amplitude and phase.
- Unit energy is exact on the discrete grid, so white noise has mean power 1 at every scale. Torrence and Compo's continuous factor gives 0.55 at period 2.
- Rows are centred on their own mean; the variance divisor is P; padding is to a power of two at least P + 6 e-folding times. rdiag is silent on all three.
- `wavelet_scale` has no `k`: it follows from P and the config.
- `spectral_summary.dj0_decorrelation` (0.60) is a new key; rdiag leaves Torrence and Compo's factor implicit.
- Bands are per row; `spectral_band_count` is added so a row with no band has a row.
- Coherence reads the bands. rdiag registers a (pair, band) test without a statistic; here it is the mean r2 over the scope's in-cone cells, and the scopes are all scales plus each overlap of the two rows' bands.
- `r2_q` is an order statistic, not an interpolated quantile. Every one of the 75 offsets that exist is used once, instead of 1,000 draws from them; p-values step by 1/76.
- Values within 1e-12 are ties. rdiag's recipe table `s3.surrogate_index` is not written.
- The lag in months is stored per scope, not per cell.
- Adjacency's effective n is the Kish count of smoothing footprints (rdiag names the correction, not the formula). Its families are two per configuration, all-scales and band. No registry is written; raw p-values and q-values are stored with their keys.

### How much rests on the AR rows and on April 2020

- AR rows: 29 of 54 configurations and 54% of pairs, but 46% of all-scales edges. Their edge rate is 22%, against 30% for Holt and SES, and their mean weight is 0.146 against 0.169 and 0.171. The AR drift does not inflate coherence here.
- April 2020: 59% of significant cells lie within two smoothing widths of April 2020, a region that holds 36% of in-cone cells; significance there is 24 to 29%, against 9.5 to 10.6% elsewhere.
- Rerunning the four stages on the grid with April 2020 replaced by each row's mean (a measurement; the build is unchanged): all-scales edges fall from 1,273 to 955, with 558 lost, 240 gained and 715 kept; band edges fall from 76 to 62, with 45 lost. The share of edges lost is 37% for AR, 44% for Holt and 59% for SES.

### What the null does (measured)

- With rdiag's minimum shift of 12 months, unrelated rows have 7.7% of in-cone cells significant against the rule's 3.9% (5% at short periods, 12 to 15% at long), and 7% of unrelated pairs sit at the smallest p-value. With every nonzero shift in the null the same code gives 4.2% against 4.1%.
- Adjacency on pure noise (300 configurations of 14 independent AR(1) rows): 6.7% of configurations get an all-scales edge, 5.7% a band edge (q = 0.10 bounds each by 10%).
- The floor arithmetic Track B raised holds: with every p >= 1/76, Benjamini-Yekutieli at q = 0.10 needs 2 of 4, 6 of 14 and 61 of 91 tests at the floor (pinned by a test). On spec 0 every configuration has 22 to 34 of its 91 pairs at the coherence floor, so BY on coherence's surrogate p-values would discover nothing. Adjacency's binomial p-values have no such floor.

### Questions for Adrian (default used)

1. The minimum shift of 12 months makes coherence's null too easy to beat (7.7% against 3.9%). Default: rdiag's 12. A minimum of 1 is calibrated.
2. `s2a.complex`: read as rdiag's holonomy complex, a wave-2 stage. Default: not built.
3. Adjacency's effective n. Default: the Kish count (6.7% of noise configurations with an edge); the first formula tried gave 51%.
4. False-discovery families. Default: two per configuration (all scales, bands).
5. The dense cell table: 397 MB at 14 series, growing as N squared. Default: kept, as rdiag has it.
6. A deterministic cycle shared by two rows is coherent under every shift, so it is never significant. Default: accepted; the null keeps each row's spectrum.
7. Chance bands: about a third of pure red-noise rows get a band under rdiag's two-scale rule. Default: rdiag's rule.
8. White noise normalization at the Nyquist scales. Default: exact discrete unit energy.
