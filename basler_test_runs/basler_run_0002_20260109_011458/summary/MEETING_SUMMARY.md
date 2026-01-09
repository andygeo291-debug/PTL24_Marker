# Basler Pose Test Summary

- Commit: `d80b65590270b31de7066cdde4710352a0a33698`
- Run dir: `/Users/Andreas/Desktop/ptl24_marker/basler_test_runs/basler_run_0002_20260109_011458`

## spike_on
- poses.csv rows: 300
- debug_metrics.csv rows: 300
- Timing stats (ms):
  - t_total_ms: median=66.827 p90=83.375 max=340.017
  - t_detect_ms: median=39.776 p90=56.843 max=149.173
  - t_ransac_ms: median=14.266 p90=21.399 max=43.296
  - mean_reproj_px: median=37.831 p90=38.040 max=38.332
- reject_reason counts:
  - OK: 158
  - REJECT_SPIKE: 75
  - HOLD_PREV_POSE: 67
- Drift stats vs first pose:
  - tvec_cam std: [0.0152, 0.0061, 0.0100]
  - tvec_cam p10: [-0.1214, 0.0354, -0.0552]
  - tvec_cam p90: [-0.1095, 0.0420, -0.0427]
  - tvec_cam min: [-0.1437, 0.0000, -0.0579]
  - tvec_cam max: [0.0000, 0.0551, 0.0280]
  - ypr_deg std: [1.6193, 0.6275, 1.5786]
  - ypr_deg p10: [-4.4413, 2.2723, 3.9508]
  - ypr_deg p90: [-2.6496, 3.0168, 6.2281]
  - ypr_deg min: [-5.2129, 0.0000, -7.5591]
  - ypr_deg max: [11.5420, 8.5199, 6.8152]

## spike_off
- poses.csv rows: 300
- debug_metrics.csv rows: 300
- Timing stats (ms):
  - t_total_ms: median=70.049 p90=114.693 max=399.311
  - t_detect_ms: median=47.853 p90=77.733 max=335.726
  - t_ransac_ms: median=15.268 p90=28.745 max=135.557
  - mean_reproj_px: median=37.825 p90=38.042 max=38.353
- reject_reason counts:
  - OK: 234
  - HOLD_PREV_POSE: 66
- Drift stats vs first pose:
  - tvec_cam std: [0.0218, 0.0083, 0.0113]
  - tvec_cam p10: [0.0168, 0.0133, 0.0097]
  - tvec_cam p90: [0.0743, 0.0316, 0.0353]
  - tvec_cam min: [-0.0114, -0.0117, -0.0108]
  - tvec_cam max: [0.0859, 0.0400, 0.0592]
  - ypr_deg std: [2.4084, 3.1432, 0.8689]
  - ypr_deg p10: [4.7097, 9.3304, -2.4235]
  - ypr_deg p90: [11.0170, 17.4525, -0.5454]
  - ypr_deg min: [0.0000, 0.0000, -5.6860]
  - ypr_deg max: [12.7265, 18.0998, 0.6924]

