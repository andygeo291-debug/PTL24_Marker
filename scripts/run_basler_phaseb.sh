#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "$REPO_ROOT"

TIMESTAMP="$(date +%Y%m%d_%H%M%S)"

SERIAL="${SERIAL:-21601161}"
NAME="${NAME:-StaticCam}"
WIDTH="${WIDTH:-960}"
HEIGHT="${HEIGHT:-720}"
FPS="${FPS:-15}"
PIXEL_FORMAT="${PIXEL_FORMAT:-Mono8}"
EXPOSURE_US="${EXPOSURE_US:-15000}"
GAIN="${GAIN:-0}"
OFFSET_X="${OFFSET_X:-320}"
OFFSET_Y="${OFFSET_Y:-200}"
INTERPACKET_DELAY="${INTERPACKET_DELAY:-3500}"
TIMEOUT_MS="${TIMEOUT_MS:-1000}"
RIG="${RIG:-phase_b/rigs/cyl_dotec.yaml}"
CALIB="${CALIB:-common/calib/basler_static_960x720_offx320_offy200_mono8.yaml}"
RANSAC_ITERS="${RANSAC_ITERS:-15}"
KPI_MS="${KPI_MS:-100}"

DEFAULT_TAG="basler_roi${WIDTH}x${HEIGHT}_off${OFFSET_X}_${OFFSET_Y}_fps${FPS}_exp${EXPOSURE_US}_r${RANSAC_ITERS}_${TIMESTAMP}"
RUN_TAG="${1:-$DEFAULT_TAG}"
RUN_DIR="runs/${RUN_TAG}"

mkdir -p "$RUN_DIR"

POSES_CSV="${RUN_DIR}/poses.csv"
DEBUG_CSV="${RUN_DIR}/debug_metrics.csv"
RUN_LOG="${RUN_DIR}/run.log"
RUN_CMD="${RUN_DIR}/run.cmd"
SUMMARY="${RUN_DIR}/summary.txt"

cmd=(
  python3 -m phase_b.v2.phase_b_tags_v2
  --camera-backend basler
  --basler-serial "$SERIAL"
  --basler-name "$NAME"
  --width "$WIDTH" --height "$HEIGHT" --fps "$FPS"
  --basler-pixel-format "$PIXEL_FORMAT"
  --basler-exposure-us "$EXPOSURE_US"
  --basler-gain "$GAIN"
  --basler-offset-x "$OFFSET_X"
  --basler-offset-y "$OFFSET_Y"
  --basler-interpacket-delay "$INTERPACKET_DELAY"
  --basler-timeout-ms "$TIMEOUT_MS"
  --rig "$RIG"
  --camera "$CALIB"
  --debug-metrics "$DEBUG_CSV"
  --save-poses "$POSES_CSV"
  --ransac --adapt --ransac-iters "$RANSAC_ITERS"
  --quiet-apriltag-stderr --no-hud
)

printf '%q ' "${cmd[@]}" > "$RUN_CMD"
printf '\n' >> "$RUN_CMD"

echo "Run dir: $RUN_DIR"

echo "Starting run..."
set +e
"${cmd[@]}" 2>&1 | tee "$RUN_LOG"
status=${PIPESTATUS[0]}
set -e

echo "Exit code: $status"

env DEBUG_CSV="$DEBUG_CSV" POSES_CSV="$POSES_CSV" CALIB="$CALIB" KPI_MS="$KPI_MS" \
  python3 - <<'PY' > "$SUMMARY"
import csv
import math
import os
import statistics

path = os.environ["DEBUG_CSV"]
poses = os.environ["POSES_CSV"]
calib = os.environ.get("CALIB", "")
kpi = float(os.environ.get("KPI_MS", "100"))

rows = []
header = None
with open(path, "r", encoding="utf-8") as handle:
    for line in handle:
        if line.startswith("#") or not line.strip():
            continue
        if header is None:
            header = [h.strip() for h in line.strip().split(",")]
            continue
        rows.append(line.strip().split(","))

if header is None:
    print("summary: no data rows")
    raise SystemExit(0)

idx = {name: i for i, name in enumerate(header)}

def get_series(col):
    if col not in idx:
        return []
    out = []
    for row in rows:
        if idx[col] >= len(row):
            continue
        try:
            out.append(float(row[idx[col]]))
        except ValueError:
            continue
    return out


def percentile(values, p):
    if not values:
        return None
    values = sorted(values)
    k = max(0, min(len(values) - 1, int(math.ceil(p * len(values)) - 1)))
    return values[k]


t_total = get_series("t_total_ms")
t_detect = get_series("t_detect_ms")
t_ransac = get_series("t_ransac_ms")

med_total = statistics.median(t_total) if t_total else None
p90_total = percentile(t_total, 0.90) if t_total else None
max_total = max(t_total) if t_total else None
med_detect = statistics.median(t_detect) if t_detect else None
med_ransac = statistics.median(t_ransac) if t_ransac else None

print("run summary")
print(f"rows: {len(rows)}")
print(f"poses_csv: {poses}")
print(f"debug_csv: {path}")
print(f"calib: {calib}")
if med_total is not None:
    print(f"t_total_ms: med={med_total:.1f} p90={p90_total:.1f} max={max_total:.1f}")
else:
    print("t_total_ms: n/a")
print(f"t_detect_ms: med={med_detect:.1f}" if med_detect is not None else "t_detect_ms: n/a")
print(f"t_ransac_ms: med={med_ransac:.1f}" if med_ransac is not None else "t_ransac_ms: n/a")
if p90_total is None:
    print(f"KPI p90<={kpi:.0f}: n/a")
else:
    status = "PASS" if p90_total <= kpi else "FAIL"
    print(f"KPI p90<={kpi:.0f}: {status} (p90={p90_total:.1f}ms)")
PY

echo "Summary: $SUMMARY"
exit "$status"
