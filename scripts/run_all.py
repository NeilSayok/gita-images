#!/usr/bin/env python3
"""Run the full image pipeline sequentially: verify, then chapters, then sloks.

    python3 scripts/run_all.py            # everything
    python3 scripts/run_all.py --force    # extra args pass through to tier_images.py

Safe to re-run: tier_images.py skips outputs that are already up to date, so an
interrupted run picks up where it stopped.
"""

import shutil
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TIER = REPO / "scripts" / "tier_images.py"
NEEDED_GB = 11

STEPS = [
    ("self-check", ["--self-check"], False),
    ("dry run", ["--dry-run"], True),
    ("chapters", ["--roots", "chapters"], True),
    ("sloks", ["--roots", "sloks"], True),
]


def run(label, args):
    print(f"\n===== {label} =====", flush=True)
    result = subprocess.run([sys.executable, str(TIER), *args], cwd=REPO)
    if result.returncode != 0:
        sys.exit(f"\n{label} failed (exit {result.returncode})")


def main():
    passthrough = sys.argv[1:]

    free_gb = shutil.disk_usage(REPO).free / 1e9
    if free_gb < NEEDED_GB:
        sys.exit(f"abort: {free_gb:.0f}GB free, need ~{NEEDED_GB}GB for the PNG output")
    print(f"{free_gb:.0f}GB free, need ~{NEEDED_GB}GB")

    start = time.monotonic()
    for i, (label, args, takes_passthrough) in enumerate(STEPS, 1):
        run(f"{i}/{len(STEPS)} {label}",
            args + (passthrough if takes_passthrough else []))

    print("\n===== totals =====")
    for root in ("chapters", "sloks"):
        for tier in sorted((REPO / root).glob("*x")):
            size = sum(f.stat().st_size for f in tier.rglob("*") if f.is_file())
            print(f"  {root}/{tier.name}: {size / 1e9:.2f} GB")

    mins, secs = divmod(int(time.monotonic() - start), 60)
    print(f"\nfinished in {mins}m{secs:02d}s")
    print("NOTE: ~10GB of PNG written. Do not 'git add' these without Git LFS.")


if __name__ == "__main__":
    main()
