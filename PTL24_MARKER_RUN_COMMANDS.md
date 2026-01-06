# PTL24_MARKER Run Commands

This document centralises the canonical commands for PTL24 marker-based pose tracking across Phase A and Phase B (v1 + v2), plus supporting utilities, calibration helpers, and validation scripts.

---

## Repository Overview

- `phase_a/` – AprilTag-based detection, calibration helpers, and visualization apps (e.g. `apriltag_demo.py`, `setup_and_run.py`).
- `phase_b/v1/` – Legacy Phase B runner (`phase_b_tags.py`) plus helper modules reused by v2.
- `phase_b/v2/` – Current Phase B runner (`phase_b_tags_v2.py`), weighted fusion, adaptive RANSAC, HUD, benchmarking.
- `phase_b/tools/` – CSV comparison (`compare_poses.py`), metrics analysis (`analyze_metrics.py`), validation archiving, pose augmentation, cleanup scripts.
- `phase_b/` root – configs, rigs, example pose CSVs, UDP receiver, validation outputs.
- `common/` – shared camera calibrations (`common/calib/`), extrinsics (`common/extrinsics/`), configs reused by both phases.
- `tools/` – repo-level utilities (`calibrate_cam.py`, `regress_v1_v2.py`) for calibration and regression testing.
- `ptl.sh` – bash helper to create a venv, install deps, generate extrinsics, run legacy Phase B, plot Euler angles, or start the UDP listener.

---

## Environment Setup

```bash
# From repo root
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# Optional: use the portable helper
./ptl.sh venv         # create venv
./ptl.sh deps         # install numpy, opencv-python, pandas, matplotlib, pupil-apriltags
```

Additional runtime tools (e.g. HUD overlays) require a working OpenCV install with GUI support (macOS: `brew install opencv` if needed).

---

## Extrinsics & Calibration

### Camera extrinsics helper

Generate a `common/extrinsics/T_WC.yaml` for any camera by specifying its height, pitch, yaw, and roll. (Negative pitch means looking downward.)

```bash
HEIGHT=0.86 PITCH=-26 YAW=0 ROLL=0 python - <<'PY'
import math, pathlib, os

h = float(os.environ["HEIGHT"])
pitch_deg = float(os.environ["PITCH"])
yaw_deg = float(os.environ.get("YAW", 0.0))
roll_deg = float(os.environ.get("ROLL", 0.0))

rx = math.radians(roll_deg)
ry = math.radians(pitch_deg)
rz = math.radians(yaw_deg)

cx, sx = math.cos(rx), math.sin(rx)
cy, sy = math.cos(ry), math.sin(ry)
cz, sz = math.cos(rz), math.sin(rz)

R_x = [[1, 0, 0], [0, cx, -sx], [0, sx, cx]]
R_y = [[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]]
R_z = [[cz, -sz, 0], [sz, cz, 0], [0, 0, 1]]

def matmul(A, B):
    return [[A[r][0]*B[0][c] + A[r][1]*B[1][c] + A[r][2]*B[2][c] for c in range(3)] for r in range(3)]

R = matmul(matmul(R_z, R_y), R_x)
t = [0.0, 0.0, h]
T = [
    [R[0][0], R[0][1], R[0][2], t[0]],
    [R[1][0], R[1][1], R[1][2], t[1]],
    [R[2][0], R[2][1], R[2][2], t[2]],
    [0.0, 0.0, 0.0, 1.0],
]

out = pathlib.Path("common/extrinsics/T_WC.yaml")
out.parent.mkdir(parents=True, exist_ok=True)
yaml = "%YAML:1.0\n---\nT_WC:\n rows: 4\n cols: 4\n data:[\n"
for row in T:
    yaml += " " + ", ".join(f"{v:.6f}" for v in row) + ",\n"
yaml += "]\n"
out.write_text(yaml)

print(f"✅ Wrote extrinsics to {out}\n")
print("Rotation matrix (R_WC):")
for row in R:
    print(" ", row)
print("Translation (t_WC):", t)
PY
```

