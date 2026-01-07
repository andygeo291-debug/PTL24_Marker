"""Charuco-based intrinsics calibration for OpenCV or Basler backends."""

import argparse
import time
from pathlib import Path

import cv2
import numpy as np
import yaml

from common.camera.factory import add_camera_cli_args, create_camera_from_args


def _get_aruco_dict(name):
    if not hasattr(cv2, "aruco"):
        raise RuntimeError("OpenCV aruco module not available.")
    if not hasattr(cv2.aruco, name):
        raise ValueError(f"Unknown aruco dict: {name}")
    return cv2.aruco.getPredefinedDictionary(getattr(cv2.aruco, name))


def _create_charuco_board(squares_x, squares_y, square_length_mm, marker_length_mm, aruco_dict):
    if hasattr(cv2.aruco, "CharucoBoard"):
        return cv2.aruco.CharucoBoard(
            (squares_x, squares_y), square_length_mm, marker_length_mm, aruco_dict
        )
    if hasattr(cv2.aruco, "CharucoBoard_create"):
        return cv2.aruco.CharucoBoard_create(
            squares_x, squares_y, square_length_mm, marker_length_mm, aruco_dict
        )
    raise RuntimeError("Charuco board creation is not supported by this OpenCV build.")


def _create_detector_params():
    if hasattr(cv2.aruco, "DetectorParameters"):
        return cv2.aruco.DetectorParameters()
    if hasattr(cv2.aruco, "DetectorParameters_create"):
        return cv2.aruco.DetectorParameters_create()
    raise RuntimeError("Aruco detector parameters are not available in this OpenCV build.")


def _parse_args():
    parser = argparse.ArgumentParser(description="Calibrate intrinsics using a Charuco board.")
    parser.add_argument(
        "--mode",
        choices=["charuco", "chessboard"],
        default="charuco",
        help="Calibration target type (default: charuco).",
    )
    add_camera_cli_args(parser)
    parser.add_argument(
        "--video",
        default="auto",
        help='OpenCV source: "auto", index like "0", a device path, or URL.',
    )

    parser.add_argument("--width", type=int, default=None, help="Requested capture width.")
    parser.add_argument("--height", type=int, default=None, help="Requested capture height.")
    parser.add_argument("--fps", type=float, default=None, help="Requested capture FPS.")
    parser.add_argument(
        "--samples",
        type=int,
        default=40,
        help="Number of accepted samples to collect (default: 40).",
    )
    parser.add_argument(
        "--frames",
        type=int,
        default=None,
        help="Alias for --samples.",
    )
    parser.add_argument(
        "--every-n",
        type=int,
        default=1,
        help="Only consider every Nth grabbed frame (default: 1).",
    )

    parser.add_argument("--squares-x", type=int, default=None, help="Charuco squares in X.")
    parser.add_argument("--squares-y", type=int, default=None, help="Charuco squares in Y.")
    parser.add_argument(
        "--square-length-mm",
        type=float,
        default=None,
        help="Square length in mm.",
    )
    parser.add_argument(
        "--marker-length-mm",
        type=float,
        default=None,
        help="Marker length in mm.",
    )
    parser.add_argument(
        "--aruco-dict",
        default="DICT_4X4_50",
        help="Aruco dictionary name (e.g., DICT_4X4_50).",
    )
    parser.add_argument(
        "--chessboard-cols",
        type=int,
        default=None,
        help="Chessboard inner corners across.",
    )
    parser.add_argument(
        "--chessboard-rows",
        type=int,
        default=None,
        help="Chessboard inner corners down.",
    )

    parser.add_argument(
        "--out-yaml",
        required=True,
        help="Output calibration YAML path.",
    )
    parser.add_argument(
        "--save-images",
        default=None,
        help="Optional directory to save accepted frames.",
    )
    parser.add_argument(
        "--show-preview",
        action="store_true",
        help="Show a live preview window with detections.",
    )
    return parser.parse_args()


def _format_matrix(matrix):
    data = [float(v) for v in matrix.reshape(-1).tolist()]
    rows, cols = matrix.shape
    return {"rows": int(rows), "cols": int(cols), "data": data}


def _format_dist(dist):
    dist = dist.reshape(-1)
    return {"rows": 1, "cols": int(dist.size), "data": [float(v) for v in dist.tolist()]}


