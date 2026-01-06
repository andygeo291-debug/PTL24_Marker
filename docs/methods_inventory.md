# Methods Inventory (PTL24)

## A. Pipeline entry points
- `phase_b/v2/phase_b_tags_v2.py`: Main Phase B v2 online pipeline (camera capture → AprilTag detect → RANSAC/SE3 fusion → optional EKF smoothing → HUD/CSV/UDP/logging). Key flags: `--config`, `--video/--width/--height/--fps`, `--calib`, `--extrinsics`, `--rig`, `--debug-metrics`, `--save-poses`, `--use-weighted-se3/--no-use-weighted-se3`, `--ekf`, `--adapt`, `--bench-print-every`, `--hud` (toggle overlay), `--no-overlay` (draw axes/HUD off even if window open), `--frames` (limit), `--stream-udp`.
- `phase_b/tools/analyze_metrics.py`: Post-process a debug_metrics CSV; computes FPS stats, tilt stats, and timing breakdown medians, writing `timing_breakdown.txt` and `timing_breakdown.csv`.
- `phase_b/tools/compare_runs.py`: Compare two debug_metrics CSVs (median FPS, median totals, per-stage medians and deltas) and write a text/markdown report.
- `phase_b/tools/trim_debug_metrics.py`: Trim an initial time window from a debug_metrics CSV, preserving comment provenance.
- Other helpers noted: `phase_b/tools/compare_poses.py` (pose CSV diffs) and `phase_b/tools/archive_validation_run.py` (pack run artifacts).

## B. Config files used
- Camera intrinsics (OpenCV YAML): `phase_b/calib/calib.yaml` (fallback to `common/calib` if missing). Excerpt:
  ```
  %YAML:1.0
  ---
  T_WC:
    rows: 4
    cols: 4
    data: [
      1.000000, 0.000000, 0.000000, -0.000000,
      0.000000, 0.987688, -0.156434, 0.167385,
      0.000000, 0.156434, 0.987688, -1.056827,
      0.0, 0.0, 0.0, 1.0
    ]
  ```
  Represents camera-to-world transform; units are meters, angles in radians inside rotation matrix.
- Extrinsics (world←camera SE3, meters): `common/extrinsics/T_WC_c920_1280x720.yaml` and `common/extrinsics/T_WC_c920_1920x1080.yaml`. Excerpt (1280x720):
  ```
  T_WC:
  - - -0.0066741895989663735
    - 0.999492622727383
    - 0.03114405732614295
    - 0.025129421726140962
  - - 0.6350679065616689
    - 0.02829419909017511
    - -0.7719379459213187
    - 0.08893413969837531
  - - -0.7724274783101495
    - 0.014626531078234806
    - -0.6349345283885897
    - 1.5679422152647917
  - - 0.0
    - 0.0
    - 0.0
    - 1.0
  ```
- Rig definition (cylindrical tag rig, meters): `phase_b/rigs/cyl_dotec.yaml`. Excerpt:
  ```
  radius_m: 0.1175
  length_m: 0.50
  top_annulus: ids: [200, 201, 202] radius_m: 0.085 size_m: 0.050
  bottom_annulus: ids: [300, 301, 302] radius_m: 0.085 size_m: 0.050 yaw0_deg: 15
  ring: ids: [100..111] size_m: 0.050 z_m: 0.0
  ```
  Defines tag IDs, physical sizes, and placement around the cylinder.
- Phase B defaults: `phase_b/config.yaml`
  ```
  ransac: trans_max_m: 0.05 rot_max_deg: 5 min_inliers: 3 adaptive: false A_ref_px2: 12000 base_trans_m: 0.05 base_rot_deg: 5
  fuse: ema_alpha: 0.3 use_weighted_se3: true axis_len_m: 0.1
  health: max_tilt_jump_deg: 15
  video: device: 2 width: 1920 height: 1080 fps: 30
  logging: poses_csv: phase_b/poses.csv debug_metrics_csv: phase_b/debug_metrics.csv
  hud: enabled: true
  bench: print_every: 60
  ```

## C. Experiment scenarios (commands)
| Scenario | Command line | Key flags | Expected outputs |
| --- | --- | --- | --- |
| 720p_nohud_trim2s | `python3 phase_b/v2/phase_b_tags_v2.py --config phase_b/config.yaml --width 1280 --height 720 --debug-metrics Preliminary_report/runs/bench_clean/720p/debug_metrics.csv --save-poses Preliminary_report/runs/bench_clean/720p/poses.csv` | HUD off by default (no `--hud`); weighted SE3 from config; RANSAC thresholds from config; no EKF; saves raw debug_metrics and poses | CSVs under `Preliminary_report/runs/bench_clean/720p/` |
| 1080p_nohud_trim2s | `python3 phase_b/v2/phase_b_tags_v2.py --config phase_b/config.yaml --width 1920 --height 1080 --debug-metrics Preliminary_report/runs/bench_clean/1080p/debug_metrics.csv --save-poses Preliminary_report/runs/bench_clean/1080p/poses.csv` | Same flags as 720p; higher capture resolution | CSVs under `Preliminary_report/runs/bench_clean/1080p/` |
| Trim first 2s | `python3 phase_b/tools/trim_debug_metrics.py --csv <run>/debug_metrics.csv --skip-seconds 2.0 --out <run>/debug_metrics_trim2s.csv` | Drops early warm-up rows based on timestamp column `t` | Trimmed debug_metrics CSV |
| Per-run analysis | `python3 phase_b/tools/analyze_metrics.py --csv <run>/debug_metrics_trim2s.csv --out Preliminary_report/metrics/<label>` | Computes FPS stats, tilt stats, timing medians; writes plots + `timing_breakdown.txt/csv` | Plots + timing tables under metrics folder |
| Compare runs | `python3 phase_b/tools/compare_runs.py --csv-a <720p_csv> --csv-b <1080p_csv> --label-a 720p --label-b 1080p --out Preliminary_report/metrics/compare_720p_vs_1080p.txt` | Uses medians only; reports FPS, t_total_ms, per-stage shares and deltas | Comparison report text/markdown |

