#!/usr/bin/env python3
"""Commit and push each file in repo individually."""
import os
import subprocess
import sys

REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
SKIP_DIRS = {".git"}


def collect_files(root):
    files = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for name in filenames:
            full_path = os.path.join(dirpath, name)
            rel_path = os.path.relpath(full_path, root)
            files.append(rel_path)
    return files


def run(cmd):
    result = subprocess.run(cmd, cwd=REPO_ROOT)
    return result.returncode == 0


def main():
    files = collect_files(REPO_ROOT)
    print(f"Found {len(files)} files.")

    for path in files:
        print(f"\n--- {path} ---")
        if not run(["git", "add", path]):
            print(f"add failed, skip: {path}")
            continue

        status = subprocess.run(
            ["git", "diff", "--cached", "--quiet"], cwd=REPO_ROOT
        )
        if status.returncode == 0:
            print("no staged changes, skip")
            continue

        if not run(["git", "commit", "-m", path]):
            print(f"commit failed, skip: {path}")
            continue

        if not run(["git", "push"]):
            print(f"push failed: {path}")
            sys.exit(1)

    print("\nDone.")


if __name__ == "__main__":
    main()
