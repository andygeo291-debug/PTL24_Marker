#!/usr/bin/env python3
"""Capture Basler chessboard images for intrinsics calibration."""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

import cv2

ROOT = Path(__file__).resolve().parents[1]


def _next_run_dir(base_dir: Path) -> Path:
    base_dir.mkdir(parents=True, exist_ok=True)
    prefix = "basler_intrinsics_"
    next_num = 1
    for path in base_dir.iterdir():
        if not path.is_dir() or not path.name.startswith(prefix):
            continue
        parts = path.name[len(prefix) :].split("_", 1)
        if not parts:
            continue
        try:
            num = int(parts[0])
        except ValueError:
            continue
        next_num = max(next_num, num + 1)
    run_tag = f"{prefix}{next_num:04d}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    return base_dir / run_tag


def _log(line: str, log_path: Path | None) -> None:
    print(line, flush=True)
    if log_path is not None:
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="Capture Basler chessboard images.")
    parser.add_argument("--serial", default="21601161")
    parser.add_argument("--name", default="StaticCam")
    parser.add_argument("--width", type=int, default=960)
    parser.add_argument("--height", type=int, default=720)
    parser.add_argument("--fps", type=float, default=12.0)
    parser.add_argument("--pixel-format", default="Mono8")
    parser.add_argument("--exposure-us", type=float, default=15000.0)
    parser.add_argument("--gain", type=float, default=0.0)
    parser.add_argument("--offset-x", type=int, default=320)
    parser.add_argument("--offset-y", type=int, default=200)
    parser.add_argument("--packet-size", type=int, default=8192)
    parser.add_argument("--interpacket-delay", type=int, default=3500)
    parser.add_argument("--timeout-ms", type=int, default=2000)
    parser.add_argument("--stream-buffer-count", type=int, default=64)
    parser.add_argument("--lens-zoom-mm", type=float, default=11.0)
    parser.add_argument(
        "--lens-notes",
        default="Kowa 1/1.8 f1.6/4.4-11mm; zoom locked at 11mm; focus locked",
    )
    parser.add_argument("--board-cols", type=int, default=9)
    parser.add_argument("--board-rows", type=int, default=6)
    parser.add_argument("--square-size-m", type=float, default=0.025)
    parser.add_argument("--num-images", type=int, default=60)
    parser.add_argument("--run-base", default="calib_runs")
    args = parser.parse_args()

    run_base = Path(args.run_base)
    if not run_base.is_absolute():
        run_base = ROOT / run_base
    try:
        base_resolved = run_base.resolve()
        root_resolved = ROOT.resolve()
        if root_resolved not in base_resolved.parents and base_resolved != root_resolved:
            raise RuntimeError(f"RUN_BASE must be inside repo: {ROOT}")
    except RuntimeError:
        raise
    except Exception:
        pass

    run_dir = _next_run_dir(run_base)
    images_dir = run_dir / "images"
    images_dir.mkdir(parents=True, exist_ok=True)
    log_path = run_dir / "terminal.log"

    meta = {
        "timestamp": time.time(),
        "camera": {
            "serial": args.serial,
            "name": args.name,
            "width": args.width,
            "height": args.height,
            "fps": args.fps,
            "pixel_format": args.pixel_format,
            "exposure_us": args.exposure_us,
            "gain": args.gain,
            "offset_x": args.offset_x,
            "offset_y": args.offset_y,
            "packet_size": args.packet_size,
            "interpacket_delay": args.interpacket_delay,
            "timeout_ms": args.timeout_ms,
            "stream_buffer_count": args.stream_buffer_count,
        },
        "lens": {"zoom_mm": args.lens_zoom_mm, "notes": args.lens_notes},
        "board": {
            "cols": args.board_cols,
            "rows": args.board_rows,
            "square_size_m": args.square_size_m,
        },
        "capture": {"num_images": args.num_images},
        "paths": {"run_dir": str(run_dir), "images_dir": str(images_dir)},
    }
    (run_dir / "calib_meta.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")

    _log("Basler calibration capture", log_path)
    _log("- Move the chessboard through the FOV (tilt/rotate/translate).", log_path)
    _log("- Press SPACE to save a frame.", log_path)
    _log("- Press Q or ESC to quit early.", log_path)
    _log(f"- Target images: {args.num_images}", log_path)
    _log(f"- Run dir: {run_dir}", log_path)

    sys.path.insert(0, str(ROOT))
    from common.camera.basler_cam import BaslerGigECam  # noqa: E402

    cam = BaslerGigECam(
        serial=args.serial,
        name=args.name,
        width=args.width,
        height=args.height,
        offset_x=args.offset_x,
        offset_y=args.offset_y,
        fps=args.fps,
        pixel_format=args.pixel_format,
        exposure_us=args.exposure_us,
        gain=args.gain,
        packet_size=args.packet_size,
        interpacket_delay=args.interpacket_delay,
        stream_buffer_count=args.stream_buffer_count,
        timeout_ms=args.timeout_ms,
    )
    cam.open()
    saved = 0
    try:
        while True:
            ok, frame = cam.read()
            if not ok:
                continue
            display = frame
            if display.ndim == 2:
                display = cv2.cvtColor(display, cv2.COLOR_GRAY2BGR)
            cv2.putText(
                display,
                f"saved {saved}/{args.num_images}",
                (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.8,
                (0, 255, 0),
                2,
                cv2.LINE_AA,
            )
            cv2.imshow("Basler Calib Capture (SPACE=save, Q=quit)", display)
            key = cv2.waitKey(1) & 0xFF
            if key in (ord("q"), 27):
                break
            if key == ord(" "):
                saved += 1
                out_path = images_dir / f"img_{saved:04d}.png"
                cv2.imwrite(str(out_path), frame)
                _log(f"Saved {out_path}", log_path)
                if saved >= args.num_images:
                    break
    finally:
        cam.release()
        cv2.destroyAllWindows()

    if saved < args.num_images:
        raise SystemExit(f"Captured {saved}/{args.num_images} images; rerun to reach target count.")

    _log(f"Capture complete: {saved} images -> {images_dir}", log_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
