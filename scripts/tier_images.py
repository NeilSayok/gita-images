#!/usr/bin/env python3
"""Generate lossless PNG density tiers from the 4x JPEG masters.

Walks chapters/4x/**/img.jpeg and sloks/4x/**/img.jpeg and writes, for each
requested tier, a lossless PNG scaled from the master's own true dimensions:

    tier 4 -> x1.00   (format conversion only, pixel-identical)
    tier 3 -> x0.75
    tier 2 -> x0.50
    tier 1 -> x0.25

Output mirrors the source layout with the "4x" path segment swapped for the
tier, e.g. sloks/4x/chapter_1/slok_1/square/img.jpeg
        -> sloks/1x/chapter_1/slok_1/square/img.png
Tier 4 has no segment to swap, so its PNG lands beside the master as img.png.

Masters are only ever read. Re-runnable: an output newer than its master is
left alone, so Ctrl-C and resume is safe.

    python3 scripts/tier_images.py --self-check
    python3 scripts/tier_images.py --dry-run
    python3 scripts/tier_images.py --roots chapters
    python3 scripts/tier_images.py
"""

import argparse
import os
import sys
import tempfile
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from PIL import Image, ImageChops

SCALES = {4: 1.0, 3: 0.75, 2: 0.5, 1: 0.25}
REPO = Path(__file__).resolve().parent.parent


def orientation(width, height):
    if width == height:
        return "square"
    return "portrait" if width < height else "landscape"


def output_path(master, tier):
    """Map a 4x master onto its path for `tier`."""
    parts = list(master.relative_to(REPO).parts)
    if tier != 4:
        parts[1] = f"{tier}x"  # chapters/4x/... -> chapters/1x/...
    return REPO.joinpath(*parts).with_suffix(".png")


def convert(args):
    """Convert one master into every requested tier. Runs in a worker process."""
    master, tiers, force = args
    written, skipped, mismatch = [], [], None
    try:
        with Image.open(master) as im:
            im = im.convert("RGB")
            src_w, src_h = im.size

            actual = orientation(src_w, src_h)
            if actual != master.parent.name:
                mismatch = (str(master.relative_to(REPO)), src_w, src_h, actual)

            for tier in tiers:
                out = output_path(master, tier)
                if (not force and out.exists()
                        and out.stat().st_mtime >= master.stat().st_mtime):
                    skipped.append(out)
                    continue

                scale = SCALES[tier]
                if scale == 1.0:
                    resized = im
                else:
                    size = (round(src_w * scale), round(src_h * scale))
                    resized = im.resize(size, Image.LANCZOS)

                out.parent.mkdir(parents=True, exist_ok=True)
                # Write to a temp file in the same dir, then rename, so an
                # interrupted run never leaves a half-written PNG that the
                # up-to-date check would later accept as done.
                tmp = out.with_suffix(".png.part")
                resized.save(tmp, "PNG", optimize=True, compress_level=9)
                os.replace(tmp, out)
                written.append((tier, out, out.stat().st_size))
    except Exception as exc:  # a corrupt master must not kill the whole run
        return {"error": (str(master.relative_to(REPO)), repr(exc))}

    return {"written": written, "skipped": skipped, "mismatch": mismatch}


def find_masters(roots):
    masters = []
    for root in roots:
        base = REPO / root / "4x"
        if not base.is_dir():
            print(f"warning: {base} is not a directory, skipping", file=sys.stderr)
            continue
        masters.extend(sorted(base.rglob("*.jpeg")))
    return masters


