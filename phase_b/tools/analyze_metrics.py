import argparse
import csv
import os

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

FPS_CANDIDATES = ["fps_inst", "fps"]
TILT_CANDIDATES = ["tilt_cam_deg", "tilt_world_deg", "tilt_deg"]
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
    parser = argparse.ArgumentParser(description="Analyze Phase B debug metrics CSV.")
    parser.add_argument(
        "--csv",
        required=True,
        help="Path to debug_metrics.csv produced by the Phase B runner.",
    )
    parser.add_argument(
        "--out",
        required=True,
        help="Directory where plots will be written.",
    )
    parser.add_argument(
        "--max-rows",
        type=int,
        default=None,
        help="Optional limit on number of rows to analyze.",
    )
    return parser.parse_args()


def load_metrics(csv_path: str, max_rows: int | None) -> pd.DataFrame:
    try:
        df = pd.read_csv(csv_path, comment="#")
    except FileNotFoundError:
        print(f"[analyze_metrics] CSV not found: {csv_path}")
        raise
    except pd.errors.ParserError:
        # Gracefully handle mixed-width rows from older logs by falling back to the
        # python engine and skipping malformed lines.
        df = pd.read_csv(
            csv_path,
            comment="#",
            engine="python",
            on_bad_lines="skip",
        )
    if df.empty:
        print(f"[analyze_metrics] CSV contains no rows: {csv_path}")
        return df
    if max_rows is not None and max_rows > 0:
        df = df.iloc[:max_rows]
    return df


def median_numeric(series: pd.Series) -> float | None:
    values = pd.to_numeric(series, errors="coerce").dropna()
    if values.empty:
        return None
    return float(values.median())


def plot_line(x, y, xlabel: str, ylabel: str, title: str, out_path: str) -> None:
    fig = plt.figure(figsize=(10, 4))
    plt.plot(x, y, linewidth=1.0)
    plt.xlabel(xlabel)
    plt.ylabel(ylabel)
    plt.title(title)
    plt.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def plot_hist(data, xlabel: str, title: str, out_path: str, bins: int = 40) -> None:
    fig = plt.figure(figsize=(6, 4))
    plt.hist(data, bins=bins, edgecolor="black", alpha=0.7)
    plt.xlabel(xlabel)
    plt.ylabel("Count")
    plt.title(title)
    plt.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def analyze_fps(df: pd.DataFrame, out_dir: str) -> bool:
    fps_col = next((col for col in FPS_CANDIDATES if col in df.columns), None)
    if fps_col is None:
        print(
            "[analyze_metrics] No FPS column found; checked "
            f"{', '.join(FPS_CANDIDATES)}. Skipping FPS analysis."
        )
        return False
    fps = pd.to_numeric(df[fps_col], errors="coerce").dropna()
    if fps.empty:
        print(f"[analyze_metrics] {fps_col} column has no numeric data; skipping.")
        return False
    stats = {
        "mean": float(fps.mean()),
        "median": float(fps.median()),
        "std": float(fps.std(ddof=0)),
        "p25": float(np.percentile(fps, 25)),
        "p50": float(np.percentile(fps, 50)),
        "p75": float(np.percentile(fps, 75)),
        "p95": float(np.percentile(fps, 95)),
    }
    print("FPS statistics:")
    print(f"  mean   : {stats['mean']:.3f}")
    print(f"  median : {stats['median']:.3f}")
    print(f"  std    : {stats['std']:.3f}")
    print(
        "  p25/p50/p75/p95: "
        f"{stats['p25']:.3f} / {stats['p50']:.3f} / {stats['p75']:.3f} / {stats['p95']:.3f}"
    )

    if "frame_idx" in df.columns:
        x = pd.to_numeric(df["frame_idx"], errors="coerce").fillna(df.index)
    else:
        x = np.arange(len(df))
    plot_line(
        x=x,
        y=fps,
        xlabel="Frame index",
        ylabel=fps_col,
        title="Instant FPS over time",
        out_path=os.path.join(out_dir, "fps_over_time.png"),
    )
    plot_hist(
        data=fps,
        xlabel=fps_col,
        title="FPS histogram",
        out_path=os.path.join(out_dir, "fps_hist.png"),
    )
    return True


