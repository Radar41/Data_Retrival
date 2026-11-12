"""Schema enforcement on every read and write.

A schema (schemas/<artifact>.yaml) fixes the column list and order, each
column's dtype, nullability and allowed values, and the primary key. Nothing is
cast: a frame that does not already match fails.
"""

from __future__ import annotations

from functools import cache
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import yaml

from . import SCHEMA_DIR, ContractError

_NUMPY: dict = {
    "int16": np.dtype("int16"),
    "int32": np.dtype("int32"),
    "float32": np.dtype("float32"),
    "float64": np.dtype("float64"),
    "bool": np.dtype("bool"),
}
LIST_F32 = "list[float32]"  # one 1-D float32 array per row, every row the same length
LIST_I16 = "list[int16]"    # one 1-D int16 array per row, lengths free (zero included)
INT16_NULLABLE = "Int16"    # pandas nullable int16; <NA> is the null
_LIST_ARROW = {LIST_F32: (pa.float32(), np.float32), LIST_I16: (pa.int16(), np.int16)}


def _check_list_f32(artifact: str, name: str, col: pd.Series, nullable: bool) -> None:
    if col.dtype != object:
        raise ContractError(f"{artifact}.{name}: dtype {col.dtype}, schema {LIST_F32}")
    vals = col.to_numpy()
    bad = sum(not (isinstance(v, np.ndarray) and v.ndim == 1 and v.dtype == np.float32) for v in vals)
    if bad:
        raise ContractError(f"{artifact}.{name}: {bad} values are not 1-D float32 arrays")
    lengths = {v.size for v in vals}
    if len(lengths) > 1:
        raise ContractError(f"{artifact}.{name}: array lengths differ ({sorted(lengths)[:5]})")
    if len(vals) and not nullable and not np.isfinite(np.stack(vals)).all():
        raise ContractError(f"{artifact}.{name}: non-finite values in a non-null column")


def _check_list_i16(artifact: str, name: str, col: pd.Series) -> None:
    if col.dtype != object:
        raise ContractError(f"{artifact}.{name}: dtype {col.dtype}, schema {LIST_I16}")
    bad = sum(not (isinstance(v, np.ndarray) and v.ndim == 1 and v.dtype == np.int16) for v in col.to_numpy())
    if bad:
        raise ContractError(f"{artifact}.{name}: {bad} values are not 1-D int16 arrays")


@cache
def load_schema(artifact: str) -> dict:
    path = SCHEMA_DIR / f"{artifact}.yaml"
    if not path.is_file():
        raise ContractError(f"no schema for artifact {artifact!r} at {path}")
    schema = yaml.safe_load(path.read_text())
    if schema.get("artifact") != artifact:
        raise ContractError(f"{path} declares artifact {schema.get('artifact')!r}")
    return schema


def empty_frame(artifact: str) -> pd.DataFrame:
    """A zero-row frame with exactly the schema's columns and dtypes."""
    schema = load_schema(artifact)
    cols = {}
    for c in schema["columns"]:
        d = c["dtype"]
        if d in ("string", "boolean"):
            cols[c["name"]] = pd.Series([], dtype=d)
        elif d == "category":
            cols[c["name"]] = pd.Categorical([], categories=c["values"])
        elif d in (LIST_F32, LIST_I16):
            cols[c["name"]] = pd.Series([], dtype=object)
        elif d == INT16_NULLABLE:
            cols[c["name"]] = pd.Series([], dtype="Int16")
        else:
            cols[c["name"]] = pd.Series([], dtype=_NUMPY[d])
    return pd.DataFrame(cols)


def from_columns(data: dict, artifact: str) -> pd.DataFrame:
    """Build a frame for `artifact` from raw column arrays, typing each column as the schema says.

    This is the one place a stage's arrays become an artifact; the result is validated,
    so a wrong value (a null in a non-null column, a stray category) still fails.
    """
    schema = load_schema(artifact)
    names = [c["name"] for c in schema["columns"]]
    if set(data) != set(names):
        raise ContractError(f"{artifact}: columns {sorted(data)} != schema {sorted(names)}")
    cols = {}
    for c in schema["columns"]:
        name, d, v = c["name"], c["dtype"], data[c["name"]]
        if d in ("string", "boolean"):
            cols[name] = pd.array(v, dtype=d)
        elif d == "category":
            cols[name] = pd.Categorical(v, categories=c["values"])
        elif d == LIST_F32:
            arr = np.asarray(v, dtype=np.float32)
            if arr.ndim != 2:
                raise ContractError(f"{artifact}.{name}: list[float32] needs a 2-D (rows, length) array")
            col = np.empty(arr.shape[0], dtype=object)
            for i in range(arr.shape[0]):
                col[i] = arr[i].copy()
            cols[name] = col
        elif d == LIST_I16:
            col = np.empty(len(v), dtype=object)
            for i, row in enumerate(v):
                col[i] = np.asarray(row, dtype=np.int16).reshape(-1)
            cols[name] = col
        elif d == INT16_NULLABLE:
            cols[name] = pd.array(v, dtype="Int16")
        else:
            cols[name] = np.asarray(v).astype(_NUMPY[d], copy=False)
    return validate(pd.DataFrame(cols), artifact)


