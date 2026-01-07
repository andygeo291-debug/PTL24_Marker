# PTL24_MARKER – Run Commands

Friendly reference for running Phase A/B pipelines and helper tools from the repo root. Examples assume calibrated intrinsics at `common/calib/calib.yaml` and the paper-roll rig at `phase_b/rigs/cyl_paper.yaml`.

## Quick start – environment
- Create venv (macOS/Linux): `python3 -m venv venv && source venv/bin/activate`
- Install deps:
 python3 -m pip install --upgrade pip
python3 -m pip install -r requirements.txt

- Later sessions: `source venv/bin/activate` (or `venv\\Scripts\\activate` on Windows)

## Phase A – Calibration & AprilTag detection
Short scripts for intrinsics, extrinsics, and tag sanity checks on a fixed camera.

🎞️ Capture calibration frames  
```bash
python phase_a/apps/capture_calib_images.py
```
Opens a live view; press SPACE to save chessboard frames into `phase_a/data/`. Use before solving intrinsics.

📐 Solve intrinsics  
```bash
python phase_a/apps/camera_calibrate.py --square-size 0.024
```
Optimises camera intrinsics from saved chessboard images and writes `phase_a/data/camera_intrinsics.npz`. Provide your chessboard square size in metres.

👀 AprilTag demo (manual pose)  
```bash
python phase_a/apps/apriltag_demo.py \
  --config phase_a/config.yaml \
  --camera-pose-mode manual \
  --log-csv phase_a/data/poses.csv
```
Streams detections using the pose baked into `phase_a/config.yaml`, logging tag poses to CSV if requested.

🧭 AprilTag demo (PnP pose)  
```bash
python phase_a/apps/apriltag_demo.py \
  --config phase_a/config.yaml \
  --camera-pose-mode pnp \
  --extrinsics-file phase_a/data/T_WC.yaml \
  --log-csv phase_a/data/poses.csv
```
Solves camera pose via PnP using `phase_a/data/T_WC.yaml`, then overlays/world-frames detections; logs CSV when provided.

🗺️ Estimate extrinsics from correspondences  
```bash
python phase_a/apps/apriltag_demo.py \
  --estimate-extrinsics \
  --points phase_a/data/world_points.yaml \
  --image-points phase_a/data/image_points.yaml \
  --intrinsics phase_a/data/camera_intrinsics.npz \
  --save phase_a/data/T_WC.yaml
```
One-off extrinsics solver: fits `T_WC` from matched world/image points and saves a YAML usable by Phase B.

## Phase B v1 – Legacy cylindrical pose estimation
Original pose pipeline kept for regressions and quick checks.

🎯 Legacy pipeline on live camera  
```bash
python -m phase_b.v1.phase_b_tags \
  --camera common/calib/calib.yaml \
  --rig phase_b/rigs/cyl_paper.yaml \
  --extrinsics common/extrinsics/T_WC.yaml \
  --video 0 --width 1920 --height 1080 --fps 30 \
  --save-poses phase_b/poses_v1.csv \
  --print-tilt --ransac --ema-alpha 0.3
```
Runs v1 with optional world-frame reporting, RANSAC, and CSV logging. Adjust `--video` for your static camera; omit `--extrinsics` for camera-frame only.

## Phase B v2 – Static camera (simple + full v2 modes)
Refactored runner with config support, weighted fusion, adaptive RANSAC, HUD, and logging.

🟢 v2 “simple” (new code, legacy-like fusion)  
```bash
python -m phase_b.v2.phase_b_tags_v2 \
  --config phase_b/config.yaml \
  --camera common/calib/calib.yaml \
  --rig phase_b/rigs/cyl_paper.yaml \
  --video 0 --width 1920 --height 1080 --fps 30 \
  --save-poses phase_b/v2/poses_v2_simple.csv \
  --debug-metrics phase_b/debug_metrics.csv \
  --ransac --no-adapt \
  --ransac-base-trans 0.05 --ransac-base-rot-deg 5 \
  --ema-alpha 0.3 --no-use-weighted-se3
```
Uses the v2 codepath with fixed RANSAC thresholds and plain SE(3)+EMA fusion. Good for baseline comparisons on the static camera.

🚀 v2 “full” (weighted fusion + adaptive RANSAC + HUD)  
```bash
python -m phase_b.v2.phase_b_tags_v2 \
  --config phase_b/config.yaml \
  --camera common/calib/calib.yaml \
  --rig phase_b/rigs/cyl_paper.yaml \
  --extrinsics common/extrinsics/T_WC.yaml \
  --video 0 --width 1920 --height 1080 --fps 30 \
  --save-poses phase_b/v2/poses_v2_full.csv \
  --debug-metrics phase_b/debug_metrics.csv \
  --ransac --adapt \
  --ema-alpha 0.25 --use-weighted-se3 \
  --hud --ekf --print-tilt
```
Full v2 stack for validation runs on the real Dotec roll; logs fused poses plus `debug_metrics.csv`, overlays HUD, and reports world-frame tilt via supplied extrinsics.

