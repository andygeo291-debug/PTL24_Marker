# Phase B v2 Pose Estimation

## Overview

Phase B v2 estimates the 6-DoF pose of cylindrical paper rolls using AprilTags detections, a calibrated cylindrical rig model, robust RANSAC outlier rejection, and optional weighted SE(3) temporal fusion. The primary entry point is `phase_b/v2/phase_b_tags_v2.py`, which can emulate the legacy v1 pipeline, run the new v2 logic with legacy-like settings (“simple”), or enable the full v2 stack (weighted fusion, adaptive thresholds, HUD/bench logging, etc.). Supporting utilities include `phase_b/tools/compare_poses.py` for pose RMS comparisons, `phase_b/tools/analyze_metrics.py` for FPS and tilt jitter plots from `debug_metrics.csv`, and `phase_b/tools/archive_validation_run.py` to snapshot validation artifacts per scenario.

## Environment setup

Phase B v2 assumes a Python virtual environment with the project dependencies installed:

```bash
python3 -m venv venv
source venv/bin/activate        # macOS / Linux
pip install --upgrade pip
pip install -r requirements.txt
```

The root README and `../PTL24_MARKER_RUN_COMMANDS.md` provide full setup details.

## Running the Phase B v2 runner

All commands below assume you are in the repository root.

### Common arguments

- `--camera common/calib/calib.yaml` selects the camera intrinsics file produced by calibration.
- `--rig phase_b/rigs/cyl_paper.yaml` loads the cylindrical tag rig description.
- `--width 1920 --height 1080 --fps 30` sets capture resolution and target frame rate.
- `--bench` enables benchmarking + `debug_metrics.csv`.
- `--save-poses phase_b/poses_*.csv` writes fused poses to a CSV for later comparison.

### 1) v1-compatible baseline

```bash
python -m phase_b.v2.phase_b_tags_v2 \
  --camera common/calib/calib.yaml \
  --rig phase_b/rigs/cyl_paper.yaml \
  --video 0 \
  --width 1920 --height 1080 --fps 30 \
  --bench \
  --save-poses phase_b/poses_v1compat.csv \
  --v1-compat
```

`--v1-compat` forces the legacy heuristics: fixed RANSAC thresholds, simple (non-weighted) fusion, EMA smoothing only, and deterministic seeding for apples-to-apples comparisons.

### 2) v2 “simple” (new code, advanced features off)

```bash
python -m phase_b.v2.phase_b_tags_v2 \
  --camera common/calib/calib.yaml \
  --rig phase_b/rigs/cyl_paper.yaml \
  --video 0 \
  --width 1920 --height 1080 --fps 30 \
  --bench \
  --save-poses phase_b/poses_v2_off_simple.csv \
  --ransac \
  --ransac-base-trans 0.05 \
  --ransac-base-rot-deg 5 \
  --no-adapt \
  --ema-alpha 0.3 \
  --no-use-weighted-se3
```

Use `--ransac` to enable geometrically consistent pose selection, `--ransac-base-trans/rot` to tune static thresholds, `--no-adapt` to keep RANSAC fixed, `--ema-alpha` for temporal smoothing, and `--no-use-weighted-se3` to match the “simple” fusion path (legacy-style SE(3) averaging with optional EMA).

### 3) v2 “full” (weighted fusion + adaptive RANSAC)

```bash
python -m phase_b.v2.phase_b_tags_v2 \
  --camera common/calib/calib.yaml \
  --rig phase_b/rigs/cyl_paper.yaml \
  --video 0 \
  --width 1920 --height 1080 --fps 30 \
  --bench \
  --save-poses phase_b/poses_v2_full.csv \
  --ransac \
  --ransac-base-trans 0.04 \
  --ransac-base-rot-deg 4 \
  --ema-alpha 0.2 \
  --use-weighted-se3 \
  --hud \
  --ekf \
  --stream-udp 127.0.0.1:6006
```

This configuration enables RANSAC plus adaptive thresholding (default unless `--no-adapt` is passed), weighted SE(3) fusion (`--use-weighted-se3`), slightly faster EMA smoothing, optional HUD overlay, EKF filtering, and UDP pose streaming. Adjust the thresholds and EMA factor per rig dynamics.

### Flag reference

- `--v1-compat`: overall compatibility mode; disables adaptive logic and weighted fusion automatically.
- `--ransac`: toggles RANSAC filtering of candidate poses.
- `--ransac-base-trans`, `--ransac-base-rot-deg`: baseline tolerances used by adaptive logic (or fixed thresholds if `--no-adapt` is set).
- `--no-adapt`: disable adaptive scaling of RANSAC thresholds; combine with explicit base values.
- `--ema-alpha`: exponential moving-average smoothing factor (0 disables EMA).
- `--use-weighted-se3` / `--no-use-weighted-se3`: override config to force weighted SE(3) fusion on or off.
- `--bench`: records per-frame timing to `debug_metrics.csv` and prints benchmark summaries.
- `--save-poses PATH`: writes fused pose CSV for comparison/archival.

