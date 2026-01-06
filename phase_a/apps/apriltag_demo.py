# apriltag_demo.py
"""
Phase A: Marker-Based Detection
--------------------------------

Example (run from repo root)
============================
python phase_a/apps/apriltag_demo.py --config phase_a/config.yaml --camera-pose-mode manual --log-csv phase_a/data/poses.csv

# One-time PnP to estimate camera extrinsics
python phase_a/apps/apriltag_demo.py --estimate-extrinsics \
  --points phase_a/data/world_points.yaml \
  --image-points phase_a/data/image_points.yaml \
  --save phase_a/data/T_WC.yaml \
  --intrinsics phase_a/data/camera_intrinsics.npz

# Run with saved extrinsics (PnP mode)
python phase_a/apps/apriltag_demo.py --config phase_a/config.yaml --camera-pose-mode pnp --extrinsics-file phase_a/data/T_WC.yaml
"""

from __future__ import annotations

import argparse
import csv
import math
import queue
import socket
import sys
import threading
import time
from collections import deque
from contextlib import suppress
from pathlib import Path
from typing import Dict

import cv2
import numpy as np
import simplejson as sjson
from pupil_apriltags import Detector

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from phase_a.lib import calib_io
from phase_a.lib.frames import compose_T, T_to_rpy_xyz, build_T_WC_from_config, rvec_tvec_to_T

# json is kept imported for compatibility with downstream scripts that expect it.
import json  # noqa: F401  # pylint: disable=unused-import

PHASE_A_ROOT = Path(__file__).resolve().parents[1]
PHASE_A_DATA = PHASE_A_ROOT / "data"
COMMON_CALIB = PROJECT_ROOT / "common" / "calib" / "calib.yaml"

WINDOW_NAME = "AprilTag Pose"
LOW_CONF_MARGIN = 30.0
LAT_AVG_WINDOW = 30
DEFAULT_INTRINSICS = (600.0, 600.0, 320.0, 240.0)


def parse_args() -> argparse.Namespace:
    """Command-line interface to adjust detector, camera pose, and tooling behaviour."""
    parser = argparse.ArgumentParser(description="AprilTag detection with world-frame pose output.")

    # Detection & runtime configuration
    parser.add_argument("--config", help="YAML/JSON config describing intrinsics/extrinsics.")
    parser.add_argument("--camera-pose-mode", choices=("manual", "pnp"), default="manual",
                        help="How to obtain camera extrinsics T_W_C.")
    parser.add_argument("--extrinsics-file", help="Path to saved T_W_C (used with --camera-pose-mode pnp).")
    parser.add_argument("--cam", type=int, default=0, help="Primary camera index (default 0).")
    parser.add_argument("--tag-family", default="tag36h11", help="AprilTag family to detect.")
    parser.add_argument("--tag-size", type=float, default=0.08, help="Printed tag edge size in meters.")
    parser.add_argument("--json-host", default="127.0.0.1",
                        help="UDP host for JSON output (empty string disables UDP).")
    parser.add_argument("--json-port", type=int, default=5005, help="UDP port for JSON output.")
    parser.add_argument("--no-axes", action="store_true", help="Disable 3D axes overlay.")
    parser.add_argument("--save-json", default="", help="Optional path to append JSONL telemetry.")
    parser.add_argument("--log-csv", default="", help="Optional CSV log path for world-frame poses.")
    parser.add_argument("--fps", type=int, default=30, help="Target display FPS (controls waitKey delay).")
    parser.add_argument("--exposure-lock", action="store_true", help="Attempt to lock exposure (best effort).")
    parser.add_argument("--focus-lock", action="store_true", help="Attempt to lock focus (best effort).")
    parser.add_argument("--ema", type=float, default=0.3, help="EMA alpha for pose smoothing (0 disables).")
    parser.add_argument("--ref-id", type=int, default=None,
                        help="Optional reference tag ID. Marks detections with frame='ref'.")
    parser.add_argument("--intrinsics", help="Override intrinsics file (YAML/JSON/NPZ).")

    # One-shot utilities
    parser.add_argument("--estimate-extrinsics", action="store_true",
                        help="Run PnP to estimate camera pose and exit.")
    parser.add_argument("--points", help="World points file (Nx3 or Nx2) for PnP.")
    parser.add_argument("--image-points", help="Image points file (Nx2) for PnP.")
    parser.add_argument("--save", help="Output path for generated extrinsics.")

    return parser.parse_args()


