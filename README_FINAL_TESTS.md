# README FINAL TESTS (Basler, Windows)

## 1) Intrinsics calibration (Basler, chessboard 9x6, 0.025m, 11mm)
Close Pylon Viewer before any Python grabs.

### 1.1 Create images folder
```powershell
$runBase = "common\calib_images"
New-Item -ItemType Directory -Force $runBase | Out-Null
```

### 1.2 Capture 60 images (live preview, SPACE to save)
```powershell
$SER="21601161"
$NAME="StaticCam"
$W=960; $H=720; $OX=320; $OY=200
$EXP=15000; $GAIN=0
$PKT=8192; $IPD=3500; $BUF=64; $TO=2000

.\.venv\Scripts\python tools\capture_basler_calib_images.py `
  --serial $SER --name $NAME `
  --pixel-format Mono8 --width $W --height $H --offset-x $OX --offset-y $OY --fps 10 `
  --exposure-us $EXP --gain $GAIN `
  --packet-size $PKT --interpacket-delay $IPD --stream-buffer-count $BUF --timeout-ms $TO `
  --board-cols 9 --board-rows 6 --square-size-m 0.025 `
  --num-images 60 --run-base $runBase `
  --lens-zoom-mm 11
```
Expected output:
- `common\calib_images\basler_intrinsics_####_YYYYMMDD_HHMMSS\images\img_0001.png` … `img_0060.png`
- `calib_meta.json`

### 1.3 Calibrate intrinsics -> YAML
```powershell
$run = Get-ChildItem $runBase -Directory | Sort-Object LastWriteTime -Descending | Select-Object -First 1
$images = Join-Path $run.FullName "images"
$calib = "common\calib\basler_lab_${W}x${H}_offx${OX}_offy${OY}_mono8_11mm_$(Get-Date -Format yyyyMMdd).yaml"

.\.venv\Scripts\python tools\calibrate_intrinsics_from_images.py `
  --images-dir $images `
  --cols 9 --rows 6 --square-size-m 0.025 `
  --out-yaml $calib
```
Expected output:
- `Calibration complete`
- `Wrote common\calib\basler_lab_960x720_offx320_offy200_mono8_11mm_YYYYMMDD.yaml`

### 1.4 Validate calibration (RMS reprojection error)
```powershell
.\.venv\Scripts\python tools\validate_calib.py `
  --calib $calib `
  --images-dir $images `
  --cols 9 --rows 6 --square-size-m 0.025
```
Expected output:
- `RMS reprojection error (px): ...`

## 2) FINAL TESTS (golden settings)
### 2.1 Basler grab smoke test
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
Expected output:
- `grabbed 120/120 failed=0`
- `Readback settings` shows `AcquisitionFrameRateAbs` and `ResultingFrameRateAbs` ~ 30

### 2.2 Short pose test (spike_off, 300 frames)
```powershell
.\.venv\Scripts\python tools\run_basler_pose_tests.py `
  --serial 21601161 --name StaticCam `
  --calib $calib `
  --width 960 --height 720 --fps 30 `
  --pixel-format Mono8 --exposure-us 15000 --gain 0 `
  --offset-x 320 --offset-y 200 `
  --packet-size 8192 --interpacket-delay 3500 `
  --timeout-ms 2000 --stream-buffer-count 64 `
  --spike-frames 300 --only spike_off --no-diagnose
```
Expected output:
- `summary\MEETING_SUMMARY.md`
- `summary\meeting_table.csv`

### 2.3 Long pose test (spike_off, 900 frames)
```powershell
.\.venv\Scripts\python tools\run_basler_pose_tests.py `
  --serial 21601161 --name StaticCam `
  --calib $calib `
  --width 960 --height 720 --fps 30 `
  --pixel-format Mono8 --exposure-us 15000 --gain 0 `
  --offset-x 320 --offset-y 200 `
  --packet-size 8192 --interpacket-delay 3500 `
  --timeout-ms 2000 --stream-buffer-count 64 `
  --spike-frames 900 --only spike_off --no-diagnose
```
Optional: change `--spike-frames 900` to `1800`.

### 2.4 Rename newest run folder
```powershell
$latest = Get-ChildItem basler_test_runs -Directory | Sort-Object LastWriteTime -Descending | Select-Object -First 1
$dst = ($latest.FullName -replace "basler_run_","final_tests_")
Rename-Item $latest.FullName $dst
echo "Renamed to: $dst"
```

## 3) LIVE MONITOR (separate terminal)
Run while the test is executing.

```powershell
.\.venv\Scripts\python tools\live_pose_monitor.py --mode spike_off
```
Expected output:
- `[pose] frame=... dist=... xyz=(...) tilt=...`
- `[time] frame=... t_total_ms=...`

## 4) Artifacts to keep
- `summary\MEETING_SUMMARY.md`
- `summary\meeting_table.csv`
- `summary\basler_stream_best.json`
- `terminal.log`
- `spike_off\poses.csv`
- `spike_off\debug_metrics.csv`
