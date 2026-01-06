#!/usr/bin/env python3
"""Attempt to lock down Logitech C920 controls on macOS via OpenCV.

Best-effort: macOS drivers often ignore manual exposure/white balance/focus,
so we print warnings whenever a control is not honored and log all attempts to JSON.
"""

from __future__ import annotations

import argparse
import json
import math
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple

import cv2


def tol_equal(expected: float, actual: float, tol: float = 0.05) -> bool:
    """Compare values with a relative tolerance; handles zero gracefully."""
    if math.isnan(actual):
        return False
    scale = max(abs(expected), 1.0)
    return abs(actual - expected) <= tol * scale


def set_prop(cap: cv2.VideoCapture, prop: int, value: float, name: str) -> Dict[str, Any]:
    """Set a property and capture set/get status for logging."""
    set_ok = bool(cap.set(prop, float(value)))
    readback = cap.get(prop)
    return {"name": name, "prop_id": prop, "requested": value, "set_ok": set_ok, "readback": readback}


def attempt_lock(cap: cv2.VideoCapture, name: str, auto_prop: int, manual_prop: int, target: float) -> Dict[str, Any]:
    """Disable auto then set a manual value; return combined status."""
    steps: List[Dict[str, Any]] = []
    steps.append(set_prop(cap, auto_prop, 0.0, f"{name}_auto"))
    steps.append(set_prop(cap, manual_prop, target, name))
    auto_ok = tol_equal(0.0, steps[0]["readback"])
    manual_ok = tol_equal(target, steps[1]["readback"])
    applied = steps[0]["set_ok"] and steps[1]["set_ok"] and auto_ok and manual_ok
    warning = not applied
    return {
        "name": name,
        "requested": target,
        "auto_step": steps[0],
        "manual_step": steps[1],
        "applied": applied,
        "warning": warning,
        "message": "OK" if applied else "macOS driver ignored or clamped value",
    }


def attempt_single(cap: cv2.VideoCapture, name: str, prop: int, target: float) -> Dict[str, Any]:
    """Set a single property (e.g., zoom) with warning if ignored."""
    step = set_prop(cap, prop, target, name)
    applied = step["set_ok"] and tol_equal(target, step["readback"])
    return {
        "name": name,
        "requested": target,
        "auto_step": None,
        "manual_step": step,
        "applied": applied,
        "warning": not applied,
        "message": "OK" if applied else "macOS driver ignored or clamped value",
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Lock Logitech C920 controls (best-effort on macOS).")
    parser.add_argument("--video", type=int, default=0, help="Video index for the C920.")
    parser.add_argument("--width", type=int, help="Optional capture width to request.")
    parser.add_argument("--height", type=int, help="Optional capture height to request.")
    parser.add_argument("--fps", type=float, help="Optional capture FPS to request.")
    parser.add_argument("--focus", type=float, default=0.0, help="Manual focus value to request (driver-specific units).")
    parser.add_argument("--exposure", type=float, default=-6.0, help="Manual exposure value to request (driver-specific units).")
    parser.add_argument("--wb-temp", type=float, default=4500.0, help="Manual white balance temperature (Kelvin).")
    parser.add_argument("--zoom", type=float, default=0.0, help="Digital zoom to request (0 disables if supported).")
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("TEST_RUNS/configure_webcam_c920_log.json"),
        help="Where to write the JSON log.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    cap = cv2.VideoCapture(args.video)
    if not cap.isOpened():
        print(f"ERROR: could not open video index {args.video}")
        return 1

    if args.width:
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, float(args.width))
    if args.height:
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, float(args.height))
    if args.fps:
        cap.set(cv2.CAP_PROP_FPS, float(args.fps))

    ret, frame = cap.read()
    frame_shape: Tuple[int, ...] | None = frame.shape if ret and frame is not None else None

    actual = {
        "width": int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0),
        "height": int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0),
        "fps": cap.get(cv2.CAP_PROP_FPS) or 0.0,
    }
    print(f"Opened video {args.video}: {actual['width']}x{actual['height']} @ {actual['fps']:.2f} fps")
    if frame_shape:
        print(f"First frame shape: {frame_shape}")
    else:
        print("WARNING: failed to grab a frame for shape inspection")

    attempts = [
        attempt_lock(cap, "focus", cv2.CAP_PROP_AUTOFOCUS, cv2.CAP_PROP_FOCUS, args.focus),
        attempt_lock(cap, "exposure", cv2.CAP_PROP_AUTO_EXPOSURE, cv2.CAP_PROP_EXPOSURE, args.exposure),
        attempt_lock(cap, "white_balance", cv2.CAP_PROP_AUTO_WB, cv2.CAP_PROP_WB_TEMPERATURE, args.wb_temp),
        attempt_single(cap, "digital_zoom", cv2.CAP_PROP_ZOOM, args.zoom),
    ]

    cap.release()

    any_warn = False
    for entry in attempts:
        status = "OK" if entry["applied"] else "WARNING"
        if entry["warning"]:
            any_warn = True
        rb = entry["manual_step"]["readback"] if entry["manual_step"] else None
        print(f"{status}: {entry['name']} requested={entry['requested']} readback={rb}")
        if entry["warning"]:
            print(f"  -> WARNING: {entry['message']} (macOS may not expose this control)")

    log = {
        "timestamp": datetime.now().isoformat(),
        "video_index": args.video,
        "requested": {"width": args.width, "height": args.height, "fps": args.fps},
        "actual": actual,
        "frame_shape": frame_shape,
        "attempts": attempts,
        "notes": "macOS often ignores manual exposure/white balance/focus; see warnings above.",
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(log, indent=2))
    print(f"Wrote log to {args.out}")
    if any_warn:
        print("Some properties were ignored by macOS; keep lighting fixed or use Logi Tune to force manual settings.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
