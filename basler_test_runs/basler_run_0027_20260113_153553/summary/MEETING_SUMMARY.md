# Basler Pose Test Summary

- Commit: `6554f09e48368d19093afeb9a1269ee253c4c2d0`
- Run dir: `D:\Electryone\PTL24_Marker\basler_test_runs\basler_run_0027_20260113_153553`

## spike_off
- poses.csv rows: 300
- debug_metrics.csv rows: 300
- effective_fps: 14.63
- Timing stats (ms):
  - t_total_ms: median=66.352 p90=75.028 max=132.223
  - t_detect_ms: median=41.964 p90=48.142 max=93.802
  - t_ransac_ms: median=21.489 p90=24.225 max=56.303
  - mean_reproj_px: median=22.401 p90=22.588 max=22.823
- reject_reason counts:
  - OK: 300
- reject_rate: 0.000
- KPI(100ms): PASS (median=66.4 p90=75.0)
- Drift stats vs first pose:
  - tvec_cam std: [0.2595, 0.1314, 0.1044]
  - tvec_cam p10: [-0.1788, -0.0782, -0.1592]
  - tvec_cam p90: [0.2871, 0.1931, 0.0661]
  - tvec_cam min: [-1.2678, -0.6986, -0.3428]
  - tvec_cam max: [1.1733, 0.3503, 0.4852]
  - ypr_deg std: [47.8437, 4.3644, 4.3986]
  - ypr_deg p10: [2.6021, -5.5878, 10.1203]
  - ypr_deg p90: [16.5845, 1.7125, 21.2170]
  - ypr_deg min: [-333.1357, -16.2506, 0.0000]
  - ypr_deg max: [23.3417, 18.9340, 25.9919]

- frame_grab_failed: 0 (rate=0.0000)
## Failure Modes and Fixes
- REJECT_SPIKE triggers when tilt jump exceeds max_tilt_jump_deg or when translation delta exceeds spike_trans_thresh_m (if set). It compares against the last accepted pose and skips spike checks for the first spike_reset_after frames after acceptance.
- Empty outputs usually come from camera lock (another app using the device), frame grab timeouts, or writing debug metrics to the default path. The runner asserts outputs and checks for fallback debug writes.
- Stability improvements: ensure >=3 tags in view, reduce motion blur (more light/shorter exposure), verify calibration matches ROI, and consider relaxing spike thresholds slightly if the rig is stable.

