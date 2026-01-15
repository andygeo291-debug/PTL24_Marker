#!/usr/bin/env python3
"""Cross-platform Basler pose test runner (replaces bash-only harness)."""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import shlex
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional

import cv2
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
KPI_MEDIAN_MS = 100.0
KPI_P90_MS = 100.0


def _git_commit() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    except Exception:
        return "unknown"


def _run_and_log(cmd: List[str], log_path: Path, cwd: Path) -> int:
    with log_path.open("a", encoding="utf-8") as log_handle:
        log_handle.write("$ " + " ".join(shlex.quote(part) for part in cmd) + "\n")
        log_handle.flush()
        proc = subprocess.Popen(
            cmd,
            cwd=str(cwd),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        assert proc.stdout is not None
        for line in proc.stdout:
            print(line, end="")
            log_handle.write(line)
        return proc.wait()


def _record_cmd(cmd: List[str], cmd_log: Path) -> None:
    with cmd_log.open("a", encoding="utf-8") as handle:
        handle.write(" ".join(shlex.quote(part) for part in cmd) + "\n")


def _count_data_rows(path: Path) -> int:
    count = 0
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.startswith("#"):
                continue
            count += 1
    return count


def _load_env(path: Path) -> Dict[str, str]:
    data: Dict[str, str] = {}
    if not path.exists():
        return data
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("export "):
            line = line[len("export ") :]
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        data[key.strip()] = value.strip().strip('"')
    return data


def _next_run_dir(base_dir: Path) -> Path:
    base_dir.mkdir(parents=True, exist_ok=True)
    pattern = re.compile(r"basler_run_(\d{4})_")
    next_num = 1
    for path in base_dir.iterdir():
        if not path.is_dir():
            continue
        match = pattern.match(path.name)
        if not match:
            continue
        try:
            num = int(match.group(1))
        except ValueError:
            continue
        next_num = max(next_num, num + 1)
    run_tag = f"basler_run_{next_num:04d}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    return base_dir / run_tag


def _resolve_calib(calib_arg: Optional[str]) -> Path:
    if calib_arg:
        return Path(calib_arg)
    primary = ROOT / "common" / "calib" / "basler_static_960x720_offx320_offy200_mono8_11mm.yaml"
    if primary.exists():
        return primary
    return ROOT / "common" / "calib" / "basler_static_960x720_offx320_offy200_mono8.yaml"


def _load_pose_df(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, comment="#")


def _rvec_to_ypr_deg(rvec: np.ndarray) -> np.ndarray:
    rot, _ = cv2.Rodrigues(rvec)
    yaw = np.degrees(np.arctan2(rot[1, 0], rot[0, 0]))
    pitch = np.degrees(np.arctan2(-rot[2, 0], np.hypot(rot[2, 1], rot[2, 2])))
    roll = np.degrees(np.arctan2(rot[2, 1], rot[2, 2]))
    return np.array([yaw, pitch, roll], dtype=float)


def _drift_stats(values: np.ndarray) -> dict:
    base = values[0]
    drift = values - base
    return {
        "std": np.std(drift, axis=0),
        "p10": np.percentile(drift, 10, axis=0),
        "p90": np.percentile(drift, 90, axis=0),
        "min": np.min(drift, axis=0),
        "max": np.max(drift, axis=0),
    }


def _timing_stats(df: pd.DataFrame, col: str) -> dict:
    series = df[col].dropna()
    return {
        "median": float(series.median()),
        "p90": float(series.quantile(0.9)),
        "max": float(series.max()),
    }


def _count_grab_failures(log_text: str, run_names: Iterable[str]) -> Dict[str, int]:
    counts = {name: 0 for name in run_names}
    current = None
    for line in log_text.splitlines():
        if line.startswith("== "):
            current = None
            for name in run_names:
                if f"== {name} " in line:
                    current = name
                    break
        if current and "Frame grab failed; skipping frame." in line:
            counts[current] += 1
    return counts


def _format_vec(values: np.ndarray) -> str:
    return "[" + ", ".join(f"{x:.4f}" for x in values) + "]"


def _choose_recommendation(on: dict, off: dict) -> str:
    def score(row: dict) -> tuple:
        p90 = float(row.get("t_total_ms_p90", 1e9))
        median = float(row.get("t_total_ms_median", 1e9))
        reject = float(row.get("reject_rate", 1.0))
        kpi_ok = 0 if (p90 <= KPI_P90_MS and median <= KPI_MEDIAN_MS) else 1
        return (kpi_ok, p90, reject, median)

    return "spike_on" if score(on) <= score(off) else "spike_off"


def _summarize_runs(run_dir: Path, runs: Dict[str, Path], log_path: Path) -> None:
    summary_dir = run_dir / "summary"
    summary_dir.mkdir(parents=True, exist_ok=True)

    log_text = log_path.read_text(encoding="utf-8") if log_path.exists() else ""
    grab_fail_counts = _count_grab_failures(log_text, runs.keys())

    lines: List[str] = []
    table_rows: List[dict] = []
    lines.append("# Basler Pose Test Summary")
    lines.append("")
    lines.append(f"- Commit: `{_git_commit()}`")
    lines.append(f"- Run dir: `{run_dir}`")
    lines.append("")

    for name, path in runs.items():
        poses_path = path / "poses.csv"
        debug_path = path / "debug_metrics.csv"
        poses_df = _load_pose_df(poses_path)
        debug_df = pd.read_csv(debug_path, comment="#")
        poses_count = len(poses_df)
        debug_count = len(debug_df)
        fps_eff = None
        if "t" in debug_df.columns and debug_count > 1:
            t0 = float(debug_df["t"].iloc[0])
            t1 = float(debug_df["t"].iloc[-1])
            if t1 > t0:
                fps_eff = (debug_count - 1) / (t1 - t0)

        lines.append(f"## {name}")
        lines.append(f"- poses.csv rows: {poses_count}")
        lines.append(f"- debug_metrics.csv rows: {debug_count}")
        if fps_eff is not None:
            lines.append(f"- effective_fps: {fps_eff:.2f}")

        stats = {col: _timing_stats(debug_df, col) for col in ["t_total_ms", "t_detect_ms", "t_ransac_ms", "mean_reproj_px"]}
        lines.append("- Timing stats (ms):")
        for col, st in stats.items():
            lines.append(
                f"  - {col}: median={st['median']:.3f} p90={st['p90']:.3f} max={st['max']:.3f}"
            )

        reject_counts = {}
        if "reject_reason" in debug_df.columns:
            reject_counts = debug_df["reject_reason"].value_counts().to_dict()
            lines.append("- reject_reason counts:")
            for key, val in reject_counts.items():
                lines.append(f"  - {key}: {val}")
        ok_count = int(reject_counts.get("OK", 0)) + int(reject_counts.get("HOLD_PREV_POSE", 0))
        reject_rate = 1.0 - (ok_count / debug_count if debug_count else 0.0)
        lines.append(f"- reject_rate: {reject_rate:.3f}")
        kpi_pass = stats["t_total_ms"]["median"] <= KPI_MEDIAN_MS and stats["t_total_ms"]["p90"] <= KPI_P90_MS
        lines.append(
            f"- KPI(100ms): {'PASS' if kpi_pass else 'FAIL'} "
            f"(median={stats['t_total_ms']['median']:.1f} p90={stats['t_total_ms']['p90']:.1f})"
        )

        tvec = poses_df[["tvec_cam_x", "tvec_cam_y", "tvec_cam_z"]].to_numpy(float)
        rvec = poses_df[["rvec_cam_x", "rvec_cam_y", "rvec_cam_z"]].to_numpy(float)
        ypr = np.vstack([_rvec_to_ypr_deg(rv) for rv in rvec])
        tvec_stats = _drift_stats(tvec)
        ypr_stats = _drift_stats(ypr)

        lines.append("- Drift stats vs first pose:")
        lines.append(f"  - tvec_cam std: {_format_vec(tvec_stats['std'])}")
        lines.append(f"  - tvec_cam p10: {_format_vec(tvec_stats['p10'])}")
        lines.append(f"  - tvec_cam p90: {_format_vec(tvec_stats['p90'])}")
        lines.append(f"  - tvec_cam min: {_format_vec(tvec_stats['min'])}")
        lines.append(f"  - tvec_cam max: {_format_vec(tvec_stats['max'])}")
        lines.append(f"  - ypr_deg std: {_format_vec(ypr_stats['std'])}")
        lines.append(f"  - ypr_deg p10: {_format_vec(ypr_stats['p10'])}")
        lines.append(f"  - ypr_deg p90: {_format_vec(ypr_stats['p90'])}")
        lines.append(f"  - ypr_deg min: {_format_vec(ypr_stats['min'])}")
        lines.append(f"  - ypr_deg max: {_format_vec(ypr_stats['max'])}")
        lines.append("")

        grab_fail = grab_fail_counts.get(name, 0)
        grab_fail_rate = grab_fail / debug_count if debug_count else 0.0
        lines.append(f"- frame_grab_failed: {grab_fail} (rate={grab_fail_rate:.4f})")

        table_rows.append(
            {
                "run": name,
                "poses_rows": poses_count,
                "debug_rows": debug_count,
                "effective_fps": fps_eff if fps_eff is not None else "",
                "t_total_ms_median": stats["t_total_ms"]["median"],
                "t_total_ms_p90": stats["t_total_ms"]["p90"],
                "t_total_ms_max": stats["t_total_ms"]["max"],
                "t_detect_ms_median": stats["t_detect_ms"]["median"],
                "t_detect_ms_p90": stats["t_detect_ms"]["p90"],
                "t_detect_ms_max": stats["t_detect_ms"]["max"],
                "t_ransac_ms_median": stats["t_ransac_ms"]["median"],
                "t_ransac_ms_p90": stats["t_ransac_ms"]["p90"],
                "t_ransac_ms_max": stats["t_ransac_ms"]["max"],
                "mean_reproj_px_median": stats["mean_reproj_px"]["median"],
                "mean_reproj_px_p90": stats["mean_reproj_px"]["p90"],
                "mean_reproj_px_max": stats["mean_reproj_px"]["max"],
                "reject_reason_counts": json.dumps(reject_counts, sort_keys=True),
                "reject_rate": reject_rate,
                "kpi_pass": kpi_pass,
                "frame_grab_failed_count": grab_fail,
                "frame_grab_failed_rate": grab_fail_rate,
            }
        )

    if "spike_on" in runs and "spike_off" in runs:
        on = next(row for row in table_rows if row["run"] == "spike_on")
        off = next(row for row in table_rows if row["run"] == "spike_off")
        lines.append("## Spike ON vs OFF")
        lines.append(f"- reject_rate: on={on['reject_rate']:.3f} off={off['reject_rate']:.3f}")
        lines.append(
            f"- t_total_ms_median: on={on['t_total_ms_median']:.3f} off={off['t_total_ms_median']:.3f}"
        )
        lines.append(
            f"- t_detect_ms_median: on={on['t_detect_ms_median']:.3f} off={off['t_detect_ms_median']:.3f}"
        )
        lines.append(
            f"- t_ransac_ms_median: on={on['t_ransac_ms_median']:.3f} off={off['t_ransac_ms_median']:.3f}"
        )
        lines.append("")

        recommendation = _choose_recommendation(on, off)
        lines.append("## Recommendation")
        lines.append(f"- Use {recommendation} for long runs (best median/p90 and reject_rate).")
        lines.append("")
        print(f"Recommendation: Use {recommendation} for long runs.")

    lines.append("## Failure Modes and Fixes")
    lines.append(
        "- REJECT_SPIKE triggers when tilt jump exceeds max_tilt_jump_deg or when translation delta "
        "exceeds spike_trans_thresh_m (if set). It compares against the last accepted pose and skips "
        "spike checks for the first spike_reset_after frames after acceptance."
    )
    lines.append(
        "- Empty outputs usually come from camera lock (another app using the device), "
        "frame grab timeouts, or writing debug metrics to the default path. "
        "The runner asserts outputs and checks for fallback debug writes."
    )
    lines.append(
        "- Stability improvements: ensure >=3 tags in view, reduce motion blur (more light/shorter exposure), "
        "verify calibration matches ROI, and consider relaxing spike thresholds slightly if the rig is stable."
    )
    lines.append("")

    diag_path = summary_dir / "basler_stream_best.json"
    if diag_path.exists():
        diag = json.loads(diag_path.read_text(encoding="utf-8"))
        best = diag.get("best", {})
        lines.append("## Stream Diagnosis")
        lines.append(
            "- Best stream config: packet=%s ipd=%s timeout=%s fail_rate=%.4f"
            % (
                best.get("packet_size"),
                best.get("interpacket_delay"),
                best.get("timeout_ms"),
                float(best.get("fail_rate", 1.0)),
            )
        )
        lines.append("")

    summary_path = summary_dir / "MEETING_SUMMARY.md"
    summary_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    table_path = summary_dir / "meeting_table.csv"
    with table_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=table_rows[0].keys())
        writer.writeheader()
        writer.writerows(table_rows)

    print(f"Wrote {summary_path}")
    print(f"Wrote {table_path}")

    snippet_lines = [
        "Basler Long-Run Summary",
        f"- Run dir: {run_dir}",
        "- Summary/plots: summary/MEETING_SUMMARY.md + summary/plots/*.png",
    ]
    snippet_path = summary_dir / "SLIDE_SNIPPET.md"
    snippet_path.write_text("\n".join(snippet_lines) + "\n", encoding="utf-8")
    print(f"Wrote {snippet_path}")

    plots_dir = summary_dir / "plots"
    plots_dir.mkdir(parents=True, exist_ok=True)
    try:
        import matplotlib.pyplot as plt

        for name, path in runs.items():
            debug_df = pd.read_csv(path / "debug_metrics.csv", comment="#")
            poses_df = _load_pose_df(path / "poses.csv")

            plt.figure(figsize=(10, 4))
            plt.plot(debug_df["t_total_ms"].to_numpy(), linewidth=1.0)
            plt.title(f"{name}: t_total_ms")
            plt.xlabel("frame")
            plt.ylabel("ms")
            plt.tight_layout()
            plt.savefig(plots_dir / f"{name}_t_total_ms.png", dpi=150)
            plt.close()

            plt.figure(figsize=(10, 4))
            plt.plot(poses_df["tvec_cam_x"].to_numpy(), label="x")
            plt.plot(poses_df["tvec_cam_y"].to_numpy(), label="y")
            plt.plot(poses_df["tvec_cam_z"].to_numpy(), label="z")
            plt.title(f"{name}: tvec_cam")
            plt.xlabel("frame")
            plt.ylabel("m")
            plt.legend()
            plt.tight_layout()
            plt.savefig(plots_dir / f"{name}_tvec_cam.png", dpi=150)
            plt.close()
    except Exception:
        print("Plotting skipped (matplotlib not available).")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Basler pose tests (cross-platform).")
    parser.add_argument("--serial", default="21601161")
    parser.add_argument("--name", default="StaticCam")
    parser.add_argument("--width", type=int, default=960)
    parser.add_argument("--height", type=int, default=720)
    parser.add_argument("--fps", type=float, default=15.0)
    parser.add_argument("--pixel-format", default="Mono8")
    parser.add_argument("--exposure-us", type=float, default=15000.0)
    parser.add_argument("--gain", type=float, default=0.0)
    parser.add_argument("--offset-x", type=int, default=320)
    parser.add_argument("--offset-y", type=int, default=200)
    parser.add_argument("--interpacket-delay", type=int, default=3500)
    parser.add_argument("--timeout-ms", type=int, default=1000)
    parser.add_argument("--packet-size", type=int, default=8192)
    parser.add_argument("--stream-buffer-count", type=int, default=None)
    parser.add_argument("--rig", default="phase_b/rigs/cyl_dotec.yaml")
    parser.add_argument("--calib", default=None)
    parser.add_argument("--run-base", default="basler_test_runs")
    parser.add_argument("--quick-frames", type=int, default=30)
    parser.add_argument("--spike-frames", type=int, default=300)
    parser.add_argument("--diagnose-frames", type=int, default=300)
    parser.add_argument("--no-diagnose", action="store_true")
    parser.add_argument("--no-auto-tune-latency", action="store_true")
    parser.add_argument("--tuned-ransac-iters", type=int, default=10)
    parser.add_argument("--print-tag-count", action="store_true", help="Print tag counts every N frames.")
    parser.add_argument(
        "--print-every",
        type=int,
        default=60,
        help="Print tag counts every N frames when enabled (default: 60).",
    )
    parser.add_argument("--print-tag-ids", action="store_true", help="Include tag IDs in tag count output.")
    parser.add_argument(
        "--det-nthreads",
        type=int,
        default=4,
        help="AprilTag detector threads (default: 4).",
    )
    parser.add_argument(
        "--det-quad-decimate",
        type=float,
        default=1.0,
        help="AprilTag quad_decimate (default: 1.0).",
    )
    parser.add_argument(
        "--det-quad-sigma",
        type=float,
        default=0.0,
        help="AprilTag quad_sigma (default: 0.0).",
    )
    parser.add_argument(
        "--det-decode-sharpen",
        type=float,
        default=0.25,
        help="AprilTag decode_sharpening (default: 0.25).",
    )
    parser.add_argument(
        "--det-refine-edges",
        dest="det_refine_edges",
        action="store_true",
        default=True,
        help="Enable edge refinement (default: on).",
    )
    parser.add_argument(
        "--det-no-refine-edges",
        dest="det_refine_edges",
        action="store_false",
        help="Disable edge refinement.",
    )
    parser.add_argument(
        "--only",
        choices=["spike_on", "spike_off", "all"],
        default="all",
        help="Run only a specific spike mode (default: all).",
    )
    args = parser.parse_args()

    run_base = Path(args.run_base)
    if not run_base.is_absolute():
        run_base = ROOT / run_base
    try:
        run_base_resolved = run_base.resolve()
        root_resolved = ROOT.resolve()
        if root_resolved not in run_base_resolved.parents and run_base_resolved != root_resolved:
            raise RuntimeError(f"RUN_BASE must be inside repo: {ROOT}")
    except RuntimeError:
        raise
    except Exception:
        pass

    run_dir = _next_run_dir(run_base)
    (run_dir / "quick_checks").mkdir(parents=True, exist_ok=True)
    (run_dir / "spike_on").mkdir(parents=True, exist_ok=True)
    (run_dir / "spike_off").mkdir(parents=True, exist_ok=True)
    (run_dir / "summary" / "plots").mkdir(parents=True, exist_ok=True)

    log_path = run_dir / "terminal.log"
    log_path.write_text("", encoding="utf-8")
    cmd_log = run_dir / "run_cmd.txt"
    cmd_log.write_text("", encoding="utf-8")

    print(f"Run dir: {run_dir}")

    calib_path = _resolve_calib(args.calib)

    diag_json = run_dir / "summary" / "basler_stream_best.json"
    diag_env = run_dir / "summary" / "basler_stream_best.env"

    if not args.no_diagnose:
        diagnose_cmd = [
            sys.executable,
            str(ROOT / "tools" / "basler_stream_diagnose.py"),
            "--serial",
            args.serial,
            "--name",
            args.name,
            "--width",
            str(args.width),
            "--height",
            str(args.height),
            "--offset-x",
            str(args.offset_x),
            "--offset-y",
            str(args.offset_y),
            "--fps",
            str(args.fps),
            "--pixel-format",
            args.pixel_format,
            "--exposure-us",
            str(args.exposure_us),
            "--gain",
            str(args.gain),
            "--frames",
            str(args.diagnose_frames),
            "--fail-threshold",
            "0.01",
            "--packet-size-candidates",
            "8192,1500,1440,1400,1300,1200",
            "--interpacket-delay-candidates",
            "3500,8000,12000",
            "--timeout-candidates",
            "1000,2000",
            "--out-json",
            str(diag_json),
            "--out-env",
            str(diag_env),
        ]
        if args.stream_buffer_count is not None:
            diagnose_cmd.extend(["--stream-buffer-count", str(args.stream_buffer_count)])
        _record_cmd(diagnose_cmd, cmd_log)
        if _run_and_log(diagnose_cmd, log_path, ROOT) != 0:
            print("Warning: stream diagnose returned non-zero status.")

    env = _load_env(diag_env)
    ipd = int(env.get("IPD", args.interpacket_delay))
    timeout_ms = int(env.get("TIMEOUT_MS", args.timeout_ms))
    packet_size = args.packet_size
    if "BASLER_PACKET_SIZE" in env:
        try:
            packet_size = int(env["BASLER_PACKET_SIZE"])
        except ValueError:
            pass

    common_args = [
        sys.executable,
        "-m",
        "phase_b.v2.phase_b_tags_v2",
        "--camera-backend",
        "basler",
        "--basler-serial",
        args.serial,
        "--basler-name",
        args.name,
        "--width",
        str(args.width),
        "--height",
        str(args.height),
        "--fps",
        str(args.fps),
        "--basler-pixel-format",
        args.pixel_format,
        "--basler-exposure-us",
        str(args.exposure_us),
        "--basler-gain",
        str(args.gain),
        "--basler-offset-x",
        str(args.offset_x),
        "--basler-offset-y",
        str(args.offset_y),
        "--basler-interpacket-delay",
        str(ipd),
        "--basler-timeout-ms",
        str(timeout_ms),
        "--rig",
        str(ROOT / args.rig),
        "--camera",
        str(calib_path),
        "--ransac",
        "--adapt",
        "--ransac-iters",
        "15",
        "--quiet-apriltag-stderr",
        "--no-hud",
    ]
    if packet_size is not None:
        common_args.extend(["--basler-packet-size", str(packet_size)])
    if args.stream_buffer_count is not None:
        common_args.extend(["--basler-stream-buffer-count", str(args.stream_buffer_count)])
    if args.print_tag_count:
        common_args.append("--print-tag-count")
        common_args.extend(["--print-every", str(args.print_every)])
        if args.print_tag_ids:
            common_args.append("--print-tag-ids")
    common_args.extend(
        [
            "--det-nthreads",
            str(args.det_nthreads),
            "--det-quad-decimate",
            str(args.det_quad_decimate),
            "--det-quad-sigma",
            str(args.det_quad_sigma),
            "--det-decode-sharpen",
            str(args.det_decode_sharpen),
        ]
    )
    if args.det_refine_edges:
        common_args.append("--det-refine-edges")
    else:
        common_args.append("--det-no-refine-edges")

    def run_phaseb(name: str, frames: int, poses_path: Path, debug_path: Path, extra: List[str]) -> None:
        poses_path.parent.mkdir(parents=True, exist_ok=True)
        debug_path.parent.mkdir(parents=True, exist_ok=True)
        fallback_debug = ROOT / "phase_b" / "debug_metrics.csv"
        start_epoch = time.time()
        cmd = common_args + [
            "--frames",
            str(frames),
            "--save-poses",
            str(poses_path),
            "--debug-metrics-out",
            str(debug_path),
        ]
        cmd.extend(extra)
        print(f"== {name} ({frames} frames) ==")
        _record_cmd(cmd, cmd_log)
        if _run_and_log(cmd, log_path, ROOT) != 0:
            raise RuntimeError(f"{name} failed")
        pose_lines = _count_data_rows(poses_path)
        debug_lines = _count_data_rows(debug_path)
        if pose_lines <= 2:
            raise RuntimeError(f"{poses_path} has no pose rows.")
        if debug_lines <= 2:
            raise RuntimeError(f"{debug_path} has no debug rows.")
        if fallback_debug.exists() and fallback_debug.stat().st_mtime >= start_epoch:
            raise RuntimeError(f"debug metrics wrote to {fallback_debug} (unexpected).")

    def run_phaseb_poses_out(name: str, frames: int, poses_path: Path, debug_path: Path) -> None:
        poses_path.parent.mkdir(parents=True, exist_ok=True)
        debug_path.parent.mkdir(parents=True, exist_ok=True)
        fallback_debug = ROOT / "phase_b" / "debug_metrics.csv"
        start_epoch = time.time()
        cmd = common_args + [
            "--frames",
            str(frames),
            "--poses-out",
            str(poses_path),
            "--debug-metrics-out",
            str(debug_path),
        ]
        print(f"== {name} ({frames} frames) ==")
        _record_cmd(cmd, cmd_log)
        if _run_and_log(cmd, log_path, ROOT) != 0:
            raise RuntimeError(f"{name} failed")
        pose_lines = _count_data_rows(poses_path)
        debug_lines = _count_data_rows(debug_path)
        if pose_lines <= 2:
            raise RuntimeError(f"{poses_path} has no pose rows.")
        if debug_lines <= 2:
            raise RuntimeError(f"{debug_path} has no debug rows.")
        if fallback_debug.exists() and fallback_debug.stat().st_mtime >= start_epoch:
            raise RuntimeError(f"debug metrics wrote to {fallback_debug} (unexpected).")

    run_phaseb(
        "quick_checks_save_poses",
        args.quick_frames,
        run_dir / "quick_checks" / "poses_save_poses.csv",
        run_dir / "quick_checks" / "debug_save_poses.csv",
        [],
    )
    run_phaseb_poses_out(
        "quick_checks_poses_out",
        args.quick_frames,
        run_dir / "quick_checks" / "poses_poses_out.csv",
        run_dir / "quick_checks" / "debug_poses_out.csv",
    )
    runs = {}
    run_spike_on = args.only in ("spike_on", "all")
    run_spike_off = args.only in ("spike_off", "all")

    if run_spike_on:
        run_phaseb(
            "spike_on",
            args.spike_frames,
            run_dir / "spike_on" / "poses.csv",
            run_dir / "spike_on" / "debug_metrics.csv",
            [],
        )
        runs["spike_on"] = run_dir / "spike_on"
    if run_spike_off:
        run_phaseb(
            "spike_off",
            args.spike_frames,
            run_dir / "spike_off" / "poses.csv",
            run_dir / "spike_off" / "debug_metrics.csv",
            ["--spike-disable"],
        )
        runs["spike_off"] = run_dir / "spike_off"
    _summarize_runs(run_dir, runs, log_path)

    if not args.no_auto_tune_latency and run_spike_on and run_spike_off:
        table_path = run_dir / "summary" / "meeting_table.csv"
        table_df = pd.read_csv(table_path)
        spike_on_p90 = float(table_df.loc[table_df["run"] == "spike_on", "t_total_ms_p90"].iloc[0])
        spike_off_p90 = float(table_df.loc[table_df["run"] == "spike_off", "t_total_ms_p90"].iloc[0])
        if spike_on_p90 > KPI_P90_MS and spike_off_p90 > KPI_P90_MS:
            tuned_flags = ["--ransac-iters", str(args.tuned_ransac_iters), "--no-use-weighted-se3"]
            print("Auto-tune latency: rerunning spike_on/off with", " ".join(tuned_flags))
            run_phaseb(
                "spike_on_tuned",
                args.spike_frames,
                run_dir / "spike_on_tuned" / "poses.csv",
                run_dir / "spike_on_tuned" / "debug_metrics.csv",
                tuned_flags,
            )
            run_phaseb(
                "spike_off_tuned",
                args.spike_frames,
                run_dir / "spike_off_tuned" / "poses.csv",
                run_dir / "spike_off_tuned" / "debug_metrics.csv",
                tuned_flags + ["--spike-disable"],
            )
            runs["spike_on_tuned"] = run_dir / "spike_on_tuned"
            runs["spike_off_tuned"] = run_dir / "spike_off_tuned"
            _summarize_runs(run_dir, runs, log_path)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
