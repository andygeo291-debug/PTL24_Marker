# Basler pipeline (Phase B v2)

## 1) Overview
Basler support adds an optional camera backend to Phase B v2 without changing any pose-estimation logic. The integration is intentionally isolated: OpenCV remains the default backend, and Basler-specific code is only imported when selected. This keeps the project usable on machines without Pylon/pypylon installed while enabling a deterministic Basler workflow for GigE cameras.

## 2) Dependencies
- **Pylon runtime**: Basler’s Pylon SDK must be installed and the device must be visible to Pylon.
- **Python binding**: `pypylon` must be available in the active environment.
- **GigE networking**:
  - Prefer a dedicated NIC and direct cable if possible.
  - Check MTU settings if using large packet sizes (9000 for jumbo frames).
  - Packet size, interpacket delay, and timeout can strongly affect reliability.

## 3) Camera discovery
Basler cameras are discovered via `pypylon.TlFactory.EnumerateDevices()`. Selection is done by:
- **serial**: exact match of `GetSerialNumber()`
- **name**: matched against `GetUserDefinedName()`, `GetModelName()`, `GetFriendlyName()`, and `GetFullName()`

CLI selection uses:
- `--basler-serial`
- `--basler-name`

If both are provided, both must match.

## 4) Basler settings explained
All settings are applied via the camera nodemap when available.

- **Pixel format** (`--basler-pixel-format`): Typically `Mono8` for grayscale. Output is converted to `Mono8` and then to BGR in the pipeline to match the OpenCV path.
- **ROI** (`--width`, `--height`, `--basler-offset-x`, `--basler-offset-y`):
  - Must satisfy camera constraints (step sizes, bounds). If invalid, the camera may clamp values.
  - Use readback (from the grab test) to confirm what was accepted.
- **FPS** (`--fps`): Set via `AcquisitionFrameRateEnable` + `AcquisitionFrameRate` when supported.
- **Exposure** (`--basler-exposure-us`): Microseconds; applied to `ExposureTime`.
- **Gain** (`--basler-gain`): Analog gain; applied to `Gain`.
- **Packet size** (`--basler-packet-size`): `GevSCPSPacketSize`. Use 1500 for standard MTU, 9000 for jumbo frames if supported.
- **Interpacket delay** (`--basler-interpacket-delay`): `GevSCPD` in ticks; can reduce dropped frames on congested links.
- **Timeout** (`--basler-timeout-ms`): Retrieve timeout for each frame.

## 5) Runtime flow
The Basler path is intentionally aligned with the OpenCV path:
1) **Grab** a frame (`BaslerGigECam.read()`), with a host timestamp set on success.
2) **Convert** `Mono8 -> BGR` (only for Basler) to match the OpenCV format.
3) **Gray** conversion: `BGR -> Gray` for detection.
4) **Undistort** (optional, `--undistort`).
5) **AprilTag detect** with Pupil Apriltag.
6) **Best-per-ID**: Keep the best detection per tag ID.
7) **Correspondences**: Build camera-to-tag transforms and reprojection errors.
8) **PnP**: Estimate pose candidates for the rig.
9) **RANSAC/adapt**: Optional rejection and adaptive thresholds.
10) **Fusion**: Weighted or EMA fusion with prior pose.
11) **HUD**: Render overlays if enabled.
12) **Logging**: Poses CSV and debug metrics CSV.

## 6) Outputs
- **Poses CSV** (default: `phase_b/poses.csv` or `--save-poses`): per-frame fused pose and tag info.
- **Debug metrics CSV** (`--debug-metrics`): per-frame diagnostics and timing.

Key timing columns (ms):
- `t_read_ms`: frame grab time
- `t_gray_ms`: grayscale conversion + undistort
- `t_detect_ms`: AprilTag detection
- `t_reproj_ms`: reprojection and correspondence building
- `t_ransac_ms`: RANSAC/fusion stage
- `t_fuse_ms`: fusion post-processing
- `t_hud_ms`: HUD rendering
- `t_total_ms`: end-to-end per-frame time

## 7) Commands
### Standalone grab test (20 frames)
```bash
python -m common.camera.test_basler_grab \
  --serial <SERIAL> --name <NAME> \
  --frames 20 --timeout-ms 1000
```

