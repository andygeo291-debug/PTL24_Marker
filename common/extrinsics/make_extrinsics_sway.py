#!/usr/bin/env python3
"""Generate camera extrinsics T_WC from a sway-axis model."""

from __future__ import annotations

import argparse
import math
from pathlib import Path

import numpy as np
import yaml

from sway_camera.lib.sway_model import SwayModel, load_sway_model_yaml


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create extrinsics along the learned sway axis.")
    parser.add_argument("--sway-model", default="sway_camera/data/sway_model.yaml",
                        help="Path to sway model YAML (default: sway_camera/data/sway_model.yaml).")
    parser.add_argument("--sway-pos", type=float, required=True,
                        help="Scalar sway position along the model axis.")
    parser.add_argument("--cam-offset-x", type=float, default=0.0,
                        help="Camera offset in world X after applying sway position.")
    parser.add_argument("--cam-offset-y", type=float, default=0.0,
                        help="Camera offset in world Y after applying sway position.")
    parser.add_argument("--cam-offset-z", type=float, default=0.0,
                        help="Camera offset in world Z after applying sway position.")
    parser.add_argument("--yaw-deg", type=float, default=0.0, help="Yaw angle in degrees.")
    parser.add_argument("--pitch-deg", type=float, default=0.0, help="Pitch angle in degrees.")
    parser.add_argument("--roll-deg", type=float, default=0.0, help="Roll angle in degrees.")
    parser.add_argument("--out", default="common/extrinsics/T_WC.yaml",
                        help="Output YAML path for extrinsics.")
    return parser.parse_args()


def build_rotation(yaw: float, pitch: float, roll: float) -> np.ndarray:
    """Build R_WC using Z-Y-X (yaw-pitch-roll) convention."""
    cy, sy = math.cos(yaw), math.sin(yaw)
    cp, sp = math.cos(pitch), math.sin(pitch)
    cr, sr = math.cos(roll), math.sin(roll)

    Rz = np.array([[cy, -sy, 0.0],
                   [sy, cy, 0.0],
                   [0.0, 0.0, 1.0]], dtype=float)
    Ry = np.array([[cp, 0.0, sp],
                   [0.0, 1.0, 0.0],
                   [-sp, 0.0, cp]], dtype=float)
    Rx = np.array([[1.0, 0.0, 0.0],
                   [0.0, cr, -sr],
                   [0.0, sr, cr]], dtype=float)
    return Rz @ Ry @ Rx


def build_T_WC(p_C: np.ndarray, R_WC: np.ndarray) -> np.ndarray:
    """Combine rotation and translation into homogeneous T_WC."""
    T = np.eye(4, dtype=float)
    T[:3, :3] = R_WC
    T[:3, 3] = p_C
    return T


def save_T_WC_yaml(T_WC: np.ndarray, path: Path) -> None:
    """Write T_WC to YAML format expected by Phase B v2."""
    data = {"T_WC": T_WC.reshape(4, 4).tolist()}
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        yaml.safe_dump(data, fh, sort_keys=False)


def main() -> None:
    args = parse_args()

    model: SwayModel = load_sway_model_yaml(args.sway_model)
    s = args.sway_pos
    p_axis = model.p0 + s * model.d
    offset = np.array([args.cam_offset_x, args.cam_offset_y, args.cam_offset_z], dtype=float)
    p_C = p_axis + offset

    yaw = math.radians(args.yaw_deg)
    pitch = math.radians(args.pitch_deg)
    roll = math.radians(args.roll_deg)
    R_WC = build_rotation(yaw, pitch, roll)

    T_WC = build_T_WC(p_C, R_WC)
    save_T_WC_yaml(T_WC, Path(args.out))

    print(f"[info] Loaded sway model: {args.sway_model}")
    print(f"[info] Sway position s: {s}")
    print(f"[info] Camera position p_C: {p_C}")
    print(f"[info] T_WC first row: {T_WC[0]}")
    print(f"[info] Extrinsics saved to: {args.out}")


if __name__ == "__main__":
    main()
