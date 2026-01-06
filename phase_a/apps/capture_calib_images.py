from __future__ import annotations

import argparse
import time
from pathlib import Path
import sys

import cv2

THIS_FILE = Path(__file__).resolve()
REPO_ROOT = THIS_FILE.parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from common.camera.factory import add_camera_cli_args, create_basler_from_args
from common.camera.opencv_cam import OpenCVCaptureAdapter

PHASE_A_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT_DIR = PHASE_A_ROOT / "assets" / "calib_images"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Capture chessboard images for camera calibration.")
    parser.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_OUT_DIR,
        help="Directory for captured images (default: phase_a/assets/calib_images).",
    )
    parser.add_argument(
        "--camera-index",
        type=int,
        default=0,
        help="Camera index to open (default: 0).",
    )
    parser.add_argument("--width", type=int, help="Requested capture width.")
    parser.add_argument("--height", type=int, help="Requested capture height.")
    parser.add_argument("--fps", type=float, help="Requested capture FPS.")
    add_camera_cli_args(parser)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    out_dir = args.out
    out_dir.mkdir(parents=True, exist_ok=True)

    cam = None
    cap = None
    if args.camera_backend == "basler":
        cam = create_basler_from_args(args)
        if not cam.open():
            print("Basler camera not available. Check connection and parameters.")
            raise SystemExit(1)
        print("[i] Using Basler backend.")
    else:
        cap = cv2.VideoCapture(args.camera_index)
        if not cap.isOpened():
            print("Camera not available. Try a different index or grant camera permission.")
            raise SystemExit(1)
        cam = OpenCVCaptureAdapter(cap, frame_format=args.frame_format)
        if not cam.open():
            print("Failed to initialize OpenCV capture.")
            raise SystemExit(1)
        print(f"[i] Using OpenCV backend (index {args.camera_index}).")

    print("[i] Press SPACE to save a frame, q to quit.")
    existing = [
        path for path in out_dir.iterdir() if path.suffix.lower() in {".png", ".jpg", ".jpeg"}
    ]
    count = len(existing)

    try:
        while True:
            ok, frame = cam.read_frame()
            if not ok or frame is None:
                print("Failed to read from camera.")
                break

            timestamp = time.strftime("%H:%M:%S")
            cv2.putText(
                frame,
                timestamp,
                (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX,
                1.0,
                (0, 255, 0),
                2,
                cv2.LINE_AA,
            )

            cv2.imshow("Calibration capture (SPACE=save, q=quit)", frame)
            key = cv2.waitKey(1) & 0xFF
            if key == ord(" "):  # SPACE
                fname = out_dir / f"calib_{count:03d}.png"
                cv2.imwrite(str(fname), frame)
                print(f"Saved {fname}")
                count += 1
            elif key == ord("q"):
                break
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
