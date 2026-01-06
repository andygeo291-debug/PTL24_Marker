#!/usr/bin/env python3
"""Log camera motion relative to an AprilTag reference without altering Phase A."""

from __future__ import annotations

import argparse
import csv
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Optional

import cv2
import numpy as np
from pupil_apriltags import Detector

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from phase_a.apps.apriltag_demo import (  # type: ignore  # pylint: disable=import-error
    FrameGrabber,
    open_camera,
    resolve_intrinsics,
)
from phase_a.lib import calib_io  # type: ignore  # pylint: disable=import-error
from phase_a.lib.frames import compose_T, T_to_rpy_xyz  # type: ignore  # pylint: disable=import-error

DEFAULT_CONFIG = "phase_a/config.yaml"
DEFAULT_CSV = "sway_camera/data/sway_poses.csv"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Log camera motion relative to a reference AprilTag.")
    parser.add_argument("--config", default=DEFAULT_CONFIG, help="Path to Phase A style config.")
    parser.add_argument("--intrinsics", help="Optional intrinsics override file.")
    parser.add_argument("--cam", type=int, default=0, help="Camera index or path (default: 0).")
    parser.add_argument("--tag-family", default="tag36h11", help="AprilTag family to detect.")
    parser.add_argument("--tag-size", type=float, default=0.08, help="Tag edge length in meters.")
    parser.add_argument("--ref-id", type=int, help="Track only this tag ID when provided.")
    parser.add_argument("--out-csv", default=DEFAULT_CSV, help="Output CSV path.")
    parser.add_argument("--no-display", action="store_true", help="Disable OpenCV annotations.")
    return parser.parse_args()


def ensure_csv_writer(path: Path) -> tuple[csv.writer, any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    file_exists = path.exists() and path.stat().st_size > 0
    fp = open(path, "a", newline="", encoding="utf-8")
    writer = csv.writer(fp)
    if not file_exists:
        writer.writerow(["frame", "timestamp", "tag_id", "X", "Y", "Z", "roll", "pitch", "yaw", "dx", "dy", "dz"])
    return writer, fp


def select_detection(detections, ref_id: Optional[int]):
    if not detections:
        return None
    if ref_id is None:
        return detections[0]
    for det in detections:
        if int(det.tag_id) == ref_id:
            return det
    return None


def draw_overlay(frame, detection, dx: float, dy: float, dz: float) -> None:
    corners = detection.corners.astype(int)
    cv2.polylines(frame, [corners], True, (0, 255, 0), 2)
    text = f"dx={dx:.3f} dy={dy:.3f} dz={dz:.3f}"
    cv2.putText(frame, text, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)


def main() -> None:
    args = parse_args()
    config_path = Path(args.config)
    config = {}

    try:
        config = calib_io.load_config(config_path)
    except FileNotFoundError:
        print(f"[warn] Config file not found: {config_path}; proceeding with defaults.")
    except Exception as exc:  # noqa: BLE001
        print(f"[error] Failed to parse config {config_path}: {exc}")
        return

    base_dir = config_path.parent if args.config else None
    intr_args = SimpleNamespace(intrinsics=args.intrinsics)
    (fx, fy, cx, cy), _, _, _ = resolve_intrinsics(intr_args, config or None, base_dir)

    cap, cam_index = open_camera(args.cam)
    if cap is None:
        print(f"[error] Unable to open camera index {args.cam}.")
        return
    print(f"[info] Using camera index {cam_index}")

    grabber = FrameGrabber(cap).start()

    out_csv = Path(args.out_csv)
    csv_writer, csv_fp = ensure_csv_writer(out_csv)

    detector = Detector(
        families=args.tag_family,
        nthreads=1,
        refine_edges=True,
        decode_sharpening=0.25,
    )

    origin_pose = None
    frame_idx = 0

    try:
        while True:
            frame = grabber.read(timeout=1.0)
            if frame is None:
                print("[info] Frame grabber returned no frame; exiting.")
                break

            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            detections = detector.detect(
                gray,
                estimate_tag_pose=True,
                camera_params=[fx, fy, cx, cy],
                tag_size=args.tag_size,
            )

            detection = select_detection(detections, args.ref_id)
            if detection is None:
                print("[debug] No matching tag detected.")
                if not args.no_display:
                    cv2.imshow("Sway Motion", frame)
                    if cv2.waitKey(1) & 0xFF in (27, ord("q")):
                        break
                continue

            T_C_Tag = compose_T(detection.pose_R, detection.pose_t.reshape(3))
            T_WC = np.linalg.inv(T_C_Tag)

            if origin_pose is None:
                origin_pose = T_WC.copy()
            T_rel = np.linalg.inv(origin_pose) @ T_WC
            dx, dy, dz = T_rel[:3, 3]

            roll, pitch, yaw, X, Y, Z = T_to_rpy_xyz(T_WC)
            timestamp = time.time()
            tag_id = int(detection.tag_id)

            csv_writer.writerow([
                frame_idx,
                f"{timestamp:.6f}",
                tag_id,
                X,
                Y,
                Z,
                roll,
                pitch,
                yaw,
                float(dx),
                float(dy),
                float(dz),
            ])

            if not args.no_display:
                draw_overlay(frame, detection, dx, dy, dz)
                cv2.imshow("Sway Motion", frame)
                key = cv2.waitKey(1) & 0xFF
                if key in (27, ord("q")):
                    break

            frame_idx += 1
    finally:
        grabber.stop()
        cap.release()
        if not args.no_display:
            cv2.destroyAllWindows()
        csv_fp.close()
        print(f"[info] Logged {frame_idx} frames to {out_csv}")


if __name__ == "__main__":
    main()
