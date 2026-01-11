# Basler Pose Test Summary

- Commit: `b1407d1ec89c9ad787726b2df95f40a1c728c68c`
- Run dir: `D:\Electryone\PTL24_Marker\basler_test_runs\basler_run_0019_20260111_195327`

## spike_on
- poses.csv rows: 300
- debug_metrics.csv rows: 300
- effective_fps: 10.02
- Timing stats (ms):
  - t_total_ms: median=99.652 p90=105.840 max=129.104
  - t_detect_ms: median=45.281 p90=53.612 max=73.788
  - t_ransac_ms: median=20.953 p90=23.640 max=48.092
  - mean_reproj_px: median=42.128 p90=42.170 max=42.247
- reject_reason counts:
  - OK: 300
- reject_rate: 0.000
- KPI(100ms): FAIL (median=99.7 p90=105.8)
- Drift stats vs first pose:
  - tvec_cam std: [0.1088, 0.1016, 0.1139]
  - tvec_cam p10: [-0.2165, -0.0066, -0.0644]
  - tvec_cam p90: [0.0204, 0.2393, 0.1883]
  - tvec_cam min: [-0.2286, -0.0708, -0.1450]
  - tvec_cam max: [0.0669, 0.2932, 0.2105]
  - ypr_deg std: [18.7438, 7.1693, 19.3715]
  - ypr_deg p10: [2.2001, 3.1898, 2.7771]
  - ypr_deg p90: [49.2168, 20.8006, 50.3804]
  - ypr_deg min: [-0.7056, 0.0000, -7.5449]
  - ypr_deg max: [76.5668, 21.4165, 80.7275]

- frame_grab_failed: 0 (rate=0.0000)
## spike_off
- poses.csv rows: 300
- debug_metrics.csv rows: 300
- effective_fps: 10.03
- Timing stats (ms):
  - t_total_ms: median=99.437 p90=106.332 max=156.632
  - t_detect_ms: median=45.023 p90=52.303 max=90.542
  - t_ransac_ms: median=21.145 p90=23.393 max=63.913
  - mean_reproj_px: median=42.120 p90=42.159 max=42.543
- reject_reason counts:
  - OK: 300
- reject_rate: 0.000
- KPI(100ms): FAIL (median=99.4 p90=106.3)
- Drift stats vs first pose:
  - tvec_cam std: [0.0692, 0.0646, 0.0730]
  - tvec_cam p10: [-0.1023, -0.0175, -0.0865]
  - tvec_cam p90: [0.0412, 0.1320, 0.0520]
  - tvec_cam min: [-0.2192, -0.0954, -0.1453]
  - tvec_cam max: [0.1062, 0.3030, 0.1988]
  - ypr_deg std: [11.7476, 4.8277, 13.2434]
  - ypr_deg p10: [2.5344, 2.3667, 3.8576]
  - ypr_deg p90: [26.8497, 16.1400, 35.1085]
  - ypr_deg min: [-0.7704, -0.8213, -3.8423]
  - ypr_deg max: [82.4645, 20.8464, 88.9571]

- frame_grab_failed: 0 (rate=0.0000)
## spike_on_tuned
- poses.csv rows: 300
- debug_metrics.csv rows: 300
- effective_fps: 10.03
- Timing stats (ms):
  - t_total_ms: median=99.723 p90=105.711 max=141.709
  - t_detect_ms: median=46.814 p90=56.006 max=77.899
  - t_ransac_ms: median=15.430 p90=18.301 max=35.039
  - mean_reproj_px: median=42.121 p90=42.163 max=42.234
- reject_reason counts:
  - OK: 300
- reject_rate: 0.000
- KPI(100ms): FAIL (median=99.7 p90=105.7)
- Drift stats vs first pose:
  - tvec_cam std: [0.0439, 0.0391, 0.1026]
  - tvec_cam p10: [-0.0005, -0.0878, -0.2593]
  - tvec_cam p90: [0.0867, 0.0033, -0.0262]
  - tvec_cam min: [-0.1150, -0.1775, -0.5324]
  - tvec_cam max: [0.2613, 0.0743, 0.0425]
  - ypr_deg std: [6.8979, 4.2623, 8.2033]
  - ypr_deg p10: [-2.8532, -2.1642, -0.5617]
  - ypr_deg p90: [12.9513, 6.4501, 20.4052]
  - ypr_deg min: [-16.2266, -15.2119, -10.7422]
  - ypr_deg max: [41.6583, 18.6890, 39.2475]

- frame_grab_failed: 0 (rate=0.0000)
## spike_off_tuned
- poses.csv rows: 300
- debug_metrics.csv rows: 300
- effective_fps: 10.03
- Timing stats (ms):
  - t_total_ms: median=99.662 p90=106.810 max=135.400
  - t_detect_ms: median=47.095 p90=58.528 max=79.970
  - t_ransac_ms: median=15.245 p90=18.632 max=27.584
  - mean_reproj_px: median=42.125 p90=42.166 max=42.218
- reject_reason counts:
  - OK: 300
- reject_rate: 0.000
- KPI(100ms): FAIL (median=99.7 p90=106.8)
- Drift stats vs first pose:
  - tvec_cam std: [0.0384, 0.0406, 0.0964]
  - tvec_cam p10: [0.0024, -0.1065, -0.2506]
  - tvec_cam p90: [0.0650, -0.0026, -0.0186]
  - tvec_cam min: [-0.1343, -0.1920, -0.5036]
  - tvec_cam max: [0.2793, 0.0767, 0.1236]
  - ypr_deg std: [8.2961, 4.9772, 8.9240]
  - ypr_deg p10: [-2.8464, -2.3682, 1.2019]
  - ypr_deg p90: [16.8339, 8.6869, 21.7632]
  - ypr_deg min: [-14.3488, -13.0078, -13.1128]
  - ypr_deg max: [42.6117, 21.1634, 40.1246]

- frame_grab_failed: 0 (rate=0.0000)
## Spike ON vs OFF
- reject_rate: on=0.000 off=0.000
- t_total_ms_median: on=99.652 off=99.437
- t_detect_ms_median: on=45.281 off=45.023
- t_ransac_ms_median: on=20.953 off=21.145

## Recommendation
- Use spike_on for long runs (best median/p90 and reject_rate).

## Failure Modes and Fixes
- REJECT_SPIKE triggers when tilt jump exceeds max_tilt_jump_deg or when translation delta exceeds spike_trans_thresh_m (if set). It compares against the last accepted pose and skips spike checks for the first spike_reset_after frames after acceptance.
- Empty outputs usually come from camera lock (another app using the device), frame grab timeouts, or writing debug metrics to the default path. The runner asserts outputs and checks for fallback debug writes.
- Stability improvements: ensure >=3 tags in view, reduce motion blur (more light/shorter exposure), verify calibration matches ROI, and consider relaxing spike thresholds slightly if the rig is stable.

## Stream Diagnosis
- Best stream config: packet=1500 ipd=3500 timeout=1000 fail_rate=0.0000

