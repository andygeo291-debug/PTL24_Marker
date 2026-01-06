#!/usr/bin/env python3
"""Regression harness to compare Phase B v1 vs v2 pose outputs."""

from __future__ import annotations

import argparse
import csv
import io
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import List, Sequence

import yaml


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run Phase B v1 and v2 with identical inputs and compare the pose logs."
    )
    parser.add_argument("--camera", required=True, help="Path to camera intrinsics YAML.")
    parser.add_argument("--rig", required=True, help="Path to rig YAML.")
    parser.add_argument("--extrinsics", required=True, help="Path to world->camera extrinsics YAML.")
    parser.add_argument(
        "--config",
        default="phase_b/config.yaml",
        help="Phase B config used for the v2 run (default: phase_b/config.yaml).",
    )
    parser.add_argument(
        "--params",
        default="phase_b/params.yaml",
        help="Phase B params file for v1 (default: phase_b/params.yaml).",
    )
    parser.add_argument(
        "--video",
        default="auto",
        help='Video source forwarded to both binaries (default: "auto").',
    )
    parser.add_argument(
        "--frames",
        type=int,
        default=200,
        help="Maximum frames to process before stopping each run (default: 200).",
    )
    parser.add_argument(
        "--tolerance",
        type=float,
        default=0.0,
        help="Numeric tolerance for per-cell comparisons (default: 0, i.e. byte-identical).",
    )
    parser.add_argument(
        "--save-poses",
        help="Optional path to copy the v2 poses after a successful comparison.",
    )
    parser.add_argument(
        "--v1-output",
        help="Override temporary CSV path for the v1 run (default: /tmp/phase_b_v1_poses.csv).",
    )
    parser.add_argument(
        "--v2-output",
        help="Override temporary CSV path for the v2 run (default: /tmp/phase_b_v2_poses.csv).",
    )
    parser.add_argument(
        "--print-tilt",
        action="store_true",
        help="Forward --print-tilt to both binaries.",
    )
    return parser.parse_args()


def load_config(config_path: Path) -> dict:
    with config_path.open("r", encoding="utf-8") as fp:
        return yaml.safe_load(fp) or {}


def build_common_args(args: argparse.Namespace, config: dict, *, output_path: Path) -> List[str]:
    fuse_cfg = config.get("fuse", {})
    ransac_cfg = config.get("ransac", {})
    health_cfg = config.get("health", {})
    base = [
        "--camera",
        str(args.camera),
        "--rig",
        str(args.rig),
        "--extrinsics",
        str(args.extrinsics),
        "--save-poses",
        str(output_path),
        "--video",
        str(args.video),
        "--params",
        str(args.params),
        "--axis-len",
        str(fuse_cfg.get("axis_len_m", 0.2)),
        "--ema-alpha",
        str(fuse_cfg.get("ema_alpha", 0.3)),
        "--min-inliers",
        str(ransac_cfg.get("min_inliers", 3)),
        "--max-tilt-jump-deg",
        str(health_cfg.get("max_tilt_jump_deg", 15)),
        "--ransac",
        "--ransac-trans",
        str(ransac_cfg.get("trans_max_m", 0.05)),
        "--ransac-rot",
        str(ransac_cfg.get("rot_max_deg", 5)),
    ]
    if args.frames is not None:
        base.extend(["--frames", str(args.frames)])
    if args.print_tilt:
        base.append("--print-tilt")
    return base


def run_command(cmd: Sequence[str]) -> None:
    print(f"[regress] running: {' '.join(cmd)}")
    subprocess.run(cmd, check=True)


def read_csv_rows(path: Path) -> tuple[str, List[List[str]]]:
    with path.open("r", encoding="utf-8") as fp:
        filtered = [line for line in fp if line.strip() and not line.lstrip().startswith("#")]
    if not filtered:
        return "", []
    reader = csv.reader(io.StringIO("".join(filtered)))
    rows = list(reader)
    if not rows:
        return "", []
    header = ",".join(rows[0])
    return header, rows[1:]


def compare_rows(
    v1_rows: List[List[str]], v2_rows: List[List[str]], tolerance: float
) -> tuple[bool, str]:
    if len(v1_rows) != len(v2_rows):
        return (
            False,
            f"Row count mismatch: v1={len(v1_rows)} vs v2={len(v2_rows)}",
        )
    for idx, (row_a, row_b) in enumerate(zip(v1_rows, v2_rows), start=1):
        if len(row_a) != len(row_b):
            return (
                False,
                f"Column count mismatch at row {idx}: v1={len(row_a)} vs v2={len(row_b)}",
            )
        for col, (cell_a, cell_b) in enumerate(zip(row_a, row_b), start=1):
            if cell_a == cell_b:
                continue
            if tolerance <= 0.0:
                return (
                    False,
                    f"Mismatch at row {idx}, col {col}: v1='{cell_a}' vs v2='{cell_b}'",
                )
            try:
                val_a = float(cell_a)
                val_b = float(cell_b)
            except ValueError:
                return (
                    False,
                    f"String mismatch at row {idx}, col {col}: v1='{cell_a}' vs v2='{cell_b}'",
                )
            if abs(val_a - val_b) > tolerance:
                return (
                    False,
                    f"Numeric mismatch at row {idx}, col {col}: {val_a} vs {val_b} (tol={tolerance})",
                )
    return True, "All rows match within tolerance."


def main() -> None:
    args = parse_args()
    config_path = Path(args.config).resolve()
    cfg = load_config(config_path)

    tmp_dir = Path(tempfile.gettempdir())
    v1_out = Path(args.v1_output).resolve() if args.v1_output else tmp_dir / "phase_b_v1_poses.csv"
    v2_out = Path(args.v2_output).resolve() if args.v2_output else tmp_dir / "phase_b_v2_poses.csv"

    for path in (v1_out, v2_out):
        if path.exists():
            path.unlink()

    common_args_v1 = build_common_args(args, cfg, output_path=v1_out)
    common_args_v2 = build_common_args(args, cfg, output_path=v2_out)

    v1_cmd = [sys.executable, "-m", "phase_b.v1.phase_b_tags", *common_args_v1]
    v2_cmd = [
        sys.executable,
        "-m",
        "phase_b.v2.phase_b_tags_v2",
        "--config",
        str(config_path),
        "--no-use-weighted-se3",
        "--no-overlay",
        *common_args_v2,
    ]
    bench_cfg = cfg.get("bench")
    if bench_cfg:
        v2_cmd.extend(["--bench-print-every", str(bench_cfg.get("print_every", 60))])

    run_command(v1_cmd)
    run_command(v2_cmd)

    header_v1, rows_v1 = read_csv_rows(v1_out)
    header_v2, rows_v2 = read_csv_rows(v2_out)

    if header_v1.strip() != header_v2.strip():
        print("[regress] FAILED: CSV headers differ")
        print(f"v1 header: {header_v1}")
        print(f"v2 header: {header_v2}")
        sys.exit(1)

    ok, message = compare_rows(rows_v1, rows_v2, args.tolerance)
    if not ok:
        print(f"[regress] FAILED: {message}")
        sys.exit(2)

    print(f"[regress] PASS: {message}")
    print(f"[regress] v1 poses: {v1_out}")
    print(f"[regress] v2 poses: {v2_out}")

    if args.save_poses:
        shutil.copy2(v2_out, Path(args.save_poses).resolve())
        print(f"[regress] Saved v2 poses to {args.save_poses}")


if __name__ == "__main__":
    main()
