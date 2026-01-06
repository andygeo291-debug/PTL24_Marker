#!/usr/bin/env python3
"""
Phase B entry point.

The pipeline detects AprilTags on a cylindrical rig, filters per-tag poses with
RANSAC, selects the most consistent minimum, and fuses the inliers via SE(3)
averaging. Stability helpers hold the last good pose when confidence is low,
reject sudden tilt spikes, apply optional EMA smoothing, and maintain quaternion
sign continuity before streaming/logging the result.

Key CLI flags:
  --camera / --rig        : inputs for intrinsics and rig layout
  --axis-len              : rendered axis length
  --ransac* / --min-inliers / --max-tilt-jump-deg : robust fusion thresholds
  --ema-alpha             : temporal smoothing over SE(3)
  --ignore-ids            : skip problematic tag IDs (comma-separated)
  --extrinsics / --print-tilt / --save-poses      : world-frame reporting
  --stream-udp / --stream-rate-hz / --no-overlay : crane-controller stream control
"""

from __future__ import annotations

import argparse
import csv
import datetime as _dt
import json
import logging
import math
import os
import random
import socket
import time
from time import perf_counter
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Set, TextIO, Tuple

import cv2
import numpy as np
import yaml
from pupil_apriltags import Detector


LOGGER = logging.getLogger("phase_b_tags")
PHASE_B_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = PHASE_B_ROOT.parent
COMMON_CALIB_FALLBACK = PROJECT_ROOT / "common" / "calib" / "calib.yaml"
EPS = 1e-9

last_axis_cam: Optional[np.ndarray] = None
last_tilt_cam: Optional[float] = None


class Tock:
    """Lightweight timer helper for cumulative stage timings."""

    def __init__(self) -> None:
        self.last = perf_counter()

    def reset(self) -> None:
        self.last = perf_counter()

    def ms(self) -> float:
        now = perf_counter()
        dt = (now - self.last) * 1000.0
        self.last = now
        return dt


def set_deterministic(seed: int = 12345) -> None:
    """Seed Python, NumPy, and hash randomization for repeatability."""
    os.environ.setdefault("PYTHONHASHSEED", str(seed))
    random.seed(seed)
    np.random.seed(seed)


def _open_metrics_writer(path: str) -> Tuple[TextIO, csv.writer]:
    """Return an append-mode CSV writer, writing header if the file is empty."""
    need_header = not os.path.exists(path) or os.path.getsize(path) == 0
    fh = open(path, "a", newline="", encoding="utf-8")
    writer = csv.writer(fh)
    if need_header:
        writer.writerow(
            [
                "timestamp_iso",
                "frame_idx",
                "dt_frame_ms",
                "fps_inst",
                "dt_detect_ms",
                "dt_pose_ms",
                "dt_ransac_ms",
                "dt_fuse_ms",
                "dt_hud_ms",
                "n_tags",
                "n_inliers",
                "inlier_ratio",
                "reproj_mean_px",
                "video_src",
                "width",
                "height",
            ]
        )
        fh.flush()
    return fh, writer


@dataclass(frozen=True)
class TagSpec:
    """Stores rig information for a single AprilTag."""

    size_m: float
    T_tag_to_cyl: np.ndarray  # 4x4 transform from tag frame to cylinder frame


@dataclass(frozen=True)
class RigSpec:
    """Holds the rig-wide parameters and tag specifications."""

    radius_m: float
    length_m: float
    tags: Dict[int, TagSpec]


@dataclass
class PoseCandidate:
    """Candidate pose hypothesis used during robust fusion."""

    transform: np.ndarray
    inliers: List[int]
    mean_error: float


# --- Linear algebra helpers ------------------------------------------------- #
# Poses are fused in SE(3) using log/exp maps, which keeps rotation and
# translation tightly coupled while averaging weighted tag poses.


def skew(vector: np.ndarray) -> np.ndarray:
    """Return the skew-symmetric matrix for a 3-vector."""
    x, y, z = vector
    return np.array([[0.0, -z, y], [z, 0.0, -x], [-y, x, 0.0]], dtype=np.float64)


def so3_exp(omega: np.ndarray) -> np.ndarray:
    """Exponential map from so(3) to SO(3)."""
    theta = np.linalg.norm(omega)
    if theta < EPS:
        Omega = skew(omega)
        return np.eye(3) + Omega + 0.5 * (Omega @ Omega)
    axis = omega / theta
    K = skew(axis)
    return (
        np.eye(3)
        + math.sin(theta) * K
        + (1.0 - math.cos(theta)) * (K @ K)
    )


def so3_log(R: np.ndarray) -> np.ndarray:
    """Logarithm map from SO(3) to so(3)."""
    trace = np.clip((np.trace(R) - 1.0) * 0.5, -1.0, 1.0)
    theta = math.acos(trace)
    if theta < EPS:
        return 0.5 * np.array([R[2, 1] - R[1, 2], R[0, 2] - R[2, 0], R[1, 0] - R[0, 1]])
    factor = theta / (2.0 * math.sin(theta))
    return factor * np.array([R[2, 1] - R[1, 2], R[0, 2] - R[2, 0], R[1, 0] - R[0, 1]])


def se3_exp(xi: np.ndarray) -> np.ndarray:
    """Exponential map from se(3) to SE(3)."""
    omega = xi[:3]
    v = xi[3:]
    theta = np.linalg.norm(omega)
    Omega = skew(omega)
    if theta < EPS:
        R = np.eye(3) + Omega + 0.5 * (Omega @ Omega)
        V = np.eye(3) + 0.5 * Omega + (1.0 / 6.0) * (Omega @ Omega)
    else:
        R = so3_exp(omega)
        Omega_sq = Omega @ Omega
        V = (
            np.eye(3)
            + (1.0 - math.cos(theta)) / (theta ** 2) * Omega
            + (theta - math.sin(theta)) / (theta ** 3) * Omega_sq
        )
    t = V @ v
    T = np.eye(4)
    T[:3, :3] = R
    T[:3, 3] = t
    return T


def se3_log(T: np.ndarray) -> np.ndarray:
    """Logarithm map from SE(3) to se(3)."""
    R = T[:3, :3]
    t = T[:3, 3]
    omega = so3_log(R)
    theta = np.linalg.norm(omega)
    Omega = skew(omega)
    if theta < EPS:
        V_inv = np.eye(3) - 0.5 * Omega + (1.0 / 12.0) * (Omega @ Omega)
    else:
        Omega_sq = Omega @ Omega
        coeff = 1.0 / (theta ** 2) - (1.0 + math.cos(theta)) / (2.0 * theta * math.sin(theta))
        V_inv = (
            np.eye(3)
            - 0.5 * Omega
            + coeff * Omega_sq
        )
    v = V_inv @ t
    return np.hstack([omega, v])


def avg_poses_SE3(Ts: Sequence[np.ndarray], ws: Sequence[float], iters: int = 5) -> np.ndarray:
    """Average SE(3) poses using iterative log/exp."""
    if not Ts:
        raise ValueError("Cannot average zero poses.")
    weights = np.asarray(ws, dtype=np.float64)
    if np.any(weights < 0):
        raise ValueError("Weights must be non-negative.")
    total_weight = float(weights.sum())
    if total_weight <= EPS:
        weights = np.ones(len(Ts), dtype=np.float64) / len(Ts)
    else:
        weights /= total_weight
    T_avg = np.array(Ts[0], dtype=np.float64)
    for _ in range(max(iters, 1)):
        xi_accum = np.zeros(6, dtype=np.float64)
        for T, w in zip(Ts, weights):
            delta = np.linalg.inv(T_avg) @ T
            xi = se3_log(delta)
            xi_accum += w * xi
        T_avg = T_avg @ se3_exp(xi_accum)
    return T_avg


def make_transform(R: np.ndarray, t: np.ndarray) -> np.ndarray:
    """Assemble a 4x4 transform from rotation and translation."""
    T = np.eye(4, dtype=np.float64)
    T[:3, :3] = R
    T[:3, 3] = t
    return T


