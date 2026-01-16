# Supervisor Runbook (Phase B v2)

One-page copy/paste commands for Basler + Phase B v2. Keep camera + rig unchanged.

## 0) Before you start
- Close Pylon Viewer (it locks the Basler camera).
- Use the correct calibration YAML for this ROI.
- Outputs go under `basler_test_runs/...` (poses, debug metrics, summaries).

## 1) Basler quick check (10-30 frames)
PowerShell:
```powershell
Set-Location "D:\Electryone\PTL24_Marker"
. .\.venv\Scripts\Activate.ps1

.\.venv\Scripts\python -m common.camera.test_basler_grab `
  --serial 21601161 --name StaticCam `
  --pixel-format Mono8 --width 960 --height 720 --fps 30 `
  --offset-x 320 --offset-y 200 `
  --exposure-us 15000 --gain 0 `
  --packet-size 8192 --interpacket-delay 3500 `
  --stream-buffer-count 64 --timeout-ms 2000 `
  --frames 20
```

macOS (bash):
```bash
cd ~/path/to/ptl24_marker
source venv/bin/activate
python -m common.camera.test_basler_grab \
  --serial 21601161 --name StaticCam \
  --pixel-format Mono8 --width 960 --height 720 --fps 30 \
  --offset-x 320 --offset-y 200 \
  --exposure-us 15000 --gain 0 \
  --packet-size 8192 --interpacket-delay 3500 \
  --stream-buffer-count 64 --timeout-ms 2000 \
  --frames 20
```

## 2) Full Basler suite (auto summary)
PowerShell:
```powershell
.\.venv\Scripts\python tools\run_basler_pose_tests.py `
  --serial 21601161 --name StaticCam `
  --calib common\calib\basler_lab_960x720_offx320_offy200_mono8_11mm.yaml `
  --width 960 --height 720 --fps 30 `
  --pixel-format Mono8 --exposure-us 15000 --gain 0 `
  --offset-x 320 --offset-y 200 `
  --packet-size 8192 --interpacket-delay 3500 `
  --timeout-ms 2000 --stream-buffer-count 64
```

macOS (bash):
```bash
python tools/run_basler_pose_tests.py \
  --serial 21601161 --name StaticCam \
  --calib common/calib/basler_lab_960x720_offx320_offy200_mono8_11mm.yaml \
  --width 960 --height 720 --fps 30 \
  --pixel-format Mono8 --exposure-us 15000 --gain 0 \
  --offset-x 320 --offset-y 200 \
  --packet-size 8192 --interpacket-delay 3500 \
  --timeout-ms 2000 --stream-buffer-count 64
```

Outputs:
- `basler_test_runs/<run>/summary/MEETING_SUMMARY.md`
- `basler_test_runs/<run>/summary/meeting_table.csv`
- `basler_test_runs/<run>/spike_off/poses.csv`
- `basler_test_runs/<run>/spike_off/debug_metrics.csv`

## 3) Intrinsics capture + calibrate + validate (9x6, 0.025 m)
PowerShell:
```powershell
$runBase = "common\calib_images"
.\.venv\Scripts\python tools\capture_basler_calib_images.py `
  --serial 21601161 --name StaticCam `
  --pixel-format Mono8 --width 960 --height 720 --offset-x 320 --offset-y 200 --fps 10 `
  --exposure-us 15000 --gain 0 `
  --packet-size 8192 --interpacket-delay 3500 --stream-buffer-count 64 --timeout-ms 2000 `
  --board-cols 9 --board-rows 6 --square-size-m 0.025 `
  --num-images 60 --run-base $runBase --lens-zoom-mm 11

$run = Get-ChildItem $runBase -Directory | Sort-Object LastWriteTime -Descending | Select-Object -First 1
$images = Join-Path $run.FullName "images"
$calib = "common\calib\basler_lab_960x720_offx320_offy200_mono8_11mm_$(Get-Date -Format yyyyMMdd).yaml"

.\.venv\Scripts\python tools\calibrate_intrinsics_from_images.py `
  --images-dir $images --cols 9 --rows 6 --square-size-m 0.025 --out-yaml $calib

.\.venv\Scripts\python tools\validate_calib.py `
  --calib $calib --images-dir $images --cols 9 --rows 6 --square-size-m 0.025
```

macOS (bash):
```bash
run_base="common/calib_images"
python tools/capture_basler_calib_images.py \
  --serial 21601161 --name StaticCam \
  --pixel-format Mono8 --width 960 --height 720 --offset-x 320 --offset-y 200 --fps 10 \
  --exposure-us 15000 --gain 0 \
  --packet-size 8192 --interpacket-delay 3500 --stream-buffer-count 64 --timeout-ms 2000 \
  --board-cols 9 --board-rows 6 --square-size-m 0.025 \
  --num-images 60 --run-base "$run_base" --lens-zoom-mm 11

run_dir="$(ls -td ${run_base}/* | head -1)"
images="${run_dir}/images"
calib="common/calib/basler_lab_960x720_offx320_offy200_mono8_11mm_$(date +%Y%m%d).yaml"

python tools/calibrate_intrinsics_from_images.py \
  --images-dir "$images" --cols 9 --rows 6 --square-size-m 0.025 --out-yaml "$calib"

python tools/validate_calib.py \
  --calib "$calib" --images-dir "$images" --cols 9 --rows 6 --square-size-m 0.025
```

## 4) Long run example (900 frames, spike_off)
PowerShell:
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

macOS (bash):
```bash
python tools/run_basler_pose_tests.py \
  --serial 21601161 --name StaticCam \
  --calib common/calib/basler_lab_960x720_offx320_offy200_mono8_11mm.yaml \
  --width 960 --height 720 --fps 30 \
  --pixel-format Mono8 --exposure-us 15000 --gain 0 \
  --offset-x 320 --offset-y 200 \
  --packet-size 8192 --interpacket-delay 3500 \
  --timeout-ms 2000 --stream-buffer-count 64 \
  --spike-frames 900 --only spike_off --no-diagnose
```

## Common failure fixes
- Camera locked: close Pylon Viewer, then retry.
- Drops: keep packet size 8192 with ipd=3500; if drops persist, fall back to 1500.
- Link issues: check NIC link speed, cable, and 169.254.x.x address.
- Timeouts: increase `--timeout-ms` to 2000.
