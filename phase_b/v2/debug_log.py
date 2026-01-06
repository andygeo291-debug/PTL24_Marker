"""Debug metrics logging and HUD helpers for Phase B v2."""

from __future__ import annotations

import csv
import time
from pathlib import Path
from typing import Iterable, Optional

import cv2


class DebugLogger:
    """Append per-frame debug metrics with a fixed header."""

    header = [
        "t",
        "fps",
        "n_visible",
        "n_inliers",
        "mean_reproj",
        "ransac_score",
        "weight_min",
        "weight_max",
        "tilt_deg",
        "mean_tag_area_px2",
        "mean_view_cos",
        "mean_reproj_px",
        "ransac_trans_eff",
        "ransac_rot_eff",
        "n_unknown_ids",
        "n_mirror_discards",
        "n_dets_raw",
        "n_dets_kept",
        "n_dropped_hamming",
        "n_dropped_unknown",
        "n_dropped_small",
        "max_hamming_used",
        "spike_delta_trans_m",
        "spike_delta_rot_deg",
        "spike_trans_thresh_m",
        "spike_rot_thresh_deg",
        "spike_ref_age_frames",
        "spike_ref_frame_idx",
        "reject_reason",
        "consecutive_reject_spike",
        "used_ids",
        "accepted",
        "t_read_ms",
        "t_gray_ms",
        "t_detect_ms",
        "t_reproj_ms",
        "t_ransac_ms",
        "t_fuse_ms",
        "t_ekf_ms",
        "t_hud_ms",
        "t_log_ms",
        "t_total_ms",
    ]

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._fp = self.path.open("a+", encoding="utf-8", newline="")
        self._writer = csv.writer(self._fp)
        self._ensure_header()

    def _ensure_header(self) -> None:
        self._fp.flush()
        self._fp.seek(0)
        existing = self._fp.readline()
        # Skip provenance comment lines.
        while existing.startswith("#"):
            existing = self._fp.readline()
        if existing:
            if existing.strip() == ",".join(self.header):
                self._fp.seek(0, 2)
                return
            # Rewind and append because header mismatch; leave existing data untouched.
            self._fp.seek(0, 2)
            return
        self._writer.writerow(self.header)
        self._fp.flush()

    def log(
        self,
        fps: float,
        n_visible: int,
        n_inliers: int,
        mean_reproj: float,
        ransac_score: float,
        weight_min: float,
        weight_max: float,
        tilt_deg: float,
        mean_tag_area_px2: Optional[float] = None,
        mean_view_cos: Optional[float] = None,
        mean_reproj_px: Optional[float] = None,
        ransac_trans_eff: Optional[float] = None,
        ransac_rot_eff: Optional[float] = None,
        n_unknown_ids: Optional[int] = None,
        n_mirror_discards: Optional[int] = None,
        spike_delta_trans_m: Optional[float] = None,
        spike_delta_rot_deg: Optional[float] = None,
        spike_trans_thresh_m: Optional[float] = None,
        spike_rot_thresh_deg: Optional[float] = None,
        spike_ref_age_frames: Optional[int] = None,
        spike_ref_frame_idx: Optional[int] = None,
        reject_reason: Optional[str] = None,
        consecutive_reject_spike: int = 0,
        used_ids: Optional[str] = None,
        accepted: bool = True,
        n_dets_raw: Optional[int] = None,
        n_dets_kept: Optional[int] = None,
        n_dropped_hamming: Optional[int] = None,
        n_dropped_unknown: Optional[int] = None,
        n_dropped_small: Optional[int] = None,
        max_hamming_used: Optional[int] = None,
        t_read_ms: Optional[float] = None,
        t_gray_ms: Optional[float] = None,
        t_detect_ms: Optional[float] = None,
        t_reproj_ms: Optional[float] = None,
        t_ransac_ms: Optional[float] = None,
        t_fuse_ms: Optional[float] = None,
        t_ekf_ms: Optional[float] = None,
        t_hud_ms: Optional[float] = None,
        t_log_ms: Optional[float] = None,
        t_total_ms: Optional[float] = None,
    ) -> None:
        def fmt_float(value: Optional[float], pattern: str) -> str:
            return "" if value is None else pattern.format(value)

        def fmt_int(value: Optional[int]) -> str:
            return "" if value is None else str(int(value))

        row = [
            f"{time.time():.6f}",
            f"{fps:.3f}",
            int(n_visible),
            int(n_inliers),
            f"{mean_reproj:.3f}",
            f"{ransac_score:.5f}",
            f"{weight_min:.3f}",
            f"{weight_max:.3f}",
            f"{tilt_deg:.3f}",
            fmt_float(mean_tag_area_px2, "{:.1f}"),
            fmt_float(mean_view_cos, "{:.4f}"),
            fmt_float(mean_reproj_px, "{:.3f}"),
            fmt_float(ransac_trans_eff, "{:.4f}"),
            fmt_float(ransac_rot_eff, "{:.3f}"),
            fmt_int(n_unknown_ids),
            fmt_int(n_mirror_discards),
            fmt_int(n_dets_raw),
            fmt_int(n_dets_kept),
            fmt_int(n_dropped_hamming),
            fmt_int(n_dropped_unknown),
            fmt_int(n_dropped_small),
            fmt_int(max_hamming_used),
            fmt_float(spike_delta_trans_m, "{:.4f}"),
            fmt_float(spike_delta_rot_deg, "{:.3f}"),
            fmt_float(spike_trans_thresh_m, "{:.4f}"),
            fmt_float(spike_rot_thresh_deg, "{:.3f}"),
            fmt_int(spike_ref_age_frames),
            fmt_int(spike_ref_frame_idx),
            reject_reason or "",
            str(int(consecutive_reject_spike)),
            used_ids or "",
            "1" if accepted else "0",
            fmt_float(t_read_ms, "{:.3f}"),
            fmt_float(t_gray_ms, "{:.3f}"),
            fmt_float(t_detect_ms, "{:.3f}"),
            fmt_float(t_reproj_ms, "{:.3f}"),
            fmt_float(t_ransac_ms, "{:.3f}"),
            fmt_float(t_fuse_ms, "{:.3f}"),
            fmt_float(t_ekf_ms, "{:.3f}"),
            fmt_float(t_hud_ms, "{:.3f}"),
            fmt_float(t_log_ms, "{:.3f}"),
            fmt_float(t_total_ms, "{:.3f}"),
        ]
        self._writer.writerow(row)
        self._fp.flush()

    def close(self) -> None:
        self._fp.close()

    def __enter__(self) -> "DebugLogger":
        return self

    def __exit__(self, exc_type, exc, exc_tb) -> None:
        self.close()


