"""Generate requirements.lock — full deterministic freeze of the ACTIVE venv.

Usage (after installing requirements.txt into a clean venv):
    python3 scripts/make_requirements_lock.py [--python /path/to/venv/bin/python]

Policy (maint M1, 2026-09-17):
  * requirements.txt  = curated, fully pinned direct dependencies (pure ASCII).
  * requirements.lock = byte-stable freeze of the verified environment
                        (direct + transitive), header-stamped, sorted.
  * Regenerate the lock ONLY after an approved dependency change, in a CLEAN
    venv, then run the full test suite before committing.
  * The lock file is pure ASCII and contains NO timestamps that vary per run
    (generator prints them to stdout instead) so diffs stay meaningful.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from typing import List

HEADER = [
    "# quant4h requirements.lock -- deterministic freeze (maint M1, 2026-09-17)",
    "# Regenerate: python3 scripts/make_requirements_lock.py   (clean venv, after",
    "#             pip install -r requirements.txt)  -- then run the FULL test suite.",
    "# Do NOT edit by hand. Pure ASCII. Sort: case-insensitive by package name.",
]


def freeze(py: str) -> List[str]:
    out = subprocess.run([py, "-m", "pip", "freeze", "--disable-pip-version-check"],
                         capture_output=True, text=True, check=True)
    lines = [ln.strip() for ln in out.stdout.splitlines() if ln.strip()]
    # drop editable/local-path entries and pip setuptools noise if present
    lines = [ln for ln in lines if not ln.startswith(("-e ", "# "))]
    return sorted(lines, key=lambda s: s.lower())


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--python", default=sys.executable,
                    help="venv python whose freeze will be written (default: current)")
    ap.add_argument("--out", default="requirements.lock")
    args = ap.parse_args()

    lines = freeze(args.python)
    payload = "\n".join(HEADER + lines) + "\n"
    payload.encode("ascii")                      # hard ASCII guarantee
    with open(args.out, "w", encoding="ascii", newline="\n") as fh:
        fh.write(payload)
    print(f"WROTE {args.out}: {len(lines)} pinned packages (python={args.python})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
