# Basler Pose Test Summary

- Commit: `9d0d519c235e0f143465da8a7535d41f591bf760`
- Run dir: `D:\Electryone\PTL24_Marker\basler_test_runs\basler_run_0030_20260114_161908`

## spike_off
- poses.csv rows: 180
- debug_metrics.csv rows: 180
- effective_fps: 15.48
- Timing stats (ms):
  - t_total_ms: median=63.234 p90=69.331 max=115.962
  - t_detect_ms: median=39.534 p90=44.461 max=82.603
  - t_ransac_ms: median=20.753 p90=22.881 max=58.626
  - mean_reproj_px: median=22.049 p90=22.781 max=23.041
- reject_reason counts:
  - OK: 180
- reject_rate: 0.000
- KPI(100ms): PASS (median=63.2 p90=69.3)
- Drift stats vs first pose:
  - tvec_cam std: [0.0899, 0.0632, 0.1586]
  - tvec_cam p10: [-0.3020, -0.1246, -0.0561]
  - tvec_cam p90: [-0.0735, 0.0313, 0.3524]
  - tvec_cam min: [-0.4272, -0.2384, -0.3271]
  - tvec_cam max: [0.0000, 0.0879, 0.4723]
  - ypr_deg std: [4.2791, 3.3555, 3.7217]
  - ypr_deg p10: [-3.3880, -7.3312, -6.3673]
  - ypr_deg p90: [7.4018, 1.9173, 3.3160]
  - ypr_deg min: [-7.8785, -10.2988, -11.4681]
  - ypr_deg max: [13.2017, 5.2711, 7.3005]

- frame_grab_failed: 0 (rate=0.0000)
## Failure Modes and Fixes
- REJECT_SPIKE triggers when tilt jump exceeds max_tilt_jump_deg or when translation delta exceeds spike_trans_thresh_m (if set). It compares against the last accepted pose and skips spike checks for the first spike_reset_after frames after acceptance.
- Empty outputs usually come from camera lock (another app using the device), frame grab timeouts, or writing debug metrics to the default path. The runner asserts outputs and checks for fallback debug writes.
- Stability improvements: ensure >=3 tags in view, reduce motion blur (more light/shorter exposure), verify calibration matches ROI, and consider relaxing spike thresholds slightly if the rig is stable.

