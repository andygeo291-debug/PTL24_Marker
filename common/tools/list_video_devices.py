#!/usr/bin/env python3
"""List usable video devices and basic capture properties (OpenCV).

Scans indices 0..N (default 10) and prints index, opened resolution/FPS, and
the first frame shape if available so we can pick the Logitech C920 reliably.
"""

from __future__ import annotations

import argparse
import platform
import subprocess
import sys
from typing import Optional

import cv2


def probe_device(
    idx: int, width: Optional[int], height: Optional[int], fps: Optional[float], grab_frame: bool
) -> None:
    cap = cv2.VideoCapture(idx)
    if not cap.isOpened():
        print(f"[{idx}] not available")
        return

    if width:
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, float(width))
    if height:
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, float(height))
    if fps:
        cap.set(cv2.CAP_PROP_FPS, float(fps))

    ret, frame = (False, None)
    if grab_frame:
        ret, frame = cap.read()

    actual_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
    actual_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
    actual_fps = cap.get(cv2.CAP_PROP_FPS) or 0.0
    msg = f"[{idx}] opened: {actual_w}x{actual_h} @ {actual_fps:.2f} fps"
    if grab_frame:
        if ret and frame is not None:
            msg += f" | frame shape: {frame.shape}"
        else:
            msg += " | frame grab failed"
    print(msg)
    cap.release()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="List available video devices via OpenCV.")
    parser.add_argument("--max-index", type=int, default=10, help="Highest device index to probe (inclusive).")
    parser.add_argument("--width", type=int, help="Try setting capture width.")
    parser.add_argument("--height", type=int, help="Try setting capture height.")
    parser.add_argument("--fps", type=float, help="Try setting capture FPS.")
    parser.add_argument(
        "--no-grab-frame",
        action="store_true",
        help="Skip grabbing a frame (by default we grab one to print its shape).",
    )
    parser.add_argument(
        "--use-ffmpeg",
        action="store_true",
        help="On macOS, also print avfoundation device list via ffmpeg before probing indices.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    if args.use_ffmpeg and platform.system() == "Darwin":
        print("ffmpeg avfoundation device list:")
        try:
            subprocess.run(
                ["ffmpeg", "-f", "avfoundation", "-list_devices", "true", "-i", ""],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.STDOUT,
            )
        except FileNotFoundError:
            print("WARNING: ffmpeg not found on PATH; skipping avfoundation listing.")

    for idx in range(args.max_index + 1):
        probe_device(idx, args.width, args.height, args.fps, grab_frame=not args.no_grab_frame)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