🕹️ v1-compatible mode (sanity/regressions)  
```bash
python -m phase_b.v2.phase_b_tags_v2 \
  --config phase_b/config.yaml \
  --camera common/calib/calib.yaml \
  --rig phase_b/rigs/cyl_paper.yaml \
  --video 0 --width 1920 --height 1080 --fps 30 \
  --save-poses phase_b/v2/poses_v1compat.csv \
  --debug-metrics phase_b/debug_metrics.csv \
  --v1-compat --bench-print-every 60
```
For apples-to-apples with v1: disables adaptive logic/weighted fusion and mirrors legacy heuristics while still emitting v2-format logs.

## Basler – Phase B v2 (GigE backend)
Basler runs use the optional backend; OpenCV remains the default. Replace `<SERIAL>` and `<NAME>` with your camera identifiers.

🧪 Basler smoke (frames=60)  
```bash
python3 -m phase_b.v2.phase_b_tags_v2 \
  --camera-backend basler \
  --basler-serial <SERIAL> \
  --basler-name <NAME> \
  --width 1280 --height 980 \
  --fps 20 \
  --basler-pixel-format Mono8 \
  --basler-exposure-us 5000 \
  --basler-gain 0 \
  --basler-offset-x 0 \
  --basler-offset-y 0 \
  --basler-interpacket-delay 3500 \
  --basler-timeout-ms 1000 \
  --rig phase_b/rigs/cyl_dotec.yaml \
  --camera common/calib/basler_static_1280x980_mono8.yaml \
  --debug-metrics /tmp/debug_basler_smoke.csv \
  --no-hud \
  --frames 60
```

🟢 Basler long-run (HUD on)  
```bash
python3 -m phase_b.v2.phase_b_tags_v2 \
  --camera-backend basler \
  --basler-serial <SERIAL> \
  --basler-name <NAME> \
  --width 1280 --height 980 \
  --fps 20 \
  --basler-pixel-format Mono8 \
  --basler-exposure-us 5000 \
  --basler-gain 0 \
  --basler-offset-x 0 \
  --basler-offset-y 0 \
  --basler-interpacket-delay 3500 \
  --basler-timeout-ms 1000 \
  --rig phase_b/rigs/cyl_dotec.yaml \
  --camera common/calib/basler_static_1280x980_mono8.yaml \
  --debug-metrics /tmp/debug_basler_long.csv \
  --frames 1200 \
  --hud
```

🟢 Basler long-run (HUD off)  
```bash
python3 -m phase_b.v2.phase_b_tags_v2 \
  --camera-backend basler \
  --basler-serial <SERIAL> \
  --basler-name <NAME> \
  --width 1280 --height 980 \
  --fps 20 \
  --basler-pixel-format Mono8 \
  --basler-exposure-us 5000 \
  --basler-gain 0 \
  --basler-offset-x 0 \
  --basler-offset-y 0 \
  --basler-interpacket-delay 3500 \
  --basler-timeout-ms 1000 \
  --rig phase_b/rigs/cyl_dotec.yaml \
  --camera common/calib/basler_static_1280x980_mono8.yaml \
  --debug-metrics /tmp/debug_basler_long_nohud.csv \
  --no-hud \
  --frames 1200
```

🔧 Basler grab test (20 frames)  
```bash
python -m common.camera.test_basler_grab \
  --serial <SERIAL> --name <NAME> \
  --frames 20 --timeout-ms 1000
```

## Phase B v2 – Sway camera experiments
Use the sway toolkit to model the camera along the crane arm, generate extrinsics per sway position, then run v2.

📝 Log sway motion against a reference tag  
```bash
python -m sway_camera.apps.motion_logger \
  --cam 0 \
  --tag-family tag36h11 --tag-size 0.10 --ref-id 3 \
  --out-csv sway_camera/data/sway_poses_tag3.csv
```
Records camera poses while moving along the sway axis with Tag 3 visible; outputs a CSV for fitting.

📊 Fit sway axis from logged poses  
```bash
python -m sway_camera.apps.fit_sway_axis \
  --csv sway_camera/data/sway_poses_tag3.csv \
  --use-absolute \
  --out sway_camera/data/sway_model.yaml
```
Extracts the sway direction and reference point, writing a reusable `sway_model.yaml`.

🧮 Generate sway-specific extrinsics  
```bash
python -m common.extrinsics.make_extrinsics_sway \
  --sway-model sway_camera/data/sway_model.yaml \
  --sway-pos 0.25 \
  --cam-offset-x 0.0 --cam-offset-y 0.0 --cam-offset-z 0.0 \
  --yaw-deg 0.0 --pitch-deg -20.0 --roll-deg 0.0 \
  --out common/extrinsics/T_WC.yaml
```
Computes `T_WC` for a given sway position `s` and saves Phase-B-ready extrinsics; tweak offsets/angles per mount.

