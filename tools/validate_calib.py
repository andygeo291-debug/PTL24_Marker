#!/usr/bin/env python3
import argparse
from pathlib import Path
from typing import Any, Dict

import numpy as np
import yaml


def _as_matrix(node: Dict[str, Any]) -> np.ndarray:
    rows = int(node["rows"])
    cols = int(node["cols"])
    data = node["data"]
    return np.array(data, dtype=float).reshape(rows, cols)


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate calibration YAML.")
    parser.add_argument("--yaml", required=True, help="Calibration YAML path.")
    parser.add_argument(
        "--rms-threshold",
        type=float,
        default=1.5,
        help="Warn if RMS reprojection error exceeds this value (px).",
    )
    args = parser.parse_args()

    path = Path(args.yaml)
    if not path.exists():
        raise SystemExit(f"YAML not found: {path}")

    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    K = _as_matrix(payload["camera_matrix"])
    dist = _as_matrix(payload["distortion_coefficients"])
    w = payload.get("image_width")
    h = payload.get("image_height")

    print(f"image_size: {w}x{h}")
    print("camera_matrix:")
    print(K)
    print("distortion_coefficients:")
    print(dist.reshape(-1))

    rms = None
    meta = payload.get("metadata", {})
    if isinstance(meta, dict):
        rms = meta.get("reprojection_error_px")
    if rms is None:
        rms = payload.get("reprojection_error_px")

    if rms is None:
        print("WARNING: reprojection_error_px not found in YAML.")
        return 1

    rms_val = float(rms)
    print(f"reprojection_error_px: {rms_val:.6f}")
    if rms_val > args.rms_threshold:
        print(
            f"WARNING: RMS {rms_val:.3f} exceeds threshold {args.rms_threshold:.3f}"
        )
        return 1

    print("RMS OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
