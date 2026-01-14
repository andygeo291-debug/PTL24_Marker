# Basler Pose Test Summary

- Commit: `6554f09e48368d19093afeb9a1269ee253c4c2d0`
- Run dir: `D:\Electryone\PTL24_Marker\basler_test_runs\basler_run_0024_20260113_140408`

## spike_off
- poses.csv rows: 900
- debug_metrics.csv rows: 900
- effective_fps: 13.85
- Timing stats (ms):
  - t_total_ms: median=67.350 p90=76.880 max=381.302
  - t_detect_ms: median=42.539 p90=48.914 max=262.946
  - t_ransac_ms: median=21.970 p90=25.744 max=114.562
  - mean_reproj_px: median=21.960 p90=21.992 max=22.697
- reject_reason counts:
  - OK: 900
- reject_rate: 0.000
- KPI(100ms): PASS (median=67.3 p90=76.9)
- Drift stats vs first pose:
  - tvec_cam std: [0.1496, 0.1234, 0.1263]
  - tvec_cam p10: [-0.1645, -0.2949, -0.3111]
  - tvec_cam p90: [0.1621, 0.0114, 0.0211]
  - tvec_cam min: [-0.4156, -0.5889, -0.5789]
  - tvec_cam max: [0.6095, 0.1597, 0.1207]
  - ypr_deg std: [6.2871, 5.0407, 2.5399]
  - ypr_deg p10: [-8.8830, -17.0599, -3.9214]
  - ypr_deg p90: [6.6426, -4.0952, 2.6930]
  - ypr_deg min: [-20.5220, -29.7200, -7.2150]
  - ypr_deg max: [21.1331, 2.2701, 7.9938]

- frame_grab_failed: 0 (rate=0.0000)
## Failure Modes and Fixes
- REJECT_SPIKE triggers when tilt jump exceeds max_tilt_jump_deg or when translation delta exceeds spike_trans_thresh_m (if set). It compares against the last accepted pose and skips spike checks for the first spike_reset_after frames after acceptance.
- Empty outputs usually come from camera lock (another app using the device), frame grab timeouts, or writing debug metrics to the default path. The runner asserts outputs and checks for fallback debug writes.
- Stability improvements: ensure >=3 tags in view, reduce motion blur (more light/shorter exposure), verify calibration matches ROI, and consider relaxing spike thresholds slightly if the rig is stable.

