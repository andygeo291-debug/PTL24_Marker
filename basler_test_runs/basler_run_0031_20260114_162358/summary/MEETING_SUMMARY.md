# Basler Pose Test Summary

- Commit: `9d0d519c235e0f143465da8a7535d41f591bf760`
- Run dir: `D:\Electryone\PTL24_Marker\basler_test_runs\basler_run_0031_20260114_162358`

## spike_off
- poses.csv rows: 180
- debug_metrics.csv rows: 180
- effective_fps: 14.87
- Timing stats (ms):
  - t_total_ms: median=65.644 p90=74.124 max=104.860
  - t_detect_ms: median=41.684 p90=48.418 max=63.104
  - t_ransac_ms: median=21.273 p90=25.032 max=50.615
  - mean_reproj_px: median=22.653 p90=22.965 max=23.394
- reject_reason counts:
  - OK: 180
- reject_rate: 0.000
- KPI(100ms): PASS (median=65.6 p90=74.1)
- Drift stats vs first pose:
  - tvec_cam std: [0.1228, 0.0753, 0.1678]
  - tvec_cam p10: [-0.4060, -0.1594, -0.0774]
  - tvec_cam p90: [-0.0848, 0.0241, 0.3150]
  - tvec_cam min: [-0.5482, -0.3104, -0.4269]
  - tvec_cam max: [0.0000, 0.0888, 0.5111]
  - ypr_deg std: [5.3521, 3.8176, 5.0889]
  - ypr_deg p10: [-1.5213, -5.4477, -4.6455]
  - ypr_deg p90: [12.0098, 4.6097, 7.3869]
  - ypr_deg min: [-6.1299, -8.2897, -14.0379]
  - ypr_deg max: [23.4813, 11.4184, 16.9808]

- frame_grab_failed: 0 (rate=0.0000)
## Failure Modes and Fixes
- REJECT_SPIKE triggers when tilt jump exceeds max_tilt_jump_deg or when translation delta exceeds spike_trans_thresh_m (if set). It compares against the last accepted pose and skips spike checks for the first spike_reset_after frames after acceptance.
- Empty outputs usually come from camera lock (another app using the device), frame grab timeouts, or writing debug metrics to the default path. The runner asserts outputs and checks for fallback debug writes.
- Stability improvements: ensure >=3 tags in view, reduce motion blur (more light/shorter exposure), verify calibration matches ROI, and consider relaxing spike thresholds slightly if the rig is stable.

