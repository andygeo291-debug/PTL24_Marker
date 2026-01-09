# Basler Pose Test Summary

- Commit: `3ca63dbbd84827a8d721fd2ec38f05df5525517d`
- Run dir: `/Users/Andreas/Desktop/ptl24_marker/basler_test_runs/basler_run_0008_20260109_111823`

## spike_on
- poses.csv rows: 300
- debug_metrics.csv rows: 300
- Timing stats (ms):
  - t_total_ms: median=89.044 p90=130.338 max=694.092
  - t_detect_ms: median=64.809 p90=92.978 max=657.575
  - t_ransac_ms: median=18.437 p90=33.503 max=216.758
  - mean_reproj_px: median=37.571 p90=37.735 max=39.603
- reject_reason counts:
  - OK: 300
- reject_rate: 0.000
- Drift stats vs first pose:
  - tvec_cam std: [0.1163, 0.0767, 0.1020]
  - tvec_cam p10: [0.2587, -0.1199, 0.0540]
  - tvec_cam p90: [0.4891, 0.0512, 0.2829]
  - tvec_cam min: [-0.0396, -0.1301, -0.2685]
  - tvec_cam max: [0.6474, 0.2496, 0.3266]
  - ypr_deg std: [7.2901, 7.0934, 3.3708]
  - ypr_deg p10: [19.6080, 19.2958, -16.7980]
  - ypr_deg p90: [31.8630, 32.7639, -13.3617]
  - ypr_deg min: [-2.0789, 0.0000, -18.3202]
  - ypr_deg max: [33.5911, 35.7000, 1.0272]

## spike_off
- poses.csv rows: 300
- debug_metrics.csv rows: 300
- Timing stats (ms):
  - t_total_ms: median=94.937 p90=148.985 max=784.096
  - t_detect_ms: median=67.145 p90=109.172 max=694.438
  - t_ransac_ms: median=21.337 p90=35.492 max=206.994
  - mean_reproj_px: median=37.574 p90=37.736 max=37.817
- reject_reason counts:
  - OK: 300
- reject_rate: 0.000
- Drift stats vs first pose:
  - tvec_cam std: [0.0690, 0.0181, 0.0330]
  - tvec_cam p10: [-0.0008, 0.0721, -0.0394]
  - tvec_cam p90: [0.1761, 0.1131, 0.0449]
  - tvec_cam min: [-0.0950, -0.0018, -0.0768]
  - tvec_cam max: [0.2269, 0.1398, 0.0867]
  - ypr_deg std: [2.7141, 3.5432, 0.9194]
  - ypr_deg p10: [0.9321, 5.9488, -1.5833]
  - ypr_deg p90: [8.0357, 15.3535, 0.7138]
  - ypr_deg min: [-3.4391, 0.0000, -3.3522]
  - ypr_deg max: [9.4203, 17.4935, 2.1290]

## Spike ON vs OFF
- reject_rate: on=0.000 off=0.000
- t_total_ms_median: on=89.044 off=94.937
- t_detect_ms_median: on=64.809 off=67.145
- t_ransac_ms_median: on=18.437 off=21.337

## Failure Modes and Fixes
- REJECT_SPIKE triggers when tilt jump exceeds max_tilt_jump_deg or when translation delta exceeds spike_trans_thresh_m (if set). It compares against the last accepted pose and skips spike checks for the first spike_reset_after frames after acceptance.
- Empty outputs usually come from camera lock (another app using the device), frame grab timeouts, or writing debug metrics to the default path. The runner now asserts outputs and checks for fallback debug writes.
- Stability improvements: ensure >=3 tags in view, reduce motion blur (more light/shorter exposure), verify calibration matches ROI, and consider relaxing spike thresholds slightly if the rig is stable.