def normalize(vec: np.ndarray) -> np.ndarray:
    """Return the unit vector while safeguarding against degenerate inputs."""
    norm = np.linalg.norm(vec)
    if norm < EPS:
        raise ValueError("Zero-length vector encountered during rig parsing.")
    return vec / norm


# --- Camera intrinsics ------------------------------------------------------ #


def _extract_matrix(value: object, expected_shape: Tuple[int, int]) -> np.ndarray:
    """Extract a matrix stored either as flat list, nested list, or OpenCV YAML."""
    rows, cols = expected_shape
    if isinstance(value, dict) and "data" in value:
        data = np.asarray(value["data"], dtype=np.float64)
        rows = int(value.get("rows", rows))
        cols = int(value.get("cols", cols))
        if data.size != rows * cols:
            raise ValueError("Matrix data size mismatch in calibration file.")
        return data.reshape(rows, cols)
    array = np.asarray(value, dtype=np.float64)
    if array.shape == expected_shape:
        return array
    if array.ndim == 1 and array.size == rows * cols:
        return array.reshape(rows, cols)
    raise ValueError(f"Cannot reshape calibration matrix to {expected_shape}.")


def _extract_vector(value: object) -> np.ndarray:
    """Extract a distortion vector from YAML."""
    if isinstance(value, dict) and "data" in value:
        data = np.asarray(value["data"], dtype=np.float64)
        return data.reshape(-1)
    arr = np.asarray(value, dtype=np.float64).reshape(-1)
    if arr.size == 0:
        raise ValueError("Distortion coefficients array is empty.")
    return arr


def load_camera_intrinsics(path: Path) -> Tuple[np.ndarray, np.ndarray]:
    """
    Load camera intrinsics from YAML.

    Accepts either {K, D} keys or {camera_matrix, distortion_coefficients}.
    """
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if data is None:
        raise ValueError(f"Camera file {path} is empty.")

    if "K" in data and "D" in data:
        K = _extract_matrix(data["K"], (3, 3))
        dist = _extract_vector(data["D"])
    elif "camera_matrix" in data and "distortion_coefficients" in data:
        K = _extract_matrix(data["camera_matrix"], (3, 3))
        dist = _extract_vector(data["distortion_coefficients"])
    else:
        raise KeyError(
            f"Camera file {path} must contain either (K, D) or "
            "(camera_matrix, distortion_coefficients)."
        )

    if not np.isclose(K[2, 2], 1.0):
        LOGGER.warning("Normalising camera matrix bottom-right element to 1.0.")
        K[2, 2] = 1.0

    return K.astype(np.float64), dist.astype(np.float64)


# --- Rig parsing ------------------------------------------------------------ #
# The cylinder frame aligns +Z along the roll axis (bottom→top).
# Ring tags sit on the barrel with +Z pointing radially outward and +X tangent.
# Cap tags sit at z = ±length/2; off-centre offsets keep them clear of lifting holes.
# Each YAML entry is converted into a TagSpec describing T_tag→cyl.


def rotation_from_axes(
    x_axis: np.ndarray, y_axis: np.ndarray, z_axis: np.ndarray
) -> np.ndarray:
    """Construct a rotation matrix from approximately orthogonal axes."""
    x_norm = normalize(x_axis)
    z_proj = z_axis - np.dot(z_axis, x_norm) * x_norm
    z_norm = normalize(z_proj)
    y_norm = np.cross(z_norm, x_norm)
    y_norm = normalize(y_norm)
    R = np.column_stack((x_norm, y_norm, z_norm))
    if np.linalg.det(R) < 0:
        R[:, 1] *= -1.0  # enforce right-handedness
    return R


def add_tag_spec(
    specs: Dict[int, TagSpec], tag_id: int, size_m: float, T_tag_to_cyl: np.ndarray
) -> None:
    """Insert a TagSpec while preventing duplicate IDs."""
    if tag_id in specs:
        raise ValueError(f"Duplicate tag id {tag_id} in rig definition.")
    specs[tag_id] = TagSpec(size_m=size_m, T_tag_to_cyl=T_tag_to_cyl)


def parse_cap_tag(
    config: Dict[str, object], length_m: float, is_top: bool
) -> Tuple[int, TagSpec]:
    """Parse a single tag located on a cylinder cap (top or bottom)."""
    tag_id = int(config["id"])
    size_m = float(config["size_m"])
    x_m = float(config.get("x_m", 0.0))
    y_m = float(config.get("y_m", 0.0))
    z_m = 0.5 * length_m if is_top else -0.5 * length_m
    yaw = math.radians(float(config.get("yaw_deg", 0.0)))
    flip = bool(config.get("flip", False))

    Rz = so3_exp(np.array([0.0, 0.0, yaw]))
    x_axis = Rz @ np.array([1.0, 0.0, 0.0])
    z_axis = np.array([0.0, 0.0, 1.0]) if is_top else np.array([0.0, 0.0, -1.0])
    if flip:
        z_axis = -z_axis
    y_axis = np.cross(z_axis, x_axis)
    R = rotation_from_axes(x_axis, y_axis, z_axis)
    t = np.array([x_m, y_m, z_m], dtype=np.float64)
    return tag_id, TagSpec(size_m=size_m, T_tag_to_cyl=make_transform(R, t))


def parse_annulus(
    config: Dict[str, object], length_m: float, is_top: bool
) -> Iterable[Tuple[int, TagSpec]]:
    """Generate TagSpecs for an annulus of tags on a cylinder cap."""
    ids = list(config["ids"])
    if len(ids) < 1:
        raise ValueError("Annulus must contain at least one tag id.")
    radius_m = float(config["radius_m"])
    size_m = float(config["size_m"])
    yaw0 = math.radians(float(config.get("yaw0_deg", 0.0)))
    z_m = 0.5 * length_m if is_top else -0.5 * length_m

    for idx, tag_id in enumerate(ids):
        phi = yaw0 + idx * (2.0 * math.pi / len(ids))
        cos_phi = math.cos(phi)
        sin_phi = math.sin(phi)
        position = np.array([radius_m * cos_phi, radius_m * sin_phi, z_m], dtype=np.float64)

        radial = np.array([cos_phi, sin_phi, 0.0], dtype=np.float64)
        normal = np.array([0.0, 0.0, 1.0], dtype=np.float64)
        if not is_top:
            normal = -normal
        tangent = np.cross(normal, radial)
        R = rotation_from_axes(radial, tangent, normal)
        yield tag_id, TagSpec(size_m=size_m, T_tag_to_cyl=make_transform(R, position))


def parse_ring(config: Dict[str, object], radius_m: float) -> Iterable[Tuple[int, TagSpec]]:
    """Generate TagSpecs for a ring around the barrel of the cylinder."""
    ids = list(config["ids"])
    if len(ids) < 1:
        raise ValueError("Ring must contain at least one tag id.")
    size_m = float(config["size_m"])
    z_m = float(config.get("z_m", 0.0))
    yaw0 = math.radians(float(config.get("yaw0_deg", 0.0)))

    for idx, tag_id in enumerate(ids):
        phi = yaw0 + idx * (2.0 * math.pi / len(ids))
        cos_phi = math.cos(phi)
        sin_phi = math.sin(phi)
        position = np.array([radius_m * cos_phi, radius_m * sin_phi, z_m], dtype=np.float64)
        radial = np.array([cos_phi, sin_phi, 0.0], dtype=np.float64)
        tangent = np.array([-sin_phi, cos_phi, 0.0], dtype=np.float64)
        normal = np.cross(radial, tangent)
        R = rotation_from_axes(tangent, normal, radial)
        yield tag_id, TagSpec(size_m=size_m, T_tag_to_cyl=make_transform(R, position))


