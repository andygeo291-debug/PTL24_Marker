# Basler Pose Test Summary

- Commit: `fd10e0e29fd0ebf90c1cdcff4ab024fdf0547711`
- Run dir: `D:\Electryone\PTL24_Marker\basler_test_runs\basler_run_0022_20260112_173044`

## spike_off
- poses.csv rows: 900
- debug_metrics.csv rows: 900
- effective_fps: 13.47
- Timing stats (ms):
  - t_total_ms: median=71.228 p90=80.840 max=196.604
  - t_detect_ms: median=46.172 p90=52.861 max=113.956
  - t_ransac_ms: median=22.684 p90=25.252 max=50.477
  - mean_reproj_px: median=29.003 p90=29.657 max=29.886
- reject_reason counts:
  - OK: 897
  - HOLD_PREV_POSE: 3
- reject_rate: 0.000
- KPI(100ms): PASS (median=71.2 p90=80.8)
- Drift stats vs first pose:
  - tvec_cam std: [0.0806, 0.0562, 0.0679]
  - tvec_cam p10: [-0.1866, -0.1609, 0.0141]
  - tvec_cam p90: [0.0040, -0.0264, 0.1789]
  - tvec_cam min: [-0.3967, -0.3351, 0.0000]
  - tvec_cam max: [0.0184, 0.0160, 0.3575]
  - ypr_deg std: [7.2888, 2.1237, 6.2172]
  - ypr_deg p10: [-43.5127, -8.2579, -45.6283]
  - ypr_deg p90: [-26.3202, -2.5789, -31.0889]
  - ypr_deg min: [-47.7616, -9.4341, -49.0566]
  - ypr_deg max: [0.0000, 0.3561, 0.0000]

- frame_grab_failed: 0 (rate=0.0000)
## Failure Modes and Fixes
- REJECT_SPIKE triggers when tilt jump exceeds max_tilt_jump_deg or when translation delta exceeds spike_trans_thresh_m (if set). It compares against the last accepted pose and skips spike checks for the first spike_reset_after frames after acceptance.
- Empty outputs usually come from camera lock (another app using the device), frame grab timeouts, or writing debug metrics to the default path. The runner asserts outputs and checks for fallback debug writes.
- Stability improvements: ensure >=3 tags in view, reduce motion blur (more light/shorter exposure), verify calibration matches ROI, and consider relaxing spike thresholds slightly if the rig is stable.

## Stream Diagnosis
- Best stream config: packet=1500 ipd=3500 timeout=1000 fail_rate=0.0000

