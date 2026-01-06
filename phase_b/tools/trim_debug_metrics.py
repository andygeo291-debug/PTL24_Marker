import argparse
import os
from typing import List, Optional

import pandas as pd


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Trim initial seconds from debug_metrics CSV.")
    parser.add_argument("--csv", required=True, help="Input debug_metrics.csv path.")
    parser.add_argument(
        "--skip-seconds",
        type=float,
        default=0.0,
        help="Seconds from start to drop (based on first timestamp column).",
    )
    parser.add_argument("--out", required=True, help="Output trimmed CSV path.")
    return parser.parse_args()


def read_with_comments(path: str) -> tuple[pd.DataFrame, List[str]]:
    """Load CSV, keeping any leading comment lines."""
    comments: List[str] = []
    with open(path, "r", encoding="utf-8") as fp:
        while True:
            pos = fp.tell()
            line = fp.readline()
            if not line:
                break
            if line.startswith("#"):
                comments.append(line.rstrip("\n"))
            else:
                fp.seek(pos)
                break
    try:
        df = pd.read_csv(path, comment="#")
    except pd.errors.ParserError:
        df = pd.read_csv(path, comment="#", engine="python", on_bad_lines="skip")
    return df, comments


def main() -> int:
    args = parse_args()
    in_path = args.csv
    out_path = args.out
    skip_seconds = max(0.0, float(args.skip_seconds))

    if not os.path.exists(in_path):
        print(f"[trim_debug_metrics] input not found: {in_path}")
        return 1

    df, comments = read_with_comments(in_path)
    if df.empty:
        print(f"[trim_debug_metrics] no data rows in {in_path}")
        return 1

    if "t" not in df.columns:
        print("[trim_debug_metrics] missing 't' column; cannot trim by time.")
        return 1

    times = pd.to_numeric(df["t"], errors="coerce").dropna()
    if times.empty:
        print("[trim_debug_metrics] no numeric timestamps; cannot trim.")
        return 1

    start_ts = float(times.iloc[0])
    cutoff = start_ts + skip_seconds
    trimmed = df[pd.to_numeric(df["t"], errors="coerce") >= cutoff]

    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    with open(out_path, "w", encoding="utf-8", newline="") as fp:
        for line in comments:
            fp.write(f"{line}\n")
        trimmed.to_csv(fp, index=False)
    print(
        f"[trim_debug_metrics] wrote {len(trimmed)} rows (skipped {len(df) - len(trimmed)}) to {out_path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
