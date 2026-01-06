#!/usr/bin/env python3
"""Estimate world-to-camera extrinsics from a floor chessboard."""

from __future__ import annotations

import argparse
import math
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

import cv2
import numpy as np
import yaml


@dataclass
class FrameResult:
    rvec: np.ndarray
    tvec: np.ndarray
    reproj_rmse: float


def load_calib(calib_path: Path) -> Tuple[np.ndarray, np.ndarray]:
    data = yaml.safe_load(calib_path.read_text(encoding="utf-8"))
    if data is None or "camera_matrix" not in data or "distortion_coefficients" not in data:
        raise ValueError(f"Calibration at {calib_path} missing required keys.")
    K = np.array(data["camera_matrix"]["data"], dtype=float).reshape(3, 3)
    dist = np.array(data["distortion_coefficients"]["data"], dtype=float).reshape(-1)
    return K, dist


def make_object_points(cols: int, rows: int, square_mm: float) -> np.ndarray:
    objp = np.zeros((cols * rows, 3), np.float32)
    grid = np.mgrid[0:cols, 0:rows].T.reshape(-1, 2)
    objp[:, :2] = grid * (square_mm / 1000.0)  # convert mm to meters
    return objp


def solve_frame(
    gray: np.ndarray,
    objp: np.ndarray,
    pattern_size: Tuple[int, int],
    K: np.ndarray,
    dist: np.ndarray,
) -> Optional[FrameResult]:
    found, corners = cv2.findChessboardCorners(
        gray,
        pattern_size,
        flags=cv2.CALIB_CB_ADAPTIVE_THRESH | cv2.CALIB_CB_NORMALIZE_IMAGE,
    )
    if not found:
        return None
    if corners.shape[0] < 4:
        return None
    cv2.cornerSubPix(gray, corners, (11, 11), (-1, -1), (
        cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER,
        30,
        0.001,
    ))
    success, rvec, tvec = cv2.solvePnP(
        objp, corners, K, dist, flags=cv2.SOLVEPNP_ITERATIVE
    )
    if not success:
        return None
    proj, _ = cv2.projectPoints(objp, rvec, tvec, K, dist)
    err = np.linalg.norm(proj.squeeze() - corners.squeeze(), axis=1).mean()
    return FrameResult(rvec=rvec.reshape(3), tvec=tvec.reshape(3), reproj_rmse=float(err))


def aggregate(results: List[FrameResult]) -> FrameResult:
    rvecs = np.stack([r.rvec for r in results], axis=0)
    tvecs = np.stack([r.tvec for r in results], axis=0)
    reproj = np.array([r.reproj_rmse for r in results], dtype=float)
    rvec_mean = np.median(rvecs, axis=0)
    tvec_mean = np.median(tvecs, axis=0)
    return FrameResult(rvec=rvec_mean, tvec=tvec_mean, reproj_rmse=float(reproj.mean()))


def to_T_wc(rvec: np.ndarray, tvec: np.ndarray) -> np.ndarray:
    R, _ = cv2.Rodrigues(rvec.astype(float))
    T = np.eye(4, dtype=float)
    T[:3, :3] = R
    T[:3, 3] = tvec.astype(float)
    return T


def camera_pose_world(T_wc: np.ndarray) -> Tuple[np.ndarray, float]:
    R_wc = T_wc[:3, :3]
    t_wc = T_wc[:3, 3]
    R_cw = R_wc.T
    cam_in_world = -R_cw @ t_wc
    height = cam_in_world[2]
    return cam_in_world, float(height)


def tilt_angles(T_wc: np.ndarray) -> Tuple[float, float]:
    """Return (angle_to_floor_normal_deg, down_tilt_from_normal_deg)."""
    R_cw = T_wc[:3, :3].T
    optical_axis_world = R_cw @ np.array([0.0, 0.0, 1.0])  # camera +Z -> world
    optical_axis_world /= np.linalg.norm(optical_axis_world) + 1e-9
    floor_normal = np.array([0.0, 0.0, 1.0])
    cos_angle = float(np.clip(optical_axis_world @ floor_normal, -1.0, 1.0))
    angle = math.degrees(math.acos(cos_angle))
    down_tilt = 180.0 - angle  # 180 => straight down, 90 => horizontal
    return float(angle), float(down_tilt)


