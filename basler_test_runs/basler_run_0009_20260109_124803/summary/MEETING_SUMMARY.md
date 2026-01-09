# Basler Pose Test Summary

- Commit: `66bc9f99c256279a4e8f5999aa985c7b0f525c68`
- Run dir: `/Users/Andreas/Desktop/ptl24_marker/basler_test_runs/basler_run_0009_20260109_124803`

## spike_on
- poses.csv rows: 300
- debug_metrics.csv rows: 300
- Timing stats (ms):
  - t_total_ms: median=104.871 p90=160.581 max=961.462
  - t_detect_ms: median=39.757 p90=69.078 max=886.339
  - t_ransac_ms: median=12.221 p90=21.525 max=95.978
  - mean_reproj_px: median=38.661 p90=38.714 max=40.279
- reject_reason counts:
  - OK: 300
- reject_rate: 0.000
- Drift stats vs first pose:
  - tvec_cam std: [0.1033, 0.0587, 0.0861]
  - tvec_cam p10: [-0.1983, 0.1501, -0.2218]
  - tvec_cam p90: [-0.0043, 0.2669, -0.0486]
  - tvec_cam min: [-0.3371, 0.0000, -0.4882]
  - tvec_cam max: [0.3120, 0.4272, 0.0052]
  - ypr_deg std: [7.9856, 3.2735, 5.7673]
  - ypr_deg p10: [-17.6525, -4.7326, 1.3696]
  - ypr_deg p90: [-3.9072, 2.1892, 12.3115]
  - ypr_deg min: [-57.8000, -16.1549, -3.2464]
  - ypr_deg max: [2.0452, 7.1680, 43.7190]

## spike_off
- poses.csv rows: 300
- debug_metrics.csv rows: 300
- Timing stats (ms):
  - t_total_ms: median=114.584 p90=164.550 max=252.137
  - t_detect_ms: median=36.954 p90=55.522 max=122.507
  - t_ransac_ms: median=12.178 p90=14.081 max=54.136
  - mean_reproj_px: median=38.651 p90=38.711 max=40.317
- reject_reason counts:
  - OK: 300
- reject_rate: 0.000
- Drift stats vs first pose:
  - tvec_cam std: [0.1206, 0.0602, 0.0968]
  - tvec_cam p10: [-0.0623, -0.0317, -0.0825]
  - tvec_cam p90: [0.2025, 0.1064, 0.1361]
  - tvec_cam min: [-0.1772, -0.0697, -0.3224]
  - tvec_cam max: [0.5552, 0.2497, 0.1975]
  - ypr_deg std: [8.7404, 4.0629, 6.1130]
  - ypr_deg p10: [18.5808, 6.1960, -28.1808]
  - ypr_deg p90: [34.9430, 15.6427, -17.0097]
  - ypr_deg min: [-10.8258, -2.2827, -31.4881]
  - ypr_deg max: [41.3109, 23.5806, 5.4911]

## Spike ON vs OFF
- reject_rate: on=0.000 off=0.000
- t_total_ms_median: on=104.871 off=114.584
- t_detect_ms_median: on=39.757 off=36.954
- t_ransac_ms_median: on=12.221 off=12.178

## Failure Modes and Fixes
- REJECT_SPIKE triggers when tilt jump exceeds max_tilt_jump_deg or when translation delta exceeds spike_trans_thresh_m (if set). It compares against the last accepted pose and skips spike checks for the first spike_reset_after frames after acceptance.
- Empty outputs usually come from camera lock (another app using the device), frame grab timeouts, or writing debug metrics to the default path. The runner now asserts outputs and checks for fallback debug writes.
- Stability improvements: ensure >=3 tags in view, reduce motion blur (more light/shorter exposure), verify calibration matches ROI, and consider relaxing spike thresholds slightly if the rig is stable.

