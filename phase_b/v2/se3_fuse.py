"""Self-contained SE(3) exponential/log utilities for weighted fusion."""

from __future__ import annotations

import math
from typing import Iterable, Sequence

import numpy as np

__all__ = ["log_se3", "exp_se3", "inv_se3", "weighted_average_se3"]

_SO3_EPS = 1e-9


def _skew(vec: np.ndarray) -> np.ndarray:
    vec = np.asarray(vec, dtype=np.float64).reshape(3)
    x, y, z = vec
    return np.array([[0.0, -z, y], [z, 0.0, -x], [-y, x, 0.0]], dtype=np.float64)


def exp_so3(omega: np.ndarray) -> np.ndarray:
    """Rodrigues' formula with small-angle handling."""
    omega = np.asarray(omega, dtype=np.float64).reshape(3)
    theta = float(np.linalg.norm(omega))
    if theta < _SO3_EPS:
        K = _skew(omega)
        return np.eye(3) + K + 0.5 * (K @ K)
    axis = omega / theta
    K = _skew(axis)
    s = math.sin(theta)
    c = math.cos(theta)
    return np.eye(3) + s * K + (1.0 - c) * (K @ K)


def log_so3(R: np.ndarray) -> np.ndarray:
    """Inverse Rodrigues with numeric guard rails."""
    R = np.asarray(R, dtype=np.float64).reshape(3, 3)
    trace = np.clip((np.trace(R) - 1.0) * 0.5, -1.0, 1.0)
    theta = math.acos(trace)
    if theta < _SO3_EPS:
        return 0.5 * np.array([R[2, 1] - R[1, 2], R[0, 2] - R[2, 0], R[1, 0] - R[0, 1]])
    denom = 2.0 * math.sin(theta)
    return (theta / denom) * np.array([R[2, 1] - R[1, 2], R[0, 2] - R[2, 0], R[1, 0] - R[0, 1]])


def left_jacobian_SO3(omega: np.ndarray) -> np.ndarray:
    """SO(3) left Jacobian J(omega)."""
    omega = np.asarray(omega, dtype=np.float64).reshape(3)
    theta = float(np.linalg.norm(omega))
    K = _skew(omega)
    I = np.eye(3)
    if theta < _SO3_EPS:
        return I + 0.5 * K + (1.0 / 12.0) * (K @ K)
    theta2 = theta * theta
    return I + ((1.0 - math.cos(theta)) / theta2) * K + ((theta - math.sin(theta)) / (theta2 * theta)) * (K @ K)


def left_jacobian_SO3_inv(omega: np.ndarray) -> np.ndarray:
    """Inverse of the SO(3) left Jacobian."""
    omega = np.asarray(omega, dtype=np.float64).reshape(3)
    theta = float(np.linalg.norm(omega))
    K = _skew(omega)
    I = np.eye(3)
    if theta < _SO3_EPS:
        return I - 0.5 * K + (1.0 / 12.0) * (K @ K)
    half = 0.5
    theta2 = theta * theta
    cot_half = math.cos(theta / 2.0) / math.sin(theta / 2.0)
    return I - half * K + ((1.0 / theta2) * (1.0 - half * theta * cot_half)) * (K @ K)


def exp_se3(xi: np.ndarray) -> np.ndarray:
    """Exponential map from se(3) to SE(3). xi=[vx,vy,vz, wx,wy,wz]."""
    xi = np.asarray(xi, dtype=np.float64).reshape(6)
    rho = xi[:3]
    omega = xi[3:]
    R = exp_so3(omega)
    V = left_jacobian_SO3(omega)
    t = V @ rho
    T = np.eye(4, dtype=np.float64)
    T[:3, :3] = R
    T[:3, 3] = t
    return T


def log_se3(T: np.ndarray) -> np.ndarray:
    """Logarithm map from SE(3) to se(3)."""
    T = np.asarray(T, dtype=np.float64).reshape(4, 4)
    R = T[:3, :3]
    t = T[:3, 3]
    omega = log_so3(R)
    V_inv = left_jacobian_SO3_inv(omega)
    rho = V_inv @ t
    return np.concatenate([rho, omega])


def inv_se3(T: np.ndarray) -> np.ndarray:
    """Return SE(3) inverse."""
    T = np.asarray(T, dtype=np.float64).reshape(4, 4)
    R = T[:3, :3]
    t = T[:3, 3]
    T_inv = np.eye(4, dtype=np.float64)
    R_T = R.T
    T_inv[:3, :3] = R_T
    T_inv[:3, 3] = -R_T @ t
    return T_inv


def weighted_average_se3(
    transforms: Sequence[np.ndarray],
    weights: Iterable[float],
    reference: np.ndarray,
) -> np.ndarray:
    """Return a left-invariant weighted average around reference pose."""
    if not transforms:
        raise ValueError("Cannot fuse an empty list of transforms.")
    weights = np.asarray(list(weights), dtype=np.float64)
    if weights.ndim != 1 or weights.size != len(transforms):
        raise ValueError("weights must align with transforms.")
    if np.any(weights < 0.0):
        raise ValueError("weights must be non-negative.")
    total = float(weights.sum())
    if total <= 0.0:
        raise ValueError("weights must sum to a positive value.")
    weights = weights / total
    reference = np.asarray(reference, dtype=np.float64).reshape(4, 4)
    T_ref_inv = inv_se3(reference)
    xi = np.zeros(6, dtype=np.float64)
    for T, w in zip(transforms, weights):
        delta = np.asarray(T, dtype=np.float64) @ T_ref_inv
        xi += w * log_se3(delta)
    return exp_se3(xi) @ reference


def _self_test() -> None:
    ident = np.eye(4, dtype=np.float64)
    assert np.allclose(exp_se3(np.zeros(6)), ident, atol=1e-9)
    xi = np.array([0.01, -0.02, 0.0, 0.003, 0.002, -0.001], dtype=np.float64)
    T = exp_se3(xi)
    xi_rt = log_se3(T)
    assert np.allclose(xi, xi_rt, atol=1e-9)
    T1 = exp_se3(np.array([0.01, 0.0, 0.0, 0.0, 0.005, 0.0]))
    T2 = exp_se3(np.array([-0.01, 0.0, 0.0, 0.0, -0.005, 0.0]))
    avg = weighted_average_se3([T1, T2], [0.6, 0.4], ident)
    xi_avg = log_se3(avg)
    expect = 0.6 * log_se3(T1) + 0.4 * log_se3(T2)
    assert np.allclose(xi_avg, expect, atol=1e-9)


if __name__ == "__main__":
    _self_test()
