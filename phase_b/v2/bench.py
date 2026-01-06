"""Micro-benchmark timers for Phase B v2."""

from __future__ import annotations

import logging
import time
from collections import defaultdict
from typing import Dict, Optional


LOGGER = logging.getLogger("phase_b.bench")


class StageTimer:
    """Collect per-stage timings and emit summaries periodically."""

    def __init__(self, print_every: int = 60) -> None:
        self.print_every = max(1, int(print_every))
        self._running: Dict[str, float] = {}
        self._frame_accum: Dict[str, float] = {}
        self._window_accum = defaultdict(float)
        self._frame_count = 0
        self._last_window_start = time.perf_counter()

    def start(self, stage: str) -> None:
        self._running[stage] = time.perf_counter()

    def stop(self, stage: str) -> float:
        start = self._running.pop(stage, None)
        if start is None:
            return 0.0
        elapsed_ms = (time.perf_counter() - start) * 1000.0
        self._frame_accum[stage] = self._frame_accum.get(stage, 0.0) + elapsed_ms
        return elapsed_ms

    def snapshot(self) -> None:
        """Commit the current frame timings and print a summary if needed."""
        self._frame_count += 1
        for stage, duration in self._frame_accum.items():
            self._window_accum[stage] += duration
        total_ms = sum(self._frame_accum.values())
        if self._frame_count % self.print_every == 0:
            denom = float(self.print_every)
            frame_total = sum(self._window_accum.values()) / denom if denom else 0.0
            wall = time.perf_counter()
            wall_elapsed = wall - self._last_window_start
            self._last_window_start = wall
            fps = (self.print_every / wall_elapsed) if wall_elapsed > 0 else 0.0
            parts = []
            for stage, acc in sorted(self._window_accum.items()):
                avg_ms = acc / denom
                pct = (avg_ms / frame_total * 100.0) if frame_total > 0.0 else 0.0
                parts.append(f"{stage}={avg_ms:.2f}ms ({pct:.1f}%)")
            if parts:
                LOGGER.info(
                    "[bench] over %d frames total=%.2fms fps=%.2f wall=%.2fs %s",
                    self.print_every,
                    frame_total,
                    fps,
                    wall_elapsed,
                    " ".join(parts),
                )
            self._window_accum.clear()
        self._frame_accum.clear()
