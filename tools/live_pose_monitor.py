#!/usr/bin/env python3
"""Live monitor for pose distance/tilt and timing during a run."""

from __future__ import annotations

import argparse
import os
import time
from pathlib import Path


def _latest_run_dir(base: Path) -> Path | None:
    runs = [p for p in base.iterdir() if p.is_dir()]
    if not runs:
        return None
    return max(runs, key=lambda p: p.stat().st_mtime)


def _last_data_line(path: Path) -> str | None:
    try:
        with path.open("rb") as handle:
            handle.seek(0, os.SEEK_END)
            size = handle.tell()
            handle.seek(max(size - 8192, 0), os.SEEK_SET)
            lines = handle.read().splitlines()
        lines = [line for line in lines if line.strip() and not line.lstrip().startswith(b"#")]
        if not lines:
            return None
        return lines[-1].decode("utf-8", errors="ignore")
    except Exception:
        return None


def _header_map(path: Path) -> dict:
    try:
        with path.open("r", encoding="utf-8", errors="ignore") as handle:
            for line in handle:
                if line.startswith("#"):
                    continue
                cols = line.strip().split(",")
                return {c: i for i, c in enumerate(cols)}
    except Exception:
        return {}
    return {}


def main() -> int:
    parser = argparse.ArgumentParser(description="Live pose/timing monitor.")
    parser.add_argument("--run-dir", default=None, help="Basler run directory.")
    parser.add_argument("--mode", default="spike_off", help="Run subdir (default: spike_off).")
    parser.add_argument("--interval", type=float, default=0.5, help="Poll interval (seconds).")
    args = parser.parse_args()

    base = Path("basler_test_runs")
    run_dir = Path(args.run_dir) if args.run_dir else _latest_run_dir(base)
    if run_dir is None:
        raise SystemExit("No run directory found under basler_test_runs.")
    pose_path = run_dir / args.mode / "poses.csv"
    met_path = run_dir / args.mode / "debug_metrics.csv"

    pose_idx = {}
    met_idx = {}
    last_pose = None
    last_met = None

    print("LIVE WATCH")
    print(f"RUN: {run_dir}")
    print(f"POSE: {pose_path}")
    print(f"MET : {met_path}")
    print("Ctrl+C to stop")

    while True:
        if not pose_idx and pose_path.exists():
            pose_idx = _header_map(pose_path)
        if not met_idx and met_path.exists():
            met_idx = _header_map(met_path)

        pose_line = _last_data_line(pose_path)
        if pose_line and pose_line != last_pose and pose_idx:
            parts = pose_line.split(",")
            try:
                frame = parts[pose_idx.get("frame", 1)]
                x = float(parts[pose_idx["tvec_cam_x"]])
                y = float(parts[pose_idx["tvec_cam_y"]])
                z = float(parts[pose_idx["tvec_cam_z"]])
                dist = (x * x + y * y + z * z) ** 0.5
                tilt = (
                    float(parts[pose_idx["tilt_cam_deg"]])
                    if "tilt_cam_deg" in pose_idx
                    else float("nan")
                )
                print(
                    f"[pose] frame={frame} dist={dist:.3f}m "
                    f"xyz=({x:+.3f},{y:+.3f},{z:+.3f}) tilt={tilt:.2f}deg"
                )
            except Exception:
                pass
            last_pose = pose_line

        met_line = _last_data_line(met_path)
        if met_line and met_line != last_met and met_idx and "t_total_ms" in met_idx:
            parts = met_line.split(",")
            try:
                frame = parts[met_idx.get("frame", 1)]
                t_total = float(parts[met_idx["t_total_ms"]])
                print(f"[time] frame={frame} t_total_ms={t_total:.1f}")
            except Exception:
                pass
            last_met = met_line

        time.sleep(args.interval)


if __name__ == "__main__":
    raise SystemExit(main())
