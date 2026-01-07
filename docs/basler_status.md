# Basler integration status (ptl24_marker)

## Summary
Basler support has been integrated as an optional camera backend with lazy `pypylon` imports. OpenCV remains the default and unchanged. A standalone Basler grab test exists, a small Basler wrapper is available, and Phase B v2 can now select the backend via CLI.

## Files added/changed
Added:
- `common/__init__.py`
- `common/camera/__init__.py`
- `common/camera/test_basler_grab.py` (standalone Basler grab test)
- `common/camera/basler_cam.py` (lazy-import Basler wrapper)
- `common/camera/factory.py` (backend factory + CLI args)

Changed:
- `phase_b/v2/phase_b_tags_v2.py` (backend selection + Basler integration + diagnostics)

## Backend selection
- Default: OpenCV (`--camera-backend opencv`)
- Basler: `--camera-backend basler`
- Lazy import: `pypylon` is only imported when Basler backend is selected or when the Basler test script is executed.

Factory entry points:
- `common.camera.factory.add_camera_cli_args(parser)`
- `common.camera.factory.create_camera_from_args(args)`

## Basler CLI args
Core selection:
- `--camera-backend {opencv,basler}` (default: `opencv`)

Basler-specific:
- `--basler-serial`
- `--basler-name`
- `--basler-pixel-format` (default: `Mono8`)
- `--basler-exposure-us`
- `--basler-gain`
- `--basler-offset-x`
- `--basler-offset-y`
- `--basler-packet-size`
- `--basler-interpacket-delay`
- `--basler-timeout-ms` (default: 1000)

Shared with OpenCV (already existing):
- `--width`, `--height`, `--fps`

Diagnostics (Basler-friendly):
- `--dump-first-frame PATH` (save first acquired frame)
- `--quiet-apriltag-stderr` (suppress C-level stderr from apriltag)
- `--print-first-frame-stats` (one-shot detection summary)
- `--print-first-pose-debug` (one-shot pose-estimation checkpoints)

## Timestamp handling
- Basler: `BaslerGigECam.read()` stamps `last_timestamp_s = time.time()` when a frame is returned.
- Pipeline: when Basler is active and `last_timestamp_s` is set, Phase B v2 uses it as `frame_ts`; otherwise it falls back to `time.time()` (OpenCV behavior unchanged).

## Current acceptance tests
- Standalone Basler grab test: `python -m common.camera.test_basler_grab ...` works and reports frame stats (may show frame drops depending on GigE settings).
- Basler pipeline: Phase B v2 can run with Basler backend and write debug CSV (`--debug-metrics`), and can dump the first frame with `--dump-first-frame`.
- OpenCV regression: baseline webcam command still works unchanged.

## Latest performance snapshot (from /tmp/debug_basler_smoke.csv)
Sample rows show the following ballpark timings (first few frames):
- `t_read_ms`: ~0.0–0.9 ms
- `t_gray_ms`: ~0.16–0.54 ms
- `t_detect_ms`: ~59–73 ms
- `t_reproj_ms`: ~0.5–3.8 ms
- `t_ransac_ms`: ~54–58 ms
- `t_fuse_ms`: ~0.18–0.49 ms
- `t_total_ms`: ~115–135 ms

These are per-frame measurements from the debug CSV and should be treated as indicative, not a stable median.

## Known gotchas / lessons learned
- **ROI alignment matters:** Basler may clamp invalid width/height (e.g., requested 1280x980 but readback is 880x980). Use the readback values from the grab test.
- **GigE reliability:** timeouts and frame drops can occur; adjust `--basler-timeout-ms`, `--basler-packet-size`, and `--basler-interpacket-delay` as needed.
- **Apriltag stderr spam:** use `--quiet-apriltag-stderr` to suppress C-level warnings during Basler runs.
- **Frame-limit behavior:** `--frames` now counts grabbed frames and exits deterministically after detection.
- **RANSAC/adaptive settings:** if poses are not produced, try enabling `--ransac --adapt` (workflow suggestion, not a code requirement).

## Recommended test commands
Standalone grab:
```
python -m common.camera.test_basler_grab \
  --serial <SERIAL> --name <NAME> \
  --frames 20 --timeout-ms 1000
```

Basler pipeline smoke (v2):
```
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
