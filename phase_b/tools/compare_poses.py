#!/usr/bin/env python3
"""Compare two pose CSV files and report RMS differences."""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd


POSE_COLUMNS = [
    "rvec_cam_x",
    "rvec_cam_y",
    "rvec_cam_z",
    "tvec_cam_x",
    "tvec_cam_y",
    "tvec_cam_z",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compare v2 pose CSVs by RMS translation/rotation deltas.")
    parser.add_argument("--a", required=True, help="Reference pose CSV.")
    parser.add_argument("--b", required=True, help="Pose CSV to compare.")
    parser.add_argument(
        "--max-rows",
        type=int,
        help="Maximum number of rows to compare (defaults to min length).",
    )
    return parser.parse_args()


def rms(values: np.ndarray) -> float:
    values = np.asarray(values, dtype=np.float64)
    if values.size == 0:
        return float("nan")
    return float(np.sqrt(np.mean(np.square(values))))


def load_csv(path: str) -> pd.DataFrame:
    csv_path = Path(path).expanduser()
    if not csv_path.exists():
        raise SystemExit(f"CSV not found: {csv_path}")
    return pd.read_csv(csv_path, comment="#")


def ensure_columns(df: pd.DataFrame, path: str) -> None:
    missing = [col for col in POSE_COLUMNS if col not in df.columns]
    if missing:
        raise SystemExit(f"Columns {missing} missing from {path}")


def main() -> int:
    args = parse_args()
    df_a = load_csv(args.a)
    df_b = load_csv(args.b)
    ensure_columns(df_a, args.a)
    ensure_columns(df_b, args.b)

    total_rows = min(len(df_a), len(df_b))
    if args.max_rows is not None:
        total_rows = min(total_rows, max(0, args.max_rows))
    if total_rows <= 0:
        print("No overlapping rows to compare.")
        return 1

    slice_a = df_a.loc[: total_rows - 1, POSE_COLUMNS].to_numpy(dtype=np.float64)
    slice_b = df_b.loc[: total_rows - 1, POSE_COLUMNS].to_numpy(dtype=np.float64)
    diffs = slice_a - slice_b

    rms_r = [rms(diffs[:, idx]) for idx in range(3)]
    rms_t = [rms(diffs[:, idx]) for idx in range(3, 6)]

    print("RMS translation (camera frame, tvec_cam_* units):")
    print(f"  tvec_cam_x: {rms_t[0]:.6f}")
    print(f"  tvec_cam_y: {rms_t[1]:.6f}")
    print(f"  tvec_cam_z: {rms_t[2]:.6f}")
    print("\nRMS rotation (camera frame, Rodrigues components):")
    print(f"  rvec_cam_x: {rms_r[0]:.6f}")
    print(f"  rvec_cam_y: {rms_r[1]:.6f}")
    print(f"  rvec_cam_z: {rms_r[2]:.6f}")
    print(f"\nCompared N = {total_rows} rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
