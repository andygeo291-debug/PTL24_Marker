"""Sway axis model utilities."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import yaml


@dataclass
class SwayModel:
    """Compact representation of a sway axis."""

    p0: np.ndarray  # reference point (3,)
    d: np.ndarray  # unit direction vector (3,)


def fit_sway_axis_from_positions(positions: np.ndarray) -> SwayModel:
    """Fit a sway axis line to sampled positions."""
    if positions.ndim != 2 or positions.shape[1] != 3:
        raise ValueError("positions must be an (N, 3) array.")
    if positions.shape[0] < 2:
        raise ValueError("At least two samples are required to fit a sway axis.")

    p0 = positions.mean(axis=0)
    centered = positions - p0
    covariance = centered.T @ centered
    eigenvalues, eigenvectors = np.linalg.eigh(covariance)
    dominant = eigenvectors[:, np.argmax(eigenvalues)]
    norm = np.linalg.norm(dominant)
    if norm <= 0:
        raise ValueError("Unable to determine sway axis direction (zero norm).")
    direction = dominant / norm
    return SwayModel(p0=p0, d=direction)


def save_sway_model_yaml(model: SwayModel, path: str) -> None:
    """Persist a sway model to YAML."""
    data = {
        "sway_model": {
            "p0": model.p0.tolist(),
            "d": model.d.tolist(),
        }
    }
    with open(path, "w", encoding="utf-8") as fh:
        yaml.safe_dump(data, fh, sort_keys=False)


def load_sway_model_yaml(path: str) -> SwayModel:
    """Load a sway model from YAML."""
    with open(path, "r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    model_data = data.get("sway_model")
    if not model_data:
        raise ValueError("YAML does not contain 'sway_model' section.")
    p0 = np.asarray(model_data["p0"], dtype=float)
    d = np.asarray(model_data["d"], dtype=float)
    if p0.shape != (3,) or d.shape != (3,):
        raise ValueError("sway_model entries must be 3-element vectors.")
    norm = np.linalg.norm(d)
    if norm <= 0:
        raise ValueError("Direction vector must be non-zero.")
    return SwayModel(p0=p0, d=d / norm)
