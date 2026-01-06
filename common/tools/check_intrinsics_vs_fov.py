#!/usr/bin/env python3
"""Check capture size and FOV against intrinsics (helpful for Continuity Camera)."""

from __future__ import annotations

import argparse
import math
from pathlib import Path

import cv2
import yaml


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate intrinsics vs actual capture for a camera stream.")
    parser.add_argument("--video", type=int, default=0, help="Video index (e.g., 0, 1).")
    parser.add_argument("--width", type=int, help="Requested capture width.")
    parser.add_argument("--height", type=int, help="Requested capture height.")
    parser.add_argument("--fps", type=float, help="Requested FPS.")
    parser.add_argument(
        "--calib",
        default="common/calib/calib.yaml",
        help="Calibration YAML path (used to read fx/fy).",
    )
    parser.add_argument(
        "--frames",
        type=int,
        default=0,
        help="Number of frames to dump for a visual check (saved as PNG).",
    )
    parser.add_argument(
        "--out-dir",
        default="TEST_RUNS/PHASE_B_v2_15_dec/frames",
        help="Directory for dumped frames when --frames > 0.",
    )
    parser.add_argument(
        "--detections",
        type=int,
        default=3,
        help="How many frames to run AprilTag detection on (just to sanity check).",
    )
    return parser.parse_args()


def load_fx(calib_path: Path) -> tuple[float, float]:
    calib = yaml.safe_load(calib_path.read_text(encoding="utf-8"))
    K = calib["camera_matrix"]["data"]
    fx, fy = float(K[0]), float(K[4])
    return fx, fy


def main() -> int:
    args = parse_args()
    calib_path = Path(args.calib)
    if not calib_path.exists():
        print(f"[error] Calibration not found: {calib_path}")
        return 1

    fx, fy = load_fx(calib_path)
    print(f"Loaded calib: {calib_path}")
    print(f"fx={fx:.3f} fy={fy:.3f}")

    cap = cv2.VideoCapture(args.video)
    if args.width:
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, float(args.width))
    if args.height:
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, float(args.height))
    if args.fps:
        cap.set(cv2.CAP_PROP_FPS, float(args.fps))

    if not cap.isOpened():
        print(f"[error] Unable to open video source {args.video}")
        return 2

    ret, frame = cap.read()
    if not ret or frame is None:
        print("[error] Failed to grab initial frame.")
        cap.release()
        return 3

    h, w = frame.shape[:2]
    fov_x_rad = 2.0 * math.atan(w / (2.0 * fx))
    fov_x_deg = math.degrees(fov_x_rad)
    print(f"Captured frame size: {w}x{h}")
    print(f"Approx horizontal FOV (deg) from fx: {fov_x_deg:.3f}")

    try:
        from pupil_apriltags import Detector
    except ImportError:
        print("[warn] pupil_apriltags not installed; skipping detections.")
        Detector = None

    detector = Detector(families="tag36h11") if Detector else None
    frames_to_process = max(args.detections, args.frames)
    if args.frames > 0:
        Path(args.out_dir).mkdir(parents=True, exist_ok=True)

    for idx in range(frames_to_process):
        ret, frame = cap.read()
        if not ret or frame is None:
            print(f"[warn] Frame {idx} grab failed; stopping.")
            break
        if detector:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            dets = detector.detect(gray, estimate_tag_pose=False)
            print(f"[info] Frame {idx}: detected {len(dets)} tags")
        if args.frames > 0 and idx < args.frames:
            out_path = Path(args.out_dir) / f"frame_{idx:03d}.png"
            cv2.imwrite(str(out_path), frame)
            print(f"[info] Saved frame to {out_path}")

    cap.release()
    print("Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
