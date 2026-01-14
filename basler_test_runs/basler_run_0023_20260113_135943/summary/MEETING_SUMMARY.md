# Basler Pose Test Summary

- Commit: `6554f09e48368d19093afeb9a1269ee253c4c2d0`
- Run dir: `D:\Electryone\PTL24_Marker\basler_test_runs\basler_run_0023_20260113_135943`

## spike_off
- poses.csv rows: 300
- debug_metrics.csv rows: 300
- effective_fps: 14.76
- Timing stats (ms):
  - t_total_ms: median=65.897 p90=72.825 max=151.039
  - t_detect_ms: median=41.507 p90=46.874 max=103.228
  - t_ransac_ms: median=21.550 p90=23.007 max=43.847
  - mean_reproj_px: median=21.940 p90=22.476 max=22.706
- reject_reason counts:
  - OK: 300
- reject_rate: 0.000
- KPI(100ms): PASS (median=65.9 p90=72.8)
- Drift stats vs first pose:
  - tvec_cam std: [0.2769, 0.1106, 0.1518]
  - tvec_cam p10: [-0.1025, -0.1894, -0.2886]
  - tvec_cam p90: [0.5156, 0.0739, 0.0723]
  - tvec_cam min: [-0.4002, -0.4916, -0.5352]
  - tvec_cam max: [1.4039, 0.1987, 0.4509]
  - ypr_deg std: [20.5037, 5.3619, 3.5213]
  - ypr_deg p10: [-16.5893, -12.4350, -2.2256]
  - ypr_deg p90: [4.4544, 0.0015, 5.7070]
  - ypr_deg min: [-30.0468, -27.3327, -6.2115]
  - ypr_deg max: [321.4298, 15.0175, 15.5371]

- frame_grab_failed: 0 (rate=0.0000)
## Failure Modes and Fixes
- REJECT_SPIKE triggers when tilt jump exceeds max_tilt_jump_deg or when translation delta exceeds spike_trans_thresh_m (if set). It compares against the last accepted pose and skips spike checks for the first spike_reset_after frames after acceptance.
- Empty outputs usually come from camera lock (another app using the device), frame grab timeouts, or writing debug metrics to the default path. The runner asserts outputs and checks for fallback debug writes.
- Stability improvements: ensure >=3 tags in view, reduce motion blur (more light/shorter exposure), verify calibration matches ROI, and consider relaxing spike thresholds slightly if the rig is stable.

