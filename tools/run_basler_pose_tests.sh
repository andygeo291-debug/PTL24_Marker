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
export CALIB_PATH="${CALIB_PATH:-common/calib/basler_static_960x720_offx320_offy200_mono8_11mm.yaml}"

BASE_RAW="${RUN_BASE:-basler_test_runs}"
if [[ "$BASE_RAW" = /* ]]; then
  BASE_DIR="$(python3 -c 'import os,sys;print(os.path.abspath(sys.argv[1]))' "$BASE_RAW")"
else
  BASE_DIR="$(python3 -c 'import os,sys;print(os.path.abspath(sys.argv[1]))' "$ROOT/$BASE_RAW")"
fi
if command -v cygpath >/dev/null 2>&1; then
  BASE_DIR="$(cygpath -u "$BASE_DIR")"
fi

case "$BASE_DIR" in
  "$ROOT"/*) ;;
  *)
    echo "ERROR: RUN_BASE must be inside repo: $ROOT"
    exit 1
    ;;
esac

mkdir -p "$BASE_DIR"

next_num=1
shopt -s nullglob
for d in "$BASE_DIR"/basler_run_*; do
  [[ -d "$d" ]] || continue
  name="$(basename "$d")"
  if [[ "$name" =~ basler_run_([0-9]{4})_ ]]; then
    num="${BASH_REMATCH[1]}"
    if ((10#$num >= next_num)); then
      next_num=$((10#$num + 1))
    fi
  fi
done
shopt -u nullglob

run_tag="$(printf "basler_run_%04d_%s" "$next_num" "$(date +%Y%m%d_%H%M%S)")"
RUN_DIR="$BASE_DIR/$run_tag"
mkdir -p "$RUN_DIR"/{quick_checks,spike_on,spike_off,summary,summary/plots}

LOG_FILE="$RUN_DIR/terminal.log"
touch "$LOG_FILE"

log() {
  echo "$@" | tee -a "$LOG_FILE"
}

log "Run dir: $RUN_DIR"

CMD_LOG="$RUN_DIR/run_cmd.txt"
touch "$CMD_LOG"

record_cmd() {
  printf '%q ' "$@" >> "$CMD_LOG"
  printf '\n' >> "$CMD_LOG"
}

# --- stream diagnosis / autotune ---
DIAG_JSON="$RUN_DIR/summary/basler_stream_best.json"
DIAG_ENV="$RUN_DIR/summary/basler_stream_best.env"

python3 tools/basler_stream_diagnose.py \
  --serial "$BASLER_SERIAL" \
  --name "$BASLER_NAME" \
  --width "$WIDTH" --height "$HEIGHT" \
  --offset-x "$OFFSET_X" --offset-y "$OFFSET_Y" \
  --fps "$FPS" \
  --pixel-format "$PIXEL_FORMAT" \
  --exposure-us "$EXPOSURE_US" \
  --gain "$GAIN" \
  --frames 300 \
  --fail-threshold 0.01 \
  --packet-size-candidates "1500,1440,1400,1300,1200" \
  --interpacket-delay-candidates "3500,8000,12000" \
  --timeout-candidates "1000,2000" \
  --out-json "$DIAG_JSON" \
  --out-env "$DIAG_ENV" 2>&1 | tee -a "$LOG_FILE"

set -a
source "$DIAG_ENV"
set +a
IPD="${IPD:-$INTERPACKET_DELAY}"

COMMON_ARGS=(
  --camera-backend basler
  --basler-serial "$BASLER_SERIAL"
  --basler-name "$BASLER_NAME"
  --width "$WIDTH" --height "$HEIGHT" --fps "$FPS"
  --basler-pixel-format "$PIXEL_FORMAT"
  --basler-exposure-us "$EXPOSURE_US"
  --basler-gain "$GAIN"
  --basler-offset-x "$OFFSET_X" --basler-offset-y "$OFFSET_Y"
  --basler-interpacket-delay "$IPD"
  --basler-timeout-ms "$TIMEOUT_MS"
  --rig "$RIG_PATH"
  --camera "$CALIB_PATH"
  --ransac --adapt --ransac-iters 15
  --quiet-apriltag-stderr
  --no-hud
)

if [[ -n "${BASLER_PACKET_SIZE:-}" ]]; then
  COMMON_ARGS+=(--basler-packet-size "$BASLER_PACKET_SIZE")
fi

run_phaseb_save_poses() {
  local name="$1"
  local frames="$2"
  local poses_path="$3"
  local debug_path="$4"
  shift 4
  local -a extra_args=("$@")
  mkdir -p "$(dirname "$poses_path")" "$(dirname "$debug_path")"
  local fallback_debug="$ROOT/phase_b/debug_metrics.csv"
  local start_epoch
  start_epoch="$(date +%s)"
  local -a cmd=(
    python3 -m phase_b.v2.phase_b_tags_v2
    "${COMMON_ARGS[@]}"
    --frames "$frames"
    --save-poses "$poses_path"
    --debug-metrics-out "$debug_path"
  )
  if [[ "${#extra_args[@]}" -gt 0 ]]; then
    cmd+=("${extra_args[@]}")
  fi
  log "== $name ($frames frames) =="
  record_cmd "${cmd[@]}"
  "${cmd[@]}" 2>&1 | tee -a "$LOG_FILE"
  wc -l "$poses_path" "$debug_path"
  local pose_lines
  pose_lines="$(wc -l < "$poses_path")"
  if [[ "$pose_lines" -le 2 ]]; then
    echo "ERROR: $poses_path has no pose rows."
    exit 1
  fi
  local debug_lines
  debug_lines="$(wc -l < "$debug_path")"
  if [[ "$debug_lines" -le 2 ]]; then
    echo "ERROR: $debug_path has no debug rows."
    exit 1
  fi
  if [[ -f "$fallback_debug" ]]; then
    local fallback_mtime
    fallback_mtime="$(stat -f %m "$fallback_debug")"
    if [[ "$fallback_mtime" -ge "$start_epoch" ]]; then
      echo "ERROR: debug metrics wrote to $fallback_debug (unexpected)."
      exit 1
    fi
  fi
}

run_phaseb_poses_out() {
  local name="$1"
  local frames="$2"
  local poses_path="$3"
  local debug_path="$4"
  shift 4
  local -a extra_args=("$@")
  mkdir -p "$(dirname "$poses_path")" "$(dirname "$debug_path")"
  local fallback_debug="$ROOT/phase_b/debug_metrics.csv"
  local start_epoch
  start_epoch="$(date +%s)"
  local -a cmd=(
    python3 -m phase_b.v2.phase_b_tags_v2
    "${COMMON_ARGS[@]}"
    --frames "$frames"
    --poses-out "$poses_path"
    --debug-metrics-out "$debug_path"
  )
  if [[ "${#extra_args[@]}" -gt 0 ]]; then
    cmd+=("${extra_args[@]}")
  fi
  log "== $name ($frames frames) =="
  record_cmd "${cmd[@]}"
  "${cmd[@]}" 2>&1 | tee -a "$LOG_FILE"
  wc -l "$poses_path" "$debug_path"
  local pose_lines
  pose_lines="$(wc -l < "$poses_path")"
  if [[ "$pose_lines" -le 2 ]]; then
    echo "ERROR: $poses_path has no pose rows."
    exit 1
  fi
  local debug_lines
  debug_lines="$(wc -l < "$debug_path")"
  if [[ "$debug_lines" -le 2 ]]; then
    echo "ERROR: $debug_path has no debug rows."
    exit 1
  fi
  if [[ -f "$fallback_debug" ]]; then
    local fallback_mtime
    fallback_mtime="$(stat -f %m "$fallback_debug")"
    if [[ "$fallback_mtime" -ge "$start_epoch" ]]; then
      echo "ERROR: debug metrics wrote to $fallback_debug (unexpected)."
      exit 1
    fi
  fi
}

run_phaseb_save_poses \
  "quick_checks_save_poses" \
  30 \
  "$RUN_DIR/quick_checks/poses_save_poses.csv" \
  "$RUN_DIR/quick_checks/debug_save_poses.csv"

run_phaseb_poses_out \
  "quick_checks_poses_out" \
  30 \
  "$RUN_DIR/quick_checks/poses_poses_out.csv" \
  "$RUN_DIR/quick_checks/debug_poses_out.csv"

run_phaseb_save_poses \
  "basler_pose_A_spikeON" \
  600 \
  "$RUN_DIR/spike_on/poses.csv" \
  "$RUN_DIR/spike_on/debug_metrics.csv"

run_phaseb_save_poses \
  "basler_pose_B_spikeOFF" \
  600 \
  "$RUN_DIR/spike_off/poses.csv" \
  "$RUN_DIR/spike_off/debug_metrics.csv" \
  --spike-disable

export RUN_DIR
python3 - <<'PY' 2>&1 | tee -a "$LOG_FILE"
import csv
import json
import os
import subprocess
from pathlib import Path

import cv2
import numpy as np
import pandas as pd

run_dir = Path(os.environ["RUN_DIR"])
KPI_MEDIAN_MS = 100.0
KPI_P90_MS = 120.0

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

summary_dir = run_dir / "summary"
summary_dir.mkdir(parents=True, exist_ok=True)

runs = {
    "spike_on": run_dir / "spike_on",
    "spike_off": run_dir / "spike_off",
}

table_rows = []
lines = []
lines.append("# Basler Pose Test Summary")
lines.append("")
lines.append(f"- Commit: `{git_commit()}`")
lines.append(f"- Run dir: `{run_dir}`")
lines.append("")

for name, path in runs.items():
    poses_path = path / "poses.csv"
    debug_path = path / "debug_metrics.csv"
    poses_df = load_pose_df(poses_path)
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

    stats = {}
    for col in ["t_total_ms", "t_detect_ms", "t_ransac_ms", "mean_reproj_px"]:
        stats[col] = timing_stats(debug_df, col)
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
        }
    )

if all(key in runs for key in ("spike_on", "spike_off")):
    on = next(row for row in table_rows if row["run"] == "spike_on")
    off = next(row for row in table_rows if row["run"] == "spike_off")
    lines.append("## Spike ON vs OFF")
    lines.append(
        f"- reject_rate: on={on['reject_rate']:.3f} off={off['reject_rate']:.3f}"
    )
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

lines.append("## Failure Modes and Fixes")
lines.append(
    "- REJECT_SPIKE triggers when tilt jump exceeds max_tilt_jump_deg or when translation delta "
    "exceeds spike_trans_thresh_m (if set). It compares against the last accepted pose and skips "
    "spike checks for the first spike_reset_after frames after acceptance."
)
lines.append(
    "- Empty outputs usually come from camera lock (another app using the device), "
    "frame grab timeouts, or writing debug metrics to the default path. "
    "The runner now asserts outputs and checks for fallback debug writes."
)
lines.append(
    "- Stability improvements: ensure >=3 tags in view, reduce motion blur (more light/shorter exposure), "
    "verify calibration matches ROI, and consider relaxing spike thresholds slightly if the rig is stable."
)
lines.append("")

diag_path = summary_dir / "basler_stream_best.json"
if diag_path.exists():
    diag = json.loads(diag_path.read_text())
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
summary_path.write_text("\n".join(lines) + "\n")

table_path = summary_dir / "meeting_table.csv"
with table_path.open("w", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=table_rows[0].keys())
    writer.writeheader()
    writer.writerows(table_rows)

print(f"Wrote {summary_path}")
print(f"Wrote {table_path}")
snippet_lines = []
snippet_lines.append("Basler Long-Run Summary")
snippet_lines.append(f"- Run dir: {run_dir}")
if diag_path.exists():
    diag = json.loads(diag_path.read_text())
    best = diag.get("best", {})
    snippet_lines.append(
        "- Stream best: packet=%s ipd=%s timeout=%s fail_rate=%.4f"
        % (
            best.get("packet_size"),
            best.get("interpacket_delay"),
            best.get("timeout_ms"),
            float(best.get("fail_rate", 1.0)),
        )
    )
if all(key in runs for key in ("spike_on", "spike_off")):
    on = next(row for row in table_rows if row["run"] == "spike_on")
    off = next(row for row in table_rows if row["run"] == "spike_off")
    snippet_lines.append(
        "- spike_on KPI: %s (median %.1f / p90 %.1f)"
        % (
            "PASS" if on["kpi_pass"] else "FAIL",
            on["t_total_ms_median"],
            on["t_total_ms_p90"],
        )
    )
    snippet_lines.append(
        "- spike_off KPI: %s (median %.1f / p90 %.1f)"
        % (
            "PASS" if off["kpi_pass"] else "FAIL",
            off["t_total_ms_median"],
            off["t_total_ms_p90"],
        )
    )
    snippet_lines.append(
        "- timing (median t_total_ms): on=%.1f ms, off=%.1f ms"
        % (on["t_total_ms_median"], off["t_total_ms_median"])
    )
    snippet_lines.append(
        "- stability (tvec std): on=%s, off=%s"
        % ("see MEETING_SUMMARY.md", "see MEETING_SUMMARY.md")
    )
snippet_lines.append("- Summary/plots: summary/MEETING_SUMMARY.md + summary/plots/*.png")

snippet_path = summary_dir / "SLIDE_SNIPPET.md"
snippet_path.write_text("\n".join(snippet_lines) + "\n")
print(f"Wrote {snippet_path}")
plots_dir = summary_dir / "plots"
plots_dir.mkdir(parents=True, exist_ok=True)
try:
    import matplotlib.pyplot as plt

    for name, path in runs.items():
        debug_df = pd.read_csv(path / "debug_metrics.csv", comment="#")
        poses_df = load_pose_df(path / "poses.csv")

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
PY