def draw_hud(
    frame,
    fps: float,
    n_visible: int,
    n_inliers: int,
    mean_reproj: float,
    tilt_deg: float,
    mean_tag_area_px2: Optional[float] = None,
    mean_view_cos: Optional[float] = None,
    ransac_trans_eff: Optional[float] = None,
    ransac_rot_eff: Optional[float] = None,
    n_unknown_ids: Optional[int] = None,
    n_mirror_discards: Optional[int] = None,
    spike_delta_trans_m: Optional[float] = None,
    spike_delta_rot_deg: Optional[float] = None,
    color: Optional[Iterable[int]] = None,
    extended: bool = True,
) -> None:
    """Render a single-line HUD overlay in the top-left corner."""
    color = tuple(int(c) for c in (color or (255, 255, 255)))
    text = (
        f"fps={fps:.1f} "
        f"vis={n_visible} "
        f"inliers={n_inliers} "
        f"reproj={mean_reproj:.2f}px "
        f"tilt={tilt_deg:.1f}deg"
    )
    if extended:
        area_str = (
            f"{int(round(mean_tag_area_px2))}" if mean_tag_area_px2 is not None else "-"
        )
        cos_str = f"{mean_view_cos:.2f}" if mean_view_cos is not None else "-"
        trans_str = (
            f"{ransac_trans_eff * 100.0:.2f}" if ransac_trans_eff is not None else "-"
        )
        rot_str = f"{ransac_rot_eff:.1f}" if ransac_rot_eff is not None else "-"
        unk_str = str(int(n_unknown_ids)) if n_unknown_ids is not None else "-"
        mir_str = str(int(n_mirror_discards)) if n_mirror_discards is not None else "-"
        text += (
            f" area:{area_str}"
            f" cos:{cos_str}"
            f" tr:{trans_str}cm"
            f" rr:{rot_str}°"
            f" unk:{unk_str}"
            f" mir:{mir_str}"
        )
    if spike_delta_trans_m is not None or spike_delta_rot_deg is not None:
        dT = f"{spike_delta_trans_m:.3f}" if spike_delta_trans_m is not None else "-"
        dR = f"{spike_delta_rot_deg:.2f}" if spike_delta_rot_deg is not None else "-"
        text += f" spike dT={dT}m dR={dR}deg"
    cv2.putText(
        frame,
        text,
        (10, 24),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.6,
        color,
        2,
        cv2.LINE_AA,
    )
