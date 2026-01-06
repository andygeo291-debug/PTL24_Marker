"""Configuration loading and provenance helpers for Phase B v2."""

from __future__ import annotations

import hashlib
import json
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Optional, Sequence

import yaml


def load_config(path: Optional[Path]) -> Dict[str, Any]:
    """Load a YAML config file; return an empty dict if the file is missing."""
    if path is None:
        return {}
    path = Path(path)
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as fp:
        data = yaml.safe_load(fp) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Config file {path} must define a YAML mapping.")
    return data


def git_commit() -> Optional[str]:
    """Return the current git commit hash, or None if unavailable."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    commit = result.stdout.strip()
    return commit or None


def sha256(path: Path) -> Optional[str]:
    """Compute the SHA-256 digest for a file, returning None if unreadable."""
    buffer_size = 128 * 1024
    digest = hashlib.sha256()
    try:
        with Path(path).open("rb") as fp:
            while True:
                chunk = fp.read(buffer_size)
                if not chunk:
                    break
                digest.update(chunk)
    except OSError:
        return None
    return digest.hexdigest()


def provenance_dict(config: Mapping[str, Any], files: Mapping[str, Optional[Path]]) -> Dict[str, Any]:
    """Assemble a provenance dictionary with git commit, config, and file hashes."""
    payload: Dict[str, Any] = {
        "timestamp": time.time(),
        "git_commit": git_commit(),
        "config": config,
        "files": {},
    }
    for label, path in files.items():
        if not path:
            continue
        p = Path(path)
        payload["files"][label] = {
            "path": str(p),
            "sha256": sha256(p),
        }
    return payload


def _load_existing_lines(path: Path) -> Sequence[str]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return []
    return text.splitlines()


def write_provenance_header(csv_path: Path, provenance: Mapping[str, Any], header_cols: Iterable[str]) -> None:
    """Ensure a CSV starts with a provenance JSON comment followed by the header."""
    csv_path = Path(csv_path)
    header_line = ",".join(header_cols)
    provenance_line = "#" + json.dumps(provenance, sort_keys=True)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    existing_lines = _load_existing_lines(csv_path) if csv_path.exists() else []
    if existing_lines and existing_lines[0].startswith("#"):
        return

    remaining: Sequence[str] = existing_lines
    if remaining and remaining[0] == header_line:
        remaining = remaining[1:]
    with csv_path.open("w", encoding="utf-8", newline="") as fp:
        fp.write(provenance_line + "\n")
        fp.write(header_line + "\n")
        for line in remaining:
            fp.write(line + "\n")