def run(roots, tiers, jobs, force, dry_run):
    masters = find_masters(roots)
    print(f"{len(masters)} masters under {', '.join(roots)}; tiers {tiers}")

    if dry_run:
        mismatches = []
        planned = 0
        for master in masters:
            with Image.open(master) as im:
                w, h = im.size
            actual = orientation(w, h)
            if actual != master.parent.name:
                mismatches.append((str(master.relative_to(REPO)), w, h, actual))
            for tier in tiers:
                out = output_path(master, tier)
                if force or not out.exists():
                    planned += 1
        print(f"would write {planned} PNGs")
        report_mismatches(mismatches)
        return

    tasks = [(m, tiers, force) for m in masters]
    written = skipped = 0
    per_tier = {t: [0, 0] for t in tiers}  # tier -> [count, bytes]
    mismatches, errors = [], []

    with ProcessPoolExecutor(max_workers=jobs) as pool:
        for i, res in enumerate(pool.map(convert, tasks, chunksize=4), 1):
            if "error" in res:
                errors.append(res["error"])
            else:
                for tier, _out, size in res["written"]:
                    per_tier[tier][0] += 1
                    per_tier[tier][1] += size
                    written += 1
                skipped += len(res["skipped"])
                if res["mismatch"]:
                    mismatches.append(res["mismatch"])
            if i % 50 == 0 or i == len(tasks):
                print(f"  {i}/{len(tasks)} masters, {written} written, "
                      f"{skipped} up-to-date", flush=True)

    print(f"\ndone: {written} written, {skipped} already up-to-date")
    for tier in sorted(per_tier, reverse=True):
        count, size = per_tier[tier]
        print(f"  {tier}x: {count} files, {size / 1e9:.2f} GB")
    report_mismatches(mismatches)
    if errors:
        print(f"\n{len(errors)} FAILED:")
        for path, exc in errors:
            print(f"  {path}: {exc}")


def report_mismatches(mismatches):
    if not mismatches:
        print("\nno aspect mismatches")
        return
    print(f"\n{len(mismatches)} images whose aspect does not match their folder "
          f"(scaled by their true size, left in place):")
    for path, w, h, actual in sorted(mismatches):
        print(f"  {path}  is {w}x{h} ({actual})")


def self_check():
    """Smallest thing that fails if the tier logic breaks."""
    global REPO
    with tempfile.TemporaryDirectory() as tmp:
        REPO = Path(tmp)
        master = REPO / "sloks" / "4x" / "chapter_1" / "slok_1" / "square" / "img.jpeg"
        master.parent.mkdir(parents=True)
        src = Image.new("RGB", (1024, 1024))
        for x in range(1024):  # non-flat, so resampling is actually exercised
            for y in range(0, 1024, 8):
                src.putpixel((x, y), (x % 256, y % 256, (x * y) % 256))
        src.save(master, "JPEG", quality=95)

        res = convert((master, [4, 3, 2, 1], False))
        assert "error" not in res, res
        assert res["mismatch"] is None, res["mismatch"]

        sizes = {tier: Image.open(out).size for tier, out, _ in res["written"]}
        assert sizes == {4: (1024, 1024), 3: (768, 768),
                         2: (512, 512), 1: (256, 256)}, sizes

        # tier 4 must be a lossless copy of the master's pixels
        with Image.open(master) as a, Image.open(output_path(master, 4)) as b:
            assert ImageChops.difference(a.convert("RGB"), b.convert("RGB")).getbbox() is None

        for tier in (1, 2, 3, 4):
            out = output_path(master, tier)
            assert Image.open(out).format == "PNG", out
            assert tier == 4 or out.parts[-5] == f"{tier}x", out

        # second run is a no-op
        again = convert((master, [4, 3, 2, 1], False))
        assert not again["written"] and len(again["skipped"]) == 4, again

        # a portrait file sitting in square/ is reported, and scaled by its own size
        odd = REPO / "sloks" / "4x" / "chapter_1" / "slok_2" / "square" / "img.jpeg"
        odd.parent.mkdir(parents=True)
        Image.new("RGB", (768, 1376), "white").save(odd, "JPEG")
        res = convert((odd, [1], False))
        assert res["mismatch"] == (str(odd.relative_to(REPO)), 768, 1376, "portrait"), res
        assert Image.open(output_path(odd, 1)).size == (192, 344)

    print("self-check OK")


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--roots", nargs="+", default=["chapters", "sloks"],
                        help="top-level trees to walk (default: chapters sloks)")
    parser.add_argument("--tiers", nargs="+", type=int, default=[4, 3, 2, 1],
                        choices=[1, 2, 3, 4], help="tiers to emit (default: 4 3 2 1)")
    parser.add_argument("--jobs", type=int, default=os.cpu_count(),
                        help="worker processes (default: all cores)")
    parser.add_argument("--force", action="store_true",
                        help="rewrite outputs even if already up to date")
    parser.add_argument("--dry-run", action="store_true",
                        help="report what would happen, write nothing")
    parser.add_argument("--self-check", action="store_true",
                        help="run the built-in assertions and exit")
    args = parser.parse_args()

    if args.self_check:
        self_check()
        return

    run(args.roots, sorted(set(args.tiers), reverse=True),
        args.jobs, args.force, args.dry_run)


if __name__ == "__main__":
    main()
