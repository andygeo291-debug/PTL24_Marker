"""Rigid-body transform utilities for AprilTag world-frame conversions."""

from __future__ import annotations

import math
from typing import Iterable, Tuple

import cv2
import numpy as np


def Rx(angle: float) -> np.ndarray:
    """Rotation about X-axis (roll)."""
    c, s = math.cos(angle), math.sin(angle)
    return np.array([[1.0, 0.0, 0.0], [0.0, c, -s], [0.0, s, c]], dtype=float)


def Ry(angle: float) -> np.ndarray:
    """Rotation about Y-axis (pitch)."""
    c, s = math.cos(angle), math.sin(angle)
    return np.array([[c, 0.0, s], [0.0, 1.0, 0.0], [-s, 0.0, c]], dtype=float)


def Rz(angle: float) -> np.ndarray:
    """Rotation about Z-axis (yaw)."""
    c, s = math.cos(angle), math.sin(angle)
    return np.array([[c, -s, 0.0], [s, c, 0.0], [0.0, 0.0, 1.0]], dtype=float)


def compose_T(R: np.ndarray, t: Iterable[float]) -> np.ndarray:
    """Create a 4×4 homogeneous transform from rotation and translation."""
    T = np.eye(4, dtype=float)
    T[:3, :3] = R
    T[:3, 3] = np.asarray(t, dtype=float).reshape(3)
    return T


def rvec_tvec_to_T(rvec: np.ndarray, tvec: np.ndarray) -> np.ndarray:
    """Convert OpenCV Rodrigues rotation + translation vectors into a 4×4 transform."""
    R, _ = cv2.Rodrigues(rvec)
    return compose_T(R, tvec.reshape(3))


def T_to_rpy_xyz(T: np.ndarray) -> Tuple[float, float, float, float, float, float]:
    """Extract roll, pitch, yaw (intrinsic ZYX) and translation from a 4×4 transform."""
    R = T[:3, :3]
    # Guard against numerical issues around asin domain.
    sy = -R[2, 0]
    sy = float(max(min(sy, 1.0), -1.0))
    pitch = math.asin(sy)

    # Detect gimbal lock when cos(pitch) ~ 0.
    if abs(math.cos(pitch)) < 1e-6:
        roll = math.atan2(-R[0, 1], R[1, 1])
        yaw = 0.0
    else:
        roll = math.atan2(R[2, 1], R[2, 2])
        yaw = math.atan2(R[1, 0], R[0, 0])

    x, y, z = T[:3, 3]
    return roll, pitch, yaw, float(x), float(y), float(z)


def build_T_WC_from_config(pose: dict[str, float]) -> np.ndarray:
    """Construct T_W<-C from a config world_pose dictionary."""
    yaw = pose.get("yaw", 0.0)
    pitch = pose["pitch"]
    roll = pose.get("roll", 0.0)
    x = pose.get("x", 0.0)
    y = pose.get("y", 0.0)
    rho = pose["rho"]

    R_wc = Rz(yaw) @ Ry(pitch) @ Rx(roll)
    return compose_T(R_wc, [x, y, rho])