def resolve_path(base: Path | None, candidate: str | None) -> str | None:
    if not candidate:
        return None
    path = Path(candidate)
    if not path.is_absolute() and base is not None:
        path = base / path
    return str(path)


def resolve_intrinsics(args: argparse.Namespace, config: dict | None, base_dir: Path | None):
    """Return ((fx,fy,cx,cy), K, dist, used_fallback) from config/CLI/npz fallback."""
    if config:
        try:
            K, dist = calib_io.load_intrinsics_from_config(config)
            fx, fy, cx, cy = float(K[0, 0]), float(K[1, 1]), float(K[0, 2]), float(K[1, 2])
            return (fx, fy, cx, cy), K, dist, False
        except KeyError:
            pass

    if args.intrinsics:
        intr_path = resolve_path(base_dir, args.intrinsics)
        if intr_path is None:
            raise FileNotFoundError("Unable to resolve intrinsics path.")
        suffix = Path(intr_path).suffix.lower()
        if suffix == ".npz":
            K, dist = calib_io.load_intrinsics_npz(intr_path)
        else:
            cfg = calib_io.load_config(intr_path)
            K, dist = calib_io.load_intrinsics_from_config(cfg)
        fx, fy, cx, cy = float(K[0, 0]), float(K[1, 1]), float(K[0, 2]), float(K[1, 2])
        return (fx, fy, cx, cy), K, dist, False

    try:
        data = np.load(PHASE_A_DATA / "camera_intrinsics.npz")
        params = (float(data["fx"]), float(data["fy"]), float(data["cx"]), float(data["cy"]))
        return params, data["K"], data["dist"], False
    except Exception:
        pass

    if COMMON_CALIB.exists():
        cfg = calib_io.load_config(COMMON_CALIB)
        if "camera" in cfg:
            K, dist = calib_io.load_intrinsics_from_config(cfg)
        else:
            K = np.array(cfg["K"], dtype=float)
            dist_vals = cfg.get("dist", cfg.get("D", []))
            dist = np.array(dist_vals, dtype=float).reshape(-1, 1)
            if dist.size == 0:
                dist = np.zeros((5, 1))
        fx, fy, cx, cy = float(K[0, 0]), float(K[1, 1]), float(K[0, 2]), float(K[1, 2])
        return (fx, fy, cx, cy), K, dist, False

    fx, fy, cx, cy = DEFAULT_INTRINSICS
    return (fx, fy, cx, cy), None, np.zeros((5, 1)), True


def determine_camera_pose(args: argparse.Namespace, config: dict | None, base_dir: Path | None) -> np.ndarray:
    """Build camera extrinsics from config/manual fields or on-disk extrinsics."""
    if args.camera_pose_mode == "manual":
        if not config:
            print("[warn] Manual mode requested but no config provided; assuming identity T_W_C.")
            return np.eye(4, dtype=float)
        try:
            pose = calib_io.load_world_pose(config)
        except KeyError as exc:
            print(f"[warn] {exc}; using identity for T_W_C.")
            return np.eye(4, dtype=float)
        return build_T_WC_from_config(pose)

    # PnP mode
    extr_path = args.extrinsics_file
    if not extr_path and config:
        extr_path = config.get("mode", {}).get("extrinsics_file")
    extr_path = resolve_path(base_dir, extr_path)
    if not extr_path:
        raise FileNotFoundError("PNP mode requires --extrinsics-file or mode.extrinsics_file in config.")
    return calib_io.load_extrinsics(extr_path)


def open_camera(primary_index: int) -> tuple[cv2.VideoCapture | None, int | None]:
    """Open the requested camera, retrying with index+1 once."""
    for index in (primary_index, primary_index + 1):
        cap = cv2.VideoCapture(index)
        if cap.isOpened():
            if index != primary_index:
                print(f"[warn] Camera {primary_index} unavailable; using index {index} instead.")
            return cap, index
        cap.release()
    return None, None


def apply_camera_controls(cap: cv2.VideoCapture, exposure_lock: bool, focus_lock: bool) -> None:
    """Best-effort exposure/focus adjustments; ignore failures."""
    if exposure_lock:
        with suppress(Exception):
            cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, 0.25)
            cap.set(cv2.CAP_PROP_EXPOSURE, -4)
    if focus_lock:
        with suppress(Exception):
            cap.set(cv2.CAP_PROP_AUTOFOCUS, 0)


def ema_update(prev: np.ndarray | None, new: np.ndarray, alpha: float) -> np.ndarray:
    """Return the exponential moving average, defaulting to the new value."""
    if prev is None or alpha <= 0.0:
        return new
    return (alpha * new) + ((1.0 - alpha) * prev)


