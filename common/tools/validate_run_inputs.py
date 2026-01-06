#!/usr/bin/env python3
"""Validate camera index/resolution against calib before running Phase B."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import cv2
import yaml


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Validate camera index, resolution, and calibration.")
    ap.add_argument("--calib", required=True, type=Path, help="Path to intrinsics YAML.")
    ap.add_argument("--width", required=True, type=int, help="Requested capture width.")
    ap.add_argument("--height", required=True, type=int, help="Requested capture height.")
    ap.add_argument("--video", required=True, type=int, help="Video index to open.")
    return ap.parse_args()


def load_calib(path: Path):
    data = yaml.safe_load(path.read_text())
    cam = data.get("camera_matrix", {}).get("data", [])
    if len(cam) != 9:
        raise ValueError("camera_matrix missing or malformed")
    fx, fy = cam[0], cam[4]
    cx, cy = cam[2], cam[5]
    return fx, fy, cx, cy, data.get("image_width"), data.get("image_height")


def main() -> int:
    args = parse_args()
    if not args.calib.exists():
        print(f"ERROR: calib not found: {args.calib}")
        return 1

    try:
        fx, fy, cx, cy, img_w, img_h = load_calib(args.calib)
    except Exception as e:
        print(f"ERROR: failed to load calib {args.calib}: {e}")
        return 1

    print(f"Calib: fx={fx:.1f} fy={fy:.1f} cx={cx:.1f} cy={cy:.1f} (image {img_w}x{img_h})")
    cx_target = args.width / 2.0
    cy_target = args.height / 2.0
    if abs(cx - cx_target) > args.width * 0.1 or abs(cy - cy_target) > args.height * 0.1:
        print("WARNING: principal point far from center for requested resolution")
    if fx < args.width * 0.3 or fy < args.height * 0.3:
        print("WARNING: focal length looks too small; check calibration")

    cap = cv2.VideoCapture(args.video)
    if not cap.isOpened():
        print(f"ERROR: failed to open video index {args.video}")
        return 1
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, float(args.width))
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, float(args.height))
    ret, frame = cap.read()
    cap.release()
    if not ret or frame is None:
        print("ERROR: failed to grab frame from camera")
        return 1
    fh, fw = frame.shape[:2]
    print(f"Grabbed frame shape: {fw}x{fh}")
    if fw != args.width or fh != args.height:
        print("WARNING: grabbed frame does not match requested width/height (driver may be scaling)")
    else:
        print("Frame size matches requested width/height.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
