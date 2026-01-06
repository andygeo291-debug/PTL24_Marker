"""
Camera calibration utility for Phase A.

Drop chessboard photos (9x6 inner corners) into ../assets/calib_images and run:
    python phase_a/apps/camera_calibrate.py --square-size 0.024  # metres, example

Only the relative scale affects the extrinsics; intrinsics are unaffected.
"""

import argparse
from pathlib import Path
from typing import Iterable, List, Tuple

import cv2
import numpy as np
import yaml

# Default chessboard pattern: 9 columns x 6 rows of inner corners.
CHESSBOARD_SIZE = (9, 6)
PHASE_A_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_IMAGES = PHASE_A_ROOT / "assets" / "calib_images"
DEFAULT_OUTPUT = PHASE_A_ROOT / "data" / "camera_intrinsics.npz"


def iter_image_paths(image_dir: Path) -> Iterable[Path]:
    """Yield image files from the calibration directory in a deterministic order."""
    exts = (".png", ".jpg", ".jpeg", ".bmp", ".tiff")
    for path in sorted(image_dir.iterdir()):
        if path.suffix.lower() in exts:
            yield path


def collect_points(
    image_paths: Iterable[Path],
    square_size: float,
) -> Tuple[List[np.ndarray], List[np.ndarray], Tuple[int, int]]:
    """Detect chessboard corners and build matching 3D/2D point arrays."""
    # Prepare single frame of object points: (0,0,0) ... (8,5,0)
    objp = np.zeros((CHESSBOARD_SIZE[0] * CHESSBOARD_SIZE[1], 3), np.float32)
    objp[:, :2] = np.mgrid[0:CHESSBOARD_SIZE[0], 0:CHESSBOARD_SIZE[1]].T.reshape(-1, 2)
    objp *= square_size

    objpoints: List[np.ndarray] = []
    imgpoints: List[np.ndarray] = []
    image_size: Tuple[int, int] | None = None

    criteria = (
        cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER,
        30,
        0.001,
    )

    for path in image_paths:
        image = cv2.imread(str(path))
        if image is None:
            # Skip unreadable files but keep processing the rest.
            print(f"[warn] Failed to read {path}")
            continue

        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        found, corners = cv2.findChessboardCorners(gray, CHESSBOARD_SIZE, None)

        if not found:
            # Seeing this usually means the board was partially out of frame or blurred.
            print(f"[warn] Chessboard not detected in {path.name}")
            continue

        # Refine corner locations to sub-pixel accuracy for better calibration.
        corners_subpix = cv2.cornerSubPix(
            gray,
            corners,
            winSize=(11, 11),
            zeroZone=(-1, -1),
            criteria=criteria,
        )

        objpoints.append(objp.copy())
        imgpoints.append(corners_subpix)

        if image_size is None:
            # Remember the resolution of the first valid image; all should match.
            image_size = (gray.shape[1], gray.shape[0])

    if not objpoints:
        raise RuntimeError("No valid chessboard detections found; check your images.")

    assert image_size is not None
    return objpoints, imgpoints, image_size


def calibrate_camera(
    objpoints: List[np.ndarray],
    imgpoints: List[np.ndarray],
    image_size: Tuple[int, int],
) -> Tuple[float, np.ndarray, np.ndarray]:
    """Run OpenCV calibration and return RMS error plus intrinsic matrices."""
    rms, K, dist, _, _ = cv2.calibrateCamera(
        objpoints,
        imgpoints,
        image_size,
        None,
        None,
    )
    return rms, K, dist


def main() -> None:
    parser = argparse.ArgumentParser(description="Estimate camera intrinsics from chessboard images.")
    parser.add_argument(
        "--square-size",
        type=float,
        default=1.0,
        help="Physical square size in meters (affects translation scale only).",
    )
    parser.add_argument(
        "--images",
        type=str,
        default=str(DEFAULT_IMAGES),
        help="Directory or glob for chessboard images (default: phase_a/assets/calib_images).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Target file for intrinsics (NumPy .npz).",
    )
    parser.add_argument(
        "--out",
        type=Path,
        help="Directory to place camera_intrinsics.npz (overrides --output when provided).",
    )
    args = parser.parse_args()

    images_arg = args.images
    has_glob = any(char in images_arg for char in "*?[]")
    if has_glob:
        image_paths = [Path(path) for path in sorted(Path().glob(images_arg))]
        if not image_paths:
            raise FileNotFoundError(f"No image files matched pattern: {images_arg}")
    else:
        image_dir = Path(images_arg)
        if not image_dir.exists():
            raise FileNotFoundError(f"Image directory not found: {image_dir}")
        image_paths = list(iter_image_paths(image_dir))
        if not image_paths:
            raise FileNotFoundError(f"No image files detected in {image_dir}")

    objpoints, imgpoints, image_size = collect_points(image_paths, args.square_size)
    rms, K, dist = calibrate_camera(objpoints, imgpoints, image_size)

    fx, fy = K[0, 0], K[1, 1]
    cx, cy = K[0, 2], K[1, 2]

    # Save compact scalars and the full intrinsic/distortion arrays for later use.
    output_path = args.output
    if args.out:
        args.out.mkdir(parents=True, exist_ok=True)
        output_path = args.out / "camera_intrinsics.npz"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    np.savez(output_path, fx=fx, fy=fy, cx=cx, cy=cy, K=K, dist=dist)
    yaml_path = output_path.with_suffix(".yaml")
    calib_yaml = {
        "camera_matrix": {"rows": 3, "cols": 3, "data": K.reshape(-1).tolist()},
        "distortion_coefficients": {
            "rows": 1,
            "cols": int(dist.size),
            "data": dist.reshape(-1).tolist(),
        },
        "image_width": int(image_size[0]),
        "image_height": int(image_size[1]),
    }
    with yaml_path.open("w", encoding="utf-8") as fp:
        yaml.safe_dump(calib_yaml, fp)

    print(f"RMS reprojection error: {rms:.4f} px")
    print(f"Image size: {image_size[0]} x {image_size[1]}")
    print(f"fx={fx:.3f}, fy={fy:.3f}, cx={cx:.3f}, cy={cy:.3f}")
    print(f"Intrinsics saved to {output_path}")
    print(f"Calibration YAML saved to {yaml_path} (Phase B compatible)")


if __name__ == "__main__":
    main()