- Store per-camera extrinsics in `common/extrinsics/<camera>.yaml`, then pass `--extrinsics` to Phase B.
- For macOS Continuity Camera / iPhone streaming apps, re-run the helper whenever the mounting geometry changes.

### Calibrations

- **Capture chessboard shots**: `python phase_a/apps/capture_calib_images.py --out phase_a/assets/calib_images`.
- **Solve intrinsics from stills**: `python phase_a/apps/camera_calibrate.py --square-size 0.024 --images phase_a/assets/calib_images --output phase_a/data/camera_intrinsics.npz`.
 - **Live chessboard calibration** (open CV UI): `python tools/calibrate_cam.py --video 0 --pattern-cols 9 --pattern-rows 6 --square-mm 24 --shots 40 --out-yaml common/calib/calib_logitech.yaml`.
- Place final intrinsics in `common/calib/` and reference via `--camera`.
- **Continuity Camera (iPhone)**: disable Center Stage / Portrait / Studio Light; keep lens at 1x; calibrate at the exact resolution you run (e.g., `--width 1920 --height 1080`) and save as `common/calib/calib_iphone13_continuity_1920x1080.yaml`. Quick FOV sanity check: `python common/tools/check_intrinsics_vs_fov.py --video 1 --width 1920 --height 1080 --calib common/calib/calib_iphone13_continuity_1920x1080.yaml --frames 3`.

## Logitech C920 Phase B v2 (stable pipeline)
This setup avoids autofocus / exposure instability seen with iPhone Continuity Camera.

**Why the iPhone failed:** autofocus hunting, auto-exposure pumping, auto-white-balance drift, and hidden digital zoom/crop from Continuity Camera.  
**Why the C920 is more stable:** fixed FOV, predictable UVC controls, and no hidden Center Stage/portrait filters. We still need to freeze auto controls as aggressively as macOS allows.

**Control matrix (macOS + OpenCV):**
- ✅ enforce: resolution/FPS selection, pose pipeline flags, chessboard geometry.
- ⚠️ best-effort: disable autofocus, auto-exposure, auto-white-balance, digital zoom (drivers often ignore).
- ❌ impossible: guarantee of manual exposure/WB on all macOS builds; Continuity Camera stability features (use C920 instead).

**Manual fallback when OpenCV is ignored:** use Logitech Camera Settings / Logi Tune (if available) to disable autofocus/auto-exposure/auto-WB and lock color temperature; otherwise keep lighting constant and avoid backlight to prevent exposure pumping.

### 1) Device discovery (find the C920 index)
```bash
python common/tools/list_video_devices.py --max-index 10
```
- macOS-specific (ffmpeg/avfoundation): `common/tools/list_avfoundation_devices.sh`
- If you see Continuity Camera warnings, you’re likely not using the C920—pick the Logitech entry in the ffmpeg list and use that index.

### 2) Configure webcam (attempt to disable auto features)
```bash
python common/tools/configure_webcam_c920.py --video <IDX>
```
- Prints which controls were honored vs ignored; saves a JSON log at `TEST_RUNS/configure_webcam_c920_log.json`.
- If you see warnings, lock controls manually in Logi Tune or stabilize lighting.

### 3) Camera intrinsics calibration
- 1080p:
```bash
python tools/calibrate_cam.py \
  --video <IDX> --width 1920 --height 1080 --fps 30 \
  --pattern-cols 9 --pattern-rows 6 --square-mm 24 \
  --shots 40 \
  --out-yaml common/calib/calib_c920_1920x1080.yaml
```
- 720p:
```bash
python tools/calibrate_cam.py \
  --video <IDX> --width 1280 --height 720 --fps 30 \
  --pattern-cols 9 --pattern-rows 6 --square-mm 24 \
  --shots 40 \
  --out-yaml common/calib/calib_c920_1280x720.yaml
```

