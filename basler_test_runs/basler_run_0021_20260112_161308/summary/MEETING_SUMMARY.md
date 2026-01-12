# Basler Pose Test Summary

- Commit: `fd10e0e29fd0ebf90c1cdcff4ab024fdf0547711`
- Run dir: `D:\Electryone\PTL24_Marker\basler_test_runs\basler_run_0021_20260112_161308`

## spike_on
- poses.csv rows: 300
- debug_metrics.csv rows: 300
- effective_fps: 13.85
- Timing stats (ms):
  - t_total_ms: median=70.691 p90=80.454 max=118.905
  - t_detect_ms: median=47.543 p90=53.807 max=80.219
  - t_ransac_ms: median=20.152 p90=24.835 max=35.571
  - mean_reproj_px: median=29.005 p90=29.169 max=29.983
- reject_reason counts:
  - OK: 300
- reject_rate: 0.000
- KPI(100ms): PASS (median=70.7 p90=80.5)
- Drift stats vs first pose:
  - tvec_cam std: [0.0405, 0.0452, 0.0350]
  - tvec_cam p10: [-0.0691, -0.1424, 0.0043]
  - tvec_cam p90: [0.0013, -0.0181, 0.0660]
  - tvec_cam min: [-0.2148, -0.2124, -0.0039]
  - tvec_cam max: [0.0041, 0.0199, 0.1942]
  - ypr_deg std: [6.8502, 2.0289, 7.7263]
  - ypr_deg p10: [-4.2292, 0.8205, 3.5258]
  - ypr_deg p90: [12.5635, 6.1303, 22.5764]
  - ypr_deg min: [-8.5692, 0.0000, 0.0000]
  - ypr_deg max: [30.9254, 9.0956, 38.8042]

- frame_grab_failed: 0 (rate=0.0000)
## spike_off
- poses.csv rows: 300
- debug_metrics.csv rows: 300
- effective_fps: 14.20
- Timing stats (ms):
  - t_total_ms: median=69.168 p90=75.514 max=105.700
  - t_detect_ms: median=46.437 p90=51.188 max=76.779
  - t_ransac_ms: median=20.155 p90=24.091 max=29.671
  - mean_reproj_px: median=28.999 p90=29.153 max=29.900
- reject_reason counts:
  - OK: 300
- reject_rate: 0.000
- KPI(100ms): PASS (median=69.2 p90=75.5)
- Drift stats vs first pose:
  - tvec_cam std: [0.0541, 0.0398, 0.0443]
  - tvec_cam p10: [-0.1136, -0.1219, 0.0030]
  - tvec_cam p90: [-0.0015, -0.0263, 0.0838]
  - tvec_cam min: [-0.3065, -0.2077, -0.0023]
  - tvec_cam max: [0.0011, 0.0169, 0.2764]
  - ypr_deg std: [5.2034, 1.6975, 5.9420]
  - ypr_deg p10: [-3.9564, -0.1500, 2.7292]
  - ypr_deg p90: [9.2171, 4.1515, 16.9840]
  - ypr_deg min: [-8.1712, -0.6104, 0.0000]
  - ypr_deg max: [20.7228, 7.4248, 35.2405]

- frame_grab_failed: 0 (rate=0.0000)
## Spike ON vs OFF
- reject_rate: on=0.000 off=0.000
- t_total_ms_median: on=70.691 off=69.168
- t_detect_ms_median: on=47.543 off=46.437
- t_ransac_ms_median: on=20.152 off=20.155

## Recommendation
- Use spike_off for long runs (best median/p90 and reject_rate).

## Failure Modes and Fixes
- REJECT_SPIKE triggers when tilt jump exceeds max_tilt_jump_deg or when translation delta exceeds spike_trans_thresh_m (if set). It compares against the last accepted pose and skips spike checks for the first spike_reset_after frames after acceptance.
- Empty outputs usually come from camera lock (another app using the device), frame grab timeouts, or writing debug metrics to the default path. The runner asserts outputs and checks for fallback debug writes.
- Stability improvements: ensure >=3 tags in view, reduce motion blur (more light/shorter exposure), verify calibration matches ROI, and consider relaxing spike thresholds slightly if the rig is stable.

## Stream Diagnosis
- Best stream config: packet=1500 ipd=3500 timeout=1000 fail_rate=0.0000