class FrameGrabber:
    """Background reader that keeps the most recent webcam frame."""

    def __init__(self, cap: cv2.VideoCapture):
        self.cap = cap
        self.queue: queue.Queue[np.ndarray | None] = queue.Queue(maxsize=1)
        self._stopped = threading.Event()
        self._thread = threading.Thread(target=self._worker, daemon=True)

    def start(self) -> "FrameGrabber":
        self._thread.start()
        return self

    def stop(self) -> None:
        self._stopped.set()
        with suppress(queue.Full):
            self.queue.put_nowait(None)
        if self._thread.is_alive():
            self._thread.join(timeout=1.0)

    def read(self, timeout: float = 1.0) -> np.ndarray | None:
        try:
            return self.queue.get(timeout=timeout)
        except queue.Empty:
            return None

    def _worker(self) -> None:
        while not self._stopped.is_set():
            ok, frame = self.cap.read()
            if not ok:
                with suppress(queue.Full):
                    self.queue.put_nowait(None)
                break
            if self.queue.full():
                with suppress(queue.Empty):
                    self.queue.get_nowait()
            try:
                self.queue.put(frame, timeout=0.1)
            except queue.Full:
                continue


def format_packet(detections: list[dict], status: str, fps_avg: float) -> str:
    return sjson.dumps({"detections": detections, "status": status, "fps": fps_avg})


def ensure_csv_writer(path: str) -> tuple[csv.writer | None, any]:
    if not path:
        return None, None
    csv_path = Path(path)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    file_exists = csv_path.exists() and csv_path.stat().st_size > 0
    fp = open(csv_path, "a", newline="", encoding="utf-8")
    writer = csv.writer(fp)
    if not file_exists:
        writer.writerow(["frame", "tag_id", "X", "Y", "Z", "roll", "pitch", "yaw"])
    return writer, fp


def estimate_extrinsics_cli(args: argparse.Namespace, base_dir: Path | None) -> None:
    world_path = resolve_path(base_dir, args.points)
    image_path = resolve_path(base_dir, args.image_points)
    intr_path = resolve_path(base_dir, args.intrinsics)
    save_path = resolve_path(base_dir, args.save)

    if not all([world_path, image_path, intr_path, save_path]):
        raise ValueError("PnP estimation requires --points, --image-points, --intrinsics, and --save.")

    world_pts = calib_io.load_points(world_path)
    if world_pts.shape[1] == 2:
        world_pts = np.hstack([world_pts, np.zeros((world_pts.shape[0], 1), dtype=float)])
    image_pts = calib_io.load_points(image_path)
    if image_pts.shape[1] != 2:
        raise ValueError("image_points must be Nx2.")

    suffix = Path(intr_path).suffix.lower()
    if suffix == ".npz":
        K, dist = calib_io.load_intrinsics_npz(intr_path)
    else:
        intr_cfg = calib_io.load_config(intr_path)
        K, dist = calib_io.load_intrinsics_from_config(intr_cfg)

    world_pts = world_pts.astype(float)
    image_pts = image_pts.astype(float)

    flag = cv2.SOLVEPNP_IPPE_SQUARE if world_pts.shape[0] >= 4 else cv2.SOLVEPNP_ITERATIVE
    success, rvec, tvec = cv2.solvePnP(world_pts, image_pts, K, dist, flags=flag)
    if not success:
        success, rvec, tvec = cv2.solvePnP(world_pts, image_pts, K, dist, flags=cv2.SOLVEPNP_ITERATIVE)
    if not success:
        raise RuntimeError("solvePnP failed to converge.")

    projected, _ = cv2.projectPoints(world_pts, rvec, tvec, K, dist)
    projected = projected.reshape(-1, 2)
    errors = np.linalg.norm(projected - image_pts, axis=1)
    rms = float(math.sqrt(np.mean(errors ** 2)))

    T_C_W = rvec_tvec_to_T(rvec, tvec)
    T_W_C = np.linalg.inv(T_C_W)
    calib_io.save_extrinsics(save_path, T_W_C)

    roll, pitch, yaw, x, y, z = T_to_rpy_xyz(T_W_C)
    print(f"[PnP] RMS reprojection error: {rms:.4f} px")
    print(f"[PnP] Camera world pose -> x={x:.3f} y={y:.3f} z={z:.3f} roll={roll:.3f} pitch={pitch:.3f} yaw={yaw:.3f}")
    print(f"[PnP] Extrinsics saved to {save_path}")