### 4) Floor-chessboard extrinsics calibration
- 1080p:
```bash
python common/tools/calibrate_extrinsics_floor_chessboard.py \
  --video <IDX> --width 1920 --height 1080 --fps 30 \
  --calib common/calib/calib_c920_1920x1080.yaml \
  --pattern-cols 9 --pattern-rows 6 --square-mm 24 \
  --samples 8 \
  --out-yaml common/extrinsics/T_WC_c920_1920x1080.yaml
```
- 720p:
```bash
python common/tools/calibrate_extrinsics_floor_chessboard.py \
  --video <IDX> --width 1280 --height 720 --fps 30 \
  --calib common/calib/calib_c920_1280x720.yaml \
  --pattern-cols 9 --pattern-rows 6 --square-mm 24 \
  --samples 8 \
  --out-yaml common/extrinsics/T_WC_c920_1280x720.yaml
```

### 5) Phase B v2 runs (demo folder)
```bash
DEMO=TEST_RUNS/DEMO_C920_$(date +%Y%m%d)
mkdir -p "$DEMO"

# 1080p
python -m phase_b.v2.phase_b_tags_v2 \
  --config phase_b/config.yaml \
  --camera common/calib/calib_c920_1920x1080.yaml \
  --rig phase_b/rigs/cyl_dotec.yaml \
  --extrinsics common/extrinsics/T_WC_c920_1920x1080.yaml \
  --video <IDX> \
  --width 1920 --height 1080 --fps 30 \
  --save-poses "$DEMO/poses_1080p.csv" \
  --debug-metrics "$DEMO/debug_1080p.csv" \
  --ransac --adapt \
  --ema-alpha 0.25 \
  --use-weighted-se3 \
  --ekf --print-tilt \
  --hud

# 720p
python -m phase_b.v2.phase_b_tags_v2 \
  --config phase_b/config.yaml \
  --camera common/calib/calib_c920_1280x720.yaml \
  --rig phase_b/rigs/cyl_dotec.yaml \
  --extrinsics common/extrinsics/T_WC_c920_1280x720.yaml \
  --video <IDX> \
  --width 1280 --height 720 --fps 30 \
  --save-poses "$DEMO/poses_720p.csv" \
  --debug-metrics "$DEMO/debug_720p.csv" \
  --ransac --adapt \
  --ema-alpha 0.25 \
  --use-weighted-se3 \
  --ekf --print-tilt \
  --hud
```

### 6) Post-run checks
```bash
python phase_b/tools/summarize_dotec_fixed.py \
  --poses TEST_RUNS/DEMO_C920_YYYYMMDD/poses_1080p.csv \
  --debug TEST_RUNS/DEMO_C920_YYYYMMDD/debug_1080p.csv

python phase_b/tools/analyze_metrics.py \
  --csv TEST_RUNS/DEMO_C920_YYYYMMDD/debug_1080p.csv \
  --out TEST_RUNS/DEMO_C920_YYYYMMDD/metrics_1080p
```
(repeat for 720p CSVs)

### 7) Distance sanity check (camera → roll center)
```bash
python - <<'PY'
import json, numpy as np, pandas as pd, yaml
demo = "TEST_RUNS/DEMO_C920_YYYYMMDD"  # set to your run directory
for label in ("1080p", "720p"):
    poses = pd.read_csv(f"{demo}/poses_{label}.csv", comment="#")
    t = poses[["tvec_world_x","tvec_world_y","tvec_world_z"]].to_numpy()
    T = yaml.safe_load(open(f"common/extrinsics/T_WC_c920_{label}.yaml"))["T_WC"]
    cam = np.array([T[0][3], T[1][3], T[2][3]], dtype=float)
    dist = np.linalg.norm(t - cam, axis=1)
    print(f"{label}: camera->roll distance mean/std (m)=({dist.mean():.4f}, {dist.std():.4f})")
PY
```

**Best practices for stability:** lock the camera physically (no wobble), avoid backlight, keep a consistent bright fill light, ensure the chessboard is flat for extrinsics, and re-run `configure_webcam_c920.py` after reconnecting the camera to catch driver resets.

