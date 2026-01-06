#!/usr/bin/env python3
"""
Augment Phase B pose CSVs with Euler angles derived from stored orientation data.
The script reads schema-v2 logs (quaternion columns) or legacy logs (Rodrigues
vectors), converts any available orientations to roll-pitch-yaw (ZYX, degrees),
and writes an updated CSV alongside a brief processing summary.
"""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path
from typing import Iterable, Optional, Sequence, Tuple

import cv2
import numpy as np
import pandas as pd


CAM_RVEC_COLS = ["rvec_cam_x", "rvec_cam_y", "rvec_cam_z"]
WORLD_RVEC_COLS = ["rvec_world_x", "rvec_world_y", "rvec_world_z"]
CAM_QUAT_COLS = ["qx", "qy", "qz", "qw"]
WORLD_QUAT_COLUMN_SETS: Sequence[Sequence[str]] = [
    ("quat_world_x", "quat_world_y", "quat_world_z", "quat_world_w"),
    ("qwx", "qwy", "qwz", "qww"),
]


def parse_args() -> argparse.Namespace:
    """Return command-line arguments for CSV augmentation."""
    parser = argparse.ArgumentParser(description="Augment Phase B pose CSV with Euler angles.")
    parser.add_argument("--source", required=True, help="Path to Phase B pose CSV.")
    parser.add_argument(
        "--out",
        help="Output CSV path (default: source directory with suffix _with_euler.csv).",
    )
    parser.add_argument(
        "--frame",
        choices=("camera", "world", "both"),
        default="both",
        help="Which frames to process (default: both).",
    )
    parser.add_argument(
        "--euler-order",
        choices=("zyx",),
        default="zyx",
        help="Euler convention (currently only ZYX).",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite output file if it already exists.",
    )
    return parser.parse_args()


def safe_out_path(source: Path, out: str | None, suffix: str = "_with_euler.csv") -> Path:
    """Derive the output path, defaulting to <source>_with_euler.csv."""
    if out:
        return Path(out)
    return source.with_name(source.stem + suffix)


def has_rvec_columns(df: pd.DataFrame, cols: Iterable[str]) -> bool:
    """Return True when every column in `cols` exists in the DataFrame."""
    return all(col in df.columns for col in cols)


def select_quat_columns(df: pd.DataFrame, candidate_sets: Sequence[Sequence[str]]) -> Optional[Sequence[str]]:
    """Return the first quaternion column set fully present in the DataFrame."""
    for cols in candidate_sets:
        if all(col in df.columns for col in cols):
            return cols
    return None


def euler_zyx_from_R(R: np.ndarray) -> Tuple[float, float, float]:
    """
    Convert rotation matrix to yaw/pitch/roll in degrees (ZYX order).

    ZYX corresponds to yaw about Z, pitch about Y, roll about X (right-handed).
    """
    sy = math.sqrt(R[0, 0] ** 2 + R[1, 0] ** 2)
    if sy > 1e-6:
        yaw = math.degrees(math.atan2(R[1, 0], R[0, 0]))
        pitch = math.degrees(math.atan2(-R[2, 0], sy))
        roll = math.degrees(math.atan2(R[2, 1], R[2, 2]))
    else:  # near gimbal lock
        yaw = math.degrees(math.atan2(-R[0, 1], R[1, 1]))
        pitch = math.degrees(math.atan2(-R[2, 0], sy))
        roll = 0.0
    # Normalize to [-180, 180)
    return tuple(((angle + 180.0) % 360.0) - 180.0 for angle in (yaw, pitch, roll))


def quaternion_to_rotation_matrix(quat: Sequence[float]) -> Optional[np.ndarray]:
    """Convert quaternion [x, y, z, w] to a 3x3 rotation matrix."""
    try:
        qx, qy, qz, qw = (float(val) for val in quat)
    except Exception:
        return None
    norm = math.sqrt(qx * qx + qy * qy + qz * qz + qw * qw)
    if norm < 1e-12:
        return None
    qx /= norm
    qy /= norm
    qz /= norm
    qw /= norm
    xx, yy, zz = qx * qx, qy * qy, qz * qz
    xy, xz, yz = qx * qy, qx * qz, qy * qz
    wx, wy, wz = qw * qx, qw * qy, qw * qz
    return np.array(
        [
            [1.0 - 2.0 * (yy + zz), 2.0 * (xy - wz), 2.0 * (xz + wy)],
            [2.0 * (xy + wz), 1.0 - 2.0 * (xx + zz), 2.0 * (yz - wx)],
            [2.0 * (xz - wy), 2.0 * (yz + wx), 1.0 - 2.0 * (xx + yy)],
        ],
        dtype=float,
    )


