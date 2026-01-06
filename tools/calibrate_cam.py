#!/usr/bin/env python3
"""Interactive chessboard-based camera calibration utility."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List, Tuple

import cv2
import numpy as np
import yaml


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Interactive camera calibration via chessboard shots.")
    parser.add_argument("--video", type=int, default=0, help="Video capture index (default: 0).")
    parser.add_argument("--width", type=int, help="Requested capture width.")
    parser.add_argument("--height", type=int, help="Requested capture height.")
    parser.add_argument("--fps", type=float, help="Requested FPS.")
    parser.add_argument("--pattern-cols", type=int, default=9, help="Chessboard inner corners along columns (default: 9).")
    parser.add_argument("--pattern-rows", type=int, default=6, help="Chessboard inner corners along rows (default: 6).")
    parser.add_argument("--square-mm", type=float, default=24.0, help="Chessboard square size in millimeters (default: 24).")
    parser.add_argument("--shots", type=int, default=30, help="Number of successful captures required (default: 30).")
    parser.add_argument("--out-yaml", default="common/calib/out.yaml", help="Output calibration YAML path.")
    return parser.parse_args()


def create_object_points(cols: int, rows: int, square_mm: float) -> np.ndarray:
    objp = np.zeros((rows * cols, 3), np.float32)
    grid = np.mgrid[0:cols, 0:rows].T.reshape(-1, 2)
    objp[:, :2] = grid * square_mm
    return objp


def save_yaml(path: Path, image_size: Tuple[int, int], camera_matrix: np.ndarray, dist_coeffs: np.ndarray) -> None:
    data = {
        "image_width": int(image_size[0]),
        "image_height": int(image_size[1]),
        "camera_matrix": {
            "rows": 3,
            "cols": 3,
            "data": camera_matrix.reshape(-1).tolist(),
        },
        "distortion_coefficients": {
            "rows": 1,
            "cols": len(dist_coeffs.reshape(-1)),
            "data": dist_coeffs.reshape(-1).tolist(),
        },
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fp:
        yaml.safe_dump(data, fp, sort_keys=False)


def main() -> int:
    args = parse_args()
    cap = cv2.VideoCapture(args.video)
    if args.width:
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, float(args.width))
    if args.height:
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, float(args.height))
    if args.fps:
        cap.set(cv2.CAP_PROP_FPS, float(args.fps))

    if not cap.isOpened():
        print(f"[error] Unable to open video source {args.video}", file=sys.stderr)
        return 1

    obj_points: List[np.ndarray] = []
    img_points: List[np.ndarray] = []
    obj_template = create_object_points(args.pattern_cols, args.pattern_rows, args.square_mm)
    target = args.shots
    window = "calibrate_cam"
    cv2.namedWindow(window, cv2.WINDOW_NORMAL)

    termination = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.001)

    print("Instructions:")
    print("  - Press SPACE to capture a frame when the chessboard is visible.")
    print("  - Press ESC to exit early.")

    while True:
        ret, frame = cap.read()
        if not ret:
            print("[warn] Frame grab failed, terminating.")
            break
        vis = frame.copy()
        status = f"Shots: {len(obj_points)}/{target}  (SPACE=capture, ESC=quit)"
        cv2.putText(vis, status, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
        cv2.imshow(window, vis)
        key = cv2.waitKey(1) & 0xFF
        if key == 27:  # ESC
            print("[info] ESC pressed; exiting capture loop.")
            break
        if key == 32:  # SPACE
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            found, corners = cv2.findChessboardCorners(
                gray,
                (args.pattern_cols, args.pattern_rows),
                cv2.CALIB_CB_ADAPTIVE_THRESH | cv2.CALIB_CB_NORMALIZE_IMAGE,
            )
            if not found:
                print("[warn] Chessboard not detected; try again.")
                continue
            cv2.cornerSubPix(gray, corners, (11, 11), (-1, -1), termination)
            obj_points.append(obj_template.copy())
            img_points.append(corners)
            print(f"[info] Captured frame {len(obj_points)}/{target}")
            if len(obj_points) >= target:
                print("[info] Target number of shots reached.")
                break

    cap.release()
    cv2.destroyAllWindows()

    if len(obj_points) < 3:
        print("[error] Need at least 3 successful captures for calibration.", file=sys.stderr)
        return 2

    image_size = (frame.shape[1], frame.shape[0]) if "frame" in locals() else (
        int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0),
        int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0),
    )
    ret, camera_matrix, dist_coeffs, _, _ = cv2.calibrateCamera(
        obj_points, img_points, image_size, None, None
    )

    dist_flat = dist_coeffs.reshape(-1)
    print(
        "[result] RMS={:.4f} fx={:.3f} fy={:.3f} cx={:.3f} cy={:.3f}".format(
            ret,
            camera_matrix[0, 0],
            camera_matrix[1, 1],
            camera_matrix[0, 2],
            camera_matrix[1, 2],
        )
    )
    print(
        "[result] Distortion coefficients: k1={:.6f} k2={:.6f} p1={:.6f} p2={:.6f} k3={:.6f}".format(
            *(dist_flat.tolist() + [0.0] * (5 - len(dist_flat)))
        )
    )

    save_yaml(Path(args.out_yaml), image_size, camera_matrix, dist_coeffs)
    print(f"[info] Calibration saved to {args.out_yaml}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
