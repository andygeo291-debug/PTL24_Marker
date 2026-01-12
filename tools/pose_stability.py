#!/usr/bin/env python3
"""Compute pose stability metrics from a poses.csv file."""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd


def _resolve_poses_path(args: argparse.Namespace) -> Path:
    if args.poses_csv:
        return Path(args.poses_csv)
    if not args.run_dir:
        raise SystemExit("Provide --poses-csv or --run-dir.")
    run_dir = Path(args.run_dir)
    return run_dir / args.mode / "poses.csv"


def main() -> int:
    parser = argparse.ArgumentParser(description="Compute stability metrics for poses.csv.")
    parser.add_argument("--poses-csv", default=None, help="Path to poses.csv.")
    parser.add_argument("--run-dir", default=None, help="Basler run directory.")
    parser.add_argument("--mode", default="spike_off", help="Run mode subdir (default: spike_off).")
    args = parser.parse_args()

    poses_path = _resolve_poses_path(args)
    if not poses_path.exists():
        raise SystemExit(f"poses.csv not found: {poses_path}")

    df = pd.read_csv(poses_path, comment="#")
    if not {"tvec_cam_x", "tvec_cam_y", "tvec_cam_z"}.issubset(df.columns):
        raise SystemExit("Expected tvec_cam_x/y/z columns not found.")

    tvec = df[["tvec_cam_x", "tvec_cam_y", "tvec_cam_z"]].astype(float).to_numpy()
    dist = np.linalg.norm(tvec, axis=1)
    dT = np.linalg.norm(np.diff(tvec, axis=0), axis=1)

    print(f"Loaded: {poses_path}")
    print(f"Frames: {len(df)}")
    print("")
    print("=== XYZ MEAN (m) camera->roll center ===")
    print("mean_x, mean_y, mean_z:", np.round(tvec.mean(axis=0), 4).tolist())
    print("")
    print("=== DISTANCE CAMERA->ROLL CENTER ===")
    print("mean (m):", round(float(dist.mean()), 3))
    print("std  (m):", round(float(dist.std()), 3))
    print("min/max (m):", round(float(dist.min()), 3), round(float(dist.max()), 3))
    print("")
    print("=== POSITION JITTER ===")
    std_mm = (tvec - tvec.mean(axis=0)).std(axis=0) * 1000.0
    print("STD around mean (mm) [x,y,z]:", np.round(std_mm, 3).tolist())
    if dT.size:
        print(
            "3D step p50/p90/p95/max (mm):",
            [
                round(float(np.percentile(dT * 1000.0, p)), 3)
                for p in (50, 90, 95)
            ]
            + [round(float(dT.max() * 1000.0), 3)],
        )
    else:
        print("3D step p50/p90/p95/max (mm): n/a")

    if "tilt_cam_deg" in df.columns:
        tilt = df["tilt_cam_deg"].astype(float).to_numpy()
        dtilt = np.abs(np.diff(tilt))
        print("")
        print("=== TILT STABILITY (tilt_cam_deg) ===")
        print("STD (deg):", round(float((tilt - tilt.mean()).std()), 3))
        if dtilt.size:
            print(
                "step p50/p90/p95/max (deg):",
                [
                    round(float(np.percentile(dtilt, p)), 3)
                    for p in (50, 90, 95)
                ]
                + [round(float(dtilt.max()), 3)],
            )
        else:
            print("step p50/p90/p95/max (deg): n/a")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
