# CODE NAVIGATION

## Start here
- `docs/SUPERVISOR_RUNBOOK.md`: operator-friendly commands and checks.
- `docs/SUPERVISOR_TECHNICAL_GUIDE.md`: pipeline overview + key concepts.
- `phase_b/v2/phase_b_tags_v2.py`: main entry point for Phase B v2.

## Pipeline map (high level)
- Capture frames -> `common/camera/factory.py` -> `common/camera/basler_cam.py` or OpenCV.
- Preprocess + AprilTag detect -> `phase_b/v2/phase_b_tags_v2.py` (calls `phase_b/v1/phase_b_tags.py` detector helpers).
- RANSAC + fusion -> `phase_b/v2/phase_b_tags_v2.py` + `phase_b/v2/se3_fuse.py`.
- Quality/spike gate -> `phase_b/v2/quality.py` and v2 main loop.
- Output logging -> `phase_b/v2/debug_log.py` (debug metrics) + poses CSV writer.
- Bench timing -> `phase_b/v2/bench.py`.

## Where things live
- Rig YAMLs: `phase_b/rigs/*.yaml`
- Calibration YAMLs: `common/calib/*.yaml` (fallbacks in `phase_b/calib/`)
- Extrinsics YAMLs: `common/extrinsics/` or `phase_b/extrinsics/`
- Run outputs: `basler_test_runs/<run_id>/` (poses.csv, debug_metrics.csv, summary/)
- Tools/scripts: `tools/` (test runners, diagnostics, calibration helpers)

## Where to change what
- Rig geometry / tag IDs: edit `phase_b/rigs/*.yaml`.
- Camera intrinsics: add/update `common/calib/*.yaml`.
- Detector parameters: CLI flags in `phase_b/v2/phase_b_tags_v2.py`
  (e.g., `--det-quad-decimate`, `--det-nthreads`).
- RANSAC thresholds/iters: CLI flags in `phase_b/v2/phase_b_tags_v2.py`
  (e.g., `--ransac-iters`, `--ransac-trans`, `--ransac-rot`).

## Run the Basler test suite
- Follow the commands in `docs/SUPERVISOR_RUNBOOK.md` (Windows + macOS blocks).

## Glossary
- SE(3): 3D rigid transform (rotation + translation).
- rvec/tvec: Rodrigues rotation vector (radians) + translation (meters).
- RANSAC: robust estimator to select consistent tag detections.
- Reprojection error: pixel distance between observed and projected tag corners.
- p90: 90th percentile (value below which 90% of samples fall).
