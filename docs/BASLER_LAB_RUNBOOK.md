# Basler Lab Runbook (Windows 11)

## 0. Before you start
Close Pylon Viewer before any Python grabs.

Environment:
```powershell
cd D:\Electryone\PTL24_Marker
.\.venv\Scripts\python --version
```

### DO NOT
- Do NOT leave Pylon Viewer open.
- Do NOT change ROI (width/height/offset) without re-calibrating.
- Do NOT use packet-size 9000 (caused drops). Default is 8192; fall back to 1500 if needed.

Known-good Basler settings (use these):
- serial=21601161, name=StaticCam
- PixelFormat=Mono8
- ROI: 960x720, offset-x=320, offset-y=200
- fps=30 (AcquisitionFrameRateAbs is used if needed)
- exposure-us=15000, gain=0
- packet-size=8192, interpacket-delay=3500
- stream-buffer-count=64, timeout-ms=2000

## 1. Quick health check
Link health grab (120 frames):
```powershell
.\.venv\Scripts\python -m common.camera.test_basler_grab `
  --serial 21601161 --name StaticCam `
  --pixel-format Mono8 --width 960 --height 720 --fps 30 `
  --offset-x 320 --offset-y 200 `
  --exposure-us 15000 --gain 0 `
  --packet-size 8192 --interpacket-delay 3500 `
  --stream-buffer-count 64 --timeout-ms 2000 `
  --frames 120
```
If you see any Frame grab failed, fall back to packet-size 1500 (MTU-safe) and keep ipd=3500.
Good indicators:
- `grabbed 120/120 failed=0`
- `Readback settings` includes `AcquisitionFrameRateAbs` and `ResultingFrameRateAbs` ~ 30

## 2. HUD check (must pass)
Run HUD first, then confirm you see >=5 tags most of the time.
```powershell
.\.venv\Scripts\python -m phase_b.v2.phase_b_tags_v2 `
  --camera-backend basler `
  --basler-serial 21601161 --basler-name StaticCam `
  --width 960 --height 720 --fps 30 `
  --basler-pixel-format Mono8 --basler-exposure-us 15000 --basler-gain 0 `
  --basler-offset-x 320 --basler-offset-y 200 `
  --basler-packet-size 8192 --basler-interpacket-delay 3500 `
  --basler-timeout-ms 2000 --basler-stream-buffer-count 64 `
  --rig phase_b\rigs\cyl_dotec.yaml `
  --camera common\calib\basler_lab_960x720_offx320_offy200_mono8_11mm.yaml `
  --ransac --adapt --ransac-iters 15 `
  --quiet-apriltag-stderr `
  --hud `
  --frames 900 `
  --save-poses basler_test_runs\hud_check\poses.csv `
  --debug-metrics-out basler_test_runs\hud_check\debug_metrics.csv
```
If you do NOT see >=5 tags consistently: move the camera higher/closer and retry.
Save a HUD screenshot for the report.

## 3. Report runs
Short run (300 frames, spike_off only):
```powershell
.\.venv\Scripts\python tools\run_basler_pose_tests.py `
  --serial 21601161 --name StaticCam `
  --calib common\calib\basler_lab_960x720_offx320_offy200_mono8_11mm.yaml `
  --width 960 --height 720 --fps 30 `
  --pixel-format Mono8 --exposure-us 15000 --gain 0 `
  --offset-x 320 --offset-y 200 `
  --packet-size 8192 --interpacket-delay 3500 `
  --timeout-ms 2000 --stream-buffer-count 64 `
  --spike-frames 300 --only spike_off --no-diagnose
```

Long run (900 frames, spike_off only):
```powershell
.\.venv\Scripts\python tools\run_basler_pose_tests.py `
  --serial 21601161 --name StaticCam `
  --calib common\calib\basler_lab_960x720_offx320_offy200_mono8_11mm.yaml `
  --width 960 --height 720 --fps 30 `
  --pixel-format Mono8 --exposure-us 15000 --gain 0 `
  --offset-x 320 --offset-y 200 `
  --packet-size 8192 --interpacket-delay 3500 `
  --timeout-ms 2000 --stream-buffer-count 64 `
  --spike-frames 900 --only spike_off --no-diagnose
```
Good indicators:
- KPI PASS (median/p90 < 100 ms)
- frame_grab_failed rate = 0

## 4. Stability metrics
Set RUN_DIR to the latest run:
```powershell
$RUN_DIR = (Get-ChildItem basler_test_runs -Directory | Sort-Object LastWriteTime -Descending | Select-Object -First 1).FullName
```

Compute stability metrics:
```powershell
.\.venv\Scripts\python tools\pose_stability.py --run-dir $RUN_DIR --mode spike_off
```

Frame grab failed count (one-liner):
```powershell
(Select-String -Path "$RUN_DIR\terminal.log" -Pattern "Frame grab failed").Count
```

Last 3 bench lines:
```powershell
Select-String -Path "$RUN_DIR\terminal.log" -Pattern "\[bench\]" | Select-Object -Last 3
```

## 5. What to save
What to paste into ChatGPT / report:
- `summary\MEETING_SUMMARY.md`
- last 3 `[bench]` lines from `terminal.log`
- stability output from `tools\pose_stability.py`
- HUD screenshot showing >=5 tags

Artifacts to keep:
- `basler_test_runs\<run>\summary\MEETING_SUMMARY.md`
- `basler_test_runs\<run>\summary\meeting_table.csv`
- `basler_test_runs\<run>\summary\basler_stream_best.json`
- `basler_test_runs\<run>\terminal.log`
- `basler_test_runs\<run>\spike_off\poses.csv`
- `basler_test_runs\<run>\spike_off\debug_metrics.csv`

## 6. Troubleshooting
- Frame grab failed: check cable/switch, ensure MTU 1500, close Pylon Viewer, increase timeout to 2000.
- Drops persist: lower fps to 15, verify packet-size 8192, keep interpacket-delay 3500 (fallback 1500).
- ROI changed: recalibrate intrinsics.

## Done checklist
- [ ] HUD check passed (>=5 tags visible)
- [ ] Short run KPI PASS (<100 ms median/p90)
- [ ] Long run KPI PASS (<100 ms median/p90)
- [ ] frame_grab_failed rate = 0
- [ ] Stability metrics captured
- [ ] MEETING_SUMMARY.md saved
- [ ] HUD screenshot saved