**NO_POSE but n_visible>0?** Usually means camera index mismatch, wrong intrinsics for the resolution, or wrong tag size. Checklist:
- Confirm the device index with `list_video_devices.py --use-ffmpeg` or `list_avfoundation_devices.sh` (look for the Logitech entry).
- Validate inputs: `python common/tools/validate_run_inputs.py --calib common/calib/calib_c920_1920x1080.yaml --width 1920 --height 1080 --video <IDX>`
- Ensure tag size in `phase_b/rigs/cyl_dotec.yaml` matches the printed tags (e.g., 0.050 for 50 mm).
- Recalibrate intrinsics at the exact run resolution and re-run extrinsics with that intrinsics file.

**RANSAC tuning quick commands (1080p, video 0):**
- Baseline (no RANSAC): omit `--ransac`
- Soft RANSAC (15° / 0.20 m): add `--ransac --ransac-rot-max-deg 15 --ransac-trans-max-m 0.20 --ransac-min-inliers 3 --ransac-adaptive`
- Tight RANSAC (5° / 0.05 m): add `--ransac --ransac-rot-max-deg 5 --ransac-trans-max-m 0.05 --ransac-min-inliers 4 --no-ransac-adaptive`

---

## Phase A Commands (AprilTag baseline)

### Run the AprilTag demo directly

```bash
python phase_a/apps/apriltag_demo.py \
  --config phase_a/config.yaml \
  --camera-pose-mode manual \
  --cam 0 \
  --tag-size 0.08 \
  --log-csv phase_a/data/poses_cam0.csv
```
- Manual mode reads camera pose from the config.
- Enable world-frame output via PnP mode:

```bash
python phase_a/apps/apriltag_demo.py \
  --config phase_a/config.yaml \
  --camera-pose-mode pnp \
  --extrinsics-file phase_a/data/T_WC.yaml \
  --log-csv phase_a/data/poses_world.csv
```

### Guided runner (creates configs/extrinsics if missing)

```bash
python phase_a/apps/setup_and_run.py \
  --config phase_a/config.yaml \
  --extrinsics-file phase_a/data/T_WC.yaml \
  --camera-pose-mode pnp \
  --apriltag-args -- --log-csv phase_a/data/poses.csv
```

- Extra args after `--` are forwarded to `apriltag_demo.py`.
- Use `--create-sample-config` to generate default configs.
- Extrinsics estimation helper:
  ```bash
  python phase_a/apps/apriltag_demo.py --estimate-extrinsics \
    --points phase_a/data/world_points.yaml \
    --image-points phase_a/data/image_points.yaml \
    --save phase_a/data/T_WC.yaml \
    --intrinsics phase_a/data/camera_intrinsics.npz
  ```

Outputs: CSV logs with world-frame poses, UDP JSON stream (if enabled), on-screen axes overlay.

---

## Phase B v1 Commands (legacy runner)

Entry point: `python -m phase_b.v1.phase_b_tags` (wraps `phase_b_tags_legacy.py`).

```bash
python -m phase_b.v1.phase_b_tags \
  --camera common/calib/calib.yaml \
  --rig phase_b/rigs/cyl_paper.yaml \
  --extrinsics common/extrinsics/T_WC.yaml \
  --video 0 \
  --width 1920 --height 1080 --fps 30 \
  --save-poses phase_b/poses_v1compat.csv \
  --ransac --ransac-trans 0.05 --ransac-rot 5 \
  --ema-alpha 0.3 \
  --min-inliers 3 \
  --print-tilt \
  --stream-udp 127.0.0.1:6006
```

- Same CLI accepts `--frames`, `--ignore-ids`, `--no-overlay`, etc.
- Quick convenience wrapper: `./ptl.sh run` (uses defaults from `ptl.sh` and environment variables such as `VIDEO`, `HEIGHT`, `PITCH`).

---

## Phase B v2 Commands (current pipeline)

