# Supervisor Technical Guide (Phase B v2)

This guide explains the Phase B v2 pipeline, where to look in code, and how to interpret outputs.

## High-level inputs/outputs
Inputs
- Camera frames (Basler or OpenCV).
- Rig definition YAML (tag ids, size_m, tag poses).
- Camera intrinsics YAML (K, dist).
- Optional extrinsics YAML (T_WC: world -> camera).

Outputs
- `poses.csv` (camera-frame pose + optional world-frame pose).
- `debug_metrics.csv` (per-frame detection/latency stats).
- Optional UDP stream (pose packets).

## Pipeline outline (diagram-like)
1) Capture frame
2) Preprocess (gray, optional undistort)
3) Detect tags (AprilTag detector)
4) PnP per tag -> candidate tag pose
5) RANSAC + fusion (weighted SE(3))
6) Spike rejection + EMA smoothing
7) Output writing (poses.csv, debug_metrics.csv, optional HUD/UDP)

## Key data structures
- `pose_record` (dict): holds `T_cam_to_cyl`, `T_cyl_to_cam`, `rvec_cam`, `tvec_cam`, optional `rvec_world`, `tvec_world`, `tilt_*`, `used_ids`.
- Debug row (`debug_metrics.csv`): see `phase_b/v2/debug_log.py` header.

## Where things happen (file/line references)
- Main CLI + loop: `phase_b/v2/phase_b_tags_v2.py` `parse_args` (~331), `run` (~763).
- Detector setup: `phase_b/v1/phase_b_tags_legacy.py` `setup_detector` (~1087).
- Pose composition: `phase_b/v1/phase_b_tags_legacy.py` `build_pose_record` (~753).
- Debug logging: `phase_b/v2/debug_log.py` `DebugLogger` (~13).
- Bench timings: `phase_b/v2/bench.py` `StageTimer` (~14).
- Fusion math: `phase_b/v2/se3_fuse.py` `weighted_average_se3` (~109).
- Basler backend: `common/camera/basler_cam.py` `BaslerGigECam` (~9).
- Backend selection: `common/camera/factory.py` `create_camera_from_args` (~59).
- Path resolution: `phase_b/v2/utils_paths.py` `resolve_calib_path` (~58).

## Transform conventions (camera/world)
Computed in `build_pose_record`:
- `T_cam_to_cyl` is the camera->cylinder transform from tag geometry.
- `T_cyl_to_cam = inv(T_cam_to_cyl)` is used for `rvec_cam`/`tvec_cam`.
  - This means `p_cam = R_cyl_to_cam * p_cyl + t_cyl_to_cam`.
- If extrinsics are provided (`T_WC`), then:
  - `T_world_to_cyl = T_world_to_cam @ T_cam_to_cyl`.
  - `rvec_world`/`tvec_world` come from `T_world_to_cyl`.

## Key parameters (impact)
Detector
- `--det-nthreads`: parallelism (higher = faster, CPU bound).
- `--det-quad-decimate`: >1.0 can be faster but reduces small tag detection.
- `--det-refine-edges`: improves accuracy at cost of compute.

RANSAC + fusion
- `--ransac-iters`: more iterations = more robust, higher latency.
- `--ransac-trans/--ransac-rot`: tighter thresholds reject outliers sooner.
- `--use-weighted-se3`: weighted fusion favors better tag quality.

Spike rejection
- `--max-tilt-jump-deg`: rejects sudden tilt spikes.
- `--spike-reset-after`: how long to skip spike checks after a good pose.

Camera control (latency vs quality)
- `--fps`, `--exposure-us`, `--gain`: motion blur vs noise.
- Basler: packet size + interpacket delay control drop rate.

## Debug metrics columns (how to read)
`debug_metrics.csv` header comes from `phase_b/v2/debug_log.py` and includes:
- `t_total_ms`, `t_detect_ms`, `t_ransac_ms`: latency breakdown.
- `n_visible`: detected tags kept for pose.
- `n_dets_raw`, `n_dets_kept`: detector raw vs accepted.
- `mean_reproj_px`: reprojection error; lower is better.
- `reject_reason`: `OK`, `HOLD_PREV_POSE`, or rejection type.

Use p50/p90 of `t_total_ms` to assess latency stability (p90 < 100 ms is the KPI).
