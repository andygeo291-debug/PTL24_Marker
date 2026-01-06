#!/usr/bin/env python3
"""
Cleanup helper for Dotec CSV runs in phase_b/v2.

Keeps a small whitelist of important CSVs and deletes noisy intermediates:
  - Any csv beginning with debug_metrics_dotec_ (unless whitelisted)
  - Any csv beginning with poses_dotec_ (unless whitelisted)
Prompts for confirmation before deleting anything.
"""

from __future__ import annotations

import os
from pathlib import Path


KEEP = {
    "debug_dotec_fulltest.csv",
    "poses_dotec_fulltest.csv",
    "poses_sway_s000.csv",
    "poses_sway_s025.csv",
    "poses_sway_s050.csv",
    "poses_sway_swing.csv",
    "poses_v2_full.csv",
    "poses_v2_simple.csv",
}


def find_targets(base: Path) -> tuple[list[str], list[str]]:
    """Return (to_delete, to_keep) lists of CSV filenames under base."""
    to_delete: list[str] = []
    to_keep: list[str] = []
    for path in sorted(base.glob("*.csv")):
        name = path.name
        if name in KEEP:
            to_keep.append(name)
            continue
        if name.startswith("debug_metrics_dotec_") or (
            name.startswith("poses_dotec_") and name != "poses_dotec_fulltest.csv"
        ):
            to_delete.append(name)
        else:
            to_keep.append(name)
    return to_delete, to_keep


def main() -> int:
    base = Path(__file__).resolve().parent
    to_delete, to_keep = find_targets(base)

    print("Will delete:")
    if to_delete:
        for name in to_delete:
            print(f"  {name}")
    else:
        print("  (nothing)")

    print("\nWill keep:")
    for name in to_keep:
        print(f"  {name}")

    if not to_delete:
        print("\nNo files to delete. Exiting.")
        return 0

    confirm = input("\nType 'yes' to actually delete these files: ").strip()
    if confirm != "yes":
        print("Aborted. No files were deleted.")
        return 0

    for name in to_delete:
        path = base / name
        try:
            if path.is_file() and path.parent == base:
                os.remove(path)
                print(f"Deleted {name}")
            else:
                print(f"Skipped (not a file in this folder): {name}")
        except OSError as exc:
            print(f"Failed to delete {name}: {exc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
