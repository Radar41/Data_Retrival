"""rattractor build <run spec> [--config PATH] [--root DIR]"""

from __future__ import annotations

import argparse
import json
import sys
import time

from .build import build
from .config import load_config
from .runspec import load_run_spec
from .stages import AcceptanceError


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="rattractor")
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build", help="run stages 1-4b for one run spec")
    b.add_argument("run_spec", help="path, or a file name under runs/")
    b.add_argument("--config", default=None, help="config YAML (default configs/default.yaml)")
    b.add_argument("--root", default=None, help="directory that gets builds/ and reports/ (default the package root)")
    args = ap.parse_args(argv)

    t0 = time.time()
    try:
        out = build(load_run_spec(args.run_spec), load_config(args.config), args.root)
    except AcceptanceError as err:
        print(f"build stopped: {err}", file=sys.stderr)
        return 2
    m = json.loads((out / "manifest.json").read_text())
    rows = {d: sum(a["rows"] for k, a in m["artifacts"].items() if k.startswith(d + "/")) for d in ("steps", "fibers")}
    print(f"build {m['build_id']} -> {out}")
    print(f"  series {len(m['split_boundary'])}, configurations {m['configurations']['admissible']} admissible, "
          f"fiber length {m['fiber']['coordinates']}, steps rows {rows['steps']:,}, fiber rows {rows['fibers']:,}, "
          f"{time.time() - t0:.1f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
