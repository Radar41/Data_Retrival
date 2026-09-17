# Normalized Observation Contract

## Purpose

This document defines the canonical normalized observation contract used by the
GDSS forecasting, rolling-origin evaluation, residual archive, and downstream
meta-analysis systems.

The contract separates source-native acquisition and parsing from forecasting
evaluation.

```text
Provider-native source
  -> raw immutable artifact
  -> provider-specific normalizer
  -> canonical normalized observation artifact
  -> target selection
  -> origin-specific forecast evaluation
  -> forecast leaves and scorecards
  -> residual/meta-analysis archive
```

The evaluator does not parse FRED, ALFRED, BLS, BEA, Census, OECD, World Bank,
or other provider-native files directly. A provider-specific normalizer is
responsible for translating source-native records into this contract.

## Canonical normalized observation schema

A canonical normalized observation file is a long-form table. Each row
represents one value for one target-series variant at one observation date,
traced to one source member and original source column.

### Required columns

| Column | MATLAB-compatible type | Meaning |
|---|---|---|
| `observation_date` | string formatted `yyyy-MM-dd` in CSV; timezone-naive `datetime` after loading | Calendar label for the observed period/date |
| `series_id` | string | Series identifier within the provider/dataset namespace |
| `transformation_code` | string | Published/normalized variant identifier, for example `LEVEL`, `PCH`, `PC1`, `LOG`, `CHG` |
| `value` | numeric | Scalar numeric observation; missing values use `NaN` if retained |
| `source_member` | string | Stable identifier of the source artifact member from which the value was derived |
| `source_column` | string | Original source column/field identity from which the series/variant was derived |

### Required ordering

The canonical CSV column ordering is:

```text
observation_date
series_id
transformation_code
value
source_member
source_column
```

Column ordering is retained for human inspection and simple CSV tooling.
Consumers must identify fields by name rather than positional index.

### Required row identity

A canonical observation row is identified logically by:

```text
immutable_data_version
source_member
series_id
transformation_code
observation_date
```

A normalizer must not emit duplicate rows with the same identity unless the
artifact explicitly supports multiple releases/vintages. In that case, vintage
identity must be modeled separately and included in the input artifact/data
version selection.

## Temporal semantics

### Observation dates

`observation_date` is a calendar observation label, not a timestamped event.

Examples:

```text
2021-08-25
2021-08-31
2021-08-01
2021-08-19
```

When loaded into MATLAB, observation dates must be represented as a
timezone-naive `datetime`:

```matlab
datetime(dateText, "InputFormat", "yyyy-MM-dd")
```

Do not attach `"UTC"` to `observation_date` unless the source itself is
explicitly an intraday/event-time series for which clock time and time zone are
part of the empirical identity.

### System timestamps

System events are instants and must use explicit UTC timestamps:

```text
retrieved_at_utc
registered_at_utc
normalized_at_utc
created_at_utc
started_at_utc
completed_at_utc
```

The preferred serialized representation is:

```text
yyyy-MM-ddTHH:mm:ss.SSSZ
```

Examples:

```text
2026-09-16T23:25:21.966Z
2026-09-02T19:14:06Z
```

## Missing values

A normalizer must preserve source missingness without converting it to zero.

Canonical options:

```text
Option A:
  retain the row and set value = NaN.

Option B:
  omit the row, provided the normalized artifact metadata records that
  omission and downstream consumers can distinguish unavailable from zero.
```

The current univariate GDSS evaluator requires finite values in the selected
target sequence. Therefore, target-loading policy must explicitly choose one
of:

```text
reject_nonfinite
drop_missing_with_audited_gap_policy
impute_with_declared_training_only_policy
backend_supports_missing
```

No generic evaluator may silently interpolate, forward-fill, back-fill, or
discard missing observations.

## Dataset provenance

Dataset-level provenance belongs in an immutable descriptor/manifest, not in
every canonical observation row.

### Required manifest identity

A normalized dataset manifest must contain at least:

| Field | Meaning |
|---|---|
| `provider_id` | Provider namespace, for example `fred`, `alfred`, `bls`, `bea`, `census`, `oecd`, `world_bank`, `local` |
| `dataset_id` | Provider-level or local dataset identity |
| `raw_artifact_sha256` | SHA-256 of the immutable raw source artifact when applicable |
| `staging_key` or immutable data-version key | Stable key that identifies this normalized data version |
| `normalizer_id` | Implementation that generated the normalized output |
| `normalizer_version` | Version/commit/version label of that implementation |
| `normalized_at_utc` | UTC instant when normalization completed |
| `normalization_status` | Completion/audit state |
| `members` | Member-level mapping from source members to normalized files and hashes |

Recommended fields:

```text
source_url
source_retrieved_at_utc
raw_artifact_path
raw_artifact_bytes
source_format
schema_version
normalization_options
normalization_manifest_sha256
catalog_export_reference
audit_reference
```

### Member manifest fields

Each canonical normalized output member should be represented in the manifest
with at least:

```text
source_member
source_path or source_artifact_reference
source_sha256 when applicable
normalized_file_name
normalized_file_path or artifact reference
normalized_file_sha256
input_row_count
normalized_row_count
series_count
variant_count
transformation_codes
```

A consumer should resolve a normalized member through the manifest rather than
constructing paths from naming assumptions.

## Target identity and selection

A forecasting target is selected from an immutable normalized data version by:

```text
source_member
series_id
transformation_code
```

The complete logical target identity is:

```text
immutable_data_version_id
source_member
series_id
transformation_code
```

The following are not sufficient as global identifiers by themselves:

```text
series_id
series_id + transformation_code
source_member + series_id
```

because the same series-like code may exist in different provider/dataset/raw
artifact versions.

