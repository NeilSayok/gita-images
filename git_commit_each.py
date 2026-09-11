#!/usr/bin/env python3
"""Commit the repo's pending changes in batches, pushing after each batch.

Replaces the old one-commit-and-one-push-per-file behaviour, which needed a
network round trip for every single file.

Two things make this fast:
  * Only changed paths are considered. `git status` reports them directly, so
    unchanged files are never handed to `git add` at all.
  * Files are committed N at a time (default 10) and each commit is pushed
    immediately, so progress survives an interrupted run.

Note on threads: git serialises all index writes on .git/index.lock, and each
commit needs the previous commit's hash, so `git add`/`git commit` cannot run
in parallel. Batching is the real win here.

    python3 git_commit_each.py                  # commit 10, push, repeat
    python3 git_commit_each.py -n 50            # batches of 50
    python3 git_commit_each.py --no-push        # commit only, no pushing
    python3 git_commit_each.py --dry-run        # show the plan, change nothing
"""

import argparse
import os
import subprocess
import sys

REPO_ROOT = os.path.dirname(os.path.abspath(__file__))


def git(*args, check=True, capture=False):
    result = subprocess.run(
        ["git", *args], cwd=REPO_ROOT,
        stdout=subprocess.PIPE if capture else None, text=True,
    )
    if check and result.returncode != 0:
        sys.exit(f"git {' '.join(args)} failed (exit {result.returncode})")
    return result


def pending_files():
    """Every path with staged, unstaged, or untracked changes.

    -z gives NUL-separated records so paths with spaces or quotes survive
    intact; --untracked-files=all lists files inside new directories rather
    than collapsing them to a single directory entry. .gitignore is honoured
    by git itself, so ignored files never show up.
    """
    out = git("status", "--porcelain", "-z", "--untracked-files=all",
              capture=True).stdout
    paths = []
    records = iter(out.split("\0"))
    for record in records:
        if not record:
            continue
        status, path = record[:2], record[3:]
        if status[0] == "R":  # rename: "R  new" then a separate old-path record
            next(records, None)
        paths.append(path)
    return sorted(paths)


def chunked(items, size):
    for i in range(0, len(items), size):
        yield items[i:i + size]


def commit_message(batch):
    if len(batch) == 1:
        return batch[0]
    return f"{batch[0]} (+{len(batch) - 1} more)"


def main():
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("-n", "--batch-size", type=int, default=10,
                        help="files per commit (default: 10)")
    parser.add_argument("--no-push", action="store_true",
                        help="commit only, do not push")
    parser.add_argument("--dry-run", action="store_true",
                        help="print what would be committed, change nothing")
    args = parser.parse_args()

    if args.batch_size < 1:
        sys.exit("--batch-size must be at least 1")

    files = pending_files()
    if not files:
        print("nothing to commit.")
        return

    batches = list(chunked(files, args.batch_size))
    print(f"{len(files)} changed files -> {len(batches)} commits "
          f"(batch size {args.batch_size})")

    if args.dry_run:
        for i, batch in enumerate(batches[:5], 1):
            print(f"  {i}. {commit_message(batch)}")
        if len(batches) > 5:
            print(f"  ... and {len(batches) - 5} more")
        print(f"would push: {'no' if args.no_push else 'yes, after every commit'}")
        return

    committed = 0
    for i, batch in enumerate(batches, 1):
        # "--" stops git treating a path that looks like a flag as one.
        git("add", "--", *batch)

        # --quiet makes the exit code the answer: 0 means nothing staged.
        if git("diff", "--cached", "--quiet", check=False).returncode == 0:
            print(f"[{i}/{len(batches)}] nothing staged, skip")
            continue

        git("commit", "-q", "-m", commit_message(batch))
        committed += 1

        if args.no_push:
            print(f"[{i}/{len(batches)}] committed {len(batch)} files")
        else:
            git("push", "-q")
            print(f"[{i}/{len(batches)}] committed {len(batch)} files, pushed")

    print(f"\nDone. {committed} commits"
          f"{'' if args.no_push else ', all pushed'}.")


if __name__ == "__main__":
    main()
