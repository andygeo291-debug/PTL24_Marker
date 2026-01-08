#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ -f venv/bin/activate ]]; then
  # shellcheck disable=SC1091
  source venv/bin/activate
fi

export BASLER_SERIAL="21601161"
export BASLER_NAME="StaticCam"
export WIDTH="960"
export HEIGHT="720"
export FPS="15"
export PIXEL_FORMAT="Mono8"
export EXPOSURE_US="15000"
export GAIN="0"
export OFFSET_X="320"
export OFFSET_Y="200"
export INTERPACKET_DELAY="3500"
export TIMEOUT_MS="1000"
export RIG_PATH="phase_b/rigs/cyl_dotec.yaml"
export CALIB_PATH="common/calib/basler_static_960x720_offx320_offy200_mono8.yaml"

RUN_BASE="${RUN_BASE:-$HOME/ptl_runs/basler_pose_tests_$(date +%Y%m%d_%H%M%S)}"
mkdir -p "$RUN_BASE"

COMMON_ARGS=(
  --camera-backend basler
  --basler-serial "$BASLER_SERIAL"
  --basler-name "$BASLER_NAME"
  --width "$WIDTH" --height "$HEIGHT" --fps "$FPS"
  --basler-pixel-format "$PIXEL_FORMAT"
  --basler-exposure-us "$EXPOSURE_US"
  --basler-gain "$GAIN"
  --basler-offset-x "$OFFSET_X" --basler-offset-y "$OFFSET_Y"
  --basler-interpacket-delay "$INTERPACKET_DELAY"
  --basler-timeout-ms "$TIMEOUT_MS"
  --rig "$RIG_PATH"
  --camera "$CALIB_PATH"
  --ransac --adapt --ransac-iters 15
  --quiet-apriltag-stderr
  --no-hud
)

echo "Run base: $RUN_BASE"

run_case() {
  local name="$1"
  local frames="$2"
  local -a extra_args=()
  shift 2
  extra_args=("$@")
  local run_dir="$RUN_BASE/$name"
  mkdir -p "$run_dir"
  echo "== $name ($frames frames) =="
  if [[ "${#extra_args[@]}" -gt 0 ]]; then
    python3 -m phase_b.v2.phase_b_tags_v2 \
      --save-run --run-name "$name" --run-dir "$run_dir" \
      "${COMMON_ARGS[@]}" \
      --frames "$frames" \
      --save-poses "$run_dir/poses.csv" \
      --debug-metrics-out "$run_dir/debug_metrics.csv" \
      "${extra_args[@]}"
  else
    python3 -m phase_b.v2.phase_b_tags_v2 \
      --save-run --run-name "$name" --run-dir "$run_dir" \
      "${COMMON_ARGS[@]}" \
      --frames "$frames" \
      --save-poses "$run_dir/poses.csv" \
      --debug-metrics-out "$run_dir/debug_metrics.csv"
  fi
  wc -l "$run_dir/poses.csv" "$run_dir/debug_metrics.csv"
  local pose_lines
  pose_lines="$(wc -l < "$run_dir/poses.csv")"
  if [[ "$pose_lines" -le 2 ]]; then
    echo "ERROR: $run_dir/poses.csv has no pose rows."
    exit 1
  fi
}

run_case "basler_pose_smoke_nohud" 30
run_case "basler_pose_A_spikeON" 300
run_case "basler_pose_B_spikeOFF" 300 --spike-disable

export RUN_BASE
python3 - <<'PY'
import json
import os
import subprocess
from pathlib import Path

import cv2
import numpy as np
import pandas as pd

run_base = Path(os.environ["RUN_BASE"])
runs = [
    "basler_pose_smoke_nohud",
    "basler_pose_A_spikeON",
    "basler_pose_B_spikeOFF",
]

def git_commit() -> str:
    try:
        return (
            subprocess.check_output(["git", "rev-parse", "HEAD"], text=True)
            .strip()
        )
    except Exception:
        return "unknown"

def load_pose_df(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, comment="#")