def validate(df: pd.DataFrame, artifact: str) -> pd.DataFrame:
    """Check df against the schema; return it unchanged or raise ContractError."""
    schema = load_schema(artifact)
    spec = schema["columns"]
    expected = [c["name"] for c in spec]
    actual = list(df.columns)
    if actual != expected:
        raise ContractError(f"{artifact}: columns {actual} != schema {expected}")

    for c in spec:
        name, d = c["name"], c["dtype"]
        col = df[name]
        if d == "string":
            if not isinstance(col.dtype, pd.StringDtype):
                raise ContractError(f"{artifact}.{name}: dtype {col.dtype}, schema string")
        elif d == "boolean":
            if not isinstance(col.dtype, pd.BooleanDtype):
                raise ContractError(f"{artifact}.{name}: dtype {col.dtype}, schema boolean")
        elif d == LIST_F32:
            _check_list_f32(artifact, name, col, c.get("nullable", False))
            continue  # the generic null and finite checks below do not apply to arrays
        elif d == LIST_I16:
            _check_list_i16(artifact, name, col)
            continue
        elif d == INT16_NULLABLE:
            if not isinstance(col.dtype, pd.Int16Dtype):
                raise ContractError(f"{artifact}.{name}: dtype {col.dtype}, schema Int16")
        elif d == "category":
            if not isinstance(col.dtype, pd.CategoricalDtype):
                raise ContractError(f"{artifact}.{name}: dtype {col.dtype}, schema category")
            if list(col.cat.categories) != list(c["values"]):
                raise ContractError(
                    f"{artifact}.{name}: categories {list(col.cat.categories)} != {c['values']}"
                )
        else:
            if col.dtype != _NUMPY[d]:
                raise ContractError(f"{artifact}.{name}: dtype {col.dtype}, schema {d}")

        if not c.get("nullable", False):
            if col.isna().any():
                raise ContractError(f"{artifact}.{name}: {int(col.isna().sum())} nulls in a non-null column")
            if d in ("float32", "float64") and not np.isfinite(col.to_numpy()).all():
                raise ContractError(f"{artifact}.{name}: non-finite values in a non-null column")

    list_cols = [c["name"] for c in spec if c["dtype"] == LIST_F32]
    if list_cols and len(df):
        lengths = {name: df[name].iloc[0].size for name in list_cols}
        if len(set(lengths.values())) > 1 or min(lengths.values()) < 1:
            raise ContractError(f"{artifact}: list[float32] columns must share one length >= 1, got {lengths}")

    pk = schema.get("primary_key", [])
    if pk and df.duplicated(subset=pk).any():
        n = int(df.duplicated(subset=pk).sum())
        raise ContractError(f"{artifact}: {n} duplicate primary keys on {pk}")
    return df


def write(df: pd.DataFrame, artifact: str, path: Path) -> Path:
    """Validate, then write Parquet."""
    validate(df, artifact)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    table = pa.Table.from_pandas(df, preserve_index=False)
    for c in load_schema(artifact)["columns"]:
        if c["dtype"] in _LIST_ARROW:
            # Built explicitly so the Arrow type is exact whatever pandas would infer (empty lists included).
            child, np_type = _LIST_ARROW[c["dtype"]]
            vals = df[c["name"]].to_numpy()
            offsets = np.concatenate(([0], np.cumsum([v.size for v in vals]))).astype(np.int32)
            flat = np.concatenate(vals) if len(vals) else np.array([], dtype=np_type)
            arr = pa.ListArray.from_arrays(pa.array(offsets), pa.array(flat.astype(np_type, copy=False), type=child))
            i = table.schema.get_field_index(c["name"])
            table = table.set_column(i, pa.field(c["name"], pa.list_(child)), arr)
    pq.write_table(table, path)
    return path


def read(path: Path, artifact: str) -> pd.DataFrame:
    """Read Parquet and validate; no casting beyond Arrow's own round trip."""
    table = pq.read_table(path)
    schema = load_schema(artifact)
    for c in schema["columns"]:
        if c["name"] not in table.column_names:
            continue
        want = pa.list_(_LIST_ARROW[c["dtype"]][0]) if c["dtype"] in _LIST_ARROW else (pa.int16() if c["dtype"] == INT16_NULLABLE else None)
        if want is not None and table.schema.field(c["name"]).type != want:
            raise ContractError(f"{artifact}.{c['name']}: Arrow type {table.schema.field(c['name']).type} on disk, schema {want}")
    df = table.to_pandas()
    # Arrow can hand back pandas "string" / "boolean" as object (an all-null
    # column has no Arrow type to carry them). Restore exactly, only for columns
    # the schema declares that way, and refuse values of any other type.
    kinds = {"string": str, "boolean": (bool, np.bool_)}
    for c in schema["columns"]:
        d = c["dtype"]
        if d in kinds and c["name"] in df and df[c["name"]].dtype == object:
            vals = df[c["name"]]
            if not vals.map(lambda v: v is None or v is pd.NA or isinstance(v, kinds[d])).all():
                raise ContractError(f"{artifact}.{c['name']}: values not of type {d} on read")
            df[c["name"]] = vals.astype(d)
        # Parquet writes no dictionary for an empty column chunk, so a zero-row category column
        # comes back with no categories; restore the schema's, which is all a zero-row column can hold.
        if d == "category" and c["name"] in df and len(df) == 0:
            df[c["name"]] = pd.Categorical([], categories=c["values"])
        if d == INT16_NULLABLE and c["name"] in df and not isinstance(df[c["name"]].dtype, pd.Int16Dtype):
            # The Arrow type on disk is int16 (checked above); without pandas metadata, nulls make it float64.
            df[c["name"]] = df[c["name"]].astype("Int16")
    # list<float32> comes back as an object column of 1-D float32 arrays, which validate checks.
    return validate(df, artifact)