Main runner: `python -m phase_b.v2.phase_b_tags_v2`. Key flags:
- `--camera`, `--rig`, `--extrinsics T_WC.yaml`
- `--video auto|0|1|2|URL`
- `--save-poses`, `--debug-metrics`, `--bench`
- `--use-weighted-se3` / `--no-use-weighted-se3`
- `--adapt` / `--no-adapt` plus `--beta-trans`, `--beta-rot`, `--gamma-few`, `--gamma-many`
- `--ransac`, `--ema-alpha`, `--min-inliers`, `--axis-len`
- `--stream-udp host:port`, `--hud`, `--ekf`

### v1-compatible baseline

```bash
python -m phase_b.v2.phase_b_tags_v2 \
  --camera common/calib/calib.yaml \
  --rig phase_b/rigs/cyl_paper.yaml \
  --video 0 \
  --width 1920 --height 1080 --fps 30 \
  --bench \
  --debug-metrics phase_b/debug_metrics.csv \
  --save-poses phase_b/poses_v1compat.csv \
  --v1-compat
```

### v2 “simple” (new runner, weighted fusion off)

```bash
python -m phase_b.v2.phase_b_tags_v2 \
  --camera common/calib/calib.yaml \
  --rig phase_b/rigs/cyl_paper.yaml \
  --video 0 \
  --width 1920 --height 1080 --fps 30 \
  --bench \
  --debug-metrics phase_b/debug_metrics.csv \
  --save-poses phase_b/poses_v2_off_simple.csv \
  --ransac \
  --ransac-base-trans 0.05 \
  --ransac-base-rot-deg 5 \
  --no-use-weighted-se3 \
  --adapt \
  --beta-trans 0.0 --beta-rot 0.0 \
  --gamma-few 1.0 --gamma-many 1.0 \
  --ema-alpha 0.3
```

(Setting betas/gammas to zero effectively keeps thresholds fixed while still using the runner’s adaptive plumbing.)

### v2 “full” (weighted SE(3) + adaptive RANSAC + HUD)

```bash
python -m phase_b.v2.phase_b_tags_v2 \
  --camera common/calib/calib.yaml \
  --rig phase_b/rigs/cyl_paper.yaml \
  --extrinsics common/extrinsics/T_WC.yaml \
  --video 1 \
  --width 1920 --height 1080 --fps 30 \
  --bench \
  --debug-metrics phase_b/debug_metrics.csv \
  --save-poses phase_b/poses_v2_full.csv \
  --ransac \
  --adapt \
  --beta-trans 0.5 --beta-rot 0.5 \
  --gamma-few 1.3 --gamma-many 0.9 \
  --use-weighted-se3 \
  --ema-alpha 0.2 \
  --hud \
  --ekf \
  --stream-udp 127.0.0.1:6006
```

### Selecting cameras

- `--video auto` (default) picks an external USB cam first, then falls back to the internal webcam.
- `--video 0` – internal MacBook camera; `--video 1` – Logitech/USB webcam; `--video 2` – Continuity Camera / iPhone virtual camera.
- IP/RTSP feeds also work when OpenCV supports them: `--video "http://PHONE_IP:8080/video"` or `--video "rtsp://PHONE_IP:8554/live.sdp"`.
- Always pair the capture device with matching `--camera` intrinsics and `--extrinsics`.

### Benchmarking + validation scenarios

All scenarios below log poses and metrics, then run analysis + archiving.

#### S1 – jitter (short, hand shakes)

```bash
python -m phase_b.v2.phase_b_tags_v2 \
  --camera common/calib/calib.yaml \
  --rig phase_b/rigs/cyl_paper.yaml \
  --extrinsics common/extrinsics/T_WC.yaml \
  --video 0 \
  --bench \
  --debug-metrics phase_b/debug_metrics.csv \
  --save-poses phase_b/poses_jitter.csv \
  --ransac --adapt --use-weighted-se3 \
  --ema-alpha 0.25

python phase_b/tools/analyze_metrics.py \
  --csv phase_b/debug_metrics.csv \
  --out phase_b/fig_jitter

python phase_b/tools/archive_validation_run.py \
  --scenario S1_jitter \
  --poses poses_jitter.csv \
  --fig-dir fig_jitter \
  --metrics debug_metrics.csv
```