def load_rig(path: Path) -> RigSpec:
    """Load rig specification YAML into a RigSpec structure."""
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if data is None:
        raise ValueError(f"Rig file {path} is empty.")

    radius_m = float(data["radius_m"])
    length_m = float(data["length_m"])
    specs: Dict[int, TagSpec] = {}

    if "top" in data:
        tag_id, spec = parse_cap_tag(dict(data["top"]), length_m, is_top=True)
        add_tag_spec(specs, tag_id, spec.size_m, spec.T_tag_to_cyl)

    if "bottom" in data:
        tag_id, spec = parse_cap_tag(dict(data["bottom"]), length_m, is_top=False)
        add_tag_spec(specs, tag_id, spec.size_m, spec.T_tag_to_cyl)

    if "top_annulus" in data:
        for tag_id, spec in parse_annulus(dict(data["top_annulus"]), length_m, is_top=True):
            add_tag_spec(specs, tag_id, spec.size_m, spec.T_tag_to_cyl)

    if "bottom_annulus" in data:
        for tag_id, spec in parse_annulus(dict(data["bottom_annulus"]), length_m, is_top=False):
            add_tag_spec(specs, tag_id, spec.size_m, spec.T_tag_to_cyl)

    if "ring" in data:
        for tag_id, spec in parse_ring(dict(data["ring"]), radius_m):
            add_tag_spec(specs, tag_id, spec.size_m, spec.T_tag_to_cyl)

    if not specs:
        raise ValueError("Rig must specify at least one tag.")

    return RigSpec(radius_m=radius_m, length_m=length_m, tags=specs)


# --- Pose fusion ------------------------------------------------------------ #


def detection_to_transform(detection) -> np.ndarray:
    """Convert a pupil_apriltags detection into a homogeneous transform."""
    R = np.asarray(detection.pose_R, dtype=np.float64)
    t = np.asarray(detection.pose_t, dtype=np.float64).reshape(3)
    return make_transform(R, t)


def fuse_cylinder_pose(
    transforms: Sequence[np.ndarray], weights: Sequence[float]
) -> np.ndarray:
    """Average a list of camera->cylinder transforms."""
    if len(transforms) == 1:
        return transforms[0]
    return avg_poses_SE3(transforms, weights)


# --- Drawing utilities ------------------------------------------------------ #


def _to_int_pts(pts: np.ndarray) -> Optional[List[Tuple[int, int]]]:
    """Convert projected points to integer tuples; return None if any value non-finite."""
    pts = np.asarray(pts).reshape(-1, 2)
    if not np.all(np.isfinite(pts)):
        return None
    return [(int(round(float(x))), int(round(float(y)))) for x, y in pts]


def draw_axes(
    frame: np.ndarray,
    K: np.ndarray,
    dist: np.ndarray,
    T_cyl_to_cam: np.ndarray,
    axis_len: float,
) -> None:
    """Draw RGB axes for the fused cylinder pose."""
    R = T_cyl_to_cam[:3, :3].astype(np.float64)
    t = T_cyl_to_cam[:3, 3].astype(np.float64).reshape(3, 1)
    rvec, _ = cv2.Rodrigues(R)
    origin_3d = np.array([[0.0, 0.0, 0.0]], dtype=np.float64)
    axis_3d = np.array(
        [
            [axis_len, 0.0, 0.0],
            [0.0, axis_len, 0.0],
            [0.0, 0.0, axis_len],
        ],
        dtype=np.float64,
    )
    origin_img, _ = cv2.projectPoints(origin_3d, rvec, t, K, dist)
    axis_img, _ = cv2.projectPoints(axis_3d, rvec, t, K, dist)
    origin_pts = _to_int_pts(origin_img)
    axis_pts = _to_int_pts(axis_img)
    if origin_pts is None or axis_pts is None:
        return
    origin = origin_pts[0]
    H, W = frame.shape[:2]

    def on_screen(pt: Tuple[int, int]) -> bool:
        return -W <= pt[0] <= 2 * W and -H <= pt[1] <= 2 * H

    if not (on_screen(origin) and all(on_screen(pt) for pt in axis_pts)):
        return

    cv2.line(frame, origin, axis_pts[0], (0, 0, 255), 2)  # X axis (red)
    cv2.line(frame, origin, axis_pts[1], (0, 255, 0), 2)  # Y axis (green)
    cv2.line(frame, origin, axis_pts[2], (255, 0, 0), 2)  # Z axis (blue)

def draw_from_last_good(frame, K, dist, last_good_pose, axis_len: float):
    """
    Draws the fused cylinder axes and tag list using the most recent valid pose.
    Prevents 'snapping' or drawing unvalidated poses.
    """
    if last_good_pose is None:
        return
    try:
        T_cyl_to_cam_final = last_good_pose["T_cyl_to_cam"]
    except KeyError:
        return
    draw_axes(frame, K, dist, T_cyl_to_cam_final, axis_len=axis_len)
    ids = last_good_pose.get("used_ids", [])
    cv2.putText(
        frame,
        f"Tags used: {ids}",
        (10, 30),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.7,
        (50, 220, 50),
        2,
        cv2.LINE_AA,
    )


# --- Extrinsics & logging helpers ----------------------------------------- #


def load_extrinsics_yaml(path: Path) -> np.ndarray:
    """Load a 4x4 world-to-camera transform from YAML."""
    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    if data is None:
        raise ValueError(f"Extrinsics file {path} is empty.")
    if isinstance(data, dict):
        for key in ("T_WC", "T", "transform"):
            if key in data:
                matrix = data[key]
                break
        else:
            matrix = data
    else:
        matrix = data
    T = np.array(matrix, dtype=np.float64)
    if T.shape != (4, 4):
        raise ValueError(f"Extrinsics in {path} must be 4x4.")
    return T


def ensure_csv_writer(csv_path: Path) -> tuple[csv.writer, TextIO]:
    """Return CSV writer and open file object if logging is requested."""
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    file_exists = csv_path.exists() and csv_path.stat().st_size > 0
    fp = csv_path.open("a", newline="", encoding="utf-8")
    writer = csv.writer(fp)
    if not file_exists:
        header = [
            "timestamp",
            "frame",
            "used_ids",
            "decision_margins",
            "rvec_cam_x",
            "rvec_cam_y",
            "rvec_cam_z",
            "tvec_cam_x",
            "tvec_cam_y",
            "tvec_cam_z",
        ]
        header.extend(
            [
                "rvec_world_x",
                "rvec_world_y",
                "rvec_world_z",
                "tvec_world_x",
                "tvec_world_y",
                "tvec_world_z",
            ]
        )
        header.append("tilt_cam_deg")
        header.append("tilt_world_deg")
        writer.writerow(header)
        fp.flush()
    return writer, fp


def format_int_list(values: Sequence[int]) -> str:
    """Serialize an integer list into a semicolon-separated string."""
    return ";".join(str(int(v)) for v in values)


def format_float_list(values: Sequence[float]) -> str:
    """Serialize a float list into a semicolon-separated string with three decimals."""
    return ";".join(f"{float(v):.3f}" for v in values)


def compute_tilt_deg(T: np.ndarray, axis: np.ndarray = np.array([0.0, 0.0, 1.0])) -> float:
    """Return tilt angle (degrees) between transformed +Z axis and reference axis."""
    cyl_axis = T[:3, :3] @ axis
    cyl_axis = cyl_axis / np.linalg.norm(cyl_axis)
    dot = float(np.clip(np.dot(cyl_axis, axis), -1.0, 1.0))
    theta = math.degrees(math.acos(dot))
    return min(theta, 180.0 - theta)


def quat_from_R(R: np.ndarray) -> np.ndarray:
    """Convert 3x3 rotation matrix to quaternion [x, y, z, w]."""
    R = np.asarray(R, dtype=np.float64)
    trace = float(np.trace(R))
    if trace > 0.0:
        s = math.sqrt(trace + 1.0) * 2.0
        qw = 0.25 * s
        qx = (R[2, 1] - R[1, 2]) / s
        qy = (R[0, 2] - R[2, 0]) / s
        qz = (R[1, 0] - R[0, 1]) / s
    else:
        if R[0, 0] > R[1, 1] and R[0, 0] > R[2, 2]:
            s = math.sqrt(1.0 + R[0, 0] - R[1, 1] - R[2, 2]) * 2.0
            qx = 0.25 * s
            qy = (R[0, 1] + R[1, 0]) / s
            qz = (R[0, 2] + R[2, 0]) / s
            qw = (R[2, 1] - R[1, 2]) / s
        elif R[1, 1] > R[2, 2]:
            s = math.sqrt(1.0 + R[1, 1] - R[0, 0] - R[2, 2]) * 2.0
            qx = (R[0, 1] + R[1, 0]) / s
            qy = 0.25 * s
            qz = (R[1, 2] + R[2, 1]) / s
            qw = (R[0, 2] - R[2, 0]) / s
        else:
            s = math.sqrt(1.0 + R[2, 2] - R[0, 0] - R[1, 1]) * 2.0
            qx = (R[0, 2] + R[2, 0]) / s
            qy = (R[1, 2] + R[2, 1]) / s
            qz = 0.25 * s
            qw = (R[1, 0] - R[0, 1]) / s
    quat = np.array([qx, qy, qz, qw], dtype=np.float64)
    return quat / np.linalg.norm(quat)


