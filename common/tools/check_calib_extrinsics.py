#!/usr/bin/env python3
"""Quick sanity check for calib + extrinsics."""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import yaml


def load_yaml(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def main() -> int:
    repo_root = Path(__file__).resolve().parents[2]
    calib_path = repo_root / "common" / "calib" / "calib.yaml"
    extr_path = repo_root / "common" / "extrinsics" / "T_WC.yaml"

    calib = load_yaml(calib_path)
    K = calib["camera_matrix"]["data"]
    fx, fy = float(K[0]), float(K[4])
    print(f"Calibration loaded from: {calib_path}")
    print(f"fx = {fx:.6f}  fy = {fy:.6f}")

    extr = load_yaml(extr_path)["T_WC"]
    rot = extr["rotation"]
    trans = extr["translation"]
    R = np.array(rot["data"], dtype=float).reshape(rot["rows"], rot["cols"])
    t = np.array(trans["data"], dtype=float).reshape(trans["rows"])

    print("\nExtrinsics T_WC loaded from:", extr_path)
    print("Rotation:\n", R)
    print("Translation (m):", t)

    # Orthonormality check
    ortho_err = np.linalg.norm(R @ R.T - np.eye(3))
    print(f"Orthonormality error ||R R^T - I||_F: {ortho_err:.3e}")

    dist = math.sqrt(float(np.dot(t, t)))
    print(f"Camera distance from origin: {dist:.4f} m")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
