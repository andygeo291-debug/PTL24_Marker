#!/usr/bin/env python3
"""Summarize a Phase B run from debug metrics and command metadata."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import shlex

import numpy as np
import pandas as pd


def _parse_args():
    parser = argparse.ArgumentParser(description="Summarize a Phase B run from debug metrics.")
    parser.add_argument("--debug-csv", required=True, help="Path to debug metrics CSV.")
    parser.add_argument(
        "--poses-csv",
        default="phase_b/poses.csv",
        help="Path to poses CSV (default: phase_b/poses.csv).",
    )
    parser.add_argument(
        "--cmd",
        default=None,
        help="Run command string or path to a .cmd file.",
    )
    parser.add_argument(
        "--kpi-ms",
        type=float,
        default=100.0,
        help="KPI threshold for t_total_ms p90 (default: 100).",
    )
    parser.add_argument(
        "--out-md",
        default=None,
        help="Optional path to write a markdown summary.",
    )
    parser.add_argument(
        "--print-worst",
        type=int,
        default=10,
        help="Print N worst frames by t_total_ms (default: 10).",
    )
    return parser.parse_args()


def _load_cmd(cmd_arg: str | None) -> str | None:
    if not cmd_arg:
        return None
    path = Path(cmd_arg)
    if path.exists():
        return path.read_text(encoding="utf-8").strip()
    return cmd_arg.strip()


def _parse_header_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.startswith("#"):
                break
            payload = line.lstrip("#").strip()
            if not payload:
                continue
            try:
                return json.loads(payload)
            except json.JSONDecodeError:
                continue
    return {}


def _get_calib_path(header: dict, cmd_str: str | None) -> str | None:
    files = header.get("files", {}) if isinstance(header, dict) else {}
    cam_file = files.get("camera_calib", {}) if isinstance(files, dict) else {}
    if isinstance(cam_file, dict) and cam_file.get("path"):
        return cam_file.get("path")
    config = header.get("config", {}) if isinstance(header, dict) else {}
    if isinstance(config, dict) and config.get("calib_path_resolved"):
        return config.get("calib_path_resolved")
    if cmd_str:
        tokens = shlex.split(cmd_str)
        return _extract_flag(tokens, "--camera")
    return None


def _extract_flag(tokens: list[str], name: str) -> str | None:
    for idx, token in enumerate(tokens):
        if token.startswith(f"{name}="):
            return token.split("=", 1)[1]
        if token == name and idx + 1 < len(tokens):
            return tokens[idx + 1]
    return None


def _collect_basler_settings(cmd_str: str | None) -> dict:
    if not cmd_str:
        return {}
    tokens = shlex.split(cmd_str)
    keys = {
        "serial": "--basler-serial",
        "name": "--basler-name",
        "pixel_format": "--basler-pixel-format",
        "exposure_us": "--basler-exposure-us",
        "gain": "--basler-gain",
        "offset_x": "--basler-offset-x",
        "offset_y": "--basler-offset-y",
        "interpacket_delay": "--basler-interpacket-delay",
        "timeout_ms": "--basler-timeout-ms",
        "width": "--width",
        "height": "--height",
        "fps": "--fps",
    }
    settings = {}
    for key, flag in keys.items():
        value = _extract_flag(tokens, flag)
        if value is not None:
            settings[key] = value
    return settings


def _stat_summary(series: pd.Series) -> dict | None:
    if series is None:
        return None
    series = series.dropna()
    if series.empty:
        return None
    p90 = float(np.percentile(series, 90))
    return {
        "median": float(series.median()),
        "p90": p90,
        "max": float(series.max()),
    }


def _median(series: pd.Series) -> float | None:
    if series is None:
        return None
    series = series.dropna()
    if series.empty:
        return None
    return float(series.median())


def _fmt_stat(label: str, stats: dict | None) -> str:
    if not stats:
        return f"{label}: n/a"
    return f"{label}: med={stats['median']:.1f} p90={stats['p90']:.1f} max={stats['max']:.1f}"


def _format_settings(settings: dict) -> str:
    if not settings:
        return "- basler: n/a"
    parts = [
        f"serial={settings.get('serial', 'n/a')}",
        f"name={settings.get('name', 'n/a')}",
        f"size={settings.get('width', '?')}x{settings.get('height', '?')}",
        f"offset={settings.get('offset_x', '?')},{settings.get('offset_y', '?')}",
        f"fps={settings.get('fps', '?')}",
        f"pixel={settings.get('pixel_format', '?')}",
        f"exposure_us={settings.get('exposure_us', '?')}",
        f"gain={settings.get('gain', '?')}",
        f"interpacket_delay={settings.get('interpacket_delay', '?')}",
        f"timeout_ms={settings.get('timeout_ms', '?')}",
    ]
    return "- basler: " + " ".join(parts)


def _format_kpi(stats: dict | None, threshold: float) -> str:
    if not stats:
        return "KPI (p90 t_total_ms <= {:.0f}): n/a".format(threshold)
    status = "PASS" if stats["p90"] <= threshold else "FAIL"
    return f"KPI (p90 t_total_ms <= {threshold:.0f}): {status} (p90={stats['p90']:.1f}ms)"


def _format_worst(df: pd.DataFrame, n: int) -> list[str]:
    if n <= 0 or "t_total_ms" not in df.columns:
        return []
    worst = df.nlargest(n, "t_total_ms")
    lines = []
    for idx, row in worst.iterrows():
        frame_id = row.get("frame_idx")
        if frame_id is None or (isinstance(frame_id, float) and np.isnan(frame_id)):
            frame_id = int(idx) + 1
        t_total = row.get("t_total_ms", float("nan"))
        t_detect = row.get("t_detect_ms", float("nan"))
        t_ransac = row.get("t_ransac_ms", float("nan"))
        lines.append(
            f"frame={frame_id} t_total={t_total:.1f} t_detect={t_detect:.1f} t_ransac={t_ransac:.1f}"
        )
    return lines


def main():
    args = _parse_args()
    debug_path = Path(args.debug_csv)
    cmd_str = _load_cmd(args.cmd)

    header = _parse_header_json(debug_path)
    df = pd.read_csv(debug_path, comment="#")

    t_total_stats = _stat_summary(df["t_total_ms"]) if "t_total_ms" in df.columns else None
    t_detect_stats = _stat_summary(df["t_detect_ms"]) if "t_detect_ms" in df.columns else None
    t_ransac_stats = _stat_summary(df["t_ransac_ms"]) if "t_ransac_ms" in df.columns else None

    dets_col = "n_visible" if "n_visible" in df.columns else "n_dets_raw"
    inliers_col = "n_inliers" if "n_inliers" in df.columns else None
    reproj_col = "mean_reproj" if "mean_reproj" in df.columns else "mean_reproj_px"

    dets_med = _median(df[dets_col]) if dets_col in df.columns else None
    inliers_med = _median(df[inliers_col]) if inliers_col and inliers_col in df.columns else None
    reproj_med = _median(df[reproj_col]) if reproj_col in df.columns else None

    calib_path = _get_calib_path(header, cmd_str)
    basler_settings = _collect_basler_settings(cmd_str)

    lines = ["Run summary"]
    if cmd_str:
        lines.append(f"- cmd: {cmd_str}")
    lines.append(_format_settings(basler_settings))
    lines.append(f"- outputs: poses={args.poses_csv} debug={debug_path} calib={calib_path or 'unknown'}")
    lines.append(f"- rows: {len(df)}")
    lines.append(f"- {_fmt_stat('t_total_ms', t_total_stats)}")
    lines.append(f"- {_fmt_stat('t_detect_ms', t_detect_stats)}")
    lines.append(f"- {_fmt_stat('t_ransac_ms', t_ransac_stats)}")
    lines.append(
        f"- medians: dets={dets_med if dets_med is not None else 'n/a'} "
        f"inliers={inliers_med if inliers_med is not None else 'n/a'} "
        f"reproj={reproj_med if reproj_med is not None else 'n/a'}"
    )
    lines.append(f"- {_format_kpi(t_total_stats, args.kpi_ms)}")

    worst_lines = _format_worst(df, args.print_worst)
    if worst_lines:
        lines.append(f"- worst {args.print_worst} by t_total_ms:")
        lines.extend([f"- {line}" for line in worst_lines])

    output = "\n".join(lines)
    print(output)

    if args.out_md:
        out_path = Path(args.out_md)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(output + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