def R_from_quat(quat: np.ndarray) -> np.ndarray:
    """Return rotation matrix from quaternion [x, y, z, w]."""
    qx, qy, qz, qw = quat
    xx, yy, zz = qx * qx, qy * qy, qz * qz
    xy, xz, yz = qx * qy, qx * qz, qy * qz
    wx, wy, wz = qw * qx, qw * qy, qw * qz
    return np.array(
        [
            [1.0 - 2.0 * (yy + zz), 2.0 * (xy - wz), 2.0 * (xz + wy)],
            [2.0 * (xy + wz), 1.0 - 2.0 * (xx + zz), 2.0 * (yz - wx)],
            [2.0 * (xz - wy), 2.0 * (yz + wx), 1.0 - 2.0 * (xx + yy)],
        ],
        dtype=np.float64,
    )


def continuous_quat(quat: np.ndarray, reference: np.ndarray) -> np.ndarray:
    """Flip quaternion sign to stay in the same hemisphere as reference."""
    if reference is None:
        return quat
    if np.dot(quat, reference) < 0.0:
        return -quat
    return quat


def slerp(q0: np.ndarray, q1: np.ndarray, t: float) -> np.ndarray:
    """Spherical linear interpolation between unit quaternions."""
    q0 = q0 / np.linalg.norm(q0)
    q1 = q1 / np.linalg.norm(q1)
    dot = float(np.clip(np.dot(q0, q1), -1.0, 1.0))
    if dot > 0.9995:
        result = q0 + t * (q1 - q0)
        return result / np.linalg.norm(result)
    theta_0 = math.acos(dot)
    sin_theta_0 = math.sin(theta_0)
    theta = theta_0 * t
    sin_theta = math.sin(theta)
    s0 = math.sin(theta_0 - theta) / sin_theta_0
    s1 = sin_theta / sin_theta_0
    return (s0 * q0) + (s1 * q1)


def se3_distance(T_a: np.ndarray, T_b: np.ndarray) -> float:
    """Distance metric combining translation (m) and rotation (rad)."""
    delta = np.linalg.inv(T_a) @ T_b
    trans = float(np.linalg.norm(delta[:3, 3]))
    rot_deg = rot_angle_deg(delta[:3, :3])
    return trans + math.radians(rot_deg)


def wrap_deg180(delta_deg: float) -> float:
    """Wrap a delta angle to [0, 180] for spike detection."""
    wrapped = abs(delta_deg) % 360.0
    return wrapped if wrapped <= 180.0 else 360.0 - wrapped


def apply_ema_pose(
    T_cam_to_cyl: np.ndarray,
    ema_state: Optional[Dict[str, np.ndarray]],
    alpha: float,
) -> Tuple[np.ndarray, Dict[str, np.ndarray]]:
    """Apply exponential moving average in SE(3) (translation + quaternion)."""
    translation = T_cam_to_cyl[:3, 3].astype(np.float64)
    quat = quat_from_R(T_cam_to_cyl[:3, :3])
    if ema_state is None:
        return T_cam_to_cyl, {"t": translation.copy(), "quat": quat.copy()}
    if alpha <= 0.0:
        quat = continuous_quat(quat, ema_state["quat"])
        return T_cam_to_cyl, {"t": translation.copy(), "quat": quat.copy()}

    quat = continuous_quat(quat, ema_state["quat"])
    new_quat = slerp(ema_state["quat"], quat, alpha)
    new_trans = (1.0 - alpha) * ema_state["t"] + alpha * translation

    T_smoothed = np.eye(4, dtype=np.float64)
    T_smoothed[:3, :3] = R_from_quat(new_quat)
    T_smoothed[:3, 3] = new_trans
    return T_smoothed, {"t": new_trans.copy(), "quat": new_quat.copy()}


def select_candidate(
    candidates: List[PoseCandidate],
    last_pose: Optional[Dict[str, np.ndarray]],
) -> PoseCandidate:
    """Choose the candidate closest to the last pose (or lowest error if none)."""
    if not candidates:
        raise ValueError("No candidates to select from.")
    if last_pose is None:
        return min(candidates, key=lambda c: c.mean_error)
    last_T = last_pose["T_cam_to_cyl"]
    return min(candidates, key=lambda c: se3_distance(last_T, c.transform))


def build_pose_record(
    T_cam_to_cyl: np.ndarray,
    used_ids: Sequence[int],
    margins: Sequence[float],
    tilt_cam_deg: float,
    extrinsics_matrix: Optional[np.ndarray],
) -> Dict[str, Optional[np.ndarray]]:
    """Assemble a dictionary holding the final pose outputs for reuse/logging."""
    record: Dict[str, Optional[np.ndarray]] = {}
    T_cam_to_cyl = np.asarray(T_cam_to_cyl, dtype=np.float64)
    T_cyl_to_cam = np.linalg.inv(T_cam_to_cyl)
    rvec_cam, _ = cv2.Rodrigues(T_cyl_to_cam[:3, :3])
    tvec_cam = T_cyl_to_cam[:3, 3]
    tilt_world_deg: Optional[float] = None
    rvec_world: Optional[np.ndarray] = None
    tvec_world: Optional[np.ndarray] = None
    if extrinsics_matrix is not None:
        T_world_to_cyl = np.asarray(extrinsics_matrix, dtype=np.float64) @ T_cam_to_cyl
        rvec_world, _ = cv2.Rodrigues(T_world_to_cyl[:3, :3])
        tvec_world = T_world_to_cyl[:3, 3]
        tilt_world_deg = compute_tilt_deg(T_world_to_cyl)
        record["T_world_to_cyl"] = T_world_to_cyl
    quat_cam = quat_from_R(T_cam_to_cyl[:3, :3])
    record.update(
        {
            "T_cam_to_cyl": T_cam_to_cyl,
            "T_cyl_to_cam": T_cyl_to_cam,
            "quat_cam": quat_cam,
            "used_ids": list(used_ids),
            "decision_margins": list(margins),
            "tilt_cam_deg": float(tilt_cam_deg),
            "tilt_world_deg": tilt_world_deg,
            "rvec_cam": rvec_cam.reshape(3),
            "tvec_cam": tvec_cam.reshape(3),
            "rvec_world": rvec_world.reshape(3) if rvec_world is not None else None,
            "tvec_world": tvec_world.reshape(3) if tvec_world is not None else None,
        }
    )
    return record


def rotation_matrix_to_quaternion(R: np.ndarray) -> Tuple[float, float, float, float]:
    """Convert rotation matrix to quaternion (x, y, z, w)."""
    trace = np.trace(R)
    if trace > 0.0:
        s = math.sqrt(trace + 1.0) * 2.0
        qw = 0.25 * s
        qx = (R[2, 1] - R[1, 2]) / s
        qy = (R[0, 2] - R[2, 0]) / s
        qz = (R[1, 0] - R[0, 1]) / s
    else:
        if R[0, 0] > R[1, 1] and R[0, 0] > R[2, 2]:
            s = math.sqrt(1.0 + R[0, 0] - R[1, 1] - R[2, 2]) * 2.0
            qx = 0.25 * s
            qy = (R[0, 1] + R[1, 0]) / s
            qz = (R[0, 2] + R[2, 0]) / s
            qw = (R[2, 1] - R[1, 2]) / s
        elif R[1, 1] > R[2, 2]:
            s = math.sqrt(1.0 + R[1, 1] - R[0, 0] - R[2, 2]) * 2.0
            qx = (R[0, 1] + R[1, 0]) / s
            qy = 0.25 * s
            qz = (R[1, 2] + R[2, 1]) / s
            qw = (R[0, 2] - R[2, 0]) / s
        else:
            s = math.sqrt(1.0 + R[2, 2] - R[0, 0] - R[1, 1]) * 2.0
            qx = (R[0, 2] + R[2, 0]) / s
            qy = (R[1, 2] + R[2, 1]) / s
            qz = 0.25 * s
            qw = (R[1, 0] - R[0, 1]) / s
    return (float(qx), float(qy), float(qz), float(qw))


