Phase A – Marker-Based AprilTag Detection
=========================================

This repository implements the Phase‑A pipeline for a fixed, high-mounted camera detecting AprilTags and reporting world-frame poses. The camera pose (extrinsics) can be supplied manually from configuration or recovered once via PnP, then reused for all subsequent runs.

Coordinate Frames
-----------------
- **World frame (W):** X forward, Y left, Z up. Ground plane is Z = 0.
- **Camera frame (C):** Provided by the AprilTag detector (rvec/tvec per tag).
- We estimate the camera pose `T_W<-C`, then compute each tag pose `T_W<-Tag = T_W<-C @ T_C<-Tag`.

Key Files
---------
- `apriltag_demo.py` – Main application. Loads intrinsics/extrinsics, runs the detector, converts tag poses to world frame, overlays diagnostics, prints JSON, and optionally logs CSV (`frame, tag_id, X, Y, Z, roll, pitch, yaw` in meters/radians).
- `frames.py` – Math helpers: rotation matrices (`Rx, Ry, Rz`), `compose_T`, `rvec_tvec_to_T`, `T_to_rpy_xyz`, and `build_T_WC_from_config`.
- `calib_io.py` – YAML/JSON utilities for reading calibration config (`camera.intrinsics`, `camera.world_pose`) and 4×4 transforms (`load_T`, `save_T`, `load_intrinsics_*`).
- `config.yaml` – Camera intrinsics and the manual world pose (x, y, rho, pitch, yaw, roll). Also contains default mode and extrinsics file path.
- `data/T_WC.yaml` – Saved camera extrinsics produced by the one-time PnP routine. Reuse while the camera mount stays fixed.
- `scripts/setup_and_run.py` – Helper that ensures config/extrinsics exist (optionally creating a sample config) and then executes `apriltag_demo.py` with the correct arguments.

Modes for Camera Pose
---------------------
1. **Manual mode** – Uses `camera.world_pose` in `config.yaml`. `build_T_WC_from_config` constructs `T_W<-C = Rz(yaw) @ Ry(pitch) @ Rx(roll)` with translation `[x, y, rho]`.
2. **PnP mode** – Loads `T_W<-C` from `data/T_WC.yaml` (created via `--estimate-extrinsics`). Recommended once accurate ground-to-camera geometry is known.

What Each Script Does
---------------------
- `capture_calib_images.py` – Interactive capture of chessboard images for calibration (SPACE to save, `q` to quit).
- `camera_calibrate.py` – Takes chessboard images, solves for intrinsics, writes `camera_intrinsics.npz`, and prints `fx, fy, cx, cy`.
- `apriltag_demo.py` – End-to-end detection loop (see steps below).
- `scripts/setup_and_run.py` – Pre-flight helper (create config, ensure extrinsics, launch demo).

How `apriltag_demo.py` Works
----------------------------
1. Parse CLI arguments (config, pose mode, extrinsics path, logging, PnP estimation flags).
2. Load intrinsics `K`, `dist` from config (or fallback NPZ). Warn if missing.
3. Determine `T_W<-C`:
   - `--camera-pose-mode manual`: read `camera.world_pose` and call `build_T_WC_from_config`.
   - `--camera-pose-mode pnp`: load `data/T_WC.yaml` via `calib_io.load_T`.
4. Spin the AprilTag detector (Pupil Labs implementation). For each detection:
   - Use returned `pose_R`, `pose_t` to form `T_C<-Tag`.
   - Compute `T_W<-Tag = T_W<-C @ T_C<-Tag`.
   - Extract `(roll, pitch, yaw, X, Y, Z)` with `T_to_rpy_xyz`.
   - Print JSON and log CSV if `--log-csv` provided.
5. Show diagnostics: FPS/latency overlay, green tag outline, optional 3D axes (ESC/`q` to quit, SPACE toggles axes).

Setup Helper (`scripts/setup_and_run.py`)
-----------------------------------------
```
python scripts/setup_and_run.py \
  --create-sample-config \
  --camera-pose-mode pnp \
  --config config.yaml \
  --extrinsics-file data/T_WC.yaml
```
Actions performed:
1. Ensure `config.yaml` exists (create sample with realistic placeholders when requested).
2. Ensure `data/` folder exists.
3. If running in PnP mode, confirm `data/T_WC.yaml` is present; otherwise, print the exact PnP command required.
4. Execute `python apriltag_demo.py --config … --camera-pose-mode … --extrinsics-file …` unless `--dry-run` is used.

