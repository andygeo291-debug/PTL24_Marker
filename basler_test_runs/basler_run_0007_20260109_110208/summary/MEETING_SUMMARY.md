# Basler Pose Test Summary

- Commit: `d9329d014fe6e05441f87a8af47116241c951f62`
- Run dir: `/Users/Andreas/Desktop/ptl24_marker/basler_test_runs/basler_run_0007_20260109_110208`

## spike_on
- poses.csv rows: 300
- debug_metrics.csv rows: 300
- Timing stats (ms):
  - t_total_ms: median=67.103 p90=85.629 max=231.647
  - t_detect_ms: median=45.148 p90=62.125 max=199.443
  - t_ransac_ms: median=14.520 p90=19.690 max=50.238
  - mean_reproj_px: median=38.004 p90=38.045 max=38.195
- reject_reason counts:
  - OK: 198
  - HOLD_PREV_POSE: 102
- reject_rate: 0.000
- Drift stats vs first pose:
  - tvec_cam std: [0.0214, 0.0087, 0.0088]
  - tvec_cam p10: [-0.1342, 0.0289, -0.0517]
  - tvec_cam p90: [-0.1061, 0.0447, -0.0382]
  - tvec_cam min: [-0.1511, 0.0000, -0.0548]
  - tvec_cam max: [0.0000, 0.0574, 0.0000]
  - ypr_deg std: [1.2464, 0.6049, 1.1092]
  - ypr_deg p10: [-5.4696, 1.8713, 3.8855]
  - ypr_deg p90: [-3.4794, 2.6964, 5.8474]
  - ypr_deg min: [-6.8373, -0.0863, -0.6623]
  - ypr_deg max: [4.7037, 6.3193, 6.2480]

## spike_off
- poses.csv rows: 300
- debug_metrics.csv rows: 300
- Timing stats (ms):
  - t_total_ms: median=68.931 p90=101.172 max=289.206
  - t_detect_ms: median=50.300 p90=72.185 max=200.727
  - t_ransac_ms: median=14.931 p90=22.313 max=114.940
  - mean_reproj_px: median=38.007 p90=38.050 max=38.210
- reject_reason counts:
  - OK: 223
  - HOLD_PREV_POSE: 77
- reject_rate: 0.000
- Drift stats vs first pose:
  - tvec_cam std: [0.0143, 0.0070, 0.0079]
  - tvec_cam p10: [-0.1268, 0.0358, -0.0547]
  - tvec_cam p90: [-0.1118, 0.0448, -0.0407]
  - tvec_cam min: [-0.1589, 0.0000, -0.0572]
  - tvec_cam max: [0.0000, 0.0656, 0.0000]
  - ypr_deg std: [1.0914, 0.7556, 1.0087]
  - ypr_deg p10: [-5.5596, 1.8850, 4.3544]
  - ypr_deg p90: [-4.2702, 2.6701, 6.1421]
  - ypr_deg min: [-7.6069, -0.0205, -0.4656]
  - ypr_deg max: [4.1735, 6.5876, 6.4226]

## Spike ON vs OFF
- reject_rate: on=0.000 off=0.000
- t_total_ms_median: on=67.103 off=68.931
- t_detect_ms_median: on=45.148 off=50.300
- t_ransac_ms_median: on=14.520 off=14.931

## Failure Modes and Fixes
- REJECT_SPIKE triggers when tilt jump exceeds max_tilt_jump_deg or when translation delta exceeds spike_trans_thresh_m (if set). It compares against the last accepted pose and skips spike checks for the first spike_reset_after frames after acceptance.
- Empty outputs usually come from camera lock (another app using the device), frame grab timeouts, or writing debug metrics to the default path. The runner now asserts outputs and checks for fallback debug writes.
- Stability improvements: ensure >=3 tags in view, reduce motion blur (more light/shorter exposure), verify calibration matches ROI, and consider relaxing spike thresholds slightly if the rig is stable.

