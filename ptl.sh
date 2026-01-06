#!/usr/bin/env bash
set -euo pipefail

# ------------------------------------------------------------
# PTL24 Phase B portable runner (macOS/Linux)
# ------------------------------------------------------------

VENV_DIR="${VENV_DIR:-venv}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
POSE_CSV="phase_b/poses.csv"
POSE_EULER_CSV="phase_b/poses_with_euler.csv"
EXTR_FILE="common/extrinsics/T_WC.yaml"
GREEN="$(printf '\033[32m')"
BOLD="$(printf '\033[1m')"
RESET="$(printf '\033[0m')"

usage() {
  cat <<USAGE
${BOLD}PTL24 Phase B runner${RESET}

Usage: ./ptl.sh <command> [extra-args]

Commands:
  help         Show this help
  venv         Create Python virtual environment (${VENV_DIR})
  deps         Install runtime dependencies (numpy, opencv-python, pandas, matplotlib)
  extrinsics   Generate ${EXTR_FILE} (uses HEIGHT, PITCH env; defaults HEIGHT=1.07 PITCH=-19)
  run          Execute phase_b/phase_b_tags.py (accepts extra args appended)
  euler        Augment ${POSE_CSV} with yaw/pitch/roll into ${POSE_EULER_CSV}
  plot         Plot Euler angles using matplotlib (outputs phase_b/poses_with_euler.png)
  all          Run venv → deps → extrinsics → run → euler → plot
  udp          Start UDP pose receiver (PORT env var, default 6006)

Environment overrides:
  HEIGHT (default 1.07 m), PITCH (default -19 deg), VIDEO (camera index/path),
  IGNORE_IDS (comma-separated), PORT (UDP port), PYTHON_BIN, VENV_DIR.

Examples:
  ./ptl.sh venv
  ./ptl.sh deps
  HEIGHT=1.10 PITCH=-22 ./ptl.sh extrinsics
  VIDEO=0 IGNORE_IDS=104,202 ./ptl.sh run
  ./ptl.sh udp
USAGE
}

ensure_venv() {
  if [[ ! -d "${VENV_DIR}" ]]; then
    echo "🔧 Creating virtual environment at ${VENV_DIR}"
    "${PYTHON_BIN}" -m venv "${VENV_DIR}"
    echo "✅ Virtualenv created"
  else
    echo "ℹ️ Virtualenv already exists (${VENV_DIR})"
  fi
}

activate_venv() {
  if [[ ! -d "${VENV_DIR}" ]]; then
    echo "❌ Virtualenv not found. Run './ptl.sh venv' first." >&2
    exit 1
  fi
  # shellcheck disable=SC1090
  source "${VENV_DIR}/bin/activate"
}

install_deps() {
  activate_venv
  echo "📦 Installing dependencies..."
  pip install --upgrade pip >/dev/null
  pip install numpy opencv-python pandas matplotlib pupil-apriltags >/dev/null
  echo "${GREEN}✅ Dependencies installed${RESET}"
}

generate_extrinsics() {
  local height pitch
  height="${HEIGHT:-1.07}"
  pitch="${PITCH:--19}"

  mkdir -p "$(dirname "${EXTR_FILE}")"

  "${PYTHON_BIN}" - <<PY
import math, pathlib

height = float("${height}")
pitch_deg = float("${pitch}")
pitch_rad = math.radians(pitch_deg)

c = math.cos(pitch_rad)
s = math.sin(pitch_rad)

# Rotation about X-axis by pitch
rows = [
    1.0, 0.0, 0.0, 0.0,
    0.0, c,  -s,  -height * math.sin(pitch_rad) * -1,
    0.0, s,   c,  -height * c,
    0.0, 0.0, 0.0, 1.0,
]

# Fix translation terms explicitly
rows[7]  = -height * math.sin(pitch_rad) * -1
rows[11] = -height * c

data = ",\n    ".join(f"{v:.6f}" for v in rows)

content = f"""%YAML:1.0
---
T_WC:
  rows: 4
  cols: 4
  data: [
    {data}
  ]
"""

path = pathlib.Path("${EXTR_FILE}")
path.write_text(content)
PY
  echo "${GREEN}✅ Extrinsics written to ${EXTR_FILE}${RESET}"
}