def rvec_to_ypr_deg(rvec: np.ndarray) -> np.ndarray:
    R, _ = cv2.Rodrigues(rvec)
    yaw = np.degrees(np.arctan2(R[1, 0], R[0, 0]))
    pitch = np.degrees(np.arctan2(-R[2, 0], np.hypot(R[2, 1], R[2, 2])))
    roll = np.degrees(np.arctan2(R[2, 1], R[2, 2]))
    return np.array([yaw, pitch, roll], dtype=float)

def drift_stats(values: np.ndarray) -> dict:
    if len(values) == 0:
        return {}
    base = values[0]
    drift = values - base
    return {
        "std": np.std(drift, axis=0),
        "p10": np.percentile(drift, 10, axis=0),
        "p90": np.percentile(drift, 90, axis=0),
        "min": np.min(drift, axis=0),
        "max": np.max(drift, axis=0),
    }

def timing_stats(df: pd.DataFrame, col: str) -> dict:
    s = df[col].dropna()
    return {
        "median": float(s.median()),
        "p90": float(s.quantile(0.9)),
        "max": float(s.max()),
    }

lines = []
lines.append("# Basler Pose Test Results")
lines.append("")
lines.append(f"- Commit: `{git_commit()}`")
lines.append(f"- Run base: `{run_base}`")
lines.append("")

for name in runs:
    run_dir = run_base / name
    poses_path = run_dir / "poses.csv"
    debug_path = run_dir / "debug_metrics.csv"
    poses_df = load_pose_df(poses_path)
    debug_df = pd.read_csv(debug_path, comment="#")
    poses_count = len(poses_df)
    debug_count = len(debug_df)

    lines.append(f"## {name}")
    lines.append(f"- Run dir: `{run_dir}`")
    lines.append(f"- poses.csv rows: {poses_count}")
    lines.append(f"- debug_metrics.csv rows: {debug_count}")

    if debug_count:
        stats = {c: timing_stats(debug_df, c) for c in [
            "t_total_ms", "t_detect_ms", "t_ransac_ms", "mean_reproj_px"
        ]}
        lines.append("- Timing stats (ms):")
        for col, st in stats.items():
            lines.append(
                f"  - {col}: median={st['median']:.3f} p90={st['p90']:.3f} max={st['max']:.3f}"
            )
        if "reject_reason" in debug_df.columns:
            counts = debug_df["reject_reason"].value_counts().to_dict()
            lines.append("- reject_reason counts:")
            for key, val in counts.items():
                lines.append(f"  - {key}: {val}")

    if poses_count:
        tvec = poses_df[["tvec_cam_x", "tvec_cam_y", "tvec_cam_z"]].to_numpy(float)
        rvec = poses_df[["rvec_cam_x", "rvec_cam_y", "rvec_cam_z"]].to_numpy(float)
        ypr = np.vstack([rvec_to_ypr_deg(rv) for rv in rvec])
        tvec_stats = drift_stats(tvec)
        ypr_stats = drift_stats(ypr)

        def fmt_vec(v: np.ndarray) -> str:
            return "[" + ", ".join(f"{x:.4f}" for x in v) + "]"

        lines.append("- Drift stats vs first pose:")
        lines.append(f"  - tvec_cam std: {fmt_vec(tvec_stats['std'])}")
        lines.append(f"  - tvec_cam p10: {fmt_vec(tvec_stats['p10'])}")
        lines.append(f"  - tvec_cam p90: {fmt_vec(tvec_stats['p90'])}")
        lines.append(f"  - tvec_cam min: {fmt_vec(tvec_stats['min'])}")
        lines.append(f"  - tvec_cam max: {fmt_vec(tvec_stats['max'])}")
        lines.append(f"  - ypr_deg std: {fmt_vec(ypr_stats['std'])}")
        lines.append(f"  - ypr_deg p10: {fmt_vec(ypr_stats['p10'])}")
        lines.append(f"  - ypr_deg p90: {fmt_vec(ypr_stats['p90'])}")
        lines.append(f"  - ypr_deg min: {fmt_vec(ypr_stats['min'])}")
        lines.append(f"  - ypr_deg max: {fmt_vec(ypr_stats['max'])}")

    lines.append("")

out_path = run_base / "RESULTS.md"
out_path.write_text("\n".join(lines) + "\n")
print(f"Wrote {out_path}")
PY
