#!/usr/bin/env python3
"""
Phase B v2 entry point with config/provenance, weighted fusion, HUD, and timing.
Includes optional Basler backend integration via a factory and lightweight
diagnostic flags without changing pose-estimation logic.

Assumptions:
  - Config defaults may enable weighted fusion; pass --no-use-weighted-se3 to
    match legacy behaviour when running this script.
  - Weighted fusion uses the previous fused pose (if available) as the
    left-invariant reference for averaging.
"""

from __future__ import annotations

# --- BEGIN SAFE IMPORT BOOTSTRAP (for script + module modes) ---
import sys
import pathlib

THIS_FILE = pathlib.Path(__file__).resolve()
REPO_ROOT = THIS_FILE.parents[2]

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

try:
    from phase_b.v1 import phase_b_tags as v1
except ImportError:
    import phase_b.v1.phase_b_tags as v1
# --- END SAFE IMPORT BOOTSTRAP ---
# This file is intentionally runnable both as:
#   python -m phase_b.v2.phase_b_tags_v2
# and:
#   python phase_b/v2/phase_b_tags_v2.py
# The sys.path bootstrap enables dual-mode execution.

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
import shlex
import shutil
import subprocess
from contextlib import contextmanager
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Set, TextIO, Tuple

import cv2
import numpy as np
from time import perf_counter
from phase_b.v2.bench import StageTimer
from phase_b.v2.debug_log import DebugLogger, draw_hud
from phase_b.v2.se3_fuse import exp_se3, inv_se3, log_se3, weighted_average_se3
from phase_b.v2.utils_paths import (
    resolve_calib_path,
    resolve_extrinsics_path,
    resolve_rig_path,
)
from phase_b.v2.utils_config import load_config, provenance_dict, write_provenance_header
from phase_b.tools.run_utils import make_run_dir, sha256_file, write_run_meta


LOGGER = logging.getLogger("phase_b_tags_v2")
V2_ROOT = Path(__file__).resolve().parent
PHASE_B_ROOT = V2_ROOT.parent
PROJECT_ROOT = PHASE_B_ROOT.parent
DEFAULT_CONFIG_PATH = PHASE_B_ROOT / "config.yaml"
EPS = 1e-9
FUSE_WEIGHT_PARAMS = {
    "alpha_e": 0.15,
    "alpha_A": 0.7,
    "alpha_v": 1.0,
    "alpha_m": 0.3,
    "area_ref": 12000.0,
    "margin_ref": 50.0,
    "score_window": 8.0,
}


def clamp(value: float, lower: float, upper: float) -> float:
    """Clamp value to [lower, upper]."""
    return max(lower, min(upper, value))


def _safe_numeric(values: Sequence[float], idx: int) -> Optional[float]:
    """Return finite float from list if available."""
    if idx < 0:
        return None
    try:
        value = values[idx]
    except (IndexError, TypeError):
        return None
    if value is None:
        return None
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(value):
        return None
    return value


@contextmanager
def suppress_stderr_fd(enabled: bool):
    # Apriltag emits C-level stderr; fd redirection is required to silence it.
    if not enabled:
        yield
        return
    dup = os.dup(2)
    try:
        with open(os.devnull, "w") as devnull:
            os.dup2(devnull.fileno(), 2)
            yield
    finally:
        os.dup2(dup, 2)
        os.close(dup)


def compute_quality_weights(
    inlier_indices: Sequence[int],
    reproj_errors: Sequence[float],
    quad_areas: Sequence[float],
    view_cosines: Sequence[float],
    decision_margins: Sequence[float],
) -> List[float]:
    """Log-linear tag quality model (reproj/area/view cosine/margin → weights)."""
    count = len(inlier_indices)
    if count == 0:
        return []
    if count == 1:
        return [1.0]
    params = FUSE_WEIGHT_PARAMS
    area_ref = params["area_ref"]
    margin_ref = params["margin_ref"]
    scores: List[float] = []
    for idx in inlier_indices:
        score = 0.0
        err = _safe_numeric(reproj_errors, idx)
        if err is not None:
            score += -params["alpha_e"] * err
        area = _safe_numeric(quad_areas, idx)
        if area is not None and area_ref > 0:
            norm_area = min(max(area / area_ref, 0.0), 3.0)
            score += params["alpha_A"] * norm_area
        view = _safe_numeric(view_cosines, idx)
        if view is not None:
            score += params["alpha_v"] * max(view - 0.5, 0.0)
        margin = _safe_numeric(decision_margins, idx)
        if margin is not None and margin_ref > 0:
            norm_margin = min(max(margin / margin_ref, 0.0), 2.0)
            score += params["alpha_m"] * norm_margin
        scores.append(score)
    max_score = max(scores)
    score_window = params["score_window"]
    threshold = max_score - score_window
    keep = [(i, score) for i, score in enumerate(scores) if score >= threshold]
    if not keep:
        uniform = 1.0 / count
        return [uniform] * count
    max_keep = max(score for _, score in keep)
    exp_vals = [(i, math.exp(score - max_keep)) for i, score in keep]
    denom = sum(val for _, val in exp_vals)
    if denom <= 0 or not math.isfinite(denom):
        uniform = 1.0 / count
        return [uniform] * count
    weights = [0.0] * count
    for rel_idx, value in exp_vals:
        weights[rel_idx] = value / denom
    return weights


POSES_HEADER = [
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
    "rvec_world_x",
    "rvec_world_y",
    "rvec_world_z",
    "tvec_world_x",
    "tvec_world_y",
    "tvec_world_z",
    "tilt_cam_deg",
    "tilt_world_deg",
]


def set_deterministic(seed: int = 12345) -> None:
    """Seed Python, NumPy, and hash randomization for reproducible runs."""
    os.environ.setdefault("PYTHONHASHSEED", str(seed))
    random.seed(seed)
    np.random.seed(seed)


def determine_cli_overrides(args: argparse.Namespace) -> Set[str]:
    """Return argparse destinations that differ from their defaults."""
    overrides: Set[str] = set()
    parser = getattr(args, "_parser", None)
    if parser is None:
        return overrides
    for action in parser._actions:
        dest = getattr(action, "dest", None)
        if not dest or dest == "help":
            continue
        default = action.default
        value = getattr(args, dest, None)
        if isinstance(default, list):
            default = list(default)
        if value != default:
            overrides.add(dest)
    return overrides


def apply_config(args: argparse.Namespace, config: Dict[str, object], cli_overrides: Set[str]) -> None:
    """Merge YAML config values into argparse args unless overridden."""

    def update(dest: str, value, caster):
        if dest in cli_overrides:
            return
        if value is None:
            return
        setattr(args, dest, caster(value))

    def update_bool(dest: str, value):
        if dest in cli_overrides:
            return
        if value is None:
            return
        setattr(args, dest, bool(value))

    ransac_cfg = config.get("ransac", {}) if isinstance(config.get("ransac"), dict) else {}
    update("ransac_trans", ransac_cfg.get("trans_max_m"), float)
    update("ransac_rot", ransac_cfg.get("rot_max_deg"), float)
    update("min_inliers", ransac_cfg.get("min_inliers"), int)
    update_bool("adapt", ransac_cfg.get("adaptive"))
    update("ransac_area_ref", ransac_cfg.get("A_ref_px2"), float)
    update("ransac_base_trans", ransac_cfg.get("base_trans_m"), float)
    update("ransac_base_rot", ransac_cfg.get("base_rot_deg"), float)
    update("beta_trans", ransac_cfg.get("beta_trans"), float)
    update("beta_rot", ransac_cfg.get("beta_rot"), float)
    update("gamma_few", ransac_cfg.get("gamma_few"), float)
    update("gamma_many", ransac_cfg.get("gamma_many"), float)

    fuse_cfg = config.get("fuse", {}) if isinstance(config.get("fuse"), dict) else {}
    update("ema_alpha", fuse_cfg.get("ema_alpha"), float)
    update("axis_len", fuse_cfg.get("axis_len_m"), float)

    health_cfg = config.get("health", {}) if isinstance(config.get("health"), dict) else {}
    update("max_tilt_jump_deg", health_cfg.get("max_tilt_jump_deg"), float)
    update("spike_reset_after", health_cfg.get("spike_reset_after"), int)

    video_cfg = config.get("video", {}) if isinstance(config.get("video"), dict) else {}
    if "device" in video_cfg and "video" not in cli_overrides:
        setattr(args, "video", str(video_cfg.get("device")))
    update("width", video_cfg.get("width"), int)
    update("height", video_cfg.get("height"), int)
    update("fps", video_cfg.get("fps"), float)

    logging_cfg = config.get("logging", {}) if isinstance(config.get("logging"), dict) else {}
    if "poses_csv" in logging_cfg and "save_poses" not in cli_overrides:
        setattr(args, "save_poses", str(logging_cfg.get("poses_csv")))
    if "debug_metrics_csv" in logging_cfg and "debug_metrics" not in cli_overrides:
        setattr(args, "debug_metrics", str(logging_cfg.get("debug_metrics_csv")))

    bench_cfg = config.get("bench", {}) if isinstance(config.get("bench"), dict) else {}
    update("bench_print_every", bench_cfg.get("print_every"), int)


