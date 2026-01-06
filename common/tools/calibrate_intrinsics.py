#!/usr/bin/env python3
"""
Capture checkerboard images and estimate camera intrinsics.

Supports OpenCV and Basler backends via the shared camera abstraction.
Default pattern: 9x6 inner corners, square size 0.025 m.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import List, Optional, Tuple

import cv2
import numpy as np

THIS_FILE = Path(__file__).resolve()
REPO_ROOT = THIS_FILE.parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from common.camera.factory import add_camera_cli_args, create_basler_from_args
from common.camera.opencv_cam import OpenCVCaptureAdapter


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Calibrate camera intrinsics using a checkerboard.")
    parser.add_argument(
        "--pattern",
        default="9x6",
        help="Checkerboard inner corners as COLSxROWS (default: 9x6).",
    )
    parser.add_argument(
        "--square-size-m",
        type=float,
        default=0.025,
        help="Square size in meters (default: 0.025).",
    )
    parser.add_argument(
        "--num-images",
        type=int,
        default=30,
        help="Number of successful detections to collect (default: 30).",
    )
    parser.add_argument("--width", type=int, help="Requested capture width (pixels).")
    parser.add_argument("--height", type=int, help="Requested capture height (pixels).")
    parser.add_argument("--fps", type=float, help="Requested capture FPS.")
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("common/calib/basler_static_1280x980_mono8.yaml"),
        help="Output YAML path for intrinsics (default: common/calib/basler_static_1280x980_mono8.yaml).",
    )
    parser.add_argument(
        "--video",
        default=0,
        help='OpenCV video source when using --camera-backend opencv (default: 0).',
    )
    parser.add_argument(
        "--preview",
        action="store_true",
        help="Show live preview while capturing (ESC to abort).",
    )
    add_camera_cli_args(parser)
    return parser.parse_args()


def parse_pattern(pattern: str) -> Tuple[int, int]:
    try:
        cols, rows = pattern.lower().split("x")
        return int(cols), int(rows)
    except Exception as exc:  # pylint: disable=broad-except
        raise ValueError(f"Invalid pattern '{pattern}', expected format COLSxROWS like 9x6") from exc


def make_object_points(cols: int, rows: int, square_size: float) -> np.ndarray:
    objp = np.zeros((cols * rows, 3), np.float32)
    objp[:, :2] = np.mgrid[0:cols, 0:rows].T.reshape(-1, 2)
    objp *= square_size
    return objp


def save_yaml(path: Path, K: np.ndarray, dist: np.ndarray, image_size: Tuple[int, int]) -> None:
    data = {
        "camera_matrix": {"rows": 3, "cols": 3, "data": K.reshape(-1).tolist()},
        "distortion_coefficients": {
            "rows": 1,
            "cols": int(dist.size),
            "data": dist.reshape(-1).tolist(),
        },
        "image_width": int(image_size[0]),
        "image_height": int(image_size[1]),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    import yaml  # local import to keep dependency optional

    with path.open("w", encoding="utf-8") as fp:
        yaml.safe_dump(data, fp)


def open_camera(args: argparse.Namespace):
    if args.camera_backend == "basler":
        cam = create_basler_from_args(args)
        if not cam.open():
            raise RuntimeError("Failed to open Basler camera.")
        return cam, None
    cap = cv2.VideoCapture(args.video)
    if not cap.isOpened():
        raise RuntimeError(f"Failed to open video source: {args.video}")
    cam = OpenCVCaptureAdapter(cap, frame_format=args.frame_format)
    if not cam.open():
        raise RuntimeError("Failed to initialize OpenCV capture adapter.")
    return cam, cap


def main() -> None:
    args = parse_args()
    cols, rows = parse_pattern(args.pattern)
    objp_template = make_object_points(cols, rows, args.square_size_m)
    cam, cap = open_camera(args)

    objpoints: List[np.ndarray] = []
    imgpoints: List[np.ndarray] = []
    image_size: Optional[Tuple[int, int]] = None
    criteria = (
        cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER,
        30,
        0.001,
    )

    print(f"[info] Collecting checkerboard {cols}x{rows}, square={args.square_size_m} m")
    print(f"[info] Need {args.num_images} good detections. Press ESC to abort.")

    try:
        while len(objpoints) < args.num_images:
            ok, frame = cam.read_frame()
            if not ok or frame is None:
                print("[warn] Frame grab failed; retrying...")
                continue

            gray = frame if frame.ndim == 2 else cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            found, corners = cv2.findChessboardCorners(gray, (cols, rows), None)
            if found:
                corners_subpix = cv2.cornerSubPix(
                    gray,
                    corners,
                    winSize=(11, 11),
                    zeroZone=(-1, -1),
                    criteria=criteria,
                )
                objpoints.append(objp_template.copy())
                imgpoints.append(corners_subpix)
                if image_size is None:
                    image_size = (gray.shape[1], gray.shape[0])
                print(f"[ok] Detected {len(objpoints)}/{args.num_images}")
                if args.preview:
                    vis = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
                    cv2.drawChessboardCorners(vis, (cols, rows), corners_subpix, True)
                    cv2.imshow("calibration", vis)
                    cv2.waitKey(1)
            else:
                if args.preview:
                    cv2.imshow("calibration", frame)
                    key = cv2.waitKey(1) & 0xFF
                    if key == 27:  # ESC
                        print("[info] Aborted by user.")
                        return
            if args.preview and cv2.waitKey(1) & 0xFF == 27:
                print("[info] Aborted by user.")
                return

        if image_size is None:
            raise RuntimeError("No valid detections collected; cannot calibrate.")

        rms, K, dist, _, _ = cv2.calibrateCamera(
            objpoints,
            imgpoints,
            image_size,
            None,
            None,
        )
        fx, fy, cx, cy = K[0, 0], K[1, 1], K[0, 2], K[1, 2]
        save_yaml(args.out, K, dist, image_size)
        print(f"[done] RMS reprojection error: {rms:.4f} px")
        print(f"[done] Image size: {image_size[0]}x{image_size[1]}")
        print(f"[done] fx={fx:.3f} fy={fy:.3f} cx={cx:.3f} cy={cy:.3f}")
        print(f"[done] Saved: {args.out}")
    finally:
        if cam:
            cam.close()
        if cap:
            try:
                cap.release()
            except Exception:
                pass
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