run_pipeline() {
  activate_venv
  mkdir -p "$(dirname "${POSE_CSV}")"
  mkdir -p "$(dirname "${EXTR_FILE}")"

  if [[ ! -f "${EXTR_FILE}" ]]; then
    echo "ℹ️ Extrinsics not found; generating defaults."
    generate_extrinsics
  fi

  local video_arg=()
  if [[ -n "${VIDEO:-}" ]]; then
    video_arg=(--video "${VIDEO}")
  fi

  local ignore_arg=()
  if [[ -n "${IGNORE_IDS:-}" ]]; then
    ignore_arg=(--ignore-ids "${IGNORE_IDS}")
  fi

  python phase_b/phase_b_tags.py \
    --camera common/calib/calib.yaml \
    --rig phase_b/rigs/cyl_paper.yaml \
    --extrinsics "${EXTR_FILE}" \
    --save-poses "${POSE_CSV}" \
    --ransac --ransac-trans 0.05 --ransac-rot 5 \
    --ema-alpha 0.3 \
    --min-inliers 3 \
    --max-tilt-jump-deg 15 \
    --print-tilt \
    "${video_arg[@]}" \
    "${ignore_arg[@]}" \
    "$@"

  echo "${GREEN}🚀 Phase B run complete${RESET}"
}

augment_euler() {
  activate_venv
  if [[ ! -f "${POSE_CSV}" ]]; then
    echo "❌ ${POSE_CSV} not found. Run './ptl.sh run' first." >&2
    exit 1
  fi

  python phase_b/tools/augment_poses.py \
    --source "${POSE_CSV}" \
    --out "${POSE_EULER_CSV}" \
    --frame both \
    --overwrite

  echo "${GREEN}✅ Euler angles written to ${POSE_EULER_CSV}${RESET}"
}

plot_euler() {
  activate_venv
  if [[ ! -f "${POSE_EULER_CSV}" ]]; then
    echo "ℹ️ Euler CSV missing; generating first."
    augment_euler
  fi

  python - <<'PY'
import pandas as pd
import matplotlib.pyplot as plt
from pathlib import Path

csv_path = Path("phase_b/poses_with_euler.csv")
df = pd.read_csv(csv_path)

required = ["yaw_cam_deg", "pitch_cam_deg", "roll_cam_deg"]
if not all(col in df.columns for col in required):
    raise SystemExit("Yaw/pitch/roll columns missing; run ./ptl.sh euler first.")

plt.figure(figsize=(10, 6))
plt.plot(df.index, df["yaw_cam_deg"], label="Yaw (deg)")
plt.plot(df.index, df["pitch_cam_deg"], label="Pitch (deg)")
plt.plot(df.index, df["roll_cam_deg"], label="Roll (deg)")
plt.xlabel("Frame")
plt.ylabel("Degrees")
plt.title("Camera-frame Euler Angles")
plt.legend()
plt.grid(True)
out_path = Path("phase_b/poses_with_euler.png")
plt.tight_layout()
plt.savefig(out_path, dpi=150)
print(f"✅ Plot saved to {out_path}")
PY
}

start_udp() {
  activate_venv
  local port="${PORT:-6006}"
  python phase_b/udp_receive_pose.py --port "${port}"
}

run_all() {
  ensure_venv
  install_deps
  generate_extrinsics
  run_pipeline "$@"
  augment_euler
  plot_euler
  echo "${GREEN}✅ All steps completed${RESET}"
}

cmd="${1:-help}"
shift || true

case "${cmd}" in
  help) usage ;;
  venv) ensure_venv ;;
  deps) install_deps ;;
  extrinsics) generate_extrinsics ;;
  run) run_pipeline "$@" ;;
  euler) augment_euler ;;
  plot) plot_euler ;;
  udp) start_udp ;;
  all) run_all "$@" ;;
  *)
    echo "Unknown command: ${cmd}" >&2
    usage
    exit 1
    ;;
esac
