#!/usr/bin/env python3
"""Compatibility wrapper for the legacy Phase B v1 pipeline.

The legacy implementation now lives in `phase_b_tags_legacy.py`. This wrapper only
patches path constants so that the original source remains byte-identical to the
pre-refactor version, then delegates to its main() entry point.
"""

from __future__ import annotations

from pathlib import Path

from . import phase_b_tags_legacy as legacy


def _patch_paths() -> None:
    """Update legacy module paths to account for the versioned package layout."""
    phase_b_root = Path(__file__).resolve().parent.parent
    project_root = phase_b_root.parent
    legacy.PHASE_B_ROOT = phase_b_root
    legacy.PROJECT_ROOT = project_root
    legacy.COMMON_CALIB_FALLBACK = project_root / "common" / "calib" / "calib.yaml"


_patch_paths()


# Re-export legacy helpers used by v2 to avoid fragile cross-imports.
_EXPORTED_NAMES = [
    "load_camera_intrinsics",
    "load_rig",
    "setup_detector",
    "_auto_select_camera",
    "_open_capture_with_settings",
    "parse_video_source",
    "load_extrinsics_yaml",
    "ensure_csv_writer",
    "parse_udp_target",
    "detection_to_transform",
    "PoseCandidate",
    "fuse_with_optional_ransac",
    "select_candidate",
    "compute_tilt_deg",
    "wrap_deg180",
    "apply_ema_pose",
    "build_pose_record",
    "continuous_quat",
    "draw_axes",
    "format_int_list",
    "format_float_list",
    "rotation_matrix_to_quaternion",
]

for _name in _EXPORTED_NAMES:
    globals()[_name] = getattr(legacy, _name)


def main() -> None:
    """Entry point matching the original script."""
    legacy.main()


if __name__ == "__main__":
    main()