## D. Outputs and schemas
- Debug metrics CSV (written by `phase_b/v2/debug_log.py`, header order):  
  `t,fps,n_visible,n_inliers,mean_reproj,ransac_score,weight_min,weight_max,tilt_deg,mean_tag_area_px2,mean_view_cos,mean_reproj_px,ransac_trans_eff,ransac_rot_eff,n_unknown_ids,n_mirror_discards,spike_delta_trans_m,spike_delta_rot_deg,spike_trans_thresh_m,spike_rot_thresh_deg,spike_ref_age_frames,spike_ref_frame_idx,t_read_ms,t_gray_ms,t_detect_ms,t_reproj_ms,t_ransac_ms,t_fuse_ms,t_ekf_ms,t_hud_ms,t_log_ms,t_total_ms`  
  - Core tracking: time, instantaneous FPS, visible/inlier counts, reprojection error, RANSAC score and effective thresholds, quality weight extrema, tilt.  
  - Health/spike detection: unknown IDs, mirror discards, spike deltas/thresholds/reference ages.  
  - Per-stage timings: per-frame milliseconds for capture/read, grayscale, detector, reprojection prep, RANSAC, fusion, EKF, HUD/imshow, logging, total loop.
- Poses CSV (written by `phase_b_tags_v2.py`, `POSES_HEADER`):  
  `timestamp,frame,used_ids,decision_margins,rvec_cam_x,rvec_cam_y,rvec_cam_z,tvec_cam_x,tvec_cam_y,tvec_cam_z,rvec_world_x,rvec_world_y,rvec_world_z,tvec_world_x,tvec_world_y,tvec_world_z,tilt_cam_deg,tilt_world_deg`  
  - Camera/world pose vectors in Rodrigues + translation (meters), tag IDs/margins used for fusion, tilt angles.
- Analysis outputs:  
  - `timing_breakdown.txt/csv` from `analyze_metrics.py` with median t_total_ms, effective_fps=1000/median_total, per-stage medians and % of median total.  
  - Comparison reports from `compare_runs.py` showing medians, per-stage shares, and deltas.

## E. Timing and performance metrics
- Total time per frame (`t_total_ms`) measured in `phase_b_tags_v2.py` as `perf_counter()` delta from loop start through render/logging.
- Stage timings (ms):  
  `t_read_ms` (capture/read), `t_gray_ms` (BGR→gray), `t_detect_ms` (AprilTag detector call), `t_reproj_ms` (reprojection error + tag prep), `t_ransac_ms` (candidate generation/RANSAC), `t_fuse_ms` (fusion/EMA/spike handling), `t_ekf_ms` (EKF update placeholder), `t_hud_ms` (axes/HUD/imshow), `t_log_ms` (CSV writes), `t_total_ms` (end-to-end).
- Reporting uses medians to avoid FPS spikes; effective FPS = `1000 / median(t_total_ms)`.
- Known caveats: warm-up frames can distort medians; trim with `trim_debug_metrics.py`. HUD/imshow overhead is captured in `t_hud_ms`; disabling HUD lowers that term. Logging overhead captured in `t_log_ms`.

## F. Provenance & environment
- Git: repository not a git working tree here (no `.git`; `git rev-parse` fails).
- Python: `Python 3.13.7`
- Pip (top packages): `opencv-python==4.12.0.88`, `pandas==2.3.3`, `numpy==2.2.6`, `matplotlib==3.10.6`, `pupil_apriltags==1.0.4.post11`, `PyYAML==6.0.3`, plus supporting libs (cycler, contourpy, pillow, etc.).
- OS/CPU: `Darwin 24.6.0 arm64 (Apple M1, T8103)`.
- Requirements file: see `requirements.txt` in repo for full dependency list (not executed here).

## G. Notes / assumptions
- HUD is disabled unless `--hud` is passed (config `hud.enabled` is not consulted by the runner).  
- Extrinsics/calib/rig paths are resolved relative to repo root with fallbacks (`utils_paths.py`); adjust if files live elsewhere.  
- No git metadata available; capture commit/branch manually if running from a cloned repo.  
- EKF timing column is present but EKF is off unless `--ekf` flag is provided.