#### S2 – sweep (wide sweeps, more tags)

```bash
python -m phase_b.v2.phase_b_tags_v2 \
  --camera common/calib/calib.yaml \
  --rig phase_b/rigs/cyl_paper.yaml \
  --extrinsics common/extrinsics/T_WC.yaml \
  --video 1 \
  --bench \
  --debug-metrics phase_b/debug_metrics.csv \
  --save-poses phase_b/poses_sweep.csv \
  --ransac --adapt --use-weighted-se3 \
  --ema-alpha 0.2 \
  --frames 2000

python phase_b/tools/analyze_metrics.py \
  --csv phase_b/debug_metrics.csv \
  --out phase_b/fig_sweep

python phase_b/tools/archive_validation_run.py \
  --scenario S2_sweep \
  --poses poses_sweep.csv \
  --fig-dir fig_sweep \
  --metrics debug_metrics.csv
```

#### S3 – long run (stress/full duration)

```bash
python -m phase_b.v2.phase_b_tags_v2 \
  --camera common/calib/calib.yaml \
  --rig phase_b/rigs/cyl_paper.yaml \
  --extrinsics common/extrinsics/T_WC.yaml \
  --video 2 \
  --bench \
  --debug-metrics phase_b/debug_metrics.csv \
  --save-poses phase_b/poses_longrun.csv \
  --ransac --adapt --use-weighted-se3 \
  --ema-alpha 0.15 \
  --frames 6000

python phase_b/tools/analyze_metrics.py \
  --csv phase_b/debug_metrics.csv \
  --out phase_b/fig_longrun

python phase_b/tools/archive_validation_run.py \
  --scenario S3_longrun \
  --poses poses_longrun.csv \
  --fig-dir fig_longrun \
  --metrics debug_metrics.csv
```

---

## Tools & Utilities

- **compare_poses.py** – RMS comparison of two pose CSVs:
  ```bash
  python phase_b/tools/compare_poses.py \
    --a phase_b/poses_v1compat.csv \
    --b phase_b/poses_v2_full.csv
  ```
- **analyze_metrics.py** – FPS and tilt plots from `debug_metrics.csv`:
  ```bash
  python phase_b/tools/analyze_metrics.py \
    --csv phase_b/debug_metrics.csv \
    --out phase_b/fig_latest \
    --max-rows 2000
  ```
- **archive_validation_run.py** – bundle current outputs:
  ```bash
  python phase_b/tools/archive_validation_run.py \
    --scenario S2_sweep \
    --poses poses_sweep.csv \
    --fig-dir fig_sweep \
    --metrics debug_metrics.csv
  ```
- **cleanup_s2_sweep.py** – reset S2 artifacts (poses, figs, metrics):
  ```bash
  python phase_b/tools/cleanup_s2_sweep.py
  ```
- **augment_poses.py** – add Euler angles to pose CSVs:
  ```bash
  python phase_b/tools/augment_poses.py \
    --source phase_b/poses_v2_full.csv \
    --frame both \
    --overwrite
  ```
- **udp_receive_pose.py** – listen for UDP pose streaming:
  ```bash
  python phase_b/udp_receive_pose.py --port 6006
  ```
- **tools/regress_v1_v2.py** – run both phases and compare outputs:
  ```bash
  python tools/regress_v1_v2.py \
    --camera common/calib/calib.yaml \
    --rig phase_b/rigs/cyl_paper.yaml \
    --extrinsics common/extrinsics/T_WC.yaml \
    --config phase_b/config.yaml \
    --video 0 \
    --frames 400 \
    --tolerance 1e-4
  ```