def build_effective_config(
    args: argparse.Namespace,
    config_path: Optional[Path],
    yaml_config: Dict[str, object],
    cli_overrides: Set[str],
    resolved_use_weighted: bool,
    hud_enabled: bool,
) -> Dict[str, object]:
    """Collect provenance-friendly configuration details."""
    runtime = {
        "ransac": {
            "trans_max_m": float(args.ransac_trans),
            "rot_max_deg": float(args.ransac_rot),
            "min_inliers": int(args.min_inliers),
            "adaptive": bool(getattr(args, "adapt", False)),
            "A_ref_px2": float(getattr(args, "ransac_area_ref", 12000.0) or 12000.0),
            "base_trans_m": float(getattr(args, "ransac_base_trans", args.ransac_trans)),
            "base_rot_deg": float(getattr(args, "ransac_base_rot", args.ransac_rot)),
        },
        "fuse": {
            "ema_alpha": float(args.ema_alpha),
            "use_weighted_se3": resolved_use_weighted,
            "axis_len_m": float(args.axis_len),
        },
        "health": {
            "max_tilt_jump_deg": float(args.max_tilt_jump_deg),
            "spike_reset_after": int(getattr(args, "spike_reset_after", 10) or 10),
        },
        "video": {
            "device": args.video,
            "width": args.width,
            "height": args.height,
            "fps": args.fps,
        },
        "logging": {
            "poses_csv": args.save_poses,
            "debug_metrics_csv": getattr(args, "debug_metrics", None),
        },
        "hud": {"enabled": bool(hud_enabled)},
        "bench": {"print_every": args.bench_print_every},
    }
    return {
        "config_path": str(config_path) if config_path else None,
        "yaml": yaml_config,
        "cli_overrides": sorted(cli_overrides),
        "runtime": runtime,
    }


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Marker-based 6-DoF pose estimation for cylindrical rigs (v2)."
    )
    parser.add_argument(
        "--config",
        default=str(DEFAULT_CONFIG_PATH),
        help="Path to Phase B YAML config (default: phase_b/config.yaml).",
    )
    parser.add_argument(
        "--camera",
        help="Path to camera calibration YAML (falls back to ../common/calib/calib.yaml if omitted).",
    )
    parser.add_argument("--rig", required=True, help="Path to rig YAML definition.")
    parser.add_argument(
        "--video",
        default="auto",
        help='Video source: "auto", index like "0", a device path, or URL (default: auto).',
    )
    parser.add_argument("--width", type=int, help="Requested capture width (pixels).")
    parser.add_argument("--height", type=int, help="Requested capture height (pixels).")
    parser.add_argument("--fps", type=float, help="Requested capture FPS.")
    from common.camera.factory import add_camera_cli_args

    # Add backend selection + Basler-specific CLI options.
    add_camera_cli_args(parser)
    # Basler-friendly diagnostics; no effect unless enabled.
    parser.add_argument(
        "--quiet-apriltag-stderr",
        action="store_true",
        default=None,
        help="Suppress apriltag C stderr during detection (default: on for basler).",
    )
    parser.add_argument(
        "--dump-first-frame",
        help="Optional path to save the first successfully acquired frame.",
    )
    parser.add_argument(
        "--print-first-frame-stats",
        action="store_true",
        help="Log a one-shot detection summary for the first grabbed frame.",
    )
    parser.add_argument(
        "--print-first-pose-debug",
        action="store_true",
        help="Log one-shot pose estimation checkpoints for the first grabbed frame.",
    )
    parser.add_argument(
        "--undistort",
        action="store_true",
        help="Undistort frames before detection using calibration coefficients (default: off).",
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
        "--poses-out",
        help="Optional override for pose CSV output path.",
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
        "--hud",
        dest="hud_force_on",
        action="store_true",
        help="Enable on-screen HUD overlay regardless of YAML settings.",
    )
    parser.add_argument(
        "--no-hud",
        dest="hud_force_off",
        action="store_true",
        help="Disable on-screen HUD overlay regardless of YAML settings.",
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
        "--ransac-trans-max-m",
        type=float,
        help="Override translational inlier threshold (meters).",
    )
    parser.add_argument(
        "--ransac-rot",
        type=float,
        default=8.0,
        help="Rotational inlier threshold in degrees (default: 8).",
    )
    parser.add_argument(
        "--ransac-rot-max-deg",
        type=float,
        help="Override rotational inlier threshold (degrees).",
    )
    parser.add_argument(
        "--ransac-base-trans",
        type=float,
        default=None,
        help="Baseline translational threshold (meters) for non-adaptive RANSAC.",
    )
    parser.add_argument(
        "--ransac-base-trans-m",
        type=float,
        help="Override baseline translational threshold (meters) for adaptive RANSAC.",
    )
    parser.add_argument(
        "--ransac-base-rot-deg",
        dest="ransac_base_rot",
        type=float,
        default=None,
        help="Baseline rotational threshold (degrees) for non-adaptive RANSAC.",
    )
    parser.add_argument(
        "--ransac-min-inliers",
        type=int,
        help="Override minimum inliers required before accepting a pose.",
    )
    parser.add_argument(
        "--ransac-adaptive",
        dest="ransac_adaptive",
        action="store_true",
        help="Force adaptive RANSAC on (overrides config).",
    )
    parser.add_argument(
        "--no-ransac-adaptive",
        dest="ransac_adaptive",
        action="store_false",
        help="Force adaptive RANSAC off (overrides config).",
    )
    parser.set_defaults(ransac_adaptive=None)
    parser.add_argument(
        "--adapt",
        dest="adapt",
        action="store_true",
        help="Enable adaptive RANSAC thresholds based on tag area/count.",
    )
    parser.add_argument(
        "--no-adapt",
        dest="adapt",
        action="store_false",
        help="Disable adaptive RANSAC thresholds regardless of config.",
    )
    parser.add_argument(
        "--beta-trans",
        type=float,
        default=0.5,
        help="Exponent for area-based scaling of translational threshold (default: 0.5).",
    )
    parser.add_argument(
        "--beta-rot",
        type=float,
        default=0.5,
        help="Exponent for area-based scaling of rotational threshold (default: 0.5).",
    )
    parser.add_argument(
        "--gamma-few",
        type=float,
        default=1.3,
        help="Scaling factor when <=2 tags are visible (default: 1.3).",
    )
    parser.add_argument(
        "--gamma-many",
        type=float,
        default=0.9,
        help="Scaling factor when >6 tags are visible (default: 0.9).",
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
        "--ekf",
        action="store_true",
        help="Enable EKF-based temporal filtering (experimental).",
    )
    parser.add_argument(
        "--use-weighted-se3",
        dest="use_weighted_se3",
        action="store_true",
        help="Force weighted SE(3) fusion on (overrides config).",
    )
    parser.add_argument(
        "--no-use-weighted-se3",
        dest="use_weighted_se3",
        action="store_false",
        help="Force weighted SE(3) fusion off (overrides config).",
    )
    parser.set_defaults(use_weighted_se3=None)
    parser.set_defaults(adapt=False)
    parser.add_argument(
        "--v1-compat",
        action="store_true",
        help="Emulate v1 pipeline (fixed RANSAC, simple fusion, EMA-only).",
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
        "--max-hamming",
        type=int,
        default=None,
        help="Maximum allowed tag hamming distance (default: no filter).",
    )
    parser.add_argument(
        "--drop-unknown-ids",
        action="store_true",
        default=False,
        help="Drop detections whose tag ID is not in the rig (default: false).",
    )
    parser.add_argument(
        "--no-drop-unknown-ids",
        action="store_false",
        dest="drop_unknown_ids",
        help="Allow unknown tag IDs (for debugging).",
    )
    parser.add_argument(
        "--min-tag-area-px2",
        type=float,
        default=0.0,
        help="Drop detections with area below this threshold (px^2). Default: 0 (off).",
    )
    parser.add_argument(
        "--save-frame-on-bad-detect",
        help="Directory to save frames/JSON when bad detections occur (hamming/unknown/small).",
    )
    parser.add_argument(
        "--spike-disable",
        action="store_true",
        help="Disable spike rejection gate for debugging.",
    )
    parser.add_argument(
        "--spike-trans-thresh-m",
        type=float,
        help="Translation delta threshold (m) for spike rejection (optional).",
    )
    parser.add_argument(
        "--spike-rot-thresh-deg",
        type=float,
        help="Rotation delta threshold (deg) for spike rejection (overrides max-tilt-jump-deg).",
    )
    parser.add_argument(
        "--spike-ref-age-frames",
        type=int,
        help="Override reference age used in spike logging (frames).",
    )
    parser.add_argument(
        "--no-spike-reject",
        action="store_true",
        help="Disable spike rejection gate for debugging (alias for --spike-disable).",
    )
    parser.add_argument(
        "--ignore-ids",
        help="Comma-separated tag IDs to ignore during fusion.",
    )
    parser.add_argument(
        "--debug-metrics",
        help="Optional CSV path for per-frame debug metrics output.",
    )
    parser.add_argument(
        "--debug-metrics-out",
        help="Optional override for debug metrics output path.",
    )
    parser.add_argument(
        "--run-dir",
        help="Optional run output directory (overrides --save-run base).",
    )
    parser.add_argument(
        "--run-name",
        help="Run name for --save-run (default: timestamp).",
    )
    parser.add_argument(
        "--save-run",
        action="store_true",
        help='Create a run folder (example: --save-run --run-name "my_run").',
    )
    parser.add_argument(
        "--bench-print-every",
        type=int,
        help="Frames between benchmark summaries (default: config).",
    )
    parser.add_argument(
        "--bench",
        action="store_true",
        help="Reserved legacy flag for backwards compatibility.",
    )
    parser.add_argument(
        "--params",
        default=str(PHASE_B_ROOT / "params.yaml"),
        help="Path to Phase B parameters lockfile (YAML).",
    )

    args = parser.parse_args(argv)
    setattr(args, "_parser", parser)
    return args


