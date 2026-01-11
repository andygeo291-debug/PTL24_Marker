# Basler Pose Test Summary

- Commit: `37fb15ecfe20e02b4f38ff11fa5fabc0dc11e185`
- Run dir: `D:\Electryone\PTL24_Marker\basler_test_runs\basler_run_0020_20260111_231833`

## spike_on
- poses.csv rows: 300
- debug_metrics.csv rows: 300
- effective_fps: 12.31
- Timing stats (ms):
  - t_total_ms: median=78.291 p90=95.651 max=160.608
  - t_detect_ms: median=51.370 p90=64.112 max=108.891
  - t_ransac_ms: median=23.515 p90=30.637 max=76.527
  - mean_reproj_px: median=42.532 p90=42.570 max=42.595
- reject_reason counts:
  - OK: 300
- reject_rate: 0.000
- KPI(100ms): PASS (median=78.3 p90=95.7)
- Drift stats vs first pose:
  - tvec_cam std: [0.0049, 0.0369, 0.0168]
  - tvec_cam p10: [-0.0000, -0.0734, -0.0885]
  - tvec_cam p90: [0.0119, 0.0212, -0.0481]
  - tvec_cam min: [-0.0086, -0.1388, -0.1094]
  - tvec_cam max: [0.0241, 0.0595, 0.0000]
  - ypr_deg std: [7.0953, 3.1760, 6.4004]
  - ypr_deg p10: [-13.2108, -5.0230, -16.1937]
  - ypr_deg p90: [4.6622, 2.9588, -0.6946]
  - ypr_deg min: [-28.1113, -14.2319, -31.8838]
  - ypr_deg max: [15.9475, 5.5565, 1.9577]

- frame_grab_failed: 0 (rate=0.0000)
## spike_off
- poses.csv rows: 300
- debug_metrics.csv rows: 300
- effective_fps: 12.98
- Timing stats (ms):
  - t_total_ms: median=74.465 p90=90.473 max=158.027
  - t_detect_ms: median=46.406 p90=56.978 max=112.228
  - t_ransac_ms: median=24.945 p90=29.466 max=52.240
  - mean_reproj_px: median=42.532 p90=42.575 max=42.616
- reject_reason counts:
  - OK: 300
- reject_rate: 0.000
- KPI(100ms): PASS (median=74.5 p90=90.5)
- Drift stats vs first pose:
  - tvec_cam std: [0.0058, 0.0378, 0.0158]
  - tvec_cam p10: [-0.0135, 0.0362, -0.0004]
  - tvec_cam p90: [-0.0005, 0.1338, 0.0368]
  - tvec_cam min: [-0.0230, -0.0189, -0.0312]
  - tvec_cam max: [0.0267, 0.1649, 0.0532]
  - ypr_deg std: [7.3083, 3.3942, 6.6925]
  - ypr_deg p10: [-31.8185, 14.8607, -14.3271]
  - ypr_deg p90: [-15.2449, 22.9493, -1.0085]
  - ypr_deg min: [-57.9839, 0.0000, -45.6880]
  - ypr_deg max: [0.0000, 26.8511, 0.7474]

- frame_grab_failed: 0 (rate=0.0000)
## Spike ON vs OFF
- reject_rate: on=0.000 off=0.000
- t_total_ms_median: on=78.291 off=74.465
- t_detect_ms_median: on=51.370 off=46.406
- t_ransac_ms_median: on=23.515 off=24.945

## Recommendation
- Use spike_off for long runs (best median/p90 and reject_rate).

## Failure Modes and Fixes
- REJECT_SPIKE triggers when tilt jump exceeds max_tilt_jump_deg or when translation delta exceeds spike_trans_thresh_m (if set). It compares against the last accepted pose and skips spike checks for the first spike_reset_after frames after acceptance.
- Empty outputs usually come from camera lock (another app using the device), frame grab timeouts, or writing debug metrics to the default path. The runner asserts outputs and checks for fallback debug writes.
- Stability improvements: ensure >=3 tags in view, reduce motion blur (more light/shorter exposure), verify calibration matches ROI, and consider relaxing spike thresholds slightly if the rig is stable.

## Stream Diagnosis
- Best stream config: packet=1500 ipd=3500 timeout=1000 fail_rate=0.0000

