# Basler Pose Test Summary

- Commit: `9d0d519c235e0f143465da8a7535d41f591bf760`
- Run dir: `D:\Electryone\PTL24_Marker\basler_test_runs\basler_run_0032_20260114_164934`

## spike_off
- poses.csv rows: 300
- debug_metrics.csv rows: 300
- effective_fps: 15.67
- Timing stats (ms):
  - t_total_ms: median=62.570 p90=71.051 max=111.852
  - t_detect_ms: median=39.911 p90=45.062 max=72.562
  - t_ransac_ms: median=20.353 p90=23.047 max=38.238
  - mean_reproj_px: median=22.027 p90=22.792 max=23.094
- reject_reason counts:
  - OK: 299
  - HOLD_PREV_POSE: 1
- reject_rate: 0.000
- KPI(100ms): PASS (median=62.6 p90=71.1)
- Drift stats vs first pose:
  - tvec_cam std: [0.3965, 0.5297, 0.6548]
  - tvec_cam p10: [-1.1676, -1.3505, -1.7674]
  - tvec_cam p90: [-0.1811, -0.0312, -0.0449]
  - tvec_cam min: [-1.3591, -1.7746, -1.8550]
  - tvec_cam max: [0.0000, 0.1539, 0.3667]
  - ypr_deg std: [106.9317, 15.4325, 47.3005]
  - ypr_deg p10: [-247.3745, -25.3001, 2.8163]
  - ypr_deg p90: [17.4501, 14.9328, 126.3666]
  - ypr_deg min: [-298.3011, -39.9790, -19.8337]
  - ypr_deg max: [59.6111, 20.5322, 142.3369]

- frame_grab_failed: 0 (rate=0.0000)
## Failure Modes and Fixes
- REJECT_SPIKE triggers when tilt jump exceeds max_tilt_jump_deg or when translation delta exceeds spike_trans_thresh_m (if set). It compares against the last accepted pose and skips spike checks for the first spike_reset_after frames after acceptance.
- Empty outputs usually come from camera lock (another app using the device), frame grab timeouts, or writing debug metrics to the default path. The runner asserts outputs and checks for fallback debug writes.
- Stability improvements: ensure >=3 tags in view, reduce motion blur (more light/shorter exposure), verify calibration matches ROI, and consider relaxing spike thresholds slightly if the rig is stable.

