import argparse
import os
from typing import Dict, List, Optional, Tuple

import pandas as pd

FPS_CANDIDATES = ["fps_inst", "fps"]
STAGE_COLUMNS = [
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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compare two Phase B debug_metrics.csv runs.")
    parser.add_argument("--csv-a", required=True, help="Debug metrics CSV for run A.")
    parser.add_argument("--csv-b", required=True, help="Debug metrics CSV for run B.")
    parser.add_argument("--label-a", required=True, help="Label for run A (e.g., 720p).")
    parser.add_argument("--label-b", required=True, help="Label for run B (e.g., 1080p).")
    parser.add_argument(
        "--out",
        required=True,
        help="Path to write the comparison report (txt/markdown).",
    )
    return parser.parse_args()


def load_csv(path: str) -> pd.DataFrame:
    try:
        df = pd.read_csv(path, comment="#")
    except FileNotFoundError as exc:
        raise SystemExit(f"[compare_runs] CSV not found: {path}") from exc
    except pd.errors.ParserError:
        # Mixed-width rows from older logs; fall back to python engine and skip bad lines.
        df = pd.read_csv(path, comment="#", engine="python", on_bad_lines="skip")
    if df.empty:
        raise SystemExit(f"[compare_runs] CSV is empty: {path}")
    return df


def median_numeric(series: pd.Series) -> Optional[float]:
    values = pd.to_numeric(series, errors="coerce").dropna()
    if values.empty:
        return None
    return float(values.median())


def pick_median(df: pd.DataFrame, candidates: List[str]) -> Tuple[Optional[float], Optional[str]]:
    for col in candidates:
        if col not in df.columns:
            continue
        median_val = median_numeric(df[col])
        if median_val is not None:
            return median_val, col
    return None, None


def stage_medians(df: pd.DataFrame) -> Dict[str, float]:
    medians: Dict[str, float] = {}
    for col in STAGE_COLUMNS:
        if col not in df.columns:
            continue
        median_val = median_numeric(df[col])
        if median_val is not None:
            medians[col] = median_val
    return medians


def format_ms(value: Optional[float]) -> str:
    return "-" if value is None else f"{value:.3f}"


def format_pct(value: Optional[float]) -> str:
    return "-" if value is None else f"{value:.2f}%"


def build_report(
    label_a: str,
    label_b: str,
    fps_a: Optional[float],
    fps_b: Optional[float],
    t_total_a: Optional[float],
    t_total_b: Optional[float],
    stages_a: Dict[str, float],
    stages_b: Dict[str, float],
) -> str:
    lines: List[str] = []
    lines.append(f"Comparison: {label_a} vs {label_b}")
    lines.append("")
    lines.append("Medians (per-frame):")
    lines.append(f"- {label_a}: fps={format_ms(fps_a)} median_t_total_ms={format_ms(t_total_a)}")
    lines.append(f"- {label_b}: fps={format_ms(fps_b)} median_t_total_ms={format_ms(t_total_b)}")

    if t_total_a is not None and t_total_b is not None and t_total_a > 0.0:
        delta_ms = t_total_b - t_total_a
        delta_pct = delta_ms / t_total_a * 100.0
        eff_fps_a = 1000.0 / t_total_a if t_total_a > 0.0 else None
        eff_fps_b = 1000.0 / t_total_b if t_total_b > 0.0 else None
        lines.append(
            f"- effective_fps (1000/median_total): {label_a}={format_ms(eff_fps_a)} "
            f"{label_b}={format_ms(eff_fps_b)}"
        )
        lines.append(
            f"- Δ total (B - A): {delta_ms:.3f} ms ({delta_pct:.2f}% relative to {label_a})"
        )
    else:
        lines.append("- Missing t_total_ms in one or both runs; skipping total comparison.")

    lines.append("")
    lines.append("Stage medians (ms) and share of median total:")
    header = (
        f"{'stage':<14} {label_a + ' ms':>12} {label_a + ' %':>10} "
        f"{label_b + ' ms':>12} {label_b + ' %':>10} {'Δms (B-A)':>12} {'Δ% vs A':>10}"
    )
    lines.append(header)
    lines.append("-" * len(header))

    all_stages = {stage for stage in STAGE_COLUMNS if stage in stages_a or stage in stages_b}

    def stage_pct(stage: str, median_total: Optional[float], medians: Dict[str, float]) -> Optional[float]:
        if median_total is None or median_total <= 0.0:
            return None
        value = medians.get(stage)
        if value is None:
            return None
        return value / median_total * 100.0

    for stage in [s for s in STAGE_COLUMNS if s in all_stages]:
        a_ms = stages_a.get(stage)
        b_ms = stages_b.get(stage)
        a_pct = stage_pct(stage, t_total_a, stages_a)
        b_pct = stage_pct(stage, t_total_b, stages_b)
        delta_ms = b_ms - a_ms if (a_ms is not None and b_ms is not None) else None
        delta_pct = None
        if delta_ms is not None and a_ms and a_ms != 0.0:
            delta_pct = delta_ms / a_ms * 100.0
        lines.append(
            f"{stage:<14} {format_ms(a_ms):>12} {format_pct(a_pct):>10} "
            f"{format_ms(b_ms):>12} {format_pct(b_pct):>10} {format_ms(delta_ms):>12} {format_pct(delta_pct):>10}"
        )

    return "\n".join(lines)


def main() -> int:
    args = parse_args()
    df_a = load_csv(args.csv_a)
    df_b = load_csv(args.csv_b)

    fps_a, fps_col_a = pick_median(df_a, FPS_CANDIDATES)
    fps_b, fps_col_b = pick_median(df_b, FPS_CANDIDATES)
    if fps_col_a is None:
        print(f"[compare_runs] No FPS column found for {args.label_a}; checked {', '.join(FPS_CANDIDATES)}")
    if fps_col_b is None:
        print(f"[compare_runs] No FPS column found for {args.label_b}; checked {', '.join(FPS_CANDIDATES)}")

    stages_a = stage_medians(df_a)
    stages_b = stage_medians(df_b)
    t_total_a = stages_a.get("t_total_ms")
    t_total_b = stages_b.get("t_total_ms")

    report = build_report(
        args.label_a,
        args.label_b,
        fps_a,
        fps_b,
        t_total_a,
        t_total_b,
        stages_a,
        stages_b,
    )

    out_path = args.out
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fp:
        fp.write(report)
    print(f"[compare_runs] Wrote report to {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
