#!/usr/bin/env python3
"""
Summarize Dotec fixed-extrinsics run.

Usage examples (repo root):
  python phase_b/tools/summarize_dotec_fixed.py
  python phase_b/tools/summarize_dotec_fixed.py --poses TEST_RUNS/PHASE_B_v2_15_dec/poses_full.csv --debug TEST_RUNS/PHASE_B_v2_15_dec/debug_full.csv
  python phase_b/tools/summarize_dotec_fixed.py poses.csv debug.csv
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Tuple

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
POSES_DEFAULT = REPO_ROOT / "phase_b" / "v2" / "poses_dotec_fixed_T_W.csv"
DEBUG_DEFAULT = REPO_ROOT / "phase_b" / "v2" / "debug_dotec_fixed_T_W.csv"


def load_with_header(path: Path) -> Tuple[dict, pd.DataFrame]:
    """Return (header_dict, dataframe) from a CSV whose first line is JSON prefixed with '#'."""
    header_line = None
    with path.open("r", encoding="utf-8") as fh:
        for raw in fh:
            if raw.startswith("#"):
                header_line = raw.lstrip("#").strip()
                break
    header = json.loads(header_line) if header_line else {}
    df = pd.read_csv(path, comment="#")
    return header, df


def stats(series: pd.Series) -> Tuple[float, float, float]:
    return float(series.min()), float(series.mean()), float(series.max())


def main() -> int:
    parser = argparse.ArgumentParser(description="Summarize Dotec fixed-extrinsics CSVs.")
    parser.add_argument("positional", nargs="*", help="Optional positional: poses.csv debug.csv")
    parser.add_argument("--poses", help="Poses CSV path (overrides default).")
    parser.add_argument("--debug", help="Debug metrics CSV path (overrides default).")
    args = parser.parse_args()

    poses_path = None
    debug_path = None
    if args.poses:
        poses_path = Path(args.poses)
    if args.debug:
        debug_path = Path(args.debug)
    if poses_path is None or debug_path is None:
        if len(args.positional) >= 2:
            poses_path = poses_path or Path(args.positional[0])
            debug_path = debug_path or Path(args.positional[1])
    poses_path = poses_path or POSES_DEFAULT
    debug_path = debug_path or DEBUG_DEFAULT

    poses_header, poses_df = load_with_header(poses_path)
    debug_header, debug_df = load_with_header(debug_path)

    print(f"Summarizing poses: {poses_path}")
    print(f"Summarizing debug: {debug_path}")

    print("=== HEADER CHECK ===")
    for label, hdr, path in [("poses", poses_header, poses_path), ("debug", debug_header, debug_path)]:
        cfg = hdr.get("config", {}) if isinstance(hdr, dict) else {}
        runtime = cfg.get("runtime", {}) if isinstance(cfg, dict) else {}
        logging_cfg = runtime.get("logging", {}) if isinstance(runtime, dict) else {}
        print(f"[{label}] file: {path}")
        print(f"[{label}] extrinsics_path_resolved: {cfg.get('extrinsics_path_resolved')}")
        print(f"[{label}] rig_path_resolved       : {cfg.get('rig_path_resolved')}")
        print(f"[{label}] poses_csv              : {logging_cfg.get('poses_csv')}")
        print(f"[{label}] debug_metrics_csv      : {logging_cfg.get('debug_metrics_csv')}")
        print()

    print("=== POSE STATS (CAMERA & WORLD) ===")
    for col in ["tilt_cam_deg", "tilt_world_deg"]:
        mn, mean, mx = stats(poses_df[col])
        label = "Camera tilt" if "cam" in col else "World tilt "
        print(f"{label:12s} (deg): min={mn:7.3f}, mean={mean:7.3f}, max={mx:7.3f}")

    for group_name, cols in [
        ("rvec_cam", ["rvec_cam_x", "rvec_cam_y", "rvec_cam_z"]),
        ("tvec_cam_m", ["tvec_cam_x", "tvec_cam_y", "tvec_cam_z"]),
        ("tvec_world_m", ["tvec_world_x", "tvec_world_y", "tvec_world_z"]),
    ]:
        print(f"\n{group_name} stats:")
        for c in cols:
            mn, mean, mx = stats(poses_df[c])
            print(f"  {c:15s}: min={mn: .4f}, mean={mean: .4f}, max={mx: .4f}")

    t_world_mean = poses_df[["tvec_world_x", "tvec_world_y", "tvec_world_z"]].mean().to_numpy(dtype=float)
    dist_world = float(np.linalg.norm(t_world_mean))
    print("\nMean world translation (m):", np.round(t_world_mean, 6))
    print(f"Approx roll-centre distance (m): {dist_world:.4f}")

    print("\n=== DEBUG STATS ===")
    for col in ["fps", "mean_reproj_px", "mean_tag_area_px2", "tilt_deg"]:
        mn, mean, mx = stats(debug_df[col])
        print(f"{col:17s}: min={mn:7.3f}, mean={mean:7.3f}, max={mx:7.3f}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