def save_yaml(T_wc: np.ndarray, out_path: Path) -> None:
    data = {"T_WC": [[float(v) for v in row] for row in T_wc.tolist()]}
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Estimate world-to-camera extrinsics using a floor chessboard."
    )
    parser.add_argument("--video", type=int, default=0, help="Video index (e.g., 0, 1).")
    parser.add_argument("--width", type=int, default=1920, help="Capture width.")
    parser.add_argument("--height", type=int, default=1080, help="Capture height.")
    parser.add_argument("--fps", type=float, default=30.0, help="Capture FPS.")
    parser.add_argument("--calib", default="common/calib/calib.yaml", help="Intrinsics YAML.")
    parser.add_argument("--pattern-cols", type=int, default=9, help="Chessboard inner corners along columns.")
    parser.add_argument("--pattern-rows", type=int, default=6, help="Chessboard inner corners along rows.")
    parser.add_argument("--square-mm", type=float, default=24.0, help="Chessboard square size in millimeters.")
    parser.add_argument("--samples", type=int, default=8, help="Number of successful frames to average.")
    parser.add_argument("--out-yaml", default="common/extrinsics/T_WC.yaml", help="Output YAML path.")
    parser.add_argument("--no-display", action="store_true", help="Disable OpenCV window preview.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    calib_path = Path(args.calib)
    out_path = Path(args.out_yaml)
    K, dist = load_calib(calib_path)

    objp = make_object_points(args.pattern_cols, args.pattern_rows, args.square_mm)
    pattern_size = (args.pattern_cols, args.pattern_rows)

    cap = cv2.VideoCapture(args.video)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, float(args.width))
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, float(args.height))
    cap.set(cv2.CAP_PROP_FPS, float(args.fps))
    if not cap.isOpened():
        print(f"[error] Unable to open video source {args.video}", file=sys.stderr)
        return 1

    window = "extrinsics_floor" if not args.no_display else None
    if window:
        cv2.namedWindow(window, cv2.WINDOW_NORMAL)
    results: List[FrameResult] = []

    print("Place the chessboard flat on the FLOOR. World frame: X right, Y forward, Z up.")
    print("Collecting samples... (SPACE to capture, ESC to quit early)")
    while len(results) < args.samples:
        ret, frame = cap.read()
        if not ret or frame is None:
            print("[warn] Failed to grab frame; stopping.")
            break
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        result = solve_frame(gray, objp, pattern_size, K, dist)
        status = f"{len(results)}/{args.samples} frames"
        if result is not None:
            status += f" reproj={result.reproj_rmse:.2f}px"
        if not args.no_display:
            vis = frame.copy()
            cv2.putText(vis, status, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 200, 0), 2)
            cv2.imshow(window, vis)
            key = cv2.waitKey(1) & 0xFF
        else:
            key = cv2.waitKey(1) & 0xFF

        if result is not None:
            results.append(result)
            print(f"[info] Captured frame {len(results)} / {args.samples} (reproj {result.reproj_rmse:.3f}px)")
        if key == 27:  # ESC
            print("[info] ESC pressed; exiting capture loop.")
            break
        if key == 32 and result is None:
            print("[warn] Chessboard not found on this frame; try again.")

    cap.release()
    if window:
        cv2.destroyWindow(window)

    if not results:
        print("[error] No successful chessboard detections; nothing to save.", file=sys.stderr)
        return 2

    fused = aggregate(results)
    T_wc = to_T_wc(fused.rvec, fused.tvec)
    cam_world, height = camera_pose_world(T_wc)
    if height < 0:
        # Flip world frame about +X to force Z-up (common planar ambiguity).
        flip_rx = np.diag([1.0, -1.0, -1.0])
        T_wc[:3, :3] = T_wc[:3, :3] @ flip_rx
        cam_world, height = camera_pose_world(T_wc)
        print("[info] World Z was downward; flipped frame about +X to enforce Z up.")
    angle_up, tilt_down = tilt_angles(T_wc)

    save_yaml(T_wc, out_path)

    print("\n=== Extrinsics Result ===")
    print(f"Saved world-to-camera T_WC to: {out_path}")
    print(T_wc)
    print("\nCamera position in world (m):", np.round(cam_world, 4))
    print(f"Camera height above floor: {height:.4f} m")
    print(f"Angle vs floor normal (upward): {angle_up:.3f} deg")
    print(f"Downward tilt from floor normal: {tilt_down:.3f} deg (180=straight down, 90=horizontal)")
    per_frame = [r.reproj_rmse for r in results]
    print(f"Reprojection RMSE per frame (px): {[round(x,3) for x in per_frame]}")
    print(f"Mean reprojection RMSE: {fused.reproj_rmse:.3f} px over {len(results)} frames")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
