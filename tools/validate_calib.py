#!/usr/bin/env python3
"""Validate calibration YAML by checking reprojection error on chessboard images."""

from __future__ import annotations

import argparse
import glob
import os
from pathlib import Path
from typing import List, Tuple

os.environ.setdefault("OPENCV_OPENCL_RUNTIME", "disabled")

import cv2
import numpy as np
import yaml


def _disable_opencv_opencl() -> None:
    try:
        if hasattr(cv2, "ocl"):
            cv2.ocl.setUseOpenCL(False)
        if hasattr(cv2, "setUseOptimized"):
            cv2.setUseOptimized(False)
        if hasattr(cv2, "setNumThreads"):
            cv2.setNumThreads(1)
    except Exception:
        pass


def _collect_images(images_dir: Path) -> List[Path]:
    patterns = ["*.png", "*.jpg", "*.jpeg", "*.bmp", "*.tiff"]
    files: List[Path] = []
    for pattern in patterns:
        files.extend(Path(p) for p in glob.glob(str(images_dir / pattern)))
    return sorted(files)


def _load_calib(path: Path) -> Tuple[np.ndarray, np.ndarray, Tuple[int, int] | None, dict]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    K = np.array(data["camera_matrix"]["data"], dtype=float).reshape(3, 3)
    dist = np.array(data["distortion_coefficients"]["data"], dtype=float).reshape(1, -1)
    image_size = None
    if "image_width" in data and "image_height" in data:
        image_size = (int(data["image_width"]), int(data["image_height"]))
    return K, dist, image_size, data


def _detect_corners(gray: np.ndarray, cols: int, rows: int):
    if hasattr(cv2, "findChessboardCornersSB"):
        found, corners = cv2.findChessboardCornersSB(gray, (cols, rows), None)
    else:
        found, corners = cv2.findChessboardCorners(gray, (cols, rows), None)
    if not found or corners is None:
        return None
    term = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.001)
    corners = cv2.cornerSubPix(gray, corners, (11, 11), (-1, -1), term)
    return corners


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a calibration YAML using chessboard images.")
    parser.add_argument("--calib", required=True, help="Calibration YAML path.")
    parser.add_argument("--images-dir", default=None, help="Directory containing calibration images.")
    parser.add_argument("--cols", type=int, default=9, help="Inner corners across.")
    parser.add_argument("--rows", type=int, default=6, help="Inner corners down.")
    parser.add_argument("--square-size-m", type=float, default=0.025, help="Square size in meters.")
    args = parser.parse_args()

    _disable_opencv_opencl()
    calib_path = Path(args.calib)
    K, dist, image_size, payload = _load_calib(calib_path)

    images_dir = Path(args.images_dir) if args.images_dir else None
    if images_dir is None:
        meta = payload.get("metadata", {}) if isinstance(payload, dict) else {}
        meta_dir = meta.get("images_dir")
        if meta_dir:
            images_dir = Path(meta_dir)

    if images_dir is None or not images_dir.exists():
        rms = None
        meta = payload.get("metadata", {}) if isinstance(payload, dict) else {}
        if "reprojection_error_px" in meta:
            rms = float(meta["reprojection_error_px"])
            print(f"Calibration: {calib_path}")
            print(f"Stored reprojection_error_px: {rms:.6f}")
            return 0
        raise SystemExit("Images dir not found and no reprojection_error_px in metadata.")

    image_paths = _collect_images(images_dir)
    if not image_paths:
        raise SystemExit(f"No images found in: {images_dir}")

    objp = np.zeros((args.rows * args.cols, 3), np.float32)
    objp[:, :2] = np.mgrid[0 : args.cols, 0 : args.rows].T.reshape(-1, 2)
    objp *= float(args.square_size_m)

    all_errors = []
    used = 0
    for path in image_paths:
        img = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
        if img is None:
            continue
        if image_size and (img.shape[1], img.shape[0]) != image_size:
            print(f"[warn] size mismatch for {path} ({img.shape[1]}x{img.shape[0]})")
        corners = _detect_corners(img, args.cols, args.rows)
        if corners is None:
            continue
        ok, rvec, tvec = cv2.solvePnP(objp, corners, K, dist, flags=cv2.SOLVEPNP_ITERATIVE)
        if not ok:
            continue
        proj, _ = cv2.projectPoints(objp, rvec, tvec, K, dist)
        err = np.linalg.norm(corners.reshape(-1, 2) - proj.reshape(-1, 2), axis=1)
        all_errors.extend(err.tolist())
        used += 1

    if not all_errors:
        raise SystemExit("No valid detections; cannot compute reprojection error.")

    rms = float(np.sqrt(np.mean(np.square(all_errors))))
    print(f"Calibration: {calib_path}")
    print(f"Images used: {used}/{len(image_paths)}")
    print(f"RMS reprojection error (px): {rms:.6f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