🌊 Run v2 with sway-camera extrinsics  
```bash
python -m phase_b.v2.phase_b_tags_v2 \
  --config phase_b/config.yaml \
  --camera common/calib/calib.yaml \
  --rig phase_b/rigs/cyl_paper.yaml \
  --extrinsics common/extrinsics/T_WC.yaml \
  --video auto --width 1920 --height 1080 --fps 30 \
  --save-poses phase_b/v2/poses_sway.csv \
  --debug-metrics phase_b/debug_metrics.csv \
  --ransac --ransac-trans 0.05 --ransac-rot 5 \
  --ema-alpha 0.3 --print-tilt
```
Processes sway camera data using the generated `T_WC`; outputs fused world-frame poses plus metrics for swing vs sway tests.

## Tools – Analysis and utilities
Post-run helpers for comparisons, metrics plots, archiving, and log augmentation.

📊 Compare pose CSVs (RMS)  
```bash
python phase_b/tools/compare_poses.py \
  --a phase_b/v2/poses_v1compat.csv \
  --b phase_b/v2/poses_v2_full.csv \
  --max-rows 2000
```
Computes RMS deltas between two pose logs (camera-frame Rodrigues + translation), optionally limiting rows.

📈 Analyze debug_metrics (FPS/tilt plots)  
```bash
python phase_b/tools/analyze_metrics.py \
  --csv phase_b/debug_metrics.csv \
  --out phase_b/fig_metrics \
  --max-rows 5000
```
Parses `debug_metrics.csv` (from `--debug-metrics`/`--bench`) to print FPS stats and save line/hist plots under the given directory.

📦 Archive validation run (S1/S2/S3)  
```bash
python phase_b/tools/archive_validation_run.py \
  --scenario S2_sweep \
  --poses phase_b/v2/poses_v2_full.csv \
  --fig-dir phase_b/fig_metrics \
  --metrics debug_metrics.csv
```
Moves pose CSV, plots, and metrics into `phase_b/validation/<scenario>/`, replacing any previous snapshot for that scenario.

🧭 Add Euler angles to pose logs  
```bash
python phase_b/tools/augment_poses.py \
  --source phase_b/v2/poses_v2_full.csv \
  --out phase_b/v2/poses_v2_full_with_euler.csv \
  --frame both --overwrite
```
Augments v2 (or legacy) pose CSVs with yaw/pitch/roll columns derived from quaternions or Rodrigues vectors; writes a new CSV.

## Cheat Sheet (everyday commands)
- 🟢 Run v2 simple on static cam: `python -m phase_b.v2.phase_b_tags_v2 --config phase_b/config.yaml --camera common/calib/calib.yaml --rig phase_b/rigs/cyl_paper.yaml --video 0 --width 1920 --height 1080 --fps 30 --save-poses phase_b/v2/poses_v2_simple.csv --debug-metrics phase_b/debug_metrics.csv --ransac --no-adapt --ransac-base-trans 0.05 --ransac-base-rot-deg 5 --ema-alpha 0.3 --no-use-weighted-se3`
- 🚀 Run v2 full on static cam: `python -m phase_b.v2.phase_b_tags_v2 --config phase_b/config.yaml --camera common/calib/calib.yaml --rig phase_b/rigs/cyl_paper.yaml --extrinsics common/extrinsics/T_WC.yaml --video 0 --width 1920 --height 1080 --fps 30 --save-poses phase_b/v2/poses_v2_full.csv --debug-metrics phase_b/debug_metrics.csv --ransac --adapt --ema-alpha 0.25 --use-weighted-se3 --hud --ekf --print-tilt`
- 🎯 Run legacy v1: `python -m phase_b.v1.phase_b_tags --camera common/calib/calib.yaml --rig phase_b/rigs/cyl_paper.yaml --extrinsics common/extrinsics/T_WC.yaml --video 0 --width 1920 --height 1080 --fps 30 --save-poses phase_b/poses_v1.csv --print-tilt --ransac --ema-alpha 0.3`
- 🌊 Run v2 with sway extrinsics: `python -m phase_b.v2.phase_b_tags_v2 --config phase_b/config.yaml --camera common/calib/calib.yaml --rig phase_b/rigs/cyl_paper.yaml --extrinsics common/extrinsics/T_WC.yaml --video auto --width 1920 --height 1080 --fps 30 --save-poses phase_b/v2/poses_sway.csv --debug-metrics phase_b/debug_metrics.csv --ransac --ransac-trans 0.05 --ransac-rot 5 --ema-alpha 0.3 --print-tilt`
- 📈 Plot metrics: `python phase_b/tools/analyze_metrics.py --csv phase_b/debug_metrics.csv --out phase_b/fig_metrics`
- 📊 Compare pose logs: `python phase_b/tools/compare_poses.py --a phase_b/v2/poses_v1compat.csv --b phase_b/v2/poses_v2_full.csv`
- 📦 Archive latest validation run: `python phase_b/tools/archive_validation_run.py --scenario S1_jitter --poses phase_b/v2/poses_v2_full.csv --fig-dir phase_b/fig_metrics --metrics debug_metrics.csv`
- 🧭 Add Euler columns: `python phase_b/tools/augment_poses.py --source phase_b/v2/poses_v2_full.csv --out phase_b/v2/poses_v2_full_with_euler.csv --frame both --overwrite`
- 🎞️ Capture calibration frames: `python phase_a/apps/capture_calib_images.py`
- 👀 Phase A AprilTag demo (manual pose): `python phase_a/apps/apriltag_demo.py --config phase_a/config.yaml --camera-pose-mode manual --log-csv phase_a/data/poses.csv`

