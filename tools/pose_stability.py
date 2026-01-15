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

def _find_columns(df: pd.DataFrame, candidates: list[list[str]]) -> list[str]:
    lower_map = {c.lower(): c for c in df.columns}
    for cand in candidates:
        if all(name in lower_map for name in cand):
            return [lower_map[name] for name in cand]
    return []


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
    tvec_cols = _find_columns(
        df,
        [
            ["tvec_cam_x", "tvec_cam_y", "tvec_cam_z"],
            ["tvec_x", "tvec_y", "tvec_z"],
            ["t_cam_x", "t_cam_y", "t_cam_z"],
            ["tx", "ty", "tz"],
            ["t_x", "t_y", "t_z"],
            ["pos_x", "pos_y", "pos_z"],
            ["x", "y", "z"],
        ],
    )
    if not tvec_cols:
        raise SystemExit(
            "Could not find position columns. Expected one of: "
            "tvec_cam_x/y/z, tvec_x/y/z, t_cam_x/y/z, tx/ty/tz, t_x/t_y/t_z, pos_x/pos_y/pos_z, x/y/z."
        )

    dist_col = _find_columns(df, [["distance_m"], ["dist_m"], ["distance"], ["dist"]])
    tilt_col = _find_columns(df, [["tilt_cam_deg"], ["tilt_deg"]])

    tvec = df[tvec_cols].astype(float).to_numpy()
    dist = (
        df[dist_col[0]].astype(float).to_numpy()
        if dist_col
        else np.linalg.norm(tvec, axis=1)
    )
    dT = np.linalg.norm(np.diff(tvec, axis=0), axis=1)

    print(f"Loaded: {poses_path}")
    print(f"Frames: {len(df)}")
    print(f"[stability] distance mean={dist.mean():.3f} std={dist.std():.3f} min={dist.min():.3f} max={dist.max():.3f}")
    std_mm = (tvec - tvec.mean(axis=0)).std(axis=0) * 1000.0
    print(
        "[stability] jitter_std_mm x={:.3f} y={:.3f} z={:.3f}".format(
            std_mm[0], std_mm[1], std_mm[2]
        )
    )
    if dT.size:
        p50, p90, p95 = (np.percentile(dT * 1000.0, p) for p in (50, 90, 95))
        print(
            "[stability] step_mm p50={:.3f} p90={:.3f} p95={:.3f} max={:.3f}".format(
                float(p50),
                float(p90),
                float(p95),
                float(dT.max() * 1000.0),
            )
        )
    else:
        print("[stability] step_mm p50=n/a p90=n/a p95=n/a max=n/a")

    if tilt_col:
        tilt = df[tilt_col[0]].astype(float).to_numpy()
        dtilt = np.abs(np.diff(tilt))
        tilt_std = float((tilt - tilt.mean()).std())
        tilt_p90 = float(np.percentile(tilt, 90))
        tilt_max = float(np.max(tilt))
        print(
            "[stability] tilt_deg std={:.3f} p90={:.3f} max={:.3f}".format(
                tilt_std,
                tilt_p90,
                tilt_max,
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