def _write_yaml(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(payload, handle, sort_keys=False)


def _prune_none(values):
    return {key: value for key, value in values.items() if value is not None}


def _detect_chessboard(gray, pattern_size):
    if hasattr(cv2, "findChessboardCornersSB"):
        found, corners = cv2.findChessboardCornersSB(gray, pattern_size)
        return found, corners
    flags = cv2.CALIB_CB_ADAPTIVE_THRESH | cv2.CALIB_CB_NORMALIZE_IMAGE
    found, corners = cv2.findChessboardCorners(gray, pattern_size, flags)
    return found, corners


def main():
    args = _parse_args()
    samples_target = args.samples if args.samples is not None else args.frames
    if args.frames is not None:
        samples_target = args.frames
    if samples_target is None or samples_target <= 0:
        raise ValueError("Sample count must be a positive integer.")

    if args.mode == "charuco":
        if args.squares_x is None or args.squares_y is None:
            raise ValueError("--squares-x and --squares-y are required for charuco.")
        if args.square_length_mm is None or args.marker_length_mm is None:
            raise ValueError("--square-length-mm and --marker-length-mm are required for charuco.")
        aruco_dict = _get_aruco_dict(args.aruco_dict)
        board = _create_charuco_board(
            args.squares_x,
            args.squares_y,
            args.square_length_mm,
            args.marker_length_mm,
            aruco_dict,
        )
        params = _create_detector_params()
    else:
        if args.chessboard_cols is None or args.chessboard_rows is None:
            raise ValueError("--chessboard-cols and --chessboard-rows are required for chessboard.")
        if args.square_length_mm is None:
            raise ValueError("--square-length-mm is required for chessboard.")
        aruco_dict = None
        board = None
        params = None

    cam = create_camera_from_args(args)
    if cam is None:
        raise RuntimeError("Unable to open camera for calibration.")

    save_dir = Path(args.save_images).expanduser() if args.save_images else None
    if save_dir:
        save_dir.mkdir(parents=True, exist_ok=True)

    all_corners = []
    all_ids = []
    obj_points = []
    img_points = []
    grabbed = 0
    accepted = 0
    image_size = None
    min_corners = 10
    chessboard_pattern = (
        (int(args.chessboard_cols), int(args.chessboard_rows))
        if args.mode == "chessboard"
        else None
    )
    chessboard_objp = None
    if chessboard_pattern:
        cols, rows = chessboard_pattern
        objp = np.zeros((rows * cols, 3), dtype=np.float32)
        objp[:, :2] = np.mgrid[0:cols, 0:rows].T.reshape(-1, 2)
        chessboard_objp = objp * float(args.square_length_mm)

    try:
        while accepted < samples_target:
            ok, frame = cam.read()
            if not ok or frame is None:
                continue
            grabbed += 1
            if args.every_n > 1 and (grabbed % args.every_n) != 0:
                continue

            if frame.ndim == 3:
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                preview = frame.copy()
            else:
                gray = frame
                preview = cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)

            if image_size is None:
                image_size = (gray.shape[1], gray.shape[0])

            if args.mode == "charuco":
                corners, ids, _ = cv2.aruco.detectMarkers(gray, aruco_dict, parameters=params)
                if ids is None or len(ids) == 0:
                    if args.show_preview:
                        cv2.imshow("charuco", preview)
                        if (cv2.waitKey(1) & 0xFF) in (27, ord("q")):
                            break
                    continue

                _, charuco_corners, charuco_ids = cv2.aruco.interpolateCornersCharuco(
                    corners, ids, gray, board
                )
                if charuco_corners is None or charuco_ids is None:
                    continue
                if len(charuco_corners) < min_corners:
                    continue

                all_corners.append(charuco_corners)
                all_ids.append(charuco_ids)
                accepted += 1

                if save_dir:
                    cv2.imwrite(str(save_dir / f"sample_{accepted:03d}.png"), preview)

                if args.show_preview:
                    cv2.aruco.drawDetectedMarkers(preview, corners, ids)
                    cv2.aruco.drawDetectedCornersCharuco(preview, charuco_corners, charuco_ids)
                    cv2.imshow("charuco", preview)
                    if (cv2.waitKey(1) & 0xFF) in (27, ord("q")):
                        break
            else:
                found, corners = _detect_chessboard(gray, chessboard_pattern)
                if not found or corners is None:
                    if args.show_preview:
                        cv2.imshow("chessboard", preview)
                        if (cv2.waitKey(1) & 0xFF) in (27, ord("q")):
                            break
                    continue
                if corners.shape[0] < min_corners:
                    continue

                obj_points.append(chessboard_objp.copy())
                img_points.append(corners)
                accepted += 1

                if save_dir:
                    cv2.imwrite(str(save_dir / f"sample_{accepted:03d}.png"), preview)

                if args.show_preview:
                    cv2.drawChessboardCorners(preview, chessboard_pattern, corners, found)
                    cv2.imshow("chessboard", preview)
                    if (cv2.waitKey(1) & 0xFF) in (27, ord("q")):
                        break

            if accepted % 5 == 0:
                print(f"Collected {accepted}/{samples_target} samples")
    finally:
        if hasattr(cam, "release"):
            cam.release()
        if args.show_preview:
            cv2.destroyAllWindows()

    if accepted == 0:
        raise RuntimeError("No Charuco samples collected; cannot calibrate.")

    if image_size is None:
        raise RuntimeError("No valid frames captured; cannot calibrate.")

    if args.mode == "charuco":
        rms, K, dist, _, _ = cv2.aruco.calibrateCameraCharuco(
            all_corners,
            all_ids,
            board,
            image_size,
            None,
            None,
        )
    else:
        rms, K, dist, _, _ = cv2.calibrateCamera(
            obj_points,
            img_points,
            image_size,
            None,
            None,
        )

    payload = {
        "image_width": int(image_size[0]),
        "image_height": int(image_size[1]),
        "camera_matrix": _format_matrix(K),
        "distortion_coefficients": _format_dist(dist),
        "metadata": _prune_none(
            {
                "timestamp": float(time.time()),
                "camera_backend": args.camera_backend,
                "width": args.width,
                "height": args.height,
                "fps": args.fps,
                "basler_serial": args.basler_serial,
                "basler_name": args.basler_name,
                "basler_offset_x": args.basler_offset_x,
                "basler_offset_y": args.basler_offset_y,
            }
        ),
    }

    _write_yaml(args.out_yaml, payload)

    fx = K[0, 0]
    fy = K[1, 1]
    cx = K[0, 2]
    cy = K[1, 2]
    dist_list = [float(v) for v in dist.reshape(-1).tolist()]

    print("Calibration complete")
    print(f"RMS reprojection error: {rms:.6f}")
    print(f"fx={fx:.3f} fy={fy:.3f} cx={cx:.3f} cy={cy:.3f}")
    print(f"dist={dist_list}")


if __name__ == "__main__":
    main()
