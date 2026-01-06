"""Quality weighting helpers for per-tag pose fusion."""

from __future__ import annotations

import math
from typing import Iterable, List


def tag_quality(reproj_err_px: float, tag_area_px2: float, view_cos: float) -> float:
    """Return a heuristic quality score for a single tag pose."""
    err = max(float(reproj_err_px), 0.0)
    area = max(float(tag_area_px2), 0.0)
    cos_term = max(min(float(view_cos), 1.0), -1.0)
    confidence = 1.0 / (err + 1.0)
    area_term = math.sqrt(area)
    angular_term = 0.5 + 0.5 * cos_term
    return confidence * area_term * angular_term


def softmax(values: Iterable[float]) -> List[float]:
    """Compute a numerically stable softmax distribution."""
    values = [float(v) for v in values]
    if not values:
        return []
    max_val = max(values)
    exp_vals = [math.exp(v - max_val) for v in values]
    total = sum(exp_vals)
    if total <= 0.0:
        count = len(values)
        return [1.0 / count for _ in values]
    return [val / total for val in exp_vals]