def analyze_tilt(df: pd.DataFrame, out_dir: str) -> bool:
    tilt_col = next((col for col in TILT_CANDIDATES if col in df.columns), None)
    if tilt_col is None:
        print(
            "No tilt column found; checked "
            f"{', '.join(TILT_CANDIDATES)}. Skipping tilt analysis."
        )
        return False

    tilt = pd.to_numeric(df[tilt_col], errors="coerce").dropna()
    if tilt.empty:
        print(f"[analyze_metrics] {tilt_col} column has no numeric data; skipping.")
        return False

    stats = {
        "mean": float(tilt.mean()),
        "std": float(tilt.std(ddof=0)),
        "min": float(tilt.min()),
        "max": float(tilt.max()),
    }
    print(f"Tilt statistics (using {tilt_col}):")
    print(f"  mean: {stats['mean']:.3f}")
    print(f"  std : {stats['std']:.3f}")
    print(f"  min : {stats['min']:.3f}")
    print(f"  max : {stats['max']:.3f}")

    if "frame_idx" in df.columns:
        x = pd.to_numeric(df["frame_idx"], errors="coerce").fillna(df.index)
    else:
        x = np.arange(len(df))
    plot_line(
        x=x,
        y=tilt,
        xlabel="Frame index",
        ylabel=tilt_col,
        title=f"{tilt_col} over time",
        out_path=os.path.join(out_dir, f"{tilt_col}_over_time.png"),
    )
    plot_hist(
        data=tilt,
        xlabel=tilt_col,
        title=f"{tilt_col} histogram",
        out_path=os.path.join(out_dir, f"{tilt_col}_hist.png"),
    )
    return True


def analyze_timing(df: pd.DataFrame, out_dir: str) -> bool:
    available = [col for col in STAGE_COLUMNS if col in df.columns]
    if not available:
        print("[analyze_metrics] No per-stage timing columns found; skipping timing breakdown.")
        return False

    medians = {}
    for col in available:
        median_val = median_numeric(df[col])
        if median_val is not None:
            medians[col] = median_val
    if not medians:
        print("[analyze_metrics] Timing columns contained no numeric data; skipping.")
        return False

    total_median = medians.get("t_total_ms")
    effective_fps = (1000.0 / total_median) if total_median and total_median > 0.0 else None

    lines = []
    lines.append("Timing breakdown (median values, milliseconds)")
    if total_median is not None:
        lines.append(f"t_total_ms: {total_median:.3f}")
    if effective_fps is not None:
        lines.append(f"effective_fps (1000/median_total): {effective_fps:.3f}")
    lines.append("")
    lines.append("Per-stage medians and share of total:")

    stage_rows = []
    for col in STAGE_COLUMNS:
        if col not in medians:
            continue
        median_val = medians[col]
        pct = (median_val / total_median * 100.0) if total_median and total_median > 0.0 else None
        stage_rows.append((col, median_val, pct))
        pct_str = f"{pct:.2f}%" if pct is not None else "-"
        lines.append(f"  {col}: {median_val:.3f} ms ({pct_str})")

    txt_path = os.path.join(out_dir, "timing_breakdown.txt")
    with open(txt_path, "w", encoding="utf-8") as fp:
        fp.write("\n".join(lines))
    print(f"[analyze_metrics] Wrote timing summary to {txt_path}")

    csv_path = os.path.join(out_dir, "timing_breakdown.csv")
    with open(csv_path, "w", encoding="utf-8", newline="") as fp:
        writer = csv.writer(fp)
        writer.writerow(["stage", "median_ms", "pct_of_median_total"])
        for stage, median_val, pct in stage_rows:
            writer.writerow(
                [
                    stage,
                    f"{median_val:.3f}",
                    f"{pct:.2f}" if pct is not None else "",
                ]
            )
    print(f"[analyze_metrics] Wrote timing table to {csv_path}")
    return True


def main() -> int:
    args = parse_args()
    csv_path = args.csv
    out_dir = args.out
    max_rows = args.max_rows

    if not os.path.exists(csv_path):
        print(f"[analyze_metrics] CSV not found: {csv_path}")
        return 1

    try:
        df = load_metrics(csv_path, max_rows)
    except FileNotFoundError:
        return 1

    if df.empty:
        return 1

    os.makedirs(out_dir, exist_ok=True)

    ran_any = False
    if analyze_fps(df, out_dir):
        ran_any = True
    if analyze_tilt(df, out_dir):
        ran_any = True
    if analyze_timing(df, out_dir):
        ran_any = True

    if not ran_any:
        print("[analyze_metrics] No analyses were run (missing columns).")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
