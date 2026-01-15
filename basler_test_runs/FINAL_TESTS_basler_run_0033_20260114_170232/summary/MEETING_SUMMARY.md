# Basler Pose Test Summary

- Commit: `9d0d519c235e0f143465da8a7535d41f591bf760`
- Run dir: `D:\Electryone\PTL24_Marker\basler_test_runs\basler_run_0033_20260114_170232`

## spike_off
- poses.csv rows: 900
- debug_metrics.csv rows: 900
- effective_fps: 16.10
- Timing stats (ms):
  - t_total_ms: median=60.686 p90=68.983 max=125.869
  - t_detect_ms: median=37.514 p90=42.880 max=92.197
  - t_ransac_ms: median=20.571 p90=23.741 max=47.159
  - mean_reproj_px: median=22.485 p90=22.573 max=23.450
- reject_reason counts:
  - OK: 899
  - HOLD_PREV_POSE: 1
- reject_rate: 0.000
- KPI(100ms): PASS (median=60.7 p90=69.0)
- Drift stats vs first pose:
  - tvec_cam std: [0.0473, 0.0851, 0.1447]
  - tvec_cam p10: [-0.1300, -0.0912, -0.2654]
  - tvec_cam p90: [-0.0087, 0.1232, 0.0823]
  - tvec_cam min: [-0.2125, -0.2767, -0.8461]
  - tvec_cam max: [0.0857, 0.3597, 0.2581]
  - ypr_deg std: [4.5797, 3.1838, 7.5412]
  - ypr_deg p10: [-7.3676, 2.2783, -5.8474]
  - ypr_deg p90: [4.0769, 10.0948, 13.1474]
  - ypr_deg min: [-12.5226, -0.9057, -12.4087]
  - ypr_deg max: [15.5237, 20.6129, 31.0585]

- frame_grab_failed: 0 (rate=0.0000)
## Failure Modes and Fixes
- REJECT_SPIKE triggers when tilt jump exceeds max_tilt_jump_deg or when translation delta exceeds spike_trans_thresh_m (if set). It compares against the last accepted pose and skips spike checks for the first spike_reset_after frames after acceptance.
- Empty outputs usually come from camera lock (another app using the device), frame grab timeouts, or writing debug metrics to the default path. The runner asserts outputs and checks for fallback debug writes.
- Stability improvements: ensure >=3 tags in view, reduce motion blur (more light/shorter exposure), verify calibration matches ROI, and consider relaxing spike thresholds slightly if the rig is stable.

