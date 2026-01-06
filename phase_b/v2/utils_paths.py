"""Path resolution helpers for Phase B v2."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable, List


def repo_root() -> Path:
    """Return the project root (directory containing phase_b)."""
    current = Path(__file__).resolve()
    for parent in [current] + list(current.parents):
        if (parent / "phase_b").is_dir():
            return parent
    raise RuntimeError("Unable to locate project root containing 'phase_b'.")


def _normalize_path(path: str) -> Path:
    expanded = os.path.expandvars(path)
    return Path(expanded).expanduser()


def resolve_file_path(path: str, search_roots: Iterable[str]) -> str:
    """Resolve a file path relative to repo root and fallback search roots."""
    if not path:
        raise FileNotFoundError("No path provided for resolution.")
    root = repo_root()
    target = _normalize_path(path)
    tried: List[Path] = []

    # 1) As provided (relative to CWD) or absolute
    candidate = target if target.is_absolute() else target.resolve()
    tried.append(candidate)
    if candidate.exists():
        return str(candidate)

    # 2) Relative to repo root
    candidate = (root / target).resolve()
    tried.append(candidate)
    if candidate.exists():
        return str(candidate)

    # 3) Within fallback search roots under repo root
    for search in search_roots:
        search_root = root / search
        candidate = (search_root / target).resolve()
        tried.append(candidate)
        if candidate.exists():
            return str(candidate)

    tried_list = "\n".join(f"  - {p}" for p in tried)
    raise FileNotFoundError(
        f"Unable to resolve '{path}'. Tried:\n{tried_list}"
    )


def resolve_calib_path(path: str) -> str:
    """Resolve calibration file path."""
    return resolve_file_path(path, ["common/calib", "phase_b/calib", "calib"])


def resolve_extrinsics_path(path: str) -> str:
    """Resolve extrinsics file path."""
    return resolve_file_path(
        path, ["common/extrinsics", "phase_b/extrinsics", "extrinsics"]
    )


def resolve_rig_path(path: str) -> str:
    """Resolve rig definition path."""
    return resolve_file_path(path, ["phase_b/rigs", "rigs"])
