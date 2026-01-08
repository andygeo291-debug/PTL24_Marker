"""Helpers for run directory management and metadata capture."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict


def make_run_dir(base: Path, name: str) -> Path:
    base = Path(base).expanduser()
    run_dir = base / name
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_run_meta(path: Path, payload: Dict[str, Any]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=False) + "\n", encoding="utf-8")