## Evaluator-facing input contract

For the current univariate evaluator, the resolved target loader must return:

```matlab
targetData = struct();

targetData.observation_dates
targetData.values

targetData.provider_id
targetData.dataset_id
targetData.immutable_data_version_id
targetData.raw_artifact_sha256

targetData.source_member
targetData.source_column
targetData.series_id
targetData.transformation_code
```

Minimum numerical requirements:

```text
observation_dates are strictly increasing.
values are numeric.
dates and values have equal length.
selected data satisfy the declared missing-value policy.
```

The evaluator may initially continue accepting a flat request struct, but it
must obtain target values through a target-loading boundary rather than
reimplementing provider/native-file parsing.

## Provider-specific normalizers

Each provider/source format receives a provider-specific normalizer.

Examples:

```text
normalize_fred_datalist_to_destination
normalize_alfred_vintage_to_destination
normalize_bls_timeseries_to_destination
normalize_bea_table_to_destination
normalize_oecd_dataset_to_destination
normalize_local_table_to_destination
```

A normalizer may parse:

```text
CSV
ZIP archives
JSON API responses
XML
XLSX
provider-specific database extracts
Parquet
MAT/HDF5
custom research tables
```

but it must emit the canonical long-form schema and an immutable manifest.

The evaluator remains provider-neutral.

## Current FRED implementations

### Preferred forward writer

`normalize_fred_datalist_to_destination` is the preferred forward FRED
normalization pattern.

It:

- takes a descriptor and explicit destination directory
- never overwrites a nonempty destination
- discovers source CSV members
- writes one compact long-form normalized file per source member
- records source and normalized SHA-256 values
- writes a member-level normalization manifest
- emits the canonical observation columns:

```text
observation_date
series_id
transformation_code
value
source_member
source_column
```

### Legacy compatibility format

`normalize_fred_datalist_zip` is an audited legacy FRED normalization path for
the historical FRED public datalist `10578` workflow.

It emits a wider schema with fields including:

```text
provider_id
dataset_id
raw_archive_sha256
source_member_path
frequency_label
observation_date
series_id
transformation_code
raw_column_name
value
is_missing
normalized_at_utc
```

This format contains valuable provenance but does not use the canonical field
names for source-member and source-column identity.

A legacy compatibility loader must map:

| Legacy field | Canonical meaning |
|---|---|
| `source_member_path` | `source_member` |
| `raw_column_name` | `source_column` |
| `observation_date` | `observation_date` |
| `series_id` | `series_id` |
| `transformation_code` | `transformation_code` |
| `value` | `value` |

Provider/dataset/raw SHA fields remain dataset-level provenance supplied by the
legacy manifest and/or loader result. A consumer must not silently assume the
legacy format is canonical.

## Data-version and artifact policy

### Immutable data version

A data version identifies the exact source artifact and normalized output used
for a fit/evaluation.

At minimum, it is derived from:

```text
provider_id
dataset_id
raw artifact SHA-256
normalization manifest identity
normalized member file SHA-256
```

A `FitRealization` must record or reference this data-version identity.

### Artifact references

Large payloads must not be copied into forecast leaves.

Examples of parent-level artifact references:

```text
raw source archive
normalization manifest
normalized member file
model artifact
training-data slice artifact
forecast-distribution parameters
interval artifact
optimizer diagnostics
```

Forecast leaves retain the values needed to reproduce scorecards and residual
analysis, while parent records carry provenance references.

## Validation requirements

A canonical normalized member should be audited before evaluation.

Minimum checks:

```text
required columns exist
column names are unique
observation dates parse as calendar dates
series IDs are nonempty
transformation codes are nonempty
source members are nonempty
source columns are nonempty
values are numeric or explicitly missing
no duplicate canonical row identity
selected series dates are strictly increasing after sorting
manifest/member file hashes match when hash verification is enabled
```

A target selection must fail loudly when:

```text
no matching rows exist
multiple incompatible versions are mixed
dates are duplicated
dates are not strictly increasing after deduplication policy
values violate the declared missing-value policy
requested origin is outside the selected target range
requested fixed horizon exceeds available future observations
```

## Relationship to model evaluation

The data contract does not define model equations. It supplies a stable,
versioned target series to all adapters.

```text
Normalized target selection
  -> ModelConfig
  -> EvaluationPolicy
  -> one origin-specific FitRealization
  -> ForecastRealization
  -> ForecastLeaves
  -> ForecastScorecard
```

Model configuration and evaluation policy are independent of provider-specific
ingestion:

```text
same model + different FRED/BLS/BEA target
  = different target/data selection

same model + same target + different origin
  = different evaluation request

same model + same target + same origin + different horizon policy
  = different evaluation request

same target + different model family
  = different ModelConfig
```

## Non-goals

This contract does not:

- prescribe one raw-data acquisition method
- expose source API credentials to the evaluator
- require all providers to use the same raw schema
- require every source to be represented in one giant file
- make provider-native identifiers globally unique without data-version context
- force a particular database, graph store, Parquet layout, or MATLAB storage
  format
- require a model adapter to know how data were acquired
- permit silent source-specific coercions in generic evaluation code

## Current implementation decision

The current GDSS evaluator has proven its model/fit/forecast/leaf/scorecard
semantics using a compact FRED normalized member.

The next implementation task is to add a provider-neutral target-loading
boundary that:

```text
1. receives a normalized target reference,
2. loads either the canonical compact schema or an explicitly declared legacy
   schema,
3. validates target identity and date/value rules,
4. returns a standard target-data structure plus immutable provenance,
5. lets run_gdss_evaluation consume that structure without direct FRED schema
   assumptions.
```

No model adapter needs to change for that work.