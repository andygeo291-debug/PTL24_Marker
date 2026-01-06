# Phase A – AprilTag Baseline

Phase A estimates world-frame poses of AprilTags observed by a fixed camera. The workflow is:

1. Collect calibration images.
2. Solve for intrinsics.
3. (Optional) Estimate extrinsics once via PnP.
4. Stream detections with `apriltag_demo.py`, logging CSV/JSON as needed.

## Directory Layout

- `apps/` – runnable scripts.
- `lib/` – utility modules (`calib_io.py`, `frames.py`).
- `assets/` – calibration/test imagery and printable tags.
- `data/` – outputs (`camera_intrinsics.npz`, `T_WC.yaml`, CSV logs).
- `config.yaml` – default intrinsics + camera pose/extrinsics reference.

## Quick Start

```bash
# 1. Capture calibration images (press SPACE to save, q to quit)
python phase_a/apps/capture_calib_images.py

# 2. Solve intrinsics (writes phase_a/data/camera_intrinsics.npz)
python phase_a/apps/camera_calibrate.py --square-size 0.024

# 3. Create config/extrinsics (optional helper)
python phase_a/apps/setup_and_run.py --create-sample-config --camera-pose-mode pnp
```

### Running the Demo

```bash
#### Manual pose (uses camera.world_pose in phase_a/config.yaml)
python phase_a/apps/apriltag_demo.py \
  --config phase_a/config.yaml \
  --camera-pose-mode manual \
  --log-csv phase_a/data/poses.csv

# PnP pose (requires phase_a/data/T_WC.yaml)
python phase_a/apps/apriltag_demo.py \
  --config phase_a/config.yaml \
  --camera-pose-mode pnp \
  --extrinsics-file phase_a/data/T_WC.yaml
```

### Estimating Extrinsics Once

```bash
python phase_a/apps/apriltag_demo.py \
  --estimate-extrinsics \
  --points phase_a/data/world_points.yaml \
  --image-points phase_a/data/image_points.yaml \
  --save phase_a/data/T_WC.yaml \
  --intrinsics phase_a/data/camera_intrinsics.npz
```

The command prints RMS reprojection error and saves `T_WC.yaml`. Reuse it while the camera mount stays fixed.

## Notes

- All intrinsics/extrinsics helpers live in `phase_a/lib`; import them via `from phase_a.lib import calib_io`.
- Default fallbacks search `phase_a/data/camera_intrinsics.npz` first, then `common/calib/calib.yaml`.
- CSV logs are created under `phase_a/data/` when `--log-csv` is supplied.