def rot_angle_deg(R_delta: np.ndarray) -> float:
    """Return rotation angle (degrees) represented by R_delta."""
    trace = np.clip((np.trace(R_delta) - 1.0) * 0.5, -1.0, 1.0)
    return math.degrees(math.acos(trace))


def se3_deviation(T_reference: np.ndarray, T_candidate: np.ndarray) -> Tuple[float, float]:
    """Return translational (m) and rotational (deg) deviation between two poses."""
    delta = np.linalg.inv(T_reference) @ T_candidate
    trans_err = float(np.linalg.norm(delta[:3, 3]))
    rot_err = rot_angle_deg(delta[:3, :3])
    return trans_err, rot_err


def average_selected(
    transforms: Sequence[np.ndarray], weights: Sequence[float], indices: Sequence[int]
) -> np.ndarray:
    """Average a subset of poses using the provided weights."""
    if not indices:
        raise ValueError("Cannot average an empty set of poses.")
    if len(indices) == 1:
        return transforms[indices[0]]
    subset_transforms = [transforms[i] for i in indices]
    subset_weights = [weights[i] for i in indices]
    return avg_poses_SE3(subset_transforms, subset_weights)


# RANSAC looks for a consensus of tag poses whose translation/rotation stay within
# user-provided thresholds. If multiple minima tie, we return them all for the
# caller to choose the one closest to the previous pose.
def ransac_consensus(
    transforms: Sequence[np.ndarray],
    weights: Sequence[float],
    args: argparse.Namespace,
    rng: random.Random,
) -> List[PoseCandidate]:
    """Return candidate consensus poses ranked by inlier count and mean error."""
    total = len(transforms)
    all_indices = list(range(total))
    base_transform = average_selected(transforms, weights, all_indices)
    base_distances = [
        se3_distance(base_transform, transforms[i]) for i in all_indices
    ]
    base_mean = float(np.mean(base_distances)) if base_distances else 0.0
    base_candidate = PoseCandidate(base_transform, list(all_indices), base_mean)
    best_candidates: List[PoseCandidate] = []
    best_inlier_count = -1
    best_error = float("inf")
    if total < 3 or args.ransac_iters <= 0:
        return [base_candidate]

    eps = 1e-6
    for _ in range(args.ransac_iters):
        sample = rng.sample(all_indices, min(3, total))
        model = average_selected(transforms, weights, sample)
        current_inliers: List[int] = []
        distances: List[float] = []
        for idx in all_indices:
            trans_err, rot_err = se3_deviation(model, transforms[idx])
            if trans_err <= args.ransac_trans and rot_err <= args.ransac_rot:
                current_inliers.append(idx)
                distances.append(trans_err + math.radians(rot_err))
        if not current_inliers:
            continue
        mean_error = float(np.mean(distances)) if distances else 0.0
        candidate = PoseCandidate(
            average_selected(transforms, weights, current_inliers),
            list(current_inliers),
            mean_error,
        )
        if len(current_inliers) > best_inlier_count:
            best_candidates = [candidate]
            best_inlier_count = len(current_inliers)
            best_error = mean_error
        elif len(current_inliers) == best_inlier_count:
            if mean_error < best_error - eps:
                best_candidates = [candidate]
                best_error = mean_error
            elif abs(mean_error - best_error) <= eps:
                if all(se3_distance(existing.transform, candidate.transform) > eps for existing in best_candidates):
                    best_candidates.append(candidate)
    return best_candidates if best_candidates else [base_candidate]


def fuse_with_optional_ransac(
    transforms: Sequence[np.ndarray],
    weights: Sequence[float],
    args: argparse.Namespace,
    rng: random.Random,
) -> List[PoseCandidate]:
    """Return pose candidates after optional RANSAC filtering."""
    count = len(transforms)
    all_indices = list(range(count))
    if count == 0:
        raise ValueError("No poses provided for fusion.")
    if count == 1 or not args.ransac:
        transform = average_selected(transforms, weights, all_indices)
        return [PoseCandidate(transform, all_indices, 0.0)]
    candidates = ransac_consensus(transforms, weights, args, rng)
    if not candidates:
        transform = average_selected(transforms, weights, all_indices)
        return [PoseCandidate(transform, all_indices, 0.0)]
    return candidates


# --- Main application ------------------------------------------------------- #


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Marker-based 6-DoF pose estimation for cylindrical rolls."
    )
    
    parser.add_argument(
        "--camera",
        help="Path to camera calibration YAML (falls back to ../common/calib/calib.yaml if omitted).",
    )
    parser.add_argument("--rig", required=True, help="Path to rig YAML definition.")

    parser.add_argument(
        "--video",
        default="auto",
        help='Video source: "auto" (prefer external, else internal), an index like "0" or "1", a device path (Linux), or a URL (rtsp/http). Default: auto',
    )
    parser.add_argument("--width", type=int, help="Requested capture width (pixels).")
    parser.add_argument("--height", type=int, help="Requested capture height (pixels).")
    parser.add_argument("--fps", type=float, help="Requested capture FPS."
    )


    parser.add_argument("--family", default="tag36h11", help="AprilTag family.")
    parser.add_argument(
        "--axis-len",
        type=float,
        default=0.2,
        help="Length of the rendered axes in meters.",
    )
    parser.add_argument(
        "--extrinsics",
        help="Optional world-to-camera transform (YAML) to report world-frame poses.",
    )
    parser.add_argument(
        "--save-poses",
        help="Optional CSV path to append per-frame poses.",
    )
    parser.add_argument(
        "--print-tilt",
        action="store_true",
        help="Print cylinder tilt angles relative to camera/world Z axes.",
    )
    parser.add_argument(
        "--frames",
        type=int,
        help="Process at most this many frames before exiting.",
    )
    parser.add_argument(
        "--no-overlay",
        action="store_true",
        help="Disable drawing on the video feed (logging/streaming still active).",
    )
    parser.add_argument(
        "--ransac",
        action="store_true",
        help="Enable RANSAC filtering before pose fusion.",
    )
    parser.add_argument(
        "--ransac-iters",
        type=int,
        default=60,
        help="Number of RANSAC iterations (default: 60).",
    )
    parser.add_argument(
        "--ransac-trans",
        type=float,
        default=0.08,
        help="Translational inlier threshold in meters (default: 0.08).",
    )
    parser.add_argument(
        "--ransac-rot",
        type=float,
        default=8.0,
        help="Rotational inlier threshold in degrees (default: 8).",
    )
    parser.add_argument(
        "--stream-udp",
        help='UDP address to stream poses, e.g. "192.168.1.50:6006".',
    )
    parser.add_argument(
        "--stream-rate-hz",
        type=float,
        default=30.0,
        help="Maximum UDP streaming rate in Hz (default: 30.0).",
    )
    parser.add_argument(
        "--ema-alpha",
        type=float,
        default=0.2,
        help="EMA smoothing factor in [0,1]; 0 disables smoothing (default: 0.2).",
    )
    parser.add_argument(
        "--min-inliers",
        type=int,
        default=3,
        help="Minimum inlier tags required before accepting a new pose (default: 3).",
    )
    parser.add_argument(
        "--max-tilt-jump-deg",
        type=float,
        default=8.0,
        help="Reject pose if tilt changes more than this threshold (degrees).",
    )
    parser.add_argument(
        "--ignore-ids",
        help="Comma-separated tag IDs to ignore during fusion.",
    )
    parser.add_argument(
        "--bench",
        action="store_true",
        help="Enable per-frame runtime metrics logging.",
    )
    parser.add_argument(
        "--params",
        default=str(PHASE_B_ROOT / "params.yaml"),
        help="Path to Phase B parameters lockfile (YAML).",
    )

    return parser.parse_args(argv)


