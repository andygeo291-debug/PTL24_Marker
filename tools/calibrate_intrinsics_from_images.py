#!/usr/bin/env python3
import argparse
import glob
import os
import time
from pathlib import Path
from typing import List, Tuple

# Disable OpenCL before importing OpenCV to avoid macOS crashes.
os.environ.setdefault("OPENCV_OPENCL_RUNTIME", "disabled")

import cv2
import numpy as np
import yaml


def _disable_opencv_opencl() -> None:
    # Avoid OpenCL crashes on some macOS OpenCV builds.
    try:
        if hasattr(cv2, "ocl"):
            cv2.ocl.setUseOpenCL(False)
        if hasattr(cv2, "setUseOptimized"):
            cv2.setUseOptimized(False)
        if hasattr(cv2, "setNumThreads"):
            cv2.setNumThreads(1)
    except Exception:
        pass


def _format_matrix(mat: np.ndarray) -> dict:
    return {
        "rows": int(mat.shape[0]),
        "cols": int(mat.shape[1]),
        "dt": "d",
        "data": [float(v) for v in mat.reshape(-1).tolist()],
    }


def _format_dist(dist: np.ndarray) -> dict:
    dist = dist.reshape(1, -1) if dist.ndim == 1 else dist
    return {
        "rows": int(dist.shape[0]),
        "cols": int(dist.shape[1]),
        "dt": "d",
        "data": [float(v) for v in dist.reshape(-1).tolist()],
    }


def _write_yaml(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(payload, f, sort_keys=False)


def _collect_images(images_dir: Path) -> List[Path]:
    patterns = ["*.png", "*.jpg", "*.jpeg", "*.bmp", "*.tiff"]
    files: List[Path] = []
    for pattern in patterns:
        files.extend(Path(p) for p in glob.glob(str(images_dir / pattern)))
    return sorted(files)


def main() -> None:
    parser = argparse.ArgumentParser(description="Chessboard intrinsics calibration from images.")
    parser.add_argument(
        "--images-dir",
        required=True,
        help="Directory containing calibration images.",
    )
    parser.add_argument(
        "--cols",
        type=int,
        default=9,
        help="Number of INNER corners across (columns).",
    )
    parser.add_argument(
        "--rows",
        type=int,
        default=6,
        help="Number of INNER corners down (rows).",
    )
    parser.add_argument(
        "--square-size-m",
        type=float,
        default=0.025,
        help="Square size in meters (e.g. 0.025 for 25mm).",
    )
    parser.add_argument(
        "--out-yaml",
        default="common/calib/basler_static_960x720_offx320_offy200_mono8_11mm.yaml",
        help="Output YAML path.",
    )

    args = parser.parse_args()
    _disable_opencv_opencl()
    images_dir = Path(args.images_dir)
    if not images_dir.exists():
        raise SystemExit(f"Images dir not found: {images_dir}")

    print("Chessboard calibration from images")
    print(f"- images_dir: {images_dir}")
    print(f"- inner corners: {args.cols}x{args.rows}")
    print(f"- square size: {args.square_size_m:.6f} m")
    print("Instructions:")
    print("- Use 40-80 images with varied angles/distances.")
    print("- Ensure the full board is visible and sharp.")

    image_paths = _collect_images(images_dir)
    if not image_paths:
        raise SystemExit("No images found.")

    objp = np.zeros((args.rows * args.cols, 3), np.float32)
    objp[:, :2] = np.mgrid[0 : args.cols, 0 : args.rows].T.reshape(-1, 2)
    objp *= float(args.square_size_m)

    obj_points: List[np.ndarray] = []
    img_points: List[np.ndarray] = []
    image_size: Tuple[int, int] | None = None

    use_sb = hasattr(cv2, "findChessboardCornersSB")
    term = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.001)

    for path in image_paths:
        img = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
        if img is None:
            print(f"Skipping unreadable image: {path}")
            continue
        if image_size is None:
            image_size = (img.shape[1], img.shape[0])

        if use_sb:
            found, corners = cv2.findChessboardCornersSB(img, (args.cols, args.rows), None)
        else:
            found, corners = cv2.findChessboardCorners(img, (args.cols, args.rows), None)
        if not found or corners is None:
            continue

        corners = cv2.cornerSubPix(img, corners, (11, 11), (-1, -1), term)
        obj_points.append(objp)
        img_points.append(corners)

    if len(obj_points) < 10:
        raise SystemExit(f"Not enough valid samples ({len(obj_points)}). Need at least 10.")

    assert image_size is not None
    rms, K, dist, _, _ = cv2.calibrateCamera(
        obj_points,
        img_points,
        image_size,
        None,
        None,
    )

    payload = {
        "image_width": int(image_size[0]),
        "image_height": int(image_size[1]),
        "camera_matrix": _format_matrix(K),
        "distortion_coefficients": _format_dist(dist),
        "metadata": {
            "timestamp": float(time.time()),
            "images_dir": str(images_dir),
            "board_cols": int(args.cols),
            "board_rows": int(args.rows),
            "square_size_m": float(args.square_size_m),
            "reprojection_error_px": float(rms),
            "samples_used": int(len(obj_points)),
        },
    }

    out_yaml = Path(args.out_yaml)
    _write_yaml(out_yaml, payload)

    fx = K[0, 0]
    fy = K[1, 1]
    cx = K[0, 2]
    cy = K[1, 2]
    dist_list = [float(v) for v in dist.reshape(-1).tolist()]

    print("Calibration complete")
    print(f"RMS reprojection error: {rms:.6f}")
    print(f"samples used: {len(obj_points)} image_size: {image_size[0]}x{image_size[1]}")
    print(f"fx={fx:.3f} fy={fy:.3f} cx={cx:.3f} cy={cy:.3f}")
    print(f"dist={dist_list}")
    print(f"Wrote {out_yaml}")


if __name__ == "__main__":
    main()
