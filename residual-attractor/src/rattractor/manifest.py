"""Build identity and content hashes.

build_id = sha256(config hash, sorted input data hashes, code commit), so two
identical runs share one id (spec: Configuration and reproducibility).
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

from . import PKG_ROOT


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def code_version() -> str:
    try:
        out = subprocess.run(
            ["git", "-C", str(PKG_ROOT), "rev-parse", "HEAD"],
            capture_output=True, text=True, check=True,
        )
        dirty = subprocess.run(
            ["git", "-C", str(PKG_ROOT), "status", "--porcelain", "--", "."],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
        return out.stdout.strip() + ("+dirty" if dirty else "")
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def build_id(config_hash: str, data_hashes: dict[str, str], commit: str) -> str:
    payload = json.dumps(
        {"config": config_hash, "data": dict(sorted(data_hashes.items())), "code": commit},
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode()).hexdigest()[:16]