def resolve_camera_path(path_str: Optional[str]) -> Path:
    """Resolve the camera calibration path with fallback to common/calib."""
    if path_str:
        candidate = Path(path_str).expanduser()
        if not candidate.is_absolute():
            candidate = (Path.cwd() / candidate).resolve()
        if candidate.exists():
            LOGGER.info("Using camera intrinsics from %s", candidate)
            return candidate
        phase_b_candidate = (PHASE_B_ROOT / path_str).resolve()
        if phase_b_candidate.exists():
            LOGGER.info("Using camera intrinsics from %s", phase_b_candidate)
            return phase_b_candidate
        LOGGER.warning("Camera file not found at %s; attempting common fallback.", candidate)

    if COMMON_CALIB_FALLBACK.exists():
        LOGGER.info("Falling back to common intrinsics at %s", COMMON_CALIB_FALLBACK)
        return COMMON_CALIB_FALLBACK

    raise FileNotFoundError(
        "No calibration file found. Provide --camera or place common/calib/calib.yaml in the repository."
    )


def parse_video_source(source: str) -> int | str:
    """Return an int index if possible, otherwise the original string."""
    try:
        return int(source)
    except ValueError:
        return source


def setup_detector(family: str) -> Detector:
    """Initialise the AprilTag detector."""
    return Detector(
        families=family,
        nthreads=4,
        quad_decimate=1.0,
        quad_sigma=0.0,
        refine_edges=True,
        decode_sharpening=0.25,
    )


# UDP payloads mirror the README schema: camera/world poses in metres, Euler vector
# form plus quaternions, and optional tilt angles for monitoring.
def parse_udp_target(target: str) -> Tuple[str, int]:
    """Parse HOST:PORT into tuple."""
    if ":" not in target:
        raise ValueError("Expected format HOST:PORT.")
    host, port_str = target.rsplit(":", 1)
    if not host:
        raise ValueError("UDP host cannot be empty.")
    try:
        port = int(port_str)
    except ValueError as exc:
        raise ValueError(f"Invalid UDP port: {port_str}") from exc
    if not (0 <= port <= 65535):
        raise ValueError("UDP port must be between 0 and 65535.")
    return host, port
def _open_capture_with_settings(source: int | str, args: argparse.Namespace) -> Optional[cv2.VideoCapture]:
    """Try to open a capture and apply width/height/fps if requested. Return cap or None."""
    cap = cv2.VideoCapture(source)
    if not cap.isOpened():
        return None

    # Apply optional settings
    if getattr(args, "width", None) is not None:
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, float(args.width))
    if getattr(args, "height", None) is not None:
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, float(args.height))
    if getattr(args, "fps", None) is not None:
        cap.set(cv2.CAP_PROP_FPS, float(args.fps))

    # Verify we can actually grab a frame
    ok, _ = cap.read()
    if not ok:
        cap.release()
        return None

    actual_w = cap.get(cv2.CAP_PROP_FRAME_WIDTH)
    actual_h = cap.get(cv2.CAP_PROP_FRAME_HEIGHT)
    actual_fps = cap.get(cv2.CAP_PROP_FPS)
    req_w = getattr(args, "width", None) if getattr(args, "width", None) is not None else "default"
    req_h = getattr(args, "height", None) if getattr(args, "height", None) is not None else "default"
    req_fps = getattr(args, "fps", None) if getattr(args, "fps", None) is not None else "default"
    LOGGER.info(
        "Capture opened on %r (requested: %sx%s @ %s FPS, actual: %dx%d @ %.2f FPS)",
        source,
        req_w,
        req_h,
        req_fps,
        int(actual_w),
        int(actual_h),
        float(actual_fps),
    )
    return cap


def _auto_select_camera(args: argparse.Namespace) -> Tuple[Optional[cv2.VideoCapture], Optional[int | str]]:
    """
    Prefer external cameras by trying indices 1..5 first, then fall back to 0.
    (On macOS, device indices are the usual way; on Linux, user may pass /dev/videoN.)
    """
    candidate_indices: List[int | str] = [1, 2, 3, 4, 5, 0]
    for src in candidate_indices:
        cap = _open_capture_with_settings(src, args)
        if cap is not None:
            LOGGER.info("Auto-selected camera source: %s", src)
            return cap, src
    return None, None


