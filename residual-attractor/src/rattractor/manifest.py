"""Build identity and content hashes.

build_id = sha256(config hash, sorted input data hashes, code commit), so two
identical runs share one id (spec: Configuration and reproducibility).
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
from pathlib import Path

from . import PKG_ROOT


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def code_version() -> str:
    """HEAD, plus "+dirty:<tree>" when the package tree differs from HEAD.

    <tree> is git's own id of the package tree as it is on disk (tracked edits and untracked,
    unignored files), written through a throwaway index so the real index is never touched.
    Git handles symlinks, nested repositories and any file-name bytes, and two different
    uncommitted states never share a build_id (or overwrite each other's build).
    """
    git = ["git", "-C", str(PKG_ROOT)]

    def run(args, **kw):
        return subprocess.run(git + args, capture_output=True, text=True, check=True, **kw).stdout

    try:
        head = run(["rev-parse", "HEAD"]).strip()
        if not run(["status", "--porcelain", "--", "."]).strip():
            return head
        prefix = run(["rev-parse", "--show-prefix"]).strip()
        with tempfile.TemporaryDirectory() as tmp:
            env = {**os.environ, "GIT_INDEX_FILE": os.path.join(tmp, "index")}
            run(["read-tree", "HEAD"], env=env)
            run(["add", "-A", "--", "."], env=env)
            tree = run(["write-tree"] + ([f"--prefix={prefix}"] if prefix else []), env=env).strip()
        return f"{head}+dirty:{tree[:12]}"
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def build_id(config_hash: str, data_hashes: dict[str, str], commit: str) -> str:
    payload = json.dumps(
        {"config": config_hash, "data": dict(sorted(data_hashes.items())), "code": commit},
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode()).hexdigest()[:16]