- **ptl.sh** – convenience wrapper (venv/deps/extrinsics/run/euler/plot/udp):
  ```bash
  ./ptl.sh help
  ./ptl.sh run VIDEO=0 IGNORE_IDS=104,202
  ./ptl.sh euler   # augment + plot yaw/pitch/roll
  ```

---

## Phase C / YOLO Status

This repository snapshot contains Phases A and B only; no Phase C or YOLO-based markerless code is present.

---

## Quickstart

1. **Clone + setup environment**
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```
2. **Create camera extrinsics + calibrations**
   ```bash
   HEIGHT=1.05 PITCH=-20 YAW=0 ROLL=0 python - <<'PY'
   # (use the helper snippet above)
   PY
   ```
3. **Run Phase A once (PnP mode)**
   ```bash
   python phase_a/apps/apriltag_demo.py \
     --config phase_a/config.yaml \
     --camera-pose-mode pnp \
     --extrinsics-file phase_a/data/T_WC.yaml \
     --log-csv phase_a/data/poses_world.csv
   ```
4. **Run Phase B v2 with weighted fusion + adaptive RANSAC**
   ```bash
   python -m phase_b.v2.phase_b_tags_v2 \
     --camera common/calib/calib.yaml \
     --rig phase_b/rigs/cyl_paper.yaml \
     --extrinsics common/extrinsics/T_WC.yaml \
     --video 1 \
     --bench \
     --debug-metrics phase_b/debug_metrics.csv \
     --save-poses phase_b/poses_v2_full.csv \
     --ransac --adapt --use-weighted-se3 \
     --ema-alpha 0.2
   ```
5. **Inspect the run + archive**
   ```bash
   python phase_b/tools/analyze_metrics.py \
     --csv phase_b/debug_metrics.csv \
     --out phase_b/fig_latest

   python phase_b/tools/archive_validation_run.py \
     --scenario S1_jitter \
     --poses poses_v2_full.csv \
     --fig-dir fig_latest \
     --metrics debug_metrics.csv
   ```

You now have calibrated inputs, a working Phase A baseline, Phase B v2 outputs (poses + metrics), diagnostic plots, and an archived validation folder ready for regression tracking.


## Phase B v2 – Sway camera world-frame tests

# s = 0.00 (sway fully left / baseline)
python -m phase_b.v2.phase_b_tags_v2 \
  --camera common/calib/calib.yaml \
  --rig phase_b/rigs/cyl_paper.yaml \
  --extrinsics common/extrinsics/T_WC.yaml \
  --video 2 \
  --width 1920 --height 1080 --fps 30 \
  --save-poses phase_b/v2/poses_sway_s000.csv \
  --ransac --ransac-trans 0.05 --ransac-rot 5 \
  --ema-alpha 0.3 \
  --min-inliers 3 \
  --max-tilt-jump-deg 15 \
  --print-tilt

# s = 0.25 (mid sway)
python -m phase_b.v2.phase_b_tags_v2 \
  --camera common/calib/calib.yaml \
  --rig phase_b/rigs/cyl_paper.yaml \
  --extrinsics common/extrinsics/T_WC.yaml \
  --video 2 \
  --width 1920 --height 1080 --fps 30 \
  --save-poses phase_b/v2/poses_sway_s025.csv \
  --ransac --ransac-trans 0.05 --ransac-rot 5 \
  --ema-alpha 0.3 \
  --min-inliers 3 \
  --max-tilt-jump-deg 15 \
  --print-tilt

# s = 0.50 (sway further along)
python -m phase_b.v2.phase_b_tags_v2 \
  --camera common/calib/calib.yaml \
  --rig phase_b/rigs/cyl_paper.yaml \
  --extrinsics common/extrinsics/T_WC.yaml \
  --video 2 \
  --width 1920 --height 1080 --fps 30 \
  --save-poses phase_b/v2/poses_sway_s050.csv \
  --ransac --ransac-trans 0.05 --ransac-rot 5 \
  --ema-alpha 0.3 \
  --min-inliers 3 \
  --max-tilt-jump-deg 15 \
  --print-tilt