def main() -> None:
    args = parse_args()

    if args.estimate_extrinsics:
        config_base = Path(args.config).parent if args.config else None
        estimate_extrinsics_cli(args, config_base)
        return

    if not 0.03 <= args.tag_size <= 0.30:
        print(f"[warn] tag_size {args.tag_size:.3f} m is outside the suggested [0.03, 0.30] range.",
              file=sys.stderr)

    config = None
    base_dir = None
    if args.config:
        cfg_path = Path(args.config)
        try:
            config = calib_io.load_config(cfg_path)
        except FileNotFoundError:
            print(f"[error] Config file not found: {cfg_path}")
            return
        except Exception as exc:  # YAML parse errors, etc.
            print(f"[error] Failed to load config {cfg_path}: {exc}")
            return
        base_dir = cfg_path.parent

    (fx, fy, cx, cy), K, dist, used_fallback = resolve_intrinsics(args, config, base_dir)
    T_W_C = determine_camera_pose(args, config, base_dir)

    det = Detector(families=args.tag_family, nthreads=2,
                   quad_decimate=1.0, quad_sigma=0.0, refine_edges=True)

    cap, _ = open_camera(args.cam)
    if cap is None:
        print(f"[error] Unable to open camera indices {args.cam} or {args.cam + 1}.")
        return

    apply_camera_controls(cap, args.exposure_lock, args.focus_lock)
    grabber = FrameGrabber(cap).start()

    udp_sock = None
    if args.json_host:
        udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        udp_sock.setblocking(False)

    json_fp = open(args.save_json, "a", encoding="utf-8") if args.save_json else None
    csv_writer, csv_fp = ensure_csv_writer(args.log_csv)

    show_axes = not args.no_axes
    ema_states: Dict[int, Dict[str, np.ndarray | float]] = {}
    latency_ms_history: deque[float] = deque(maxlen=LAT_AVG_WINDOW)
    fps_history: deque[float] = deque(maxlen=LAT_AVG_WINDOW)
    last_frame_time: float | None = None

    wait_delay = max(1, int(1000 / max(1, args.fps)))
    print("ESC or 'q' = quit, SPACE = toggle axes")

    frame_index = 0

    try:
        while True:
            frame = grabber.read(timeout=1.0)
            if frame is None:
                print("[warn] Frame grabber returned no frame; exiting.")
                break

            frame_ts = time.time()
            if last_frame_time is not None:
                delta = frame_ts - last_frame_time
                if delta > 0:
                    fps_history.append(1.0 / delta)
            last_frame_time = frame_ts
            fps_avg = sum(fps_history) / len(fps_history) if fps_history else 0.0

            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

            t0 = time.perf_counter()
            dets = det.detect(
                gray,
                estimate_tag_pose=True,
                camera_params=(fx, fy, cx, cy),
                tag_size=args.tag_size,
            )
            dt_ms = (time.perf_counter() - t0) * 1000.0
            latency_ms_history.append(dt_ms)
            latency_avg = sum(latency_ms_history) / len(latency_ms_history) if latency_ms_history else 0.0

            detections_json = []
            status = "no_tag"

            for detection in dets:
                corners = detection.corners.astype(int)
                for i in range(4):
                    p1 = tuple(corners[i - 1])
                    p2 = tuple(corners[i])
                    cv2.line(frame, p1, p2, (0, 255, 0), 2)

                R_cam = detection.pose_R
                t_cam = detection.pose_t.reshape(3)
                yaw_cam = math.atan2(R_cam[1, 0], R_cam[0, 0])

                tag_id = int(detection.tag_id)
                T_C_Tag = compose_T(R_cam, t_cam)
                T_W_Tag = T_W_C @ T_C_Tag
                roll_w, pitch_w, yaw_w, X, Y, Z = T_to_rpy_xyz(T_W_Tag)

                ema_alpha = args.ema
                prev = ema_states.get(tag_id)

                cam_t = t_cam.astype(float)
                world_t = np.array([X, Y, Z], dtype=float)
                world_rpy = np.array([roll_w, pitch_w, yaw_w], dtype=float)

                smooth_cam_t = ema_update(prev["cam_t"] if prev else None, cam_t, ema_alpha)
                smooth_cam_yaw = float(ema_alpha * yaw_cam + (1.0 - ema_alpha) * prev["cam_yaw"]) \
                    if prev and ema_alpha > 0 else yaw_cam
                smooth_world_t = ema_update(prev["world_t"] if prev else None, world_t, ema_alpha)
                smooth_world_rpy = ema_update(prev["world_rpy"] if prev else None, world_rpy, ema_alpha)

                ema_states[tag_id] = {
                    "cam_t": smooth_cam_t,
                    "cam_yaw": smooth_cam_yaw,
                    "world_t": smooth_world_t,
                    "world_rpy": smooth_world_rpy,
                }

                if K is not None and show_axes:
                    rvec_for_axes, _ = cv2.Rodrigues(R_cam)
                    dist_coeffs = dist.ravel() if dist is not None else np.zeros(5)
                    cv2.drawFrameAxes(frame, K, dist_coeffs, rvec_for_axes, t_cam, 0.05)

                overlay = f"id {tag_id} W({X:.2f},{Y:.2f},{Z:.2f}) yaw {yaw_w:.2f}"
                cv2.putText(
                    frame,
                    overlay,
                    (int(corners[0][0]), int(corners[0][1] - 10)),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.5,
                    (0, 255, 255),
                    1,
                )

                detection_json = {
                    "id": tag_id,
                    "pose": {"x": float(cam_t[0]), "y": float(cam_t[1]), "z": float(cam_t[2]), "yaw": yaw_cam},
                    "pose_smooth": {
                        "x": float(smooth_cam_t[0]),
                        "y": float(smooth_cam_t[1]),
                        "z": float(smooth_cam_t[2]),
                        "yaw": smooth_cam_yaw,
                    },
                    "world": {"X": X, "Y": Y, "Z": Z, "roll": roll_w, "pitch": pitch_w, "yaw": yaw_w},
                    "world_smooth": {
                        "X": float(smooth_world_t[0]),
                        "Y": float(smooth_world_t[1]),
                        "Z": float(smooth_world_t[2]),
                        "roll": float(smooth_world_rpy[0]),
                        "pitch": float(smooth_world_rpy[1]),
                        "yaw": float(smooth_world_rpy[2]),
                    },
                    "conf": float(detection.decision_margin),
                    "latency_ms": dt_ms,
                    "ts": frame_ts,
                    "frame": "ref" if args.ref_id is not None and tag_id == args.ref_id else "camera",
                }
                detections_json.append(detection_json)

                if csv_writer:
                    csv_writer.writerow([
                        frame_index,
                        tag_id,
                        X,
                        Y,
                        Z,
                        roll_w,
                        pitch_w,
                        yaw_w,
                    ])

            if detections_json:
                max_conf = max(det["conf"] for det in detections_json)
                status = "ok" if max_conf >= LOW_CONF_MARGIN else "low_conf"
            else:
                status = "no_tag"

            fps_inst = fps_history[-1] if fps_history else 0.0
            cv2.putText(
                frame,
                f"FPS {fps_inst:.1f} avg {fps_avg:.1f}   tags {len(detections_json)}",
                (10, 20),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                (255, 255, 255),
                2,
            )
            cv2.putText(
                frame,
                f"Latency {dt_ms:.1f} ms avg {latency_avg:.1f} ms",
                (10, 45),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                (255, 255, 255),
                1,
            )
            if used_fallback:
                cv2.putText(
                    frame,
                    "USING FALLBACK INTRINSICS",
                    (10, 70),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.6,
                    (0, 255, 255),
                    2,
                )
            if status == "low_conf":
                cv2.putText(
                    frame,
                    "LOW CONFIDENCE TAGS",
                    (10, 95),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.5,
                    (0, 140, 255),
                    2,
                )

            packet_str = format_packet(detections_json, status, fps_avg)

            if udp_sock and args.json_host:
                with suppress(OSError):
                    udp_sock.sendto(packet_str.encode("utf-8"), (args.json_host, args.json_port))
            if json_fp:
                json_fp.write(packet_str + "\n")

            if detections_json:
                print(packet_str, flush=True)

            cv2.imshow(WINDOW_NAME, frame)
            if cv2.getWindowProperty(WINDOW_NAME, cv2.WND_PROP_VISIBLE) < 1:
                print("[info] Window closed by user.")
                break

            key = cv2.waitKey(wait_delay) & 0xFF
            if key in (27, ord("q")):
                break
            if key == 32 and not args.no_axes:
                show_axes = not show_axes

            frame_index += 1
    except KeyboardInterrupt:
        pass
    finally:
        grabber.stop()
        cap.release()
        cv2.destroyAllWindows()
        if udp_sock:
            udp_sock.close()
        if json_fp:
            json_fp.close()
        if csv_fp:
            csv_fp.close()
        print("[i] Closed camera and windows.")


if __name__ == "__main__":
    main()
