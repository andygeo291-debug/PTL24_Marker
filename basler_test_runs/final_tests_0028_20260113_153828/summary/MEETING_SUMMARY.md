# Basler Pose Test Summary

- Commit: `6554f09e48368d19093afeb9a1269ee253c4c2d0`
- Run dir: `D:\Electryone\PTL24_Marker\basler_test_runs\basler_run_0028_20260113_153828`

## spike_off
- poses.csv rows: 900
- debug_metrics.csv rows: 900
- effective_fps: 13.86
- Timing stats (ms):
  - t_total_ms: median=68.946 p90=81.691 max=211.459
  - t_detect_ms: median=43.246 p90=50.827 max=130.750
  - t_ransac_ms: median=23.273 p90=27.512 max=73.805
  - mean_reproj_px: median=22.404 p90=22.593 max=22.848
- reject_reason counts:
  - OK: 900
- reject_rate: 0.000
- KPI(100ms): PASS (median=68.9 p90=81.7)
- Drift stats vs first pose:
  - tvec_cam std: [0.2268, 0.1177, 0.1028]
  - tvec_cam p10: [-0.2415, -0.1683, -0.2450]
  - tvec_cam p90: [0.0418, 0.0913, -0.0302]
  - tvec_cam min: [-1.3961, -0.8647, -0.4930]
  - tvec_cam max: [0.9658, 0.2914, 0.4240]
  - ypr_deg std: [51.9512, 4.5044, 4.3130]
  - ypr_deg p10: [-1.0744, -9.0899, -13.2228]
  - ypr_deg p90: [11.3210, -0.8631, -1.9312]
  - ypr_deg min: [-341.2971, -38.3387, -21.1642]
  - ypr_deg max: [18.0106, 13.1885, 6.1066]

- frame_grab_failed: 0 (rate=0.0000)
## Failure Modes and Fixes
- REJECT_SPIKE triggers when tilt jump exceeds max_tilt_jump_deg or when translation delta exceeds spike_trans_thresh_m (if set). It compares against the last accepted pose and skips spike checks for the first spike_reset_after frames after acceptance.
- Empty outputs usually come from camera lock (another app using the device), frame grab timeouts, or writing debug metrics to the default path. The runner asserts outputs and checks for fallback debug writes.
- Stability improvements: ensure >=3 tags in view, reduce motion blur (more light/shorter exposure), verify calibration matches ROI, and consider relaxing spike thresholds slightly if the rig is stable.