## Selecting the camera (video source)

- `--video auto` lets OpenCV choose the first available camera (commonly the built-in MacBook camera).
- `--video 0`, `--video 1`, `--video 2`, … select explicit device indices. Typical mapping: `0` = internal MacBook camera, `1` = Logitech C525 USB webcam, `2` = virtual camera feed from iPhone apps like Camo/Iriun. Indices vary per machine, so probe with a short trial run.
- Network/IP streams can also work if OpenCV supports the URL:
  - `--video "http://PHONE_IP:8080/video"` (MJPEG HTTP stream)
  - `--video "rtsp://PHONE_IP:8554/live.sdp"` (RTSP stream)
  These are advanced scenarios and depend on the phone streaming app. Calibrate each camera/stream separately; the `--camera` file must match the device actually used.

## Validation tools and workflow

1. `compare_poses.py` – computes RMS/mean differences between two pose CSVs:
   ```bash
   python phase_b/tools/compare_poses.py \
     --a phase_b/poses_v1compat.csv \
     --b phase_b/poses_v2_off_simple.csv
   ```
2. `analyze_metrics.py` – parses `debug_metrics.csv` (from `--bench`) to plot FPS and tilt jitter:
   ```bash
   python phase_b/tools/analyze_metrics.py \
     --csv phase_b/debug_metrics.csv \
     --out phase_b/fig
   ```
3. `archive_validation_run.py` – bundles the latest run into a scenario folder:
   ```bash
   python phase_b/tools/archive_validation_run.py \
     --scenario S1_jitter \
     --poses poses_jitter.csv \
     --fig-dir fig_jitter
   ```

Typical workflow: run the v2 pipeline with `--bench` and `--save-poses`, inspect performance using `analyze_metrics.py`, compare against baselines with `compare_poses.py`, and then archive the artifacts for that scenario via `archive_validation_run.py`.

## Quick reference

- Run v1 baseline: `python -m phase_b.v2.phase_b_tags_v2 --v1-compat ...`
- Run v2 simple: `python -m phase_b.v2.phase_b_tags_v2 --no-adapt --no-use-weighted-se3 ...`
- Run v2 full: `python -m phase_b.v2.phase_b_tags_v2 --ransac --use-weighted-se3 ...`
- Compare poses: `python phase_b/tools/compare_poses.py --a ... --b ...`
- Analyze metrics: `python phase_b/tools/analyze_metrics.py --csv phase_b/debug_metrics.csv --out phase_b/fig`
- Archive run: `python phase_b/tools/archive_validation_run.py --scenario S1_jitter --poses poses_jitter.csv --fig-dir fig_jitter`

## Multi-camera extrinsics (webcam, phone, crane camera)

- Store one `T_WC.yaml` per physical device inside `common/extrinsics/`, for example:
  - `common/extrinsics/T_WC_webcam.yaml`
  - `common/extrinsics/T_WC_phone.yaml`
  - `common/extrinsics/T_WC_crane_cam.yaml`
- When experimenting with a single camera, overwrite the canonical `common/extrinsics/T_WC.yaml` using the helper command (HEIGHT/PITCH/YAW/ROLL). Example:

```bash
HEIGHT=1.10 PITCH=-20 YAW=0 ROLL=0 python - <<'PY'
import math, pathlib, os
h = float(os.environ["HEIGHT"]); pitch = math.radians(float(os.environ["PITCH"]))
yaw = math.radians(float(os.environ.get("YAW", 0.0))); roll = math.radians(float(os.environ.get("ROLL", 0.0)))
cx, sx = math.cos(roll), math.sin(roll); cy, sy = math.cos(pitch), math.sin(pitch); cz, sz = math.cos(yaw), math.sin(yaw)
R_x = [[1,0,0],[0,cx,-sx],[0,sx,cx]]; R_y = [[cy,0,sy],[0,1,0],[-sy,0,cy]]; R_z = [[cz,-sz,0],[sz,cz,0],[0,0,1]]
def mm(A,B): return [[sum(A[r][k]*B[k][c] for k in range(3)) for c in range(3)] for r in range(3)]
R = mm(mm(R_z, R_y), R_x); T = [[*R[0],0],[*R[1],0],[*R[2],h],[0,0,0,1]]
out = pathlib.Path("common/extrinsics/T_WC.yaml"); out.parent.mkdir(parents=True, exist_ok=True)
out.write_text("%YAML:1.0\n---\nT_WC:\n rows:4\n cols:4\n data:[\n " + ", ".join(f"{v:.6f}" for row in T for v in row) + "\n]\n")
PY
```

