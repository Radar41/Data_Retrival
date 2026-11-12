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

_NUMPY = {
    "int16": np.dtype("int16"),
    "int32": np.dtype("int32"),
    "float32": np.dtype("float32"),
    "float64": np.dtype("float64"),
    "bool": np.dtype("bool"),
}


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
        if d == "string":
            cols[c["name"]] = pd.Series([], dtype="string")
        elif d == "category":
            cols[c["name"]] = pd.Categorical([], categories=c["values"])
        else:
            cols[c["name"]] = pd.Series([], dtype=_NUMPY[d])
    return pd.DataFrame(cols)


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
    pq.write_table(pa.Table.from_pandas(df, preserve_index=False), path)
    return path


def read(path: Path, artifact: str) -> pd.DataFrame:
    """Read Parquet and validate; no casting beyond Arrow's own round trip."""
    table = pq.read_table(path)
    df = table.to_pandas()
    # Arrow round-trips pandas "string" as object unless told; restore exactly,
    # but only for columns the schema declares string, and refuse anything else.
    schema = load_schema(artifact)
    for c in schema["columns"]:
        if c["dtype"] == "string" and c["name"] in df and df[c["name"]].dtype == object:
            vals = df[c["name"]]
            if not vals.map(lambda v: v is None or isinstance(v, str)).all():
                raise ContractError(f"{artifact}.{c['name']}: non-string values on read")
            df[c["name"]] = vals.astype("string")
    return validate(df, artifact)