Estimating Extrinsics Once (PnP)
--------------------------------
Collect corresponding world/image points (e.g., corners of ground markers) and run:
```
python apriltag_demo.py --estimate-extrinsics \
  --points data/world_points.yaml \
  --image-points data/image_points.yaml \
  --save data/T_WC.yaml \
  --intrinsics data/K.yaml
```
The command prints RMS reprojection error and saves `data/T_WC.yaml`. Reuse this file for every future run (as long as the camera mount does not move).

Running the Demo
----------------
- **Manual pose (uses `camera.world_pose`):**
  ```
  python apriltag_demo.py --config config.yaml --camera-pose-mode manual --log-csv out.csv
  ```
  CSV columns: `frame, tag_id, X, Y, Z, roll, pitch, yaw` (world frame, meters/radians).

- **PnP pose (recommended once `data/T_WC.yaml` exists):**
  ```
  python apriltag_demo.py --config config.yaml --camera-pose-mode pnp --extrinsics-file data/T_WC.yaml
  ```

Validating the Pipeline
-----------------------
1. Place a tag at a known ground location. The reported `(X, Y)` should match within a few centimetres when PnP extrinsics are accurate.
2. Lift the tag by a known height – Z should track that value (with minor noise).
3. Run CSV logging, open the file, and confirm columns match the printed JSON.
4. Quick regressions:
   - `python scripts/setup_and_run.py --dry-run` (checks paths only).
   - `python apriltag_demo.py --estimate-extrinsics …` (completes successfully with sample data).
   - `python apriltag_demo.py --config config.yaml --camera-pose-mode pnp --extrinsics-file data/T_WC.yaml` (prints world-frame poses).
  - `grep -Ri "ground-plane helper" .` (should output nothing).

Copy & Paste Quick Start
------------------------
```bash
# From project root:
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# 1) Create default config (if missing) and attempt run (PNP mode)
python scripts/setup_and_run.py --create-sample-config --camera-pose-mode pnp --config config.yaml --extrinsics-file data/T_WC.yaml

# 2) If extrinsics are missing, first estimate them (one-time):
python apriltag_demo.py --estimate-extrinsics \
  --points data/world_points.yaml \
  --image-points data/image_points.yaml \
  --save data/T_WC.yaml \
  --intrinsics data/K.yaml

# 3) Then run with PNP
python apriltag_demo.py --config config.yaml --camera-pose-mode pnp --extrinsics-file data/T_WC.yaml

# 4) Or run in manual mode (uses world_pose from config.yaml)
python apriltag_demo.py --config config.yaml --camera-pose-mode manual --log-csv out.csv
```

Beyond Phase A: Phase B and validation
--------------------------------------
- Phase B handles geometry-assisted roll pose estimation using an AprilTag rig, RANSAC, and SE(3) fusion.
- Phase B v2 introduces weighted SE(3) fusion, adaptive RANSAC, HUD diagnostics, and benchmark logging; see `phase_b/README_phase_b_v2.md`.
- For the wider Phase B overview (context, rigs, streaming), read `phase_b/README.md`.
- `PTL24_MARKER_RUN_COMMANDS.md` consolidates Phase A/B setup, multi-camera extrinsics, validation scenarios (S1/S2/S3), and tooling commands into a single cheat sheet.

Basler Lab Runbook
------------------
- `docs/BASLER_LAB_RUNBOOK.md` – Windows-first checklist for Basler link health, HUD check, report runs, stability metrics, and report artifacts.
- `README_FINAL_TESTS.md` - Final tests runbook with calibration, golden runs, and live monitoring.

Docs
----
- `docs/SUPERVISOR_RUNBOOK.md` – One-page supervisor cheat sheet (Windows/macOS).
- `docs/SUPERVISOR_TECHNICAL_GUIDE.md` – Architecture + key functions and metrics.
- `basler_test_runs/README.md` – Notes on run artifacts and folder structure.
