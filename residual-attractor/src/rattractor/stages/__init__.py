"""Pipeline stages. Each is a pure function from input artifacts to output artifacts;
acceptance checks raise AcceptanceError carrying the failing rows."""

from __future__ import annotations

import pandas as pd


class AcceptanceError(RuntimeError):
    def __init__(self, stage: str, message: str, rows: pd.DataFrame | None = None):
        super().__init__(f"{stage}: {message}")
        self.stage = stage
        self.rows = rows