def run(argv: Optional[Sequence[str]] = None) -> int:
    """Main entry-point for CLI execution."""
    set_deterministic()
    t0 = perf_counter()
    global last_axis_cam, last_tilt_cam
    args = parse_args(argv)

    bench_enabled = bool(getattr(args, "bench", False))
    metrics_fh: Optional[TextIO] = None
    metrics_writer: Optional[csv.writer] = None
    flush_every = 15
    flush_ctr = 0
    t_frame = Tock() if bench_enabled else None
    t_stage = Tock() if bench_enabled else None
    bench_video_src = str(args.video) if hasattr(args, "video") else ""
    bench_width = args.width if getattr(args, "width", None) is not None else ""
    bench_height = args.height if getattr(args, "height", None) is not None else ""
    if bench_enabled:
        print("⚙️  Benchmark logging → phase_b/debug_metrics.csv")
        metrics_path = PROJECT_ROOT / "phase_b" / "debug_metrics.csv"
        metrics_path.parent.mkdir(parents=True, exist_ok=True)
        metrics_fh, metrics_writer = _open_metrics_writer(str(metrics_path))

    try:
        camera_path = resolve_camera_path(args.camera)
    except FileNotFoundError as exc:
        LOGGER.error("%s", exc)
        return 1

    rig_path = Path(args.rig)
    if not rig_path.exists():
        LOGGER.error("Rig file not found: %s", rig_path)
        return 1

    K, dist = load_camera_intrinsics(camera_path)
    rig = load_rig(rig_path)
    LOGGER.info(
        "Loaded rig with %d tags (radius %.3f m, length %.3f m).",
        len(rig.tags),
        rig.radius_m,
        rig.length_m,
    )

    detector = setup_detector(args.family)
        # Open video according to --video
    video_opt = str(args.video).lower() if isinstance(args.video, str) else args.video
    if video_opt == "auto":
        cap, chosen_src = _auto_select_camera(args)
        if cap is None:
            LOGGER.error('Auto camera selection failed (tried indices 1..5, then 0).')
            return 1
        LOGGER.info("Using video source: %s", chosen_src)
    else:
        video_source = parse_video_source(args.video)
        cap = _open_capture_with_settings(video_source, args)
        if cap is None:
            LOGGER.error("Unable to open video source: %s", args.video)
            return 1
        LOGGER.info("Using video source: %s", video_source)


    rng = random.Random()

    extrinsics_matrix: Optional[np.ndarray] = None
    if args.extrinsics:
        extr_candidate = Path(args.extrinsics).expanduser()
        if not extr_candidate.is_absolute():
            extr_candidate = (Path.cwd() / extr_candidate).resolve()
        if not extr_candidate.exists():
            alt = (PHASE_B_ROOT / args.extrinsics).resolve()
            if alt.exists():
                extr_candidate = alt
        if extr_candidate.exists():
            try:
                extrinsics_matrix = load_extrinsics_yaml(extr_candidate)
                LOGGER.info("Using extrinsics from %s", extr_candidate)
            except Exception as exc:
                LOGGER.warning("Failed to load extrinsics from %s: %s", extr_candidate, exc)
                extrinsics_matrix = None
        else:
            LOGGER.warning("Extrinsics file not found: %s", args.extrinsics)

    csv_writer: Optional[csv.writer] = None
    csv_fp: Optional[TextIO] = None
    if args.save_poses:
        csv_candidate = Path(args.save_poses).expanduser()
        if not csv_candidate.is_absolute():
            csv_candidate = (Path.cwd() / csv_candidate).resolve()
        try:
            csv_writer, csv_fp = ensure_csv_writer(csv_candidate)
            LOGGER.info("Appending poses to %s", csv_candidate)
        except OSError as exc:
            LOGGER.error("Failed to open pose log %s: %s", csv_candidate, exc)
            csv_writer = None
            csv_fp = None

    udp_sock: Optional[socket.socket] = None
    udp_target: Optional[Tuple[str, int]] = None
    stream_period = 1.0 / max(args.stream_rate_hz, 1e-3)
    next_stream_time = 0.0
    if args.stream_udp:
        try:
            host, port = parse_udp_target(args.stream_udp)
            udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            udp_target = (host, port)
            LOGGER.info("Streaming UDP to %s:%d", host, port)
        except (ValueError, OSError) as exc:
            LOGGER.error("Unable to initialise UDP streaming: %s", exc)
            if udp_sock:
                udp_sock.close()
            udp_sock = None
            udp_target = None

    ema_alpha = max(0.0, min(1.0, float(args.ema_alpha)))
    min_inliers = max(0, int(args.min_inliers))
    max_tilt_jump_deg = max(0.0, float(args.max_tilt_jump_deg))
    ema_state: Optional[Dict[str, np.ndarray]] = None
    last_good_pose: Optional[Dict[str, Optional[np.ndarray]]] = None
    ignore_ids: Set[int] = set()
    if args.ignore_ids:
        for token in args.ignore_ids.split(","):
            token = token.strip()
            if not token:
                continue
            try:
                ignore_ids.add(int(token))
            except ValueError:
                LOGGER.warning("Invalid tag id in --ignore-ids: %s", token)
    if ignore_ids:
        LOGGER.info("Ignoring tag ids: %s", sorted(ignore_ids))

    unique_sizes = sorted({spec.size_m for spec in rig.tags.values()})
    LOGGER.info("Expecting tag sizes (m): %s", ", ".join(f"{s:.3f}" for s in unique_sizes))

    cv2.namedWindow("phase_b_tags", cv2.WINDOW_NORMAL)
    last_used_ids: List[int] = []
    frame_idx = 0
    frame_count = 0

    try:
        while True:
            dt_detect_ms = dt_pose_ms = dt_ransac_ms = dt_fuse_ms = dt_hud_ms = 0.0
            n_tags = 0
            n_inliers = 0
            inlier_ratio = ""
            reproj_mean_px = ""
            if bench_enabled and t_frame and t_stage:
                t_frame.reset()
                t_stage.reset()

            ret, frame = cap.read()
            if not ret:
                LOGGER.warning("Video stream ended or frame grab failed.")
                break

            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            detections: Dict[int, Tuple[np.ndarray, float]] = {}
            for size_m in unique_sizes:
                dets = detector.detect(
                    gray,
                    estimate_tag_pose=True,
                    camera_params=(
                        float(K[0, 0]),
                        float(K[1, 1]),
                        float(K[0, 2]),
                        float(K[1, 2]),
                    ),
                    tag_size=size_m,
                )
                for det in dets:
                    tag_id = det.tag_id
                    if ignore_ids and tag_id in ignore_ids:
                        continue
                    if tag_id not in rig.tags:
                        continue
                    spec = rig.tags[tag_id]
                    if not math.isclose(spec.size_m, size_m, rel_tol=1e-3, abs_tol=1e-6):
                        continue
                    current = detections.get(tag_id)
                    if current is None or det.decision_margin > current[1]:
                        T_tag_to_cam = detection_to_transform(det)
                        detections[tag_id] = (T_tag_to_cam, det.decision_margin)

            n_tags = len(detections)
            if bench_enabled and t_stage:
                dt_detect_ms = t_stage.ms()

            status = "OK"
            pose_record: Optional[Dict[str, Optional[np.ndarray]]] = None
            current_inlier_indices: List[int] = []
            current_inlier_ids: List[int] = []
            current_margins: List[float] = []
            total_candidates = 0

            if detections:
                transforms_cam_to_cyl: List[np.ndarray] = []
                weights: List[float] = []
                candidate_ids: List[int] = []
                decision_margins: List[float] = []

                for tag_id, (T_tag_to_cam, margin) in detections.items():
                    spec = rig.tags[tag_id]
                    T_cam_to_tag = np.linalg.inv(T_tag_to_cam)
                    T_cam_to_cyl = T_cam_to_tag @ spec.T_tag_to_cyl
                    transforms_cam_to_cyl.append(T_cam_to_cyl)
                    weights.append(max(float(margin), 0.1))
                    candidate_ids.append(tag_id)
                    decision_margins.append(float(margin))

                if bench_enabled and t_stage:
                    dt_pose_ms = t_stage.ms()

                total_candidates = len(transforms_cam_to_cyl)
                if transforms_cam_to_cyl:
                    try:
                        candidates = fuse_with_optional_ransac(transforms_cam_to_cyl, weights, args, rng)
                    except Exception as exc:  # pylint: disable=broad-except
                        lower = str(exc).lower()
                        fallback: List[PoseCandidate] = []
                        raw_candidates = getattr(exc, "candidates", None)
                        if raw_candidates:
                            for item in raw_candidates:
                                try:
                                    transform = np.asarray(item["transform"], dtype=np.float64)
                                    inliers = list(item.get("inliers", []))
                                    mean_error = float(item.get("mean_error", 0.0))
                                    fallback.append(PoseCandidate(transform, inliers, mean_error))
                                except Exception:  # best-effort recovery
                                    continue
                        if fallback and "more than one" in lower:
                            candidates = fallback
                        else:
                            LOGGER.warning("Fusion error: %s", exc)
                            candidates = []

                    if candidates:
                        selected_candidate = select_candidate(candidates, last_good_pose)
                        if len(candidates) > 1:
                            LOGGER.debug(
                                "Multiple minima detected; chosen candidate with %d inliers",
                                len(selected_candidate.inliers),
                            )
                        current_inlier_indices = selected_candidate.inliers or list(range(total_candidates))
                        fused_cam_to_cyl = selected_candidate.transform
                        fused_cyl_to_cam = np.linalg.inv(fused_cam_to_cyl)

                        # --- BEGIN axis direction + tilt normalization ---
                        axis_obj = np.array([0.0, 0.0, 1.0])
                        axis_cam = fused_cam_to_cyl[:3, :3] @ axis_obj
                        if last_axis_cam is not None and float(np.dot(axis_cam, last_axis_cam)) < 0.0:
                            axis_cam = -axis_cam
                        last_axis_cam = axis_cam

                        def _tilt_deg(vec: np.ndarray, z_ref: np.ndarray) -> float:
                            vec_n = vec / np.linalg.norm(vec)
                            z_n = z_ref / np.linalg.norm(z_ref)
                            angle = np.degrees(np.arccos(np.clip(np.dot(vec_n, z_n), -1.0, 1.0)))
                            return min(angle, 180.0 - angle)

                        z_cam = np.array([0.0, 0.0, 1.0])
                        raw_tilt_cam_deg = _tilt_deg(axis_cam, z_cam)
                        # --- END axis direction + tilt normalization ---
                        current_inlier_ids = [candidate_ids[i] for i in current_inlier_indices]
                        current_margins = [decision_margins[i] for i in current_inlier_indices]
                        n_inliers = len(current_inlier_ids)

                        if len(current_inlier_ids) < min_inliers:
                            if last_good_pose is not None:
                                status = "HOLD_PREV_POSE"
                                pose_record = last_good_pose
                            else:
                                status = "NO_POSE"
                        elif last_good_pose is not None:
                            tilt_jump = wrap_deg180(raw_tilt_cam_deg - last_good_pose["tilt_cam_deg"])
                            if tilt_jump > max_tilt_jump_deg:
                                status = "REJECT_SPIKE"
                                pose_record = last_good_pose

                        if status == "OK":
                            fused_cam_to_cyl, ema_state = apply_ema_pose(
                                fused_cam_to_cyl, ema_state, ema_alpha
                            )
                            fused_cyl_to_cam = np.linalg.inv(fused_cam_to_cyl)
                            smooth_tilt_cam_deg = compute_tilt_deg(fused_cyl_to_cam)
                            pose_record = build_pose_record(
                                fused_cam_to_cyl,
                                current_inlier_ids,
                                current_margins,
                                smooth_tilt_cam_deg,
                                extrinsics_matrix,
                            )
                            pose_record["quat_cam"] = continuous_quat(
                                pose_record["quat_cam"],
                                last_good_pose["quat_cam"] if last_good_pose else None,
                            )
                            if ema_state is not None:
                                ema_state["quat"] = pose_record["quat_cam"].copy()
                                ema_state["t"] = pose_record["T_cam_to_cyl"][:3, 3].copy()
                            last_good_pose = pose_record
                        elif status in {"HOLD_PREV_POSE", "REJECT_SPIKE"}:
                            pose_record = last_good_pose
                        else:
                            pose_record = None
                    else:
                        status = "NO_POSE"
                else:
                    status = "NO_POSE"
                if bench_enabled and t_stage:
                    dt_ransac_ms = t_stage.ms()
            else:
                status = "NO_POSE"

            if bench_enabled and t_stage:
                dt_fuse_ms = t_stage.ms()

            if status == "NO_POSE" and last_good_pose is not None and len(current_inlier_ids) < min_inliers:
                status = "HOLD_PREV_POSE"
                pose_record = last_good_pose

            if pose_record is None:
                if status == "NO_POSE":
                    LOGGER.info("frame=%d status=NO_POSE", frame_idx)
                if not args.no_overlay:
                    cv2.putText(
                        frame,
                        "No rig tags detected",
                        (10, 30),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.7,
                        (0, 0, 255),
                        2,
                        cv2.LINE_AA,
                    )
            else:
                final_used_ids = pose_record["used_ids"]
                final_margins = pose_record["decision_margins"]
                tilt_cam_deg = pose_record["tilt_cam_deg"]
                tilt_world_deg = pose_record["tilt_world_deg"]
                T_cyl_to_cam_final = pose_record["T_cyl_to_cam"]
                rvec_cam = pose_record["rvec_cam"].reshape(3)
                tvec_cam = pose_record["tvec_cam"].reshape(3)
                rvec_world = pose_record["rvec_world"]
                tvec_world = pose_record["tvec_world"]

                if not args.no_overlay:
                    draw_axes(frame, K, dist, T_cyl_to_cam_final, axis_len=float(args.axis_len))

                last_tilt_cam = tilt_cam_deg

                log_msg = (
                    f"frame={frame_idx} inliers={len(current_inlier_indices)}/{total_candidates} "
                    f"used={final_used_ids}"
                )
                if status != "OK":
                    log_msg += f" status={status}"
                if args.print_tilt:
                    log_msg += f" tilt_cam={tilt_cam_deg:.1f}deg"
                    if tilt_world_deg is not None:
                        log_msg += f" tilt_world={tilt_world_deg:.1f}deg"
                LOGGER.info(log_msg)

                if csv_writer and csv_fp:
                    timestamp = time.time()
                    row: List[object] = [
                        f"{timestamp:.6f}",
                        frame_idx,
                        format_int_list(final_used_ids),
                        format_float_list(final_margins),
                    ]
                    row.extend(float(v) for v in rvec_cam.reshape(-1))
                    row.extend(float(v) for v in tvec_cam.reshape(-1))
                    if rvec_world is not None and tvec_world is not None:
                        row.extend(float(v) for v in rvec_world.reshape(-1))
                        row.extend(float(v) for v in tvec_world.reshape(-1))
                    else:
                        row.extend([""] * 6)
                    row.append(f"{tilt_cam_deg:.3f}")
                    row.append(f"{tilt_world_deg:.3f}" if tilt_world_deg is not None else "")
                    csv_writer.writerow(row)
                    csv_fp.flush()

                if udp_sock and udp_target:
                    now = time.monotonic()
                    if now >= next_stream_time:
                        payload: Dict[str, object] = {
                            "ts": time.time(),
                            "frame": frame_idx,
                            "status": status,
                            "used_ids": final_used_ids,
                            "decision_margins": [float(m) for m in final_margins],
                            "cam": {
                                "t_m": [float(v) for v in tvec_cam.reshape(-1)],
                                "rvec": [float(v) for v in rvec_cam.reshape(-1)],
                                "quat_xyzw": list(rotation_matrix_to_quaternion(T_cyl_to_cam_final[:3, :3])),
                            },
                        }
                        world_T = pose_record.get("T_world_to_cyl")
                        if world_T is not None and rvec_world is not None and tvec_world is not None:
                            payload["world"] = {
                                "t_m": [float(v) for v in tvec_world.reshape(-1)],
                                "rvec": [float(v) for v in rvec_world.reshape(-1)],
                                "quat_xyzw": list(rotation_matrix_to_quaternion(world_T[:3, :3])),
                            }
                        if args.print_tilt:
                            payload["tilt_cam_deg"] = float(tilt_cam_deg)
                            if tilt_world_deg is not None:
                                payload["tilt_world_deg"] = float(tilt_world_deg)
                        try:
                            data = json.dumps(payload).encode("utf-8")
                            udp_sock.sendto(data, udp_target)
                            LOGGER.debug(
                                "udp -> %s:%d bytes=%d",
                                udp_target[0],
                                udp_target[1],
                                len(data),
                            )
                        except OSError as exc:
                            LOGGER.warning("UDP send failed: %s", exc)
                        next_stream_time = now + stream_period

                if final_used_ids != last_used_ids:
                    LOGGER.info("Tags used for fusion: %s", final_used_ids)
                    last_used_ids = final_used_ids

                if not args.no_overlay:
                    cv2.putText(
                        frame,
                        f"Tags used: {final_used_ids}",
                        (10, 30),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.7,
                        (50, 220, 50),
                        2,
                        cv2.LINE_AA,
                    )

            if total_candidates > 0:
                inlier_ratio = f"{n_inliers / float(total_candidates):.3f}"
            else:
                inlier_ratio = ""

            if bench_enabled and t_stage:
                dt_hud_ms = t_stage.ms()

            cv2.imshow("phase_b_tags", frame)
            key = cv2.waitKey(1) & 0xFF
            if bench_enabled and metrics_writer and metrics_fh and t_frame:
                dt_frame_ms = t_frame.ms()
                fps_inst = 1000.0 / dt_frame_ms if dt_frame_ms > 0 else 0.0
                timestamp_iso = _dt.datetime.now().isoformat(timespec="milliseconds")
                metrics_writer.writerow(
                    [
                        timestamp_iso,
                        frame_idx,
                        f"{dt_frame_ms:.3f}",
                        f"{fps_inst:.2f}",
                        f"{dt_detect_ms:.3f}",
                        f"{dt_pose_ms:.3f}",
                        f"{dt_ransac_ms:.3f}",
                        f"{dt_fuse_ms:.3f}",
                        f"{dt_hud_ms:.3f}",
                        n_tags,
                        n_inliers,
                        inlier_ratio,
                        reproj_mean_px,
                        bench_video_src,
                        bench_width,
                        bench_height,
                    ]
                )
                flush_ctr += 1
                if flush_ctr % flush_every == 0:
                    metrics_fh.flush()
            if key == 27:  # ESC
                LOGGER.info("ESC pressed, exiting.")
                break
            frame_idx += 1
            frame_count += 1
            if args.frames is not None and frame_idx >= args.frames:
                LOGGER.info("Reached frame limit (%d); exiting.", args.frames)
                break
    except KeyboardInterrupt:
        LOGGER.info("Interrupted by user.")
    finally:
        cap.release()
        cv2.destroyAllWindows()
        if csv_fp:
            csv_fp.close()
        if udp_sock:
            udp_sock.close()
        if metrics_fh:
            metrics_fh.flush()
            metrics_fh.close()
        elapsed = perf_counter() - t0
        avg_fps = (frame_count / elapsed) if elapsed > 0 else 0.0
        print(f"[wall] elapsed={elapsed:.2f} frames={frame_count} avg_fps={avg_fps:.2f}")

    return 0


def main() -> None:
    """Configure logging and run the application."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )
    exit_code = run()
    if exit_code != 0:
        raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
