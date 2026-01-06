import argparse
import shutil
import sys
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Archive Phase B validation run artifacts into scenario folders."
    )
    parser.add_argument(
        "--scenario",
        required=True,
        help="Scenario name (e.g. S1_jitter, S2_sweep, S3_longrun).",
    )
    parser.add_argument(
        "--poses",
        required=True,
        help="Poses CSV filename under phase_b/ (e.g. poses_jitter.csv).",
    )
    parser.add_argument(
        "--fig-dir",
        required=True,
        help="Figure directory under phase_b/ (e.g. fig_jitter).",
    )
    parser.add_argument(
        "--metrics",
        default="debug_metrics.csv",
        help="Metrics CSV filename under phase_b/ (default: debug_metrics.csv).",
    )
    return parser.parse_args()


def resolve_under_phase_b(phase_b_root: Path, path_str: str) -> Path:
    path = Path(path_str)
    if not path.is_absolute():
        path = phase_b_root / path
    return path


def require_path(path: Path, label: str) -> None:
    if not path.exists():
        print(f"[archive] Missing {label}: {path}")
        sys.exit(1)


def remove_destination(dest: Path) -> None:
    if not dest.exists():
        return
    if dest.is_dir() and not dest.is_symlink():
        shutil.rmtree(dest)
    else:
        dest.unlink()


def move_path(src: Path, dest: Path, phase_b_root: Path) -> None:
    display_src = (
        str(src.relative_to(phase_b_root)) if phase_b_root in src.parents else str(src)
    )
    display_dest = (
        str(dest.relative_to(phase_b_root)) if phase_b_root in dest.parents else str(dest)
    )
    print(f"[archive] Moving {display_src} -> {display_dest}")
    remove_destination(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src), str(dest))


def main() -> int:
    args = parse_args()
    phase_b_root = Path(__file__).resolve().parents[1]
    scenario_dir = phase_b_root / "validation" / args.scenario
    scenario_dir.mkdir(parents=True, exist_ok=True)

    poses_src = resolve_under_phase_b(phase_b_root, args.poses)
    fig_src = resolve_under_phase_b(phase_b_root, args.fig_dir)
    metrics_src = resolve_under_phase_b(phase_b_root, args.metrics)

    require_path(poses_src, "poses CSV")
    require_path(fig_src, "figure directory")
    require_path(metrics_src, "metrics CSV")

    poses_dest = scenario_dir / Path(args.poses).name
    plots_dest = scenario_dir / "plots"
    metrics_dest = scenario_dir / "debug_metrics.csv"

    move_path(poses_src, poses_dest, phase_b_root)
    move_path(fig_src, plots_dest, phase_b_root)
    move_path(metrics_src, metrics_dest, phase_b_root)

    print(f"[archive] Scenario archived at {scenario_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