def _resolve_output_path(path_str: str) -> Path:
    path = Path(path_str).expanduser()
    if not path.is_absolute():
        path = (Path.cwd() / path).resolve()
    return path


def _object_points_cache(size_m: float, cache: Dict[float, np.ndarray]) -> np.ndarray:
    pts = cache.get(size_m)
    if pts is None:
        half = size_m / 2.0
        pts = np.array(
            [
                [-half, -half, 0.0],
                [half, -half, 0.0],
                [half, half, 0.0],
                [-half, half, 0.0],
            ],
            dtype=np.float64,
        )
        cache[size_m] = pts
    return pts


def run(argv: Optional[Sequence[str]] = None) -> int:
    """Main entry-point for CLI execution."""
    set_deterministic()
    t0 = perf_counter()
    args = parse_args(argv)

    config_path = Path(args.config).expanduser()
    if not config_path.is_absolute():
        config_path = (Path.cwd() / config_path).resolve()
    if not config_path.exists():
        LOGGER.warning("Config file not found: %s", config_path)
    yaml_config = load_config(config_path)
    cli_overrides = determine_cli_overrides(args)
    apply_config(args, yaml_config, cli_overrides)
    if getattr(args, "adapt", None) is None:
        args.adapt = False
    args.adapt = bool(args.adapt)
    if getattr(args, "ransac_area_ref", None) is None:
        args.ransac_area_ref = 12000.0
    args.ransac_area_ref = float(args.ransac_area_ref)
    if getattr(args, "ransac_rot_max_deg", None) is not None:
        args.ransac_rot = float(args.ransac_rot_max_deg)
    if getattr(args, "ransac_trans_max_m", None) is not None:
        args.ransac_trans = float(args.ransac_trans_max_m)
    if getattr(args, "ransac_base_trans_m", None) is not None:
        args.ransac_base_trans = float(args.ransac_base_trans_m)
    if getattr(args, "ransac_base_trans", None) is None:
        args.ransac_base_trans = float(args.ransac_trans)
    args.ransac_base_trans = float(args.ransac_base_trans)
    if getattr(args, "ransac_base_rot", None) is None:
        args.ransac_base_rot = float(args.ransac_rot)
    args.ransac_base_rot = float(args.ransac_base_rot)
    if getattr(args, "ransac_min_inliers", None) is not None:
        args.min_inliers = int(args.ransac_min_inliers)
    if getattr(args, "ransac_adaptive", None) is not None:
        args.adapt = bool(args.ransac_adaptive)
    if getattr(args, "spike_reset_after", None) is None:
        args.spike_reset_after = 10
    if getattr(args, "spike_rot_thresh_deg", None) is not None:
        args.max_tilt_jump_deg = float(args.spike_rot_thresh_deg)

    v1_mode = bool(getattr(args, "v1_compat", False))
    if v1_mode:
        args.adapt = False
        args.use_weighted_se3 = False
        args.ema_alpha = 0.3
        if hasattr(args, "ekf"):
            args.ekf = False
        print("⬅️  v1-compat mode enabled (fixed RANSAC, simple fusion, EMA only)")
        random.seed(0)
        np.random.seed(0)

    try:
        calib_path = resolve_calib_path(args.camera or "calib.yaml")
        extrinsics_path = (
            resolve_extrinsics_path(args.extrinsics) if args.extrinsics else None
        )
        rig_path = resolve_rig_path(args.rig)
    except FileNotFoundError as exc:
        print(f"[error] {exc}")
        return 2
    LOGGER.info(
        "Resolved paths: calib=%s extrinsics=%s rig=%s config=%s",
        calib_path,
        extrinsics_path if extrinsics_path else "(none)",
        rig_path,
        str(config_path),
    )
    if extrinsics_path:
        print(f"[run] Using extrinsics: {extrinsics_path}")
    print(f"[run] Using calib: {calib_path}")
    print(f"[run] Using rig: {rig_path}")

    if args.poses_out:
        args.save_poses = args.poses_out
    if args.debug_metrics_out:
        args.debug_metrics = args.debug_metrics_out

    run_dir: Optional[Path] = None
    run_name = args.run_name or _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    if args.run_dir or args.save_run:
        if args.run_dir:
            run_dir = Path(args.run_dir).expanduser()
            run_dir.mkdir(parents=True, exist_ok=True)
        else:
            run_dir = make_run_dir(Path.home() / "ptl_runs", run_name)
        run_dir = run_dir.resolve()

        if not args.save_poses and "save_poses" not in cli_overrides:
            args.save_poses = str(run_dir / "poses.csv")

        if not getattr(args, "debug_metrics", None) and "debug_metrics" not in cli_overrides:
            args.debug_metrics = str(run_dir / "debug_metrics.csv")

    hud_cfg = yaml_config.get("hud", {}) if isinstance(yaml_config.get("hud"), dict) else {}
    hud_enabled = bool(hud_cfg.get("enabled", False))
    if getattr(args, "hud_force_on", False):
        hud_enabled = True
    if getattr(args, "hud_force_off", False):
        hud_enabled = False

    fuse_cfg = yaml_config.get("fuse")
    if not isinstance(fuse_cfg, dict):
        fuse_cfg = {}
        yaml_config["fuse"] = fuse_cfg
    cfg_use_weighted = bool(fuse_cfg.get("use_weighted_se3", False))
    # Tri-state override: None means config default, True/False come from CLI.
    if args.use_weighted_se3 is None:
        use_weighted = cfg_use_weighted
    else:
        use_weighted = bool(args.use_weighted_se3)
    if v1_mode:
        use_weighted = False
    args.use_weighted_se3 = use_weighted
    fuse_cfg["use_weighted_se3"] = bool(use_weighted)
    fusion_mode = "simple" if not use_weighted else "weighted"
    use_ekf = bool(getattr(args, "ekf", False)) and not v1_mode
    adaptive_requested = bool(getattr(args, "adapt", False))
    use_adaptive = bool(args.ransac and adaptive_requested and not v1_mode)
    if args.bench_print_every is None:
        args.bench_print_every = 60

    effective_config = build_effective_config(
        args,
        config_path if config_path.exists() else None,
        yaml_config,
        cli_overrides,
        use_weighted,
        hud_enabled,
    )
    effective_config["calib_path_resolved"] = calib_path
    effective_config["rig_path_resolved"] = rig_path
    effective_config["extrinsics_path_resolved"] = extrinsics_path

    K, dist = v1.load_camera_intrinsics(Path(calib_path))
    rig = v1.load_rig(Path(rig_path))
    LOGGER.info(
        "Loaded rig with %d tags (radius %.3f m, length %.3f m).",
        len(rig.tags),
        rig.radius_m,
        rig.length_m,
    )

    detector = v1.setup_detector(args.family)
    bench_timer = StageTimer(args.bench_print_every)
    LOGGER.info("Fusion mode: %s", fusion_mode)
    LOGGER.info("Adaptive RANSAC: %s", "enabled" if use_adaptive else "disabled")
    LOGGER.info("EKF filtering: %s", "enabled" if use_ekf else "disabled")
    LOGGER.info(
        "RANSAC thresholds: trans=%.3f m rot=%.3f deg base_trans=%.3f base_rot=%.3f min_inliers=%d adaptive=%s",
        float(args.ransac_trans),
        float(args.ransac_rot),
        float(args.ransac_base_trans),
        float(args.ransac_base_rot),
        int(args.min_inliers),
        str(use_adaptive),
    )

    cap = None
    basler_cam = None
    pending_frame = None
    dump_first_frame_path = getattr(args, "dump_first_frame", None)
    dumped_first_frame = False
    n_grabbed = 0
    printed_first_stats = False
    printed_first_pose_debug = False
    requested_w = int(args.width) if args.width else None
    requested_h = int(args.height) if args.height else None
    actual_w = 0
    actual_h = 0

    # Basler backend uses the wrapper; OpenCV path remains unchanged.
    use_basler = getattr(args, "camera_backend", "opencv") == "basler"
    # Default to suppressing apriltag stderr only for Basler runs.
    if args.quiet_apriltag_stderr is None:
        quiet_apriltag_stderr = use_basler
    else:
        quiet_apriltag_stderr = bool(args.quiet_apriltag_stderr)
    if use_basler:
        from common.camera.factory import create_camera_from_args

        try:
            basler_cam = create_camera_from_args(args)
        except Exception as exc:  # pylint: disable=broad-except
            LOGGER.error("Unable to open Basler camera: %s", exc)
            return 1
    else:
        video_opt = str(args.video).lower() if isinstance(args.video, str) else args.video
        if video_opt == "auto":
            cap, chosen_src = v1._auto_select_camera(args)  # pylint: disable=protected-access
            if cap is None:
                LOGGER.error("Auto camera selection failed (tried indices 1..5, then 0).")
                return 1
            LOGGER.info("Using video source: %s", chosen_src)
        else:
            video_source = v1.parse_video_source(args.video)
            cap = v1._open_capture_with_settings(video_source, args)  # pylint: disable=protected-access
            if cap is None:
                LOGGER.error("Unable to open video source: %s", args.video)
                return 1
            LOGGER.info("Using video source: %s", video_source)

        backend_name = None
        if hasattr(cap, "getBackendName"):
            try:
                backend_name = cap.getBackendName()
            except Exception:  # pylint: disable=broad-except
                backend_name = None
        if backend_name:
            LOGGER.info("OpenCV backend: %s", backend_name)

        actual_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
        actual_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)

    if basler_cam is not None:
        ret0, frame0 = basler_cam.read()
    else:
        ret0, frame0 = cap.read()
    if ret0 and frame0 is not None:
        if basler_cam is not None and frame0.ndim == 2:
            frame0 = cv2.cvtColor(frame0, cv2.COLOR_GRAY2BGR)
        if basler_cam is not None and dump_first_frame_path and not dumped_first_frame:
            if cv2.imwrite(dump_first_frame_path, frame0):
                LOGGER.info("Wrote first frame to %s", dump_first_frame_path)
                dumped_first_frame = True
        pending_frame = frame0
        actual_h, actual_w = frame0.shape[:2]

    if requested_w and requested_h and actual_w and actual_h:
        if actual_w != requested_w or actual_h != requested_h:
            LOGGER.warning(
                "Capture size mismatch: requested %sx%s but first frame is %sx%s",
                requested_w,
                requested_h,
                actual_w,
                actual_h,
            )
        else:
            LOGGER.info("Capture opened: %sx%s", actual_w, actual_h)
    if cap is None and basler_cam is None:
        LOGGER.error("Camera capture failed to initialize.")
        return 1

    rng = random.Random()
    if v1_mode:
        rng.seed(0)

    extrinsics_matrix: Optional[np.ndarray] = None
    if extrinsics_path:
        try:
            extrinsics_matrix = v1.load_extrinsics_yaml(Path(extrinsics_path))
            LOGGER.info("World-frame output enabled using extrinsics: %s", extrinsics_path)
        except Exception as exc:  # pylint: disable=broad-except
            LOGGER.warning("Failed to load extrinsics from %s: %s", extrinsics_path, exc)
            extrinsics_matrix = None

    provenance_files = {
        "camera_calib": Path(calib_path),
        "extrinsics": Path(extrinsics_path) if extrinsics_path else None,
        "rig": Path(rig_path),
        "config": config_path,
    }
    provenance_payload = provenance_dict(effective_config, provenance_files)

    poses_path = _resolve_output_path(args.save_poses) if args.save_poses else None
    debug_path = (
        _resolve_output_path(args.debug_metrics)
        if getattr(args, "debug_metrics", None)
        else None
    )

    print(
        "[run] outputs: run_dir=%s poses=%s debug=%s"
        % (
            str(run_dir) if run_dir else "(none)",
            str(poses_path) if poses_path else "(none)",
            str(debug_path) if debug_path else "(none)",
        )
    )

    if run_dir:
        cmd_argv = list(sys.argv) if argv is None else [sys.argv[0], *argv]
        cmd_str = shlex.join(cmd_argv)
        (run_dir / "run_cmd.txt").write_text(cmd_str + "\n", encoding="utf-8")
        (run_dir / "run_header.json").write_text(
            json.dumps(provenance_payload, indent=2, sort_keys=False) + "\n",
            encoding="utf-8",
        )

        inputs_dir = run_dir / "inputs"
        inputs_dir.mkdir(parents=True, exist_ok=True)
        inputs_meta = []
        input_items = [
            ("camera_calib", Path(calib_path)),
            ("rig", Path(rig_path)),
            ("config", config_path),
        ]
        if extrinsics_path:
            input_items.append(("extrinsics", Path(extrinsics_path)))
        for label, path in input_items:
            copied = None
            sha256 = None
            if path.exists():
                sha256 = sha256_file(path)
                copied_path = inputs_dir / path.name
                try:
                    shutil.copy2(path, copied_path)
                    copied = str(copied_path)
                except OSError:
                    copied = None
            inputs_meta.append(
                {
                    "name": label,
                    "path": str(path),
                    "sha256": sha256,
                    "copied_to": copied,
                }
            )

        git_commit = None
        try:
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=REPO_ROOT,
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            if result.returncode == 0:
                git_commit = result.stdout.strip() or None
        except (OSError, ValueError):
            git_commit = None

        run_meta = {
            "timestamp": _dt.datetime.now().isoformat(),
            "run_name": run_name,
            "run_dir": str(run_dir),
            "git_commit": git_commit,
            "paths": {
                "camera_calib": str(calib_path),
                "rig": str(rig_path),
                "config": str(config_path),
                "extrinsics": str(extrinsics_path) if extrinsics_path else None,
            },
            "camera": {
                "backend": getattr(args, "camera_backend", "opencv"),
                "width": args.width,
                "height": args.height,
                "fps": args.fps,
                "pixel_format": getattr(args, "basler_pixel_format", None),
                "exposure_us": getattr(args, "basler_exposure_us", None),
                "gain": getattr(args, "basler_gain", None),
                "offset_x": getattr(args, "basler_offset_x", None),
                "offset_y": getattr(args, "basler_offset_y", None),
                "interpacket_delay": getattr(args, "basler_interpacket_delay", None),
                "timeout_ms": getattr(args, "basler_timeout_ms", None),
                "packet_size": getattr(args, "basler_packet_size", None),
                "serial": getattr(args, "basler_serial", None),
                "name": getattr(args, "basler_name", None),
            },
            "outputs": {
                "poses_csv": str(poses_path) if poses_path else None,
                "debug_metrics_csv": str(debug_path) if debug_path else None,
            },
            "inputs": inputs_meta,
        }
        write_run_meta(run_dir / "run_meta.json", run_meta)

    csv_writer: Optional[csv.writer] = None
    csv_fp: Optional[TextIO] = None
    if poses_path:
        try:
            write_provenance_header(poses_path, provenance_payload, POSES_HEADER)
            csv_writer, csv_fp = v1.ensure_csv_writer(poses_path)
            LOGGER.info("Appending poses to %s", poses_path)
        except OSError as exc:
            LOGGER.error("Failed to open pose log %s: %s", poses_path, exc)
            csv_writer = None
            csv_fp = None

    debug_logger: Optional[DebugLogger] = None
    if debug_path:
        try:
            write_provenance_header(debug_path, provenance_payload, DebugLogger.header)
            debug_logger = DebugLogger(debug_path)
            LOGGER.info("Writing debug metrics to %s", debug_path)
        except OSError as exc:
            LOGGER.error("Failed to open debug metrics log %s: %s", debug_path, exc)
            debug_logger = None

    udp_sock: Optional[socket.socket] = None
    udp_target: Optional[Tuple[str, int]] = None
    stream_period = 1.0 / max(args.stream_rate_hz, 1e-3)
    next_stream_time = 0.0
    if args.stream_udp:
        try:
            host, port = v1.parse_udp_target(args.stream_udp)
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
    spike_reset_after = int(getattr(args, "spike_reset_after", 10) or 10)
    spike_disable = bool(getattr(args, "spike_disable", False) or getattr(args, "no_spike_reject", False))
    spike_trans_thresh_cli = getattr(args, "spike_trans_thresh_m", None)
    spike_ref_age_override = getattr(args, "spike_ref_age_frames", None)
    ema_state: Optional[Dict[str, np.ndarray]] = None
    last_good_pose: Optional[Dict[str, Optional[np.ndarray]]] = None
    last_accept_frame_idx: Optional[int] = None
    spike_reject_streak = 0
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

    window_name = "phase_b_tags_v2"
    if hud_enabled:
        cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
    last_used_ids: List[int] = []
    frame_idx = 0
    frame_count = 0
    start_time = time.perf_counter()
    n_frames_processed = 0
    last_axis_cam: Optional[np.ndarray] = None
    last_tilt_cam: Optional[float] = None
    last_frame_ts = time.time()
    fps_estimate = 0.0
    object_cache: Dict[float, np.ndarray] = {}
    final_used_ids: List[int] = []
    save_bad_dir = Path(args.save_frame_on_bad_detect).expanduser() if getattr(args, "save_frame_on_bad_detect", None) else None
    last_bad_save_ts = 0.0

    try:
        while True:
            loop_t0 = perf_counter()
            t_read_ms = 0.0
            t_gray_ms = 0.0
            t_detect_ms = 0.0
            t_reproj_ms = 0.0
            t_ransac_ms = 0.0
            t_fuse_ms = 0.0
            t_ekf_ms = 0.0
            t_hud_ms = 0.0
            t_log_ms = 0.0
            t_total_ms: Optional[float] = None

            read_start = perf_counter()
            bench_timer.start("capture")
            if pending_frame is not None:
                ret, frame = True, pending_frame
                pending_frame = None
            else:
                if basler_cam is not None:
                    ret, frame = basler_cam.read()
                else:
                    ret, frame = cap.read() if cap is not None else (False, None)
            bench_timer.stop("capture")
            t_read_ms = (perf_counter() - read_start) * 1000.0
            if not ret:
                LOGGER.warning("Frame grab failed; skipping frame.")
                continue
            n_grabbed += 1
            log_grabbed = (n_grabbed % 10 == 0)
            if log_grabbed:
                LOGGER.info("grabbed=%d grab_ms=%.1f poses=%d", n_grabbed, t_read_ms, n_frames_processed)
            # Defer frame-limit exit until after detection so diagnostics can run.
            stop_after_frame = args.frames is not None and n_grabbed >= args.frames
            pose_debug_active = args.print_first_pose_debug and not printed_first_pose_debug
            if basler_cam is not None and frame is not None and frame.ndim == 2:
                # Basler returns Mono8; normalize to BGR to match OpenCV path.
                frame = cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)
            if basler_cam is not None and dump_first_frame_path and not dumped_first_frame:
                if cv2.imwrite(dump_first_frame_path, frame):
                    LOGGER.info("Wrote first frame to %s", dump_first_frame_path)
                    dumped_first_frame = True
            if frame is not None and frame.ndim == 2:
                frame = cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)

            # Prefer Basler host timestamp when provided.
            if basler_cam is not None and basler_cam.last_timestamp_s is not None:
                frame_ts = basler_cam.last_timestamp_s
            else:
                frame_ts = time.time()
            delta_t = frame_ts - last_frame_ts
            if delta_t > 0.0:
                fps_estimate = 1.0 / delta_t
            last_frame_ts = frame_ts
            mean_tag_area_px2: Optional[float] = None
            mean_view_cos: Optional[float] = None
            mean_reproj_px: Optional[float] = None
            n_unknown_ids = 0

            bench_timer.start("detect")
            gray_start = perf_counter()
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            if args.undistort and dist is not None and np.size(dist) > 0:
                gray = cv2.undistort(gray, K, dist)
            t_gray_ms = (perf_counter() - gray_start) * 1000.0

            detect_start = perf_counter()
            best_detections: Dict[int, object] = {}
            for size_m in unique_sizes:
                # libapriltag (pupil_apriltags) may stderr "Error, more than one new minima found."
                # This indicates an ambiguous decode; detector returns multiple candidates and we drop them here.
                with suppress_stderr_fd(quiet_apriltag_stderr):
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
                    spec = rig.tags.get(tag_id)
                    if spec is None:
                        n_unknown_ids += 1
                        continue
                    if not math.isclose(spec.size_m, size_m, rel_tol=1e-3, abs_tol=1e-6):
                        continue
                    current = best_detections.get(tag_id)
                    if current is None or det.decision_margin > current.decision_margin:
                        best_detections[tag_id] = det
            bench_timer.stop("detect")
            t_detect_ms = (perf_counter() - detect_start) * 1000.0

            bench_timer.start("pnp")
            reproj_start = perf_counter()
            transforms_cam_to_cyl: List[np.ndarray] = []
            legacy_weights: List[float] = []
            candidate_ids: List[int] = []
            decision_margins: List[float] = []
            reproj_errors: List[float] = []
            quad_areas: List[float] = []
            view_cosines: List[float] = []
            n_mirror_discards = 0
            n_dets_raw = len(best_detections)
            n_dropped_hamming = 0
            n_dropped_unknown = 0
            n_dropped_small = 0
            max_hamming_used = None
            raw_det_info: List[Dict[str, object]] = []
            for tag_id, det in best_detections.items():
                spec = rig.tags.get(tag_id)
                if spec is None:
                    n_dropped_unknown += 1
                    continue
                T_tag_to_cam = v1.detection_to_transform(det)
                normal_cam = T_tag_to_cam[:3, 2]
                normal_cam = normal_cam / (np.linalg.norm(normal_cam) + EPS)
                view_cos = float(np.clip(normal_cam.dot(np.array([0.0, 0.0, 1.0])), -1.0, 1.0))
                if view_cos <= 0.0:
                    n_mirror_discards += 1
                    continue
                T_cam_to_tag = np.linalg.inv(T_tag_to_cam)
                T_cam_to_cyl = T_cam_to_tag @ spec.T_tag_to_cyl
                transforms_cam_to_cyl.append(T_cam_to_cyl)
                legacy_weights.append(max(float(det.decision_margin), 0.1))
                candidate_ids.append(tag_id)
                decision_margins.append(float(det.decision_margin))

                corners = np.asarray(det.corners, dtype=np.float64).reshape(-1, 2)
                area = float(abs(cv2.contourArea(corners.astype(np.float32))))
                quad_areas.append(area)
                raw_det_info.append({"id": int(tag_id), "hamming": int(getattr(det, "hamming", 0)), "area_px2": area})
                obj_pts = _object_points_cache(spec.size_m, object_cache)
                rvec, _ = cv2.Rodrigues(T_tag_to_cam[:3, :3])
                tvec = T_tag_to_cam[:3, 3].reshape(3, 1)
                proj_pts, _ = cv2.projectPoints(obj_pts, rvec, tvec, K, dist)
                proj_pts = proj_pts.reshape(-1, 2)
                reproj = np.linalg.norm(proj_pts - corners, axis=1)
                reproj_errors.append(float(np.mean(reproj)))

                view_cosines.append(view_cos)
            bench_timer.stop("pnp")
            t_reproj_ms = (perf_counter() - reproj_start) * 1000.0

            if pose_debug_active:
                used_ids = sorted(set(candidate_ids)) if candidate_ids else []
                LOGGER.info("pose_dbg: n_used_ids=%d ids=%s", len(used_ids), used_ids)
                LOGGER.info(
                    "pose_dbg: n_corr=%d points=%d",
                    len(transforms_cam_to_cyl),
                    len(candidate_ids) * 4,
                )

            if args.print_first_frame_stats and not printed_first_stats:
                used_ids = sorted(candidate_ids) if candidate_ids else []
                LOGGER.info(
                    "first_frame: dets_raw=%d dets_kept=%d unknown=%d used_ids=%s accepted=%s reject_reason=%s",
                    n_dets_raw,
                    len(candidate_ids),
                    n_unknown_ids,
                    used_ids,
                    None,
                    None,
                )
                printed_first_stats = True

            mean_candidate_area = float(np.mean(quad_areas)) if quad_areas else None
            depth_estimate = 0.0
            if transforms_cam_to_cyl:
                depth_estimate = float(np.mean([T[2, 3] for T in transforms_cam_to_cyl]))
            elif last_good_pose and last_good_pose.get("T_cam_to_cyl") is not None:
                depth_estimate = float(last_good_pose["T_cam_to_cyl"][2, 3])
    
            if save_bad_dir and (n_dropped_hamming > 0 or n_dropped_unknown > 0 or n_dropped_small > 0):
                now_ts = time.time()
                if now_ts - last_bad_save_ts >= 1.0:
                    save_bad_dir.mkdir(parents=True, exist_ok=True)
                    fname = save_bad_dir / f"frame_{frame_idx:06d}"
                    try:
                        cv2.imwrite(str(fname) + ".png", gray)
                        meta = {
                            "frame_idx": frame_idx,
                            "raw_detections": raw_det_info,
                            "kept_ids": [int(uid) for uid in candidate_ids],
                            "dropped_hamming": int(n_dropped_hamming),
                            "dropped_unknown": int(n_dropped_unknown),
                            "dropped_small": int(n_dropped_small),
                        }
                        with open(str(fname) + ".json", "w", encoding="utf-8") as fp:
                            json.dump(meta, fp)
                        last_bad_save_ts = now_ts
                    except Exception as exc:  # pylint: disable=broad-except
                        LOGGER.warning("Failed to save bad-detect frame: %s", exc)
    
            base_trans = float(getattr(args, "ransac_base_trans", args.ransac_trans) or args.ransac_trans)
            base_rot = float(getattr(args, "ransac_base_rot", args.ransac_rot) or args.ransac_rot)
            A_ref = float(getattr(args, "ransac_area_ref", 12000.0) or 12000.0)
            N_vis = len(transforms_cam_to_cyl)
            adaptive_enabled = bool(use_adaptive and N_vis > 0)
            ransac_trans_eff = base_trans
            ransac_rot_eff = base_rot
            if pose_debug_active and not adaptive_enabled:
                reason = "NO_TRANSFORMS" if N_vis == 0 else "ADAPTIVE_DISABLED"
                LOGGER.info("pose_dbg: early_exit reason=%s", reason)
                printed_first_pose_debug = True
            # Exit after detection to keep frame-limit tied to grabbed frames.
            if stop_after_frame and not adaptive_enabled:
                LOGGER.info("Reached frame limit (%d); exiting.", args.frames)
                break
            if adaptive_enabled:
                area_ratio = 1.0
                if mean_candidate_area and mean_candidate_area > 0.0 and A_ref > 0.0:
                    area_ratio = max(min(A_ref / mean_candidate_area, 10.0), 0.1)
                gamma_few = getattr(args, "gamma_few", 1.3)
                gamma_many = getattr(args, "gamma_many", 0.9)
                beta_trans = getattr(args, "beta_trans", 0.5)
                beta_rot = getattr(args, "beta_rot", 0.5)
                psi = 1.0
                if N_vis <= 2:
                    psi = float(gamma_few if gamma_few is not None else 1.3)
                elif N_vis > 6:
                    psi = float(gamma_many if gamma_many is not None else 0.9)
                ransac_trans_eff = base_trans * (area_ratio ** float(beta_trans if beta_trans is not None else 0.5)) * psi
                ransac_rot_eff = base_rot * (area_ratio ** float(beta_rot if beta_rot is not None else 0.5)) * psi
    
                status = "OK"
                pose_record: Optional[Dict[str, Optional[np.ndarray]]] = None
                total_candidates = len(transforms_cam_to_cyl)
                current_inlier_indices: List[int] = []
                mean_reproj_inliers = 0.0
                weight_min = 0.0
                weight_max = 0.0
                ransac_score = 0.0
                final_used_ids: List[int] = []
                final_margins: List[float] = []
                spike_delta_trans_m: Optional[float] = None
                spike_delta_rot_deg: Optional[float] = None
                spike_trans_thresh_m: Optional[float] = (
                    float(spike_trans_thresh_cli) if spike_trans_thresh_cli is not None else None
                )
                spike_rot_thresh_deg: float = float(max_tilt_jump_deg)
                spike_ref_age_frames: Optional[int] = (
                    int(spike_ref_age_override) if spike_ref_age_override is not None else None
                )
                spike_ref_frame_idx: Optional[int] = None
                consecutive_reject_spike = 0
                reject_reason = "OK"

                if pose_debug_active:
                    LOGGER.info("pose_dbg: ransac_in=%d", total_candidates)
        
                bench_timer.start("ransac")
                ransac_start = perf_counter()
                candidates: List[v1.PoseCandidate] = []
                override_thresholds = adaptive_enabled
                base_ransac_trans = float(args.ransac_trans)
                base_ransac_rot = float(args.ransac_rot)
                if override_thresholds:
                    args.ransac_trans = ransac_trans_eff
                    args.ransac_rot = ransac_rot_eff
                if transforms_cam_to_cyl:
                    try:
                        candidates = v1.fuse_with_optional_ransac(
                            transforms_cam_to_cyl, legacy_weights, args, rng
                        )
                    except Exception as exc:  # pylint: disable=broad-except
                        lower = str(exc).lower()
                        fallback: List[v1.PoseCandidate] = []
                        raw_candidates = getattr(exc, "candidates", None)
                        if raw_candidates:
                            for item in raw_candidates:
                                try:
                                    transform = np.asarray(item["transform"], dtype=np.float64)
                                    inliers = list(item.get("inliers", []))
                                    mean_error = float(item.get("mean_error", 0.0))
                                    fallback.append(v1.PoseCandidate(transform, inliers, mean_error))
                                except Exception:
                                    continue
                        if fallback and "more than one" in lower:
                            candidates = fallback
                        else:
                            LOGGER.warning("Fusion error: %s", exc)
                            candidates = []
                    finally:
                        if override_thresholds:
                            args.ransac_trans = base_ransac_trans
                            args.ransac_rot = base_ransac_rot
                    bench_timer.stop("ransac")
                    t_ransac_ms = (perf_counter() - ransac_start) * 1000.0
        
                    bench_timer.start("fuse")
                    fuse_start = perf_counter()
                    if not transforms_cam_to_cyl or not candidates:
                        status = "NO_POSE"
                    else:
                        selected = v1.select_candidate(candidates, last_good_pose)
                        ransac_score = float(selected.mean_error)
                        current_inlier_indices = selected.inliers or list(range(total_candidates))
                        if current_inlier_indices:
                            inlier_errors = [reproj_errors[i] for i in current_inlier_indices]
                            mean_reproj_inliers = float(np.mean(inlier_errors))
                            if quad_areas:
                                inlier_areas = [quad_areas[i] for i in current_inlier_indices if i < len(quad_areas)]
                                if inlier_areas:
                                    mean_tag_area_px2 = float(np.mean(inlier_areas))
                            if view_cosines:
                                inlier_cos = [view_cosines[i] for i in current_inlier_indices if i < len(view_cosines)]
                                if inlier_cos:
                                    mean_view_cos = float(np.mean(inlier_cos))
                            if inlier_errors:
                                mean_reproj_px = mean_reproj_inliers
                        # Log-linear tag quality model combines reprojection error, apparent area,
                        # view cosine, and detector margin; scores are softmaxed into fusion weights.
                        quality_weights: List[float] = []
                        if use_weighted and current_inlier_indices:
                            quality_weights = compute_quality_weights(
                                current_inlier_indices,
                                reproj_errors,
                                quad_areas,
                                view_cosines,
                                decision_margins,
                            )
                        if quality_weights:
                            weight_min = float(min(quality_weights))
                            weight_max = float(max(quality_weights))
                        else:
                            weight_min = 0.0
                            weight_max = 0.0
                        fused_cam_to_cyl = selected.transform
                        if use_weighted and quality_weights:
                            reference = (
                                last_good_pose["T_cam_to_cyl"]
                                if last_good_pose and last_good_pose.get("T_cam_to_cyl") is not None
                                else fused_cam_to_cyl
                            )
                            inlier_transforms = [transforms_cam_to_cyl[i] for i in current_inlier_indices]
                            fused_cam_to_cyl = weighted_average_se3(inlier_transforms, quality_weights, reference)
        
                        axis_obj = np.array([0.0, 0.0, 1.0])
                        axis_cam = fused_cam_to_cyl[:3, :3] @ axis_obj
                        if last_axis_cam is not None and float(np.dot(axis_cam, last_axis_cam)) < 0.0:
                            axis_cam = -axis_cam
                        last_axis_cam = axis_cam
        
                        fused_cyl_to_cam_pre = np.linalg.inv(fused_cam_to_cyl)
                        raw_tilt_cam_deg = v1.compute_tilt_deg(fused_cyl_to_cam_pre)
        
                        current_inlier_ids = [candidate_ids[i] for i in current_inlier_indices]
                        current_margins = [decision_margins[i] for i in current_inlier_indices]
        
                        spike_delta_trans_m: Optional[float] = None
                        spike_delta_rot_deg: Optional[float] = None
                        spike_trans_thresh_m: Optional[float] = None
                        spike_rot_thresh_deg: Optional[float] = None
                        spike_ref_age_frames: Optional[int] = None
                        spike_ref_frame_idx: Optional[int] = None
        
                        if len(current_inlier_ids) < min_inliers:
                            if last_good_pose is not None:
                                status = "HOLD_PREV_POSE"
                                pose_record = last_good_pose
                            else:
                                status = "NO_POSE"
                            spike_reject_streak = 0
                        elif last_good_pose is not None:
                            if spike_disable:
                                spike_reject_streak = 0
                            else:
                                can_spike_check = True
                                if last_accept_frame_idx is None:
                                    can_spike_check = False
                                elif spike_reset_after and (frame_idx - last_accept_frame_idx) < spike_reset_after:
                                    can_spike_check = False

                                if can_spike_check:
                                    tilt_jump = v1.wrap_deg180(
                                        raw_tilt_cam_deg - last_good_pose["tilt_cam_deg"]
                                    )
                                    trans_delta = float(
                                        np.linalg.norm(
                                            fused_cam_to_cyl[:3, 3]
                                            - last_good_pose["T_cam_to_cyl"][:3, 3]
                                        )
                                    )
                                    spike_delta_trans_m = trans_delta
                                    if tilt_jump > max_tilt_jump_deg:
                                        status = "REJECT_SPIKE"
                                        pose_record = last_good_pose
                                        spike_rot_thresh_deg = max_tilt_jump_deg
                                        spike_delta_rot_deg = float(tilt_jump)
                                    if (
                                        spike_trans_thresh_m is not None
                                        and trans_delta > spike_trans_thresh_m
                                    ):
                                        status = "REJECT_SPIKE"
                                        pose_record = last_good_pose
                                    if last_accept_frame_idx is not None:
                                        spike_ref_age_frames = frame_idx - last_accept_frame_idx
                                        spike_ref_frame_idx = last_accept_frame_idx
                                spike_reject_streak = 0
                        else:
                            spike_reject_streak = 0
        
                if status == "REJECT_SPIKE":
                    consecutive_reject_spike += 1
                else:
                    consecutive_reject_spike = 0
                reject_reason = status

                if pose_debug_active:
                    reproj_val = mean_reproj_inliers if mean_reproj_inliers is not None else mean_reproj_px
                    LOGGER.info(
                        "pose_dbg: pnp_ok=%s ransac_inliers=%d reproj_mean=%s",
                        bool(candidates),
                        len(current_inlier_indices),
                        f"{reproj_val:.3f}" if reproj_val is not None else "n/a",
                    )
                    if not candidates:
                        LOGGER.info("pose_dbg: early_exit reason=NO_CANDIDATES")
                    elif len(current_inlier_indices) < min_inliers:
                        LOGGER.info("pose_dbg: early_exit reason=TOO_FEW_INLIERS")
                    printed_first_pose_debug = True
    
                if status == "OK":
                    fused_cam_to_cyl, ema_state = v1.apply_ema_pose(
                        fused_cam_to_cyl, ema_state, ema_alpha
                    )
                    fused_cyl_to_cam = np.linalg.inv(fused_cam_to_cyl)
                    smooth_tilt_cam_deg = v1.compute_tilt_deg(fused_cyl_to_cam)
                    pose_record = v1.build_pose_record(
                        fused_cam_to_cyl,
                        current_inlier_ids,
                        current_margins,
                        smooth_tilt_cam_deg,
                        extrinsics_matrix,
                    )
                    pose_record["quat_cam"] = v1.continuous_quat(
                        pose_record["quat_cam"],
                        last_good_pose["quat_cam"] if last_good_pose else None,
                    )
                    if ema_state is not None:
                        ema_state["quat"] = pose_record["quat_cam"].copy()
                        ema_state["t"] = pose_record["T_cam_to_cyl"][:3, 3].copy()
                    last_good_pose = pose_record
                    last_tilt_cam = smooth_tilt_cam_deg
                    last_accept_frame_idx = frame_idx
                    spike_reject_streak = 0
                elif status in {"HOLD_PREV_POSE", "REJECT_SPIKE"}:
                    pose_record = last_good_pose
                bench_timer.stop("fuse")
                t_fuse_ms = (perf_counter() - fuse_start) * 1000.0
        
                if status == "NO_POSE" and last_good_pose is not None and len(current_inlier_indices) < min_inliers:
                    status = "HOLD_PREV_POSE"
                    pose_record = last_good_pose
    
                bench_timer.start("render")
                tilt_for_log = last_tilt_cam if last_tilt_cam is not None else 0.0
                if status == "REJECT_SPIKE":
                    reproj_val = mean_reproj_inliers if mean_reproj_inliers is not None else mean_reproj_px
                    if pose_record and "used_ids" in pose_record:
                        final_used_ids = pose_record["used_ids"]
                    used_ids_str = ",".join(str(uid) for uid in final_used_ids) if final_used_ids else ""
                    dt_s = (
                        "n/a"
                        if spike_delta_trans_m is None
                        else f"{format(spike_delta_trans_m, '.4f')}m"
                    )
                    dr_s = (
                        "n/a"
                        if spike_delta_rot_deg is None
                        else f"{format(spike_delta_rot_deg, '.3f')}deg"
                    )
                    thrT_s = (
                        "n/a"
                        if spike_trans_thresh_m is None
                        else f"{format(spike_trans_thresh_m, '.4f')}m"
                    )
                    thrR_s = (
                        "n/a"
                        if spike_rot_thresh_deg is None
                        else f"{format(spike_rot_thresh_deg, '.3f')}deg"
                    )
                    LOGGER.info(
                        "frame=%d reject=REJECT_SPIKE used_ids=%s dT=%s dR=%s thrT=%s thrR=%s ref_age=%s streak=%d reproj=%s",
                        frame_idx,
                        used_ids_str or "none",
                        dt_s,
                        dr_s,
                        thrT_s,
                        thrR_s,
                        spike_ref_age_frames if spike_ref_age_frames is not None else "n/a",
                        consecutive_reject_spike,
                        f"{reproj_val:.3f}" if reproj_val is not None else "n/a",
                    )
                if hud_enabled:
                    if pose_record is None:
                        if status == "NO_POSE":
                            LOGGER.info("frame=%d status=NO_POSE", frame_idx)
                        if not args.no_overlay:
                            hud_overlay_start = perf_counter()
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
                            t_hud_ms += (perf_counter() - hud_overlay_start) * 1000.0
                    else:
                        final_used_ids = pose_record["used_ids"]
                        final_margins = pose_record["decision_margins"]
                        tilt_cam_deg = pose_record["tilt_cam_deg"]
                        tilt_world_deg = pose_record.get("tilt_world_deg")
                        T_cyl_to_cam_final = pose_record["T_cyl_to_cam"]
                        rvec_cam = pose_record["rvec_cam"].reshape(3)
                        tvec_cam = pose_record["tvec_cam"].reshape(3)
                        rvec_world = pose_record.get("rvec_world")
                        tvec_world = pose_record.get("tvec_world")
    
                        if not args.no_overlay:
                            hud_overlay_start = perf_counter()
                            v1.draw_axes(frame, K, dist, T_cyl_to_cam_final, axis_len=float(args.axis_len))
                            draw_hud(
                                frame,
                                fps_estimate,
                                len(best_detections),
                                len(current_inlier_indices),
                                mean_reproj_inliers,
                                tilt_cam_deg,
                                mean_tag_area_px2,
                                mean_view_cos,
                                ransac_trans_eff,
                                ransac_rot_eff,
                                n_unknown_ids,
                                n_mirror_discards,
                                spike_delta_trans_m if status == "REJECT_SPIKE" else None,
                                spike_delta_rot_deg if status == "REJECT_SPIKE" else None,
                                extended=not v1_mode,
                            )
                            t_hud_ms += (perf_counter() - hud_overlay_start) * 1000.0
    
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
                        if status == "REJECT_SPIKE":
                            dt_s = (
                                "n/a"
                                if spike_delta_trans_m is None
                                else f"{format(spike_delta_trans_m, '.4f')}m"
                            )
                            dr_s = (
                                "n/a"
                                if spike_delta_rot_deg is None
                                else f"{format(spike_delta_rot_deg, '.3f')}deg"
                            )
                            thrR_s = (
                                "n/a"
                                if spike_rot_thresh_deg is None
                                else f"{format(spike_rot_thresh_deg, '.3f')}deg"
                            )
                            log_msg += (
                                f" spike dT={dt_s} dR={dr_s} "
                                f"thrR={thrR_s} ref_age={spike_ref_age_frames}"
                            )
                        LOGGER.info(log_msg)
    
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
                                        "quat_xyzw": list(
                                            v1.rotation_matrix_to_quaternion(T_cyl_to_cam_final[:3, :3])
                                        ),
                                    },
                                }
                                world_T = pose_record.get("T_world_to_cyl")
                                if world_T is not None and rvec_world is not None and tvec_world is not None:
                                    payload["world"] = {
                                        "t_m": [float(v) for v in tvec_world.reshape(-1)],
                                        "rvec": [float(v) for v in rvec_world.reshape(-1)],
                                        "quat_xyzw": list(v1.rotation_matrix_to_quaternion(world_T[:3, :3])),
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
    
                        tilt_for_log = tilt_cam_deg
    
                    if hud_enabled and not args.no_overlay and pose_record is None:
                        hud_overlay_start = perf_counter()
                        draw_hud(
                            frame,
                            fps_estimate,
                            len(best_detections),
                            len(current_inlier_indices),
                            mean_reproj_inliers,
                            tilt_for_log,
                            mean_tag_area_px2,
                            mean_view_cos,
                            ransac_trans_eff,
                            ransac_rot_eff,
                            n_unknown_ids,
                            n_mirror_discards,
                            None,
                            None,
                            extended=not v1_mode,
                        )
                        t_hud_ms += (perf_counter() - hud_overlay_start) * 1000.0
    
                    hud_overlay_start = perf_counter()
                    cv2.imshow(window_name, frame)
                    key = cv2.waitKey(1) & 0xFF
                    t_hud_ms += (perf_counter() - hud_overlay_start) * 1000.0
                else:
                    key = -1
                    t_hud_ms = 0.0

                if pose_record is not None and csv_writer and csv_fp:
                    timestamp = time.time()
                    final_used_ids = pose_record["used_ids"]
                    final_margins = pose_record["decision_margins"]
                    rvec_cam = pose_record["rvec_cam"].reshape(3)
                    tvec_cam = pose_record["tvec_cam"].reshape(3)
                    rvec_world = pose_record.get("rvec_world")
                    tvec_world = pose_record.get("tvec_world")
                    tilt_cam_deg = pose_record["tilt_cam_deg"]
                    tilt_world_deg = pose_record.get("tilt_world_deg")
                    row: List[object] = [
                        f"{timestamp:.6f}",
                        frame_idx,
                        v1.format_int_list(final_used_ids),
                        v1.format_float_list(final_margins),
                    ]
                    row.extend(float(v) for v in rvec_cam.reshape(-1))
                    row.extend(float(v) for v in tvec_cam.reshape(-1))
                    if rvec_world is not None and tvec_world is not None:
                        row.extend(float(v) for v in rvec_world.reshape(-1))
                        row.extend(float(v) for v in tvec_world.reshape(-1))
                    else:
                        row.extend([""] * 6)
                    row.append(f"{tilt_cam_deg:.3f}" if tilt_cam_deg is not None else "")
                    row.append(f"{tilt_world_deg:.3f}" if tilt_world_deg is not None else "")
                    log_start = perf_counter()
                    csv_writer.writerow(row)
                    csv_fp.flush()
                    t_log_ms += (perf_counter() - log_start) * 1000.0
                bench_timer.stop("render")
        
                if t_total_ms is None:
                    t_total_ms = (perf_counter() - loop_t0) * 1000.0
    
                if status == "REJECT_SPIKE":
                    reproj_val = mean_reproj_inliers if mean_reproj_inliers is not None else mean_reproj_px
                    LOGGER.info(
                        "frame=%d reject=%s dets=%d inliers=%d reproj=%s t_total_ms=%.3f",
                        frame_idx,
                        status,
                        total_candidates,
                        len(current_inlier_indices),
                        f"{reproj_val:.3f}" if reproj_val is not None else "n/a",
                        t_total_ms if t_total_ms is not None else (perf_counter() - loop_t0) * 1000.0,
                    )
    
                accepted = status in {"OK", "HOLD_PREV_POSE"}
                if args.print_first_frame_stats and not printed_first_stats:
                    used_ids = sorted(final_used_ids) if final_used_ids else sorted(candidate_ids)
                    LOGGER.info(
                        "first_frame: dets_raw=%d dets_kept=%d unknown=%d used_ids=%s accepted=%s reject_reason=%s",
                        n_dets_raw,
                        len(candidate_ids),
                        n_unknown_ids,
                        used_ids,
                        accepted,
                        reject_reason,
                    )
                    printed_first_stats = True
                if debug_logger:
                    debug_logger.log(
                        fps_estimate,
                        len(best_detections),
                        len(current_inlier_indices),
                        mean_reproj_inliers,
                        ransac_score,
                        weight_min,
                        weight_max,
                        tilt_for_log,
                        mean_tag_area_px2,
                        mean_view_cos,
                        mean_reproj_px,
                        ransac_trans_eff,
                        ransac_rot_eff,
                        n_unknown_ids,
                        n_mirror_discards,
                        n_dets_raw=n_dets_raw,
                        n_dets_kept=len(candidate_ids),
                        n_dropped_hamming=n_dropped_hamming,
                        n_dropped_unknown=n_dropped_unknown,
                        n_dropped_small=n_dropped_small,
                        max_hamming_used=max_hamming_used,
                        spike_delta_trans_m=spike_delta_trans_m,
                        spike_delta_rot_deg=spike_delta_rot_deg,
                        spike_trans_thresh_m=spike_trans_thresh_m,
                        spike_rot_thresh_deg=spike_rot_thresh_deg,
                        spike_ref_age_frames=spike_ref_age_frames,
                        spike_ref_frame_idx=spike_ref_frame_idx,
                        reject_reason=reject_reason,
                        consecutive_reject_spike=consecutive_reject_spike,
                        used_ids=",".join(str(uid) for uid in final_used_ids) if final_used_ids else "",
                        accepted=accepted,
                        t_read_ms=t_read_ms,
                        t_gray_ms=t_gray_ms,
                        t_detect_ms=t_detect_ms,
                        t_reproj_ms=t_reproj_ms,
                        t_ransac_ms=t_ransac_ms,
                        t_fuse_ms=t_fuse_ms,
                        t_ekf_ms=t_ekf_ms,
                        t_hud_ms=t_hud_ms,
                        t_log_ms=t_log_ms,
                        t_total_ms=t_total_ms,
                    )
                n_frames_processed += 1
                if key == 27:  # ESC
                    LOGGER.info("ESC pressed, exiting.")
                    break
                frame_idx += 1
                frame_count += 1
                bench_timer.snapshot()
                if stop_after_frame:
                    # Honor --frames after processing this grabbed frame.
                    LOGGER.info("Reached frame limit (%d); exiting.", args.frames)
                    break
    except KeyboardInterrupt:
        LOGGER.info("Interrupted by user.")
    finally:
        if basler_cam is not None:
            basler_cam.release()
        if cap is not None:
            cap.release()
        if hud_enabled:
            cv2.destroyAllWindows()
        if csv_fp:
            csv_fp.close()
        if debug_logger:
            debug_logger.close()
        if udp_sock:
            udp_sock.close()
        if start_time is not None:
            end_time = time.perf_counter()
            elapsed = end_time - start_time
            if n_frames_processed > 0 and elapsed > 0:
                LOGGER.info(
                    "Processed %d frames in %.3f s (effective FPS: %.2f)",
                    n_frames_processed,
                    elapsed,
                    n_frames_processed / elapsed,
                )
            else:
                LOGGER.warning("No frames processed or zero elapsed time; skipping FPS report.")
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
