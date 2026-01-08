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
export LENS_ZOOM_MM="11"
export LENS_NOTES="Kowa 1/1.8 f1.6/4.4-11mm; zoom locked at 11mm; focus locked"

export BOARD_COLS="${BOARD_COLS:-9}"
export BOARD_ROWS="${BOARD_ROWS:-6}"
export BOARD_SQUARE_SIZE_M="${BOARD_SQUARE_SIZE_M:-0.025}"
export NUM_IMAGES="${NUM_IMAGES:-60}"

BASE_RAW="${RUN_BASE:-calib_runs}"
if [[ "$BASE_RAW" = /* ]]; then
  BASE_DIR="$(python3 -c 'import os,sys;print(os.path.abspath(sys.argv[1]))' "$BASE_RAW")"
else
  BASE_DIR="$(python3 -c 'import os,sys;print(os.path.abspath(sys.argv[1]))' "$ROOT/$BASE_RAW")"
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
for d in "$BASE_DIR"/basler_intrinsics_*; do
  [[ -d "$d" ]] || continue
  name="$(basename "$d")"
  if [[ "$name" =~ basler_intrinsics_([0-9]{4})_ ]]; then
    num="${BASH_REMATCH[1]}"
    if ((10#$num >= next_num)); then
      next_num=$((10#$num + 1))
    fi
  fi
done
shopt -u nullglob

run_tag="$(printf "basler_intrinsics_%04d_%s" "$next_num" "$(date +%Y%m%d_%H%M%S)")"
RUN_DIR="$BASE_DIR/$run_tag"
IMAGES_DIR="$RUN_DIR/images"
mkdir -p "$IMAGES_DIR"

exec > >(tee -a "$RUN_DIR/terminal.log") 2>&1

export RUN_DIR
export IMAGES_DIR
export PYTHONPATH="$ROOT"

python3 - <<'PY'
import json
import os
import time
from pathlib import Path

meta = {
    "timestamp": time.time(),
    "camera": {
        "serial": os.environ["BASLER_SERIAL"],
        "name": os.environ["BASLER_NAME"],
        "width": int(os.environ["WIDTH"]),
        "height": int(os.environ["HEIGHT"]),
        "fps": float(os.environ["FPS"]),
        "pixel_format": os.environ["PIXEL_FORMAT"],
        "exposure_us": float(os.environ["EXPOSURE_US"]),
        "gain": float(os.environ["GAIN"]),
        "offset_x": int(os.environ["OFFSET_X"]),
        "offset_y": int(os.environ["OFFSET_Y"]),
        "interpacket_delay": int(os.environ["INTERPACKET_DELAY"]),
        "timeout_ms": int(os.environ["TIMEOUT_MS"]),
    },
    "lens": {
        "zoom_mm": float(os.environ["LENS_ZOOM_MM"]),
        "notes": os.environ["LENS_NOTES"],
    },
    "board": {
        "cols": int(os.environ["BOARD_COLS"]),
        "rows": int(os.environ["BOARD_ROWS"]),
        "square_size_m": float(os.environ["BOARD_SQUARE_SIZE_M"]),
    },
    "capture": {
        "num_images": int(os.environ["NUM_IMAGES"]),
    },
}

out = Path(os.environ["RUN_DIR"]) / "calib_meta.json"
out.write_text(json.dumps(meta, indent=2) + "\n")
print(f"Wrote {out}")
PY

python3 - <<'PY'
import os
import sys
from pathlib import Path

import cv2

ROOT = Path(os.environ["PYTHONPATH"])
sys.path.insert(0, str(ROOT))

from common.camera.basler_cam import BaslerGigECam  # noqa: E402

count = int(os.environ["NUM_IMAGES"])
out_dir = Path(os.environ["IMAGES_DIR"])

print("Basler calibration capture")
print("Instructions:")
print("- Move the chessboard through the FOV (tilt/rotate/translate).")
print("- Press SPACE to save a frame.")
print("- Press Q or ESC to quit early.")
print(f"- Target images: {count}")

cam = BaslerGigECam(
    serial=os.environ["BASLER_SERIAL"],
    name=os.environ["BASLER_NAME"],
    width=int(os.environ["WIDTH"]),
    height=int(os.environ["HEIGHT"]),
    offset_x=int(os.environ["OFFSET_X"]),
    offset_y=int(os.environ["OFFSET_Y"]),
    fps=float(os.environ["FPS"]),
    pixel_format=os.environ["PIXEL_FORMAT"],
    exposure_us=float(os.environ["EXPOSURE_US"]),
    gain=float(os.environ["GAIN"]),
    interpacket_delay=int(os.environ["INTERPACKET_DELAY"]),
    timeout_ms=int(os.environ["TIMEOUT_MS"]),
)

cam.open()
saved = 0
try:
    while True:
        ok, frame = cam.read()
        if not ok:
            continue
        display = frame
        if display.ndim == 2:
            display = cv2.cvtColor(display, cv2.COLOR_GRAY2BGR)
        cv2.putText(
            display,
            f"saved {saved}/{count}",
            (10, 30),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            (0, 255, 0),
            2,
            cv2.LINE_AA,
        )
        cv2.imshow("Basler Calib Capture (SPACE=save, Q=quit)", display)
        key = cv2.waitKey(1) & 0xFF
        if key in (ord("q"), 27):
            break
        if key == ord(" "):
            saved += 1
            out_path = out_dir / f"img_{saved:04d}.png"
            cv2.imwrite(str(out_path), frame)
            print(f"Saved {out_path}")
            if saved >= count:
                break
finally:
    cam.release()
    cv2.destroyAllWindows()

if saved < count:
    raise SystemExit(
        f"Captured {saved}/{count} images; rerun to reach target count."
    )

print(f"Capture complete: {saved} images -> {out_dir}")
PY
