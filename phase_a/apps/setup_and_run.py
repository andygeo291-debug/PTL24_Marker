#!/usr/bin/env python3
"""Helper to prepare config/extrinsics and run apriltag_demo.py."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

# Ensure project root is on sys.path so imports resolve regardless of CWD.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
PHASE_A_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from phase_a.lib import calib_io


DEFAULT_CONFIG_PATH = PHASE_A_ROOT / "config.yaml"
DEFAULT_EXTRINSICS_PATH = PHASE_A_ROOT / "data" / "T_WC.yaml"

SAMPLE_CONFIG = {
    "camera": {
        "intrinsics": {
            "K": [
                [1068.668, 0.0, 960.0],
                [0.0, 1067.500, 540.0],
                [0.0, 0.0, 1.0],
            ],
            "dist": [0.01, -0.02, 0.0, 0.0, 0.0],
        },
        "world_pose": {
            "x": 0.0,
            "y": 0.0,
            "rho": 6.5,
            "pitch": -0.35,
            "yaw": 0.0,
            "roll": 0.0,
        },
    },
    "mode": {
        "camera_pose": "pnp",
        "extrinsics_file": "./data/T_WC.yaml",
    },
}


APRILTAG_DEMO = Path(__file__).with_name("apriltag_demo.py")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Setup and run AprilTag demo with sensible defaults.")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG_PATH),
                        help="Path to config file (default: phase_a/config.yaml).")
    parser.add_argument("--extrinsics-file", default=str(DEFAULT_EXTRINSICS_PATH),
                        help="Extrinsics file (default: phase_a/data/T_WC.yaml).")
    parser.add_argument("--camera-pose-mode", choices=("manual", "pnp"), default="pnp",
                        help="Camera pose mode to use when running apriltag_demo.py (default: pnp).")
    parser.add_argument("--create-sample-config", action="store_true",
                        help="Create a sample config if the specified config does not exist.")
    parser.add_argument("--dry-run", action="store_true", help="Only print actions without executing the demo.")
    parser.add_argument("--apriltag-args", nargs=argparse.REMAINDER,
                        help="Extra args to forward to apriltag_demo.py (after '--').")
    return parser.parse_args()


def ensure_config(config_path: Path, create_sample: bool) -> None:
    if config_path.exists():
        print(f"[setup] Found config at: {config_path}", flush=True)
        return

    if not create_sample:
        raise FileNotFoundError(
            f"[setup] Config file missing: {config_path}. "
            "Re-run with --create-sample-config or point --config to an existing file."
        )

    print(f"[setup] Creating sample config at: {config_path}", flush=True)
    calib_io.save_yaml(config_path, SAMPLE_CONFIG)


def ensure_extrinsics(extrinsics_path: Path, mode: str) -> None:
    if mode != "pnp":
        return
    if extrinsics_path.exists():
        print(f"[setup] Found extrinsics at: {extrinsics_path}", flush=True)
        return
    print(f"[setup] Extrinsics missing: {extrinsics_path}", flush=True)
    print("         Run this to create it:", flush=True)
    print(f"         python {APRILTAG_DEMO} --estimate-extrinsics \\", flush=True)
    print("           --points phase_a/data/world_points.yaml \\", flush=True)
    print("           --image-points phase_a/data/image_points.yaml \\", flush=True)
    print(f"           --save {extrinsics_path} \\", flush=True)
    print("           --intrinsics phase_a/data/camera_intrinsics.npz", flush=True)
    raise FileNotFoundError("[setup] Extrinsics file is required for pnp mode.")


def main() -> int:
    args = parse_args()
    config_path = Path(args.config)
    extrinsics_path = Path(args.extrinsics_file)

    # Ensure config directory exists when user wants to create a config.
    if args.create_sample_config:
        config_path.parent.mkdir(parents=True, exist_ok=True)

    # Ensure data directory exists for extrinsics.
    if extrinsics_path.parent and not extrinsics_path.parent.exists():
        extrinsics_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        ensure_config(config_path, args.create_sample_config)
        ensure_extrinsics(extrinsics_path, args.camera_pose_mode)
    except FileNotFoundError as exc:
        print(exc)
        return 1

    cmd = [
        sys.executable,
        str(APRILTAG_DEMO),
        "--config",
        str(config_path),
        "--camera-pose-mode",
        args.camera_pose_mode,
        "--extrinsics-file",
        str(extrinsics_path),
    ]
    if args.apriltag_args:
        if args.apriltag_args[0] == "--":
            extra = args.apriltag_args[1:]
        else:
            extra = args.apriltag_args
        cmd.extend(extra)

    print(f"[setup] Executing: {' '.join(cmd)}", flush=True)
    if args.dry_run:
        print("[setup] Dry run enabled; command not executed.", flush=True)
        return 0

    result = subprocess.run(cmd, check=False)
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
