"""Configuration and calibration I/O helpers for AprilTag world-frame workflows."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Tuple

import numpy as np

try:
    import yaml
except ModuleNotFoundError as exc:
    raise ModuleNotFoundError(
        "PyYAML is required. Install dependencies with 'pip install -r requirements.txt'."
    ) from exc


def _read_text(path: os.PathLike[str] | str) -> str:
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read()


def _write_text(path: os.PathLike[str] | str, data: str) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(data)


def load_config(path: os.PathLike[str] | str) -> dict[str, Any]:
    """Load a YAML or JSON config file."""
    text = _read_text(path)
    suffix = Path(path).suffix.lower()
    if suffix in {".json"}:
        return json.loads(text)
    return yaml.safe_load(text)


def save_yaml(path: os.PathLike[str] | str, data: Any) -> None:
    """Write data to YAML."""
    _write_text(path, yaml.safe_dump(data, sort_keys=False))


def save_json(path: os.PathLike[str] | str, data: Any) -> None:
    """Write data to JSON."""
    _write_text(path, json.dumps(data, indent=2))


def load_intrinsics_from_config(config: dict[str, Any]) -> Tuple[np.ndarray, np.ndarray]:
    """Extract calibration intrinsics/distortion arrays from a configuration mapping."""
    cam = config.get("camera", {})
    intr = cam.get("intrinsics")
    if intr is None:
        raise KeyError("Config is missing camera.intrinsics section.")
    K = np.array(intr["K"], dtype=float)
    if K.shape != (3, 3):
        raise ValueError("camera.intrinsics.K must be 3x3.")
    dist = np.array(intr.get("dist", []), dtype=float).reshape(-1, 1)
    return K, dist


def load_world_pose(config: dict[str, Any]) -> dict[str, float]:
    """Return the world pose dictionary for the camera with validation."""
    pose = config.get("camera", {}).get("world_pose")
    if pose is None:
        raise KeyError("Config is missing camera.world_pose section.")
    required = {"pitch", "rho"}
    missing = required - pose.keys()
    if missing:
        raise KeyError(f"camera.world_pose missing required keys: {sorted(missing)}")
    return {
        "x": float(pose.get("x", 0.0)),
        "y": float(pose.get("y", 0.0)),
        "rho": float(pose["rho"]),
        "pitch": float(pose["pitch"]),
        "yaw": float(pose.get("yaw", 0.0)),
        "roll": float(pose.get("roll", 0.0)),
    }


def load_extrinsics(path: os.PathLike[str] | str) -> np.ndarray:
    """Load a 4x4 transform from YAML or JSON."""
    return load_T(path)


def save_extrinsics(path: os.PathLike[str] | str, T: np.ndarray) -> None:
    """Persist a 4x4 transform to YAML or JSON, inferring format from suffix."""
    save_T(path, T)


def load_points(path: os.PathLike[str] | str) -> np.ndarray:
    """Load a NxM array (points) from YAML or JSON."""
    data = load_config(path)
    arr = np.array(data, dtype=float)
    if arr.ndim != 2:
        raise ValueError("Points file must describe a 2D array.")
    return arr


def load_intrinsics_npz(path: os.PathLike[str] | str) -> Tuple[np.ndarray, np.ndarray]:
    """Load intrinsic parameters from an npz bundle for backwards compatibility."""
    data = np.load(path)
    K = data["K"]
    dist = data["dist"]
    return K, dist


def load_T(path: os.PathLike[str] | str) -> np.ndarray:
    """Load a 4x4 transform from disk."""
    try:
        config = load_config(path)
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"Extrinsics file not found: {path}") from exc

    matrix = config["T"] if isinstance(config, dict) and "T" in config else config
    T = np.asarray(matrix, dtype=float)
    if T.shape != (4, 4):
        raise ValueError(f"Extrinsics file {path} must contain a 4x4 matrix.")
    return T


def save_T(path: os.PathLike[str] | str, T: np.ndarray) -> None:
    """Save a 4x4 transform to YAML/JSON."""
    suffix = Path(path).suffix.lower()
    data = {"T": np.asarray(T, dtype=float).tolist()}
    if suffix == ".json":
        save_json(path, data)
    else:
        save_yaml(path, data)