### Notes on video devices
- Built-in laptop cam is often `--video 0`; iPhone/Continuity/virtual cams frequently show up as `--video 1`. Use that value with the commands above when feeding from the iPhone. If unsure, start with `--video auto` and check the logged “Capture opened…” line for the actual source and resolution.

.

## DOTEC ROLL – Phase B v2 Commands
These commands run Phase B v2 using the real industrial Dotec roll with the new rig file `cyl_dotec.yaml`.

1. Run Phase B v2 (simple mode)  
```bash
python -m phase_b.v2.phase_b_tags_v2 \
  --config phase_b/config.yaml \
  --camera common/calib/calib.yaml \
  --rig phase_b/rigs/cyl_dotec.yaml \
  --extrinsics common/extrinsics/T_WC.yaml \
  --video 1 \
  --width 1920 --height 1080 --fps 30 \
  --save-poses phase_b/v2/poses_dotec.csv \
  --debug-metrics phase_b/v2/debug_metrics_dotec.csv \
  --simple
```

2. Run Phase B v2 (full v2 pipeline)  
```bash
python -m phase_b.v2.phase_b_tags_v2 \
  --config phase_b/config.yaml \
  --camera common/calib/calib.yaml \
  --rig phase_b/rigs/cyl_dotec.yaml \
  --extrinsics common/extrinsics/T_WC.yaml \
  --video 1 \
  --width 1920 --height 1080 --fps 30 \
  --save-poses phase_b/v2/poses_dotec_full.csv \
  --debug-metrics phase_b/v2/debug_metrics_dotec_full.csv \
  --ransac --adapt \
  --ema-alpha 0.25 \
  --use-weighted-se3 \
  --ekf --print-tilt
```

Notes:
- `phase_b/rigs/cyl_dotec.yaml` is the rig for the real Dotec roll.
- Adjust `--video` to the correct source (0, 1, or a device/URL) if needed.
- Outputs use Dotec-specific filenames to avoid overwriting other runs.

### Fixed-extrinsics validation (updated T_WC)
Use this to validate with the updated iPhone static extrinsics (1.10 m distance, 0.92 m height, ~45° down):
```bash
python -m phase_b.v2.phase_b_tags_v2 \
  --config phase_b/config.yaml \
  --camera common/calib/calib.yaml \
  --rig phase_b/rigs/cyl_dotec.yaml \
  --extrinsics common/extrinsics/T_WC.yaml \
  --video 1 \
  --width 1920 --height 1080 --fps 30 \
  --save-poses phase_b/v2/poses_dotec_fixed_T_W.csv \
  --debug-metrics phase_b/v2/debug_dotec_fixed_T_W.csv \
  --ransac --adapt \
  --ema-alpha 0.25 \
  --use-weighted-se3 \
  --ekf --print-tilt \
  --no-hud
```

### Dotec run (iPhone 13 landscape, 1080p)
```bash
python -m phase_b.v2.phase_b_tags_v2 \
  --config phase_b/config.yaml \
  --camera common/calib/calib.yaml \
  --rig phase_b/rigs/cyl_dotec.yaml \
  --extrinsics common/extrinsics/T_WC.yaml \
  --video 1 \
  --width 1920 --height 1080 --fps 30 \
  --save-poses phase_b/v2/poses_dotec_check_fixed.csv \
  --debug-metrics phase_b/v2/debug_dotec_check_fixed.csv \
  --ransac --adapt \
  --ema-alpha 0.25 \
  --use-weighted-se3 \
  --ekf --print-tilt --hud
```
Use the iPhone 13 landscape 1× calibration in `common/calib/calib.yaml`; adjust `--video` if the device index differs on your machine.
