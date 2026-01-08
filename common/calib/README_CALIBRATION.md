# Calibration (Charuco intrinsics)

This folder includes an intrinsics calibration tool that supports both OpenCV and Basler backends with chessboard (default) or Charuco targets.

## Requirements
- OpenCV with aruco: `python3 -c "import cv2; print(hasattr(cv2,'aruco'))"` should print `True`.
- For Basler: Pylon + `pypylon` installed and the camera visible.

## Example commands
### Chessboard (9x6, 25mm squares)
```bash
python3 common/calib/calibrate_intrinsics_charuco.py \
  --mode chessboard \
  --camera-backend opencv \
  --video 0 \
  --width 1920 --height 1080 --fps 30 \
  --chessboard-cols 9 --chessboard-rows 6 \
  --square-length-mm 25 \
  --samples 40 \
  --show-preview \
  --out-yaml common/calib/calib_chessboard.yaml
```

### Chessboard (Basler ROI, 960x980 offset_x=320)
```bash
python3 common/calib/calibrate_intrinsics_charuco.py \
  --mode chessboard \
  --camera-backend basler \
  --basler-serial <SERIAL> \
  --basler-name <NAME> \
  --width 960 --height 980 \
  --basler-offset-x 320 \
  --basler-offset-y 0 \
  --fps 20 \
  --basler-pixel-format Mono8 \
  --basler-exposure-us 20000 \
  --basler-gain 0 \
  --basler-interpacket-delay 3500 \
  --basler-timeout-ms 1000 \
  --chessboard-cols 9 --chessboard-rows 6 \
  --square-length-mm 25 \
  --samples 40 \
  --show-preview \
  --out-yaml common/calib/basler_static_960x980_offx320_mono8.yaml
```

### OpenCV backend
```bash
python3 common/calib/calibrate_intrinsics_charuco.py \
  --mode charuco \
  --camera-backend opencv \
  --video 0 \
  --width 1920 --height 1080 --fps 30 \
  --squares-x 7 --squares-y 5 \
  --square-length-mm 24.0 \
  --marker-length-mm 18.0 \
  --aruco-dict DICT_4X4_50 \
  --samples 40 \
  --show-preview \
  --out-yaml common/calib/calib_charuco.yaml
```

### Basler backend
```bash
python3 common/calib/calibrate_intrinsics_charuco.py \
  --mode charuco \
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
  --squares-x 7 --squares-y 5 \
  --square-length-mm 24.0 \
  --marker-length-mm 18.0 \
  --aruco-dict DICT_4X4_50 \
  --samples 40 \
  --show-preview \
  --out-yaml common/calib/calib_charuco_basler.yaml
```

## Notes
- The output YAML matches the existing `camera_matrix` + `distortion_coefficients` schema used by Phase B v2.
- If ROI settings are clamped by the camera, use the readback values from the Basler grab test to match the actual resolution.
- For unreliable GigE streams, increase `--basler-timeout-ms` or reduce `--fps`.
