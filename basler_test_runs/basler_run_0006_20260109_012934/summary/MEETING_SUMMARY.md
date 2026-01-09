# Basler Pose Test Summary

- Commit: `d80b65590270b31de7066cdde4710352a0a33698`
- Run dir: `/Users/Andreas/Desktop/ptl24_marker/basler_test_runs/basler_run_0006_20260109_012934`

## spike_on
- poses.csv rows: 299
- debug_metrics.csv rows: 300
- Timing stats (ms):
  - t_total_ms: median=66.703 p90=92.369 max=300.514
  - t_detect_ms: median=41.801 p90=65.101 max=223.508
  - t_ransac_ms: median=14.878 p90=23.271 max=70.269
  - mean_reproj_px: median=37.825 p90=37.908 max=39.283
- reject_reason counts:
  - OK: 206
  - HOLD_PREV_POSE: 93
  - NO_POSE: 1
- reject_rate: 0.003
- Drift stats vs first pose:
  - tvec_cam std: [0.0525, 0.0611, 0.0608]
  - tvec_cam p10: [0.3770, -0.4088, 0.3690]
  - tvec_cam p90: [0.4265, -0.3673, 0.4071]
  - tvec_cam min: [0.0000, -0.4340, 0.0000]
  - tvec_cam max: [0.4502, 0.0000, 0.4306]
  - ypr_deg std: [35.8696, 5.8729, 4.0893]
  - ypr_deg p10: [305.5661, 41.0831, -22.8829]
  - ypr_deg p90: [310.5368, 43.8267, -19.0175]
  - ypr_deg min: [0.0000, 0.0000, -25.9230]
  - ypr_deg max: [346.0479, 46.1411, 0.4559]

## spike_off
- poses.csv rows: 300
- debug_metrics.csv rows: 300
- Timing stats (ms):
  - t_total_ms: median=67.519 p90=93.734 max=379.728
  - t_detect_ms: median=46.186 p90=63.575 max=200.027
  - t_ransac_ms: median=14.673 p90=22.992 max=123.994
  - mean_reproj_px: median=37.822 p90=37.995 max=38.124
- reject_reason counts:
  - OK: 207
  - HOLD_PREV_POSE: 93
- reject_rate: 0.000
- Drift stats vs first pose:
  - tvec_cam std: [0.0266, 0.0179, 0.0218]
  - tvec_cam p10: [-0.1503, 0.0086, -0.0460]
  - tvec_cam p90: [-0.0912, 0.0561, 0.0093]
  - tvec_cam min: [-0.1890, -0.0109, -0.0544]
  - tvec_cam max: [0.0000, 0.0836, 0.0514]
  - ypr_deg std: [4.0264, 2.1108, 3.2337]
  - ypr_deg p10: [-4.1474, 2.2144, -4.3117]
  - ypr_deg p90: [6.3375, 7.6538, 4.2371]
  - ypr_deg min: [-7.1689, 0.0000, -9.4918]
  - ypr_deg max: [12.8413, 11.2539, 5.3215]

## Spike ON vs OFF
- reject_rate: on=0.003 off=0.000
- t_total_ms_median: on=66.703 off=67.519
- t_detect_ms_median: on=41.801 off=46.186
- t_ransac_ms_median: on=14.878 off=14.673

## Failure Modes and Fixes
- REJECT_SPIKE triggers when tilt jump exceeds max_tilt_jump_deg or when translation delta exceeds spike_trans_thresh_m (if set). It compares against the last accepted pose and skips spike checks for the first spike_reset_after frames after acceptance.
- Empty outputs usually come from camera lock (another app using the device), frame grab timeouts, or writing debug metrics to the default path. The runner now asserts outputs and checks for fallback debug writes.
- Stability improvements: ensure >=3 tags in view, reduce motion blur (more light/shorter exposure), verify calibration matches ROI, and consider relaxing spike thresholds slightly if the rig is stable.