### Basler pipeline (HUD on)
```bash
python3 -m phase_b.v2.phase_b_tags_v2 \
  --camera-backend basler \
  --basler-serial <SERIAL> \
  --basler-name <NAME> \
  --width 1280 --height 980 \
  --fps 20 \
  --basler-pixel-format Mono8 \
  --basler-exposure-us 5000 \
  --basler-gain 0 \
  --basler-offset-x 0 \
  --basler-offset-y 0 \
  --basler-interpacket-delay 3500 \
  --basler-timeout-ms 1000 \
  --rig phase_b/rigs/cyl_dotec.yaml \
  --camera common/calib/basler_static_1280x980_mono8.yaml \
  --debug-metrics /tmp/debug_basler.csv \
  --frames 600
```

### Basler pipeline (HUD off, long run)
```bash
python3 -m phase_b.v2.phase_b_tags_v2 \
  --camera-backend basler \
  --basler-serial <SERIAL> \
  --basler-name <NAME> \
  --width 1280 --height 980 \
  --fps 20 \
  --basler-pixel-format Mono8 \
  --basler-exposure-us 5000 \
  --basler-gain 0 \
  --basler-offset-x 0 \
  --basler-offset-y 0 \
  --basler-interpacket-delay 3500 \
  --basler-timeout-ms 1000 \
  --rig phase_b/rigs/cyl_dotec.yaml \
  --camera common/calib/basler_static_1280x980_mono8.yaml \
  --debug-metrics /tmp/debug_basler_long.csv \
  --no-hud \
  --frames 1200
```

### Basler smoke run (frames=60)
```bash
python3 -m phase_b.v2.phase_b_tags_v2 \
  --camera-backend basler \
  --basler-serial <SERIAL> \
  --basler-name <NAME> \
  --width 1280 --height 980 \
  --fps 20 \
  --basler-pixel-format Mono8 \
  --basler-exposure-us 5000 \
  --basler-gain 0 \
  --basler-offset-x 0 \
  --basler-offset-y 0 \
  --basler-interpacket-delay 3500 \
  --basler-timeout-ms 1000 \
  --rig phase_b/rigs/cyl_dotec.yaml \
  --camera common/calib/basler_static_1280x980_mono8.yaml \
  --debug-metrics /tmp/debug_basler_smoke.csv \
  --no-hud \
  --frames 60
```

### Webcam regression run
```bash
python -m phase_b.v2.phase_b_tags_v2 \
  --config phase_b/config.yaml \
  --camera common/calib/calib.yaml \
  --rig phase_b/rigs/cyl_dotec.yaml \
  --extrinsics common/extrinsics/T_WC.yaml \
  --video 0 \
  --width 1920 --height 1080 --fps 30 \
  --save-poses phase_b/v2/poses_dotec_check_fixed.csv \
  --debug-metrics phase_b/v2/debug_dotec_check_fixed.csv \
  --ransac --adapt \
  --ema-alpha 0.25 \
  --use-weighted-se3 \
  --ekf --print-tilt --hud
```

## 8) Troubleshooting
### “No poses” with valid detections
Symptom: tags are detected, but `poses=0` and `reject_reason` stays `NO_POSE`.
- Ensure RANSAC/adapt are enabled if required by your rig configuration:
  - Add `--ransac --adapt`
- Verify calibration and rig YAML alignment (camera intrinsics, tag sizes).

### Apriltag stderr spam
Symptom: repeated `Error, more than one new minima found.` messages.
- Use `--quiet-apriltag-stderr` to suppress C-level stderr during detection.

### Frame grab timeouts / dropped frames
Symptom: `Frame grab failed; skipping frame.` and runs stall.
- Increase timeout: `--basler-timeout-ms 3000`
- Adjust FPS or exposure if the link is saturated
- Set packet size: `--basler-packet-size 1500` (or 9000 with jumbo frames)
- Reduce interpacket delay if set too high or try `--basler-interpacket-delay 0`

## 9) Performance
### Check the <=100ms target
Use the debug CSV to compute medians:
```bash
python3 - <<'PY'
import pandas as pd
p = "/tmp/debug_basler_smoke.csv"
df = pd.read_csv(p, comment="#")
print("median t_total_ms:", df["t_total_ms"].median())
print("median detect:", df["t_detect_ms"].median(), "median ransac:", df["t_ransac_ms"].median())
PY
```

### Current measured numbers (example)
From recent runs, the dominant contributors are typically:
- **t_detect_ms**: ~60–70 ms
- **t_ransac_ms**: ~50–60 ms
- **t_total_ms**: ~115–135 ms

Treat these as indicative; actual numbers vary with ROI, FPS, and tag visibility.

### Safe optimization levers
- Reduce ROI and resolution (largest impact on detect time).
- Lower FPS if not required.
- Ensure exposure/gain are appropriate to avoid noisy detections.
- Keep packet size and interpacket delay tuned for stable delivery.
