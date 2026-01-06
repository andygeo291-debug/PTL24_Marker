#!/usr/bin/env python3
"""Sanity-check the Dotec static camera extrinsics."""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import yaml


def load_T_WC(path: Path) -> np.ndarray:
    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    if not isinstance(data, dict) or "T_WC" not in data:
        raise ValueError("T_WC key not found in YAML.")
    arr = np.asarray(data["T_WC"], dtype=float)
    if arr.shape != (4, 4):
        raise ValueError(f"Expected 4x4 matrix, got shape {arr.shape}.")
    return arr


def rotation_to_ypr(R: np.ndarray) -> tuple[float, float, float]:
    """Return yaw, pitch, roll in degrees (world y is up)."""
    # camera forward in world = R^T * z_cam
    forward = R.T @ np.array([0.0, 0.0, 1.0])
    yaw = math.degrees(math.atan2(forward[0], forward[2]))
    pitch = math.degrees(math.atan2(-forward[1], math.hypot(forward[0], forward[2])))
    # roll from camera x/up; using standard Y (up) roll extraction
    up = R.T @ np.array([0.0, 1.0, 0.0])
    roll = math.degrees(math.atan2(up[0], up[1]))
    return yaw, pitch, roll


def main() -> int:
    path = Path(__file__).resolve().parents[1] / "extrinsics" / "T_WC.yaml"
    T = load_T_WC(path)
    R = T[:3, :3]
    t = T[:3, 3]

    # Camera position in world (C_W) from world->camera extrinsics.
    C = -R.T @ t
    horiz_dist = math.hypot(C[0], C[2])
    yaw, pitch, roll = rotation_to_ypr(R)

    print(f"T_WC loaded from: {path}")
    print(f"Camera position (world): x={C[0]:.4f} m, y={C[1]:.4f} m, z={C[2]:.4f} m")
    print(f"Horizontal distance to origin: {horiz_dist:.4f} m")
    print(f"Yaw={yaw:.2f} deg, Pitch={pitch:.2f} deg, Roll={roll:.2f} deg")
    print("\nChecks (approx):")
    print(f"  Height ~0.92 m -> {C[1]:.4f} m")
    print(f"  Horizontal distance ~1.10 m -> {horiz_dist:.4f} m")
    print(f"  Pitch ~-45 deg -> {pitch:.2f} deg")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
