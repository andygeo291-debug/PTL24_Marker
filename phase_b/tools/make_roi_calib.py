#!/usr/bin/env python3
"""Generate an ROI-adjusted calibration YAML by shifting the principal point."""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import yaml


def _parse_args():
    parser = argparse.ArgumentParser(description="Create an ROI-adjusted calibration YAML.")
    parser.add_argument(
        "--src",
        default="common/calib/basler_static_1280x980_mono8.yaml",
        help="Source calibration YAML (OpenCV-style).",
    )
    parser.add_argument(
        "--dst",
        default="common/calib/basler_static_960x720_offx320_offy200_mono8.yaml",
        help="Destination calibration YAML.",
    )
    parser.add_argument("--width", type=int, default=960, help="ROI width.")
    parser.add_argument("--height", type=int, default=720, help="ROI height.")
    parser.add_argument("--offx", type=int, default=320, help="ROI offset X.")
    parser.add_argument("--offy", type=int, default=200, help="ROI offset Y.")
    return parser.parse_args()


def _read_matrix(node, shape):
    if not isinstance(node, dict) or "data" not in node:
        raise ValueError("camera_matrix must include a data array.")
    data = np.asarray(node["data"], dtype=float)
    return data.reshape(shape)


def _read_dist(node):
    if not isinstance(node, dict) or "data" not in node:
        raise ValueError("distortion_coefficients must include a data array.")
    data = np.asarray(node["data"], dtype=float)
    return data.reshape(-1)


def _format_matrix(matrix):
    data = [float(v) for v in matrix.reshape(-1).tolist()]
    rows, cols = matrix.shape
    return {"rows": int(rows), "cols": int(cols), "data": data}


def _format_dist(dist):
    dist = dist.reshape(-1)
    return {"rows": 1, "cols": int(dist.size), "data": [float(v) for v in dist.tolist()]}


def main():
    args = _parse_args()
    src_path = Path(args.src)
    dst_path = Path(args.dst)

    data = yaml.safe_load(src_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Invalid calibration YAML.")

    if "camera_matrix" not in data or "distortion_coefficients" not in data:
        raise ValueError("Expected camera_matrix and distortion_coefficients in YAML.")

    K = _read_matrix(data["camera_matrix"], (3, 3))
    D = _read_dist(data["distortion_coefficients"])

    K2 = K.copy()
    K2[0, 2] -= float(args.offx)
    K2[1, 2] -= float(args.offy)

    out = {
        "image_width": int(args.width),
        "image_height": int(args.height),
        "camera_matrix": _format_matrix(K2),
        "distortion_coefficients": _format_dist(D),
    }

    dst_path.parent.mkdir(parents=True, exist_ok=True)
    dst_path.write_text(yaml.safe_dump(out, sort_keys=False), encoding="utf-8")

    print(f"Wrote {dst_path}")
    print("K2=")
    print(K2)
    print("D=", D.tolist())


if __name__ == "__main__":
    main()