def compute_euler_from_rvec(row: pd.Series, prefix: str) -> Tuple[float, float, float]:
    """Compute ZYX Euler angles from a Rodrigues vector stored under `prefix`."""
    cols = [f"rvec_{prefix}_x", f"rvec_{prefix}_y", f"rvec_{prefix}_z"]
    if any(col not in row for col in cols):
        return (np.nan, np.nan, np.nan)
    try:
        rvec = row[cols].astype(float)
    except Exception:
        return (np.nan, np.nan, np.nan)
    if pd.isna(rvec).any():
        return (np.nan, np.nan, np.nan)
    rvec_arr = np.asarray(rvec, dtype=float).reshape(3, 1)
    if np.isnan(rvec_arr).any():
        return (np.nan, np.nan, np.nan)
    R, _ = cv2.Rodrigues(rvec_arr)
    return euler_zyx_from_R(R)


def compute_euler_from_quat(row: pd.Series, cols: Sequence[str]) -> Tuple[float, float, float]:
    """Compute ZYX Euler angles from quaternion columns."""
    try:
        quat = [float(row[col]) for col in cols]
    except Exception:
        return (np.nan, np.nan, np.nan)
    if any(math.isnan(val) for val in quat):
        return (np.nan, np.nan, np.nan)
    R = quaternion_to_rotation_matrix(quat)
    if R is None:
        return (np.nan, np.nan, np.nan)
    return euler_zyx_from_R(R)


def append_euler_columns(df: pd.DataFrame, which: str) -> Tuple[pd.DataFrame, int]:
    """Append Euler columns for the requested frame (`camera` or `world`)."""
    prefix = "cam" if which == "camera" else "world"
    yaw_col = f"yaw_{prefix}_deg"
    pitch_col = f"pitch_{prefix}_deg"
    roll_col = f"roll_{prefix}_deg"

    quat_cols: Optional[Sequence[str]] = None
    if which == "camera":
        if all(col in df.columns for col in CAM_QUAT_COLS):
            quat_cols = CAM_QUAT_COLS
    else:
        quat_cols = select_quat_columns(df, WORLD_QUAT_COLUMN_SETS)

    rvec_cols = CAM_RVEC_COLS if which == "camera" else WORLD_RVEC_COLS

    added = 0
    yaw_list: list[float] = []
    pitch_list: list[float] = []
    roll_list: list[float] = []

    if quat_cols is None and not has_rvec_columns(df, rvec_cols):
        filled = df.assign(
            **{yaw_col: np.nan, pitch_col: np.nan, roll_col: np.nan}
        )
        return filled, added

    for idx, row in df.iterrows():
        if quat_cols is not None:
            yaw_deg, pitch_deg, roll_deg = compute_euler_from_quat(row, quat_cols)
        else:
            yaw_deg, pitch_deg, roll_deg = compute_euler_from_rvec(row, prefix)
        if not any(np.isnan([yaw_deg, pitch_deg, roll_deg])):
            added += 1
        yaw_list.append(yaw_deg)
        pitch_list.append(pitch_deg)
        roll_list.append(roll_deg)

    df = df.assign(**{yaw_col: yaw_list, pitch_col: pitch_list, roll_col: roll_list})
    return df, added


def main() -> int:
    """CLI entry point."""
    args = parse_args()

    source_path = Path(args.source)
    if not source_path.exists():
        print(f"[error] Source CSV not found: {source_path}", file=sys.stderr)
        return 1

    out_path = safe_out_path(source_path, args.out)
    if out_path.exists() and not args.overwrite:
        print(f"[error] Output exists ({out_path}). Use --overwrite to replace.", file=sys.stderr)
        return 1

    try:
        df = pd.read_csv(source_path)
    except Exception as exc:
        print(f"[error] Failed to read CSV: {exc}", file=sys.stderr)
        return 1

    total_rows = len(df)
    if total_rows == 0:
        print("[warn] Source CSV is empty; nothing to do.")
        return 1

    frames_to_process: list[str] = []
    if args.frame in ("camera", "both"):
        frames_to_process.append("camera")
    if args.frame in ("world", "both"):
        frames_to_process.append("world")

    camera_added = 0
    world_added = 0

    if "camera" in frames_to_process:
        camera_quat_present = all(col in df.columns for col in CAM_QUAT_COLS)
        camera_rvec_present = has_rvec_columns(df, CAM_RVEC_COLS)
        if not (camera_quat_present or camera_rvec_present):
            print("[error] Camera orientation columns missing; cannot compute camera Euler.", file=sys.stderr)
            if args.frame == "camera":
                return 1
            frames_to_process.remove("camera")
        else:
            df, camera_added = append_euler_columns(df, "camera")

    if "world" in frames_to_process:
        world_quat_present = select_quat_columns(df, WORLD_QUAT_COLUMN_SETS)
        world_rvec_present = has_rvec_columns(df, WORLD_RVEC_COLS)
        if world_quat_present is None and not world_rvec_present:
            print("[warn] World rotation columns missing; skipping world Euler.")
        else:
            df, world_added = append_euler_columns(df, "world")

    if camera_added == 0 and world_added == 0:
        print("[error] No Euler angles could be computed.", file=sys.stderr)
        return 1

    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_path, index=False)

    print(f"[info] Source: {source_path}")
    print(f"[info] Rows processed: {total_rows}")
    print(f"[info] Camera Euler added: {camera_added}")
    print(f"[info] World Euler added: {world_added}")
    print(f"[info] Output: {out_path}")
    print(f"✅ Euler CSV → {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
