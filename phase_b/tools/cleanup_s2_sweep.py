import shutil
from pathlib import Path


def remove_path(path: Path) -> bool:
    if not path.exists():
        print(f"[cleanup] Skipped {path} (not found)")
        return False
    display = f"{path}/" if path.is_dir() and not path.is_symlink() else str(path)
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
    else:
        path.unlink()
    print(f"[cleanup] Removed {display}")
    return True


def main() -> None:
    phase_b_root = Path(__file__).resolve().parents[1]

    validation_dir = phase_b_root / "validation" / "S2_sweep"
    remove_path(validation_dir)

    poses_csv = phase_b_root / "poses_sweep.csv"
    remove_path(poses_csv)

    fig_dir = phase_b_root / "fig_sweep"
    fig_removed = remove_path(fig_dir)

    metrics_csv = phase_b_root / "debug_metrics.csv"
    if fig_removed:
        remove_path(metrics_csv)
    else:
        print(f"[cleanup] Skipped {metrics_csv} (fig_sweep not removed)")


if __name__ == "__main__":
    main()