- Pair the correct extrinsics with the matching video source:

```bash
python -m phase_b.v2.phase_b_tags_v2 \
  --camera common/calib/calib.yaml \
  --rig phase_b/rigs/cyl_paper.yaml \
  --extrinsics common/extrinsics/T_WC_phone.yaml \
  --video 2 \
  --bench --save-poses phase_b/poses_phone.csv \
  --ransac --adapt --use-weighted-se3
```

Switching devices means updating both `--video` and `--extrinsics` (or regenerating `T_WC.yaml`) so the world frame remains consistent across runs.

## Validation scenarios: S1 (jitter), S2 (sweep), S3 (long run)

Each validation scenario captures a different motion profile; all should run with `--bench`, `--save-poses`, and the appropriate extrinsics.

### S1 – jitter (short handheld shake)
- Duration: ~1–2 minutes while inducing hand/rig jitter.
- Command:
  ```bash
  python -m phase_b.v2.phase_b_tags_v2 \
    --camera common/calib/calib.yaml \
    --rig phase_b/rigs/cyl_paper.yaml \
    --extrinsics common/extrinsics/T_WC_webcam.yaml \
    --video 0 \
    --bench \
    --debug-metrics phase_b/debug_metrics.csv \
    --save-poses phase_b/poses_jitter.csv \
    --ransac --adapt --use-weighted-se3 \
    --ema-alpha 0.25
  ```

### S2 – sweep (wide motion, varied tag counts)
- Duration: ~2–3 minutes sweeping across the roll with larger camera motion.
- Command:
  ```bash
  python -m phase_b.v2.phase_b_tags_v2 \
    --camera common/calib/calib.yaml \
    --rig phase_b/rigs/cyl_paper.yaml \
    --extrinsics common/extrinsics/T_WC_webcam.yaml \
    --video 1 \
    --bench \
    --debug-metrics phase_b/debug_metrics.csv \
    --save-poses phase_b/poses_sweep.csv \
    --ransac --adapt --use-weighted-se3 \
    --ema-alpha 0.2 \
    --frames 2000
  ```

### S3 – long run (steady-state stress test)
- Duration: multi-minute continuous capture (e.g., crane-style mount).
- Command:
  ```bash
  python -m phase_b.v2.phase_b_tags_v2 \
    --camera common/calib/calib.yaml \
    --rig phase_b/rigs/cyl_paper.yaml \
    --extrinsics common/extrinsics/T_WC_crane_cam.yaml \
    --video 2 \
    --bench \
    --debug-metrics phase_b/debug_metrics.csv \
    --save-poses phase_b/poses_longrun.csv \
    --ransac --adapt --use-weighted-se3 \
    --ema-alpha 0.15 \
    --frames 6000
  ```

### Analyze + archive for every scenario

```bash
python phase_b/tools/analyze_metrics.py \
  --csv phase_b/debug_metrics.csv \
  --out phase_b/fig_<scenario>

python phase_b/tools/archive_validation_run.py \
  --scenario S1_jitter \
  --poses poses_jitter.csv \
  --fig-dir fig_jitter \
  --metrics debug_metrics.csv
```

Change the `<scenario>` placeholders (and `--scenario` argument) for S2/S3. Archiving creates `phase_b/validation/S1_jitter`, `S2_sweep`, or `S3_longrun` with poses, metrics, and plots.

## World-frame pose logging (T_WC → T_WR)

- Supplying `--extrinsics path/to/T_WC.yaml` causes the runner to load `T_WC` (world→camera) and compute per-frame `T_W_R = T_W_C @ T_C_R`.
- Pose CSV columns appear in this order:
  ```
  rvec_cam_x,y,z, tvec_cam_x,y,z,
  rvec_world_x,y,z, tvec_world_x,y,z,
  tilt_cam_deg, tilt_world_deg
  ```
  World columns are blank when extrinsics are absent.
- To verify world logging, run a short capture with `--extrinsics`, then inspect the CSV:
  ```bash
  head -n 5 phase_b/poses_world_test.csv
  ```
  Non-empty `rvec_world_*` / `tvec_world_*` indicates world-frame output is active. UDP payloads currently include camera-frame poses; extend as needed if a consumer expects world data.

## See also

- `../README.md` – Phase A baseline, calibration helpers, and project overview.
- `../PTL24_MARKER_RUN_COMMANDS.md` – single file aggregating all setup steps, validation commands, and tooling invocations across Phase A + Phase B.
