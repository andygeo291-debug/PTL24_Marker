from __future__ import annotations

import argparse
import logging
import sys
import time
from typing import Optional

from common.camera.factory import create_basler_from_args

LOGGER = logging.getLogger(__name__)


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Test Basler GigE frame grabbing.")
    parser.add_argument("--serial", dest="basler_serial", help="Basler serial to open.")
    parser.add_argument("--name", dest="basler_name", help="Basler user-defined name.")
    parser.add_argument("--count", type=int, default=100, help="Number of frames to grab.")
    parser.add_argument(
        "--timeout-ms",
        dest="basler_timeout_ms",
        type=int,
        default=5000,
        help="Grab timeout in milliseconds (default: 5000).",
    )
    parser.add_argument(
        "--frame-format",
        choices=["bgr", "gray"],
        default="bgr",
        help="Output frame format (default: bgr).",
    )
    return parser.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> int:
    args = parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    cam = create_basler_from_args(args)
    if not cam.open():
        LOGGER.error("Failed to open Basler camera.")
        return 1

    n_frames = int(args.count)
    frame_times = []
    start = time.perf_counter()
    try:
        last_ts = None
        for _ in range(n_frames):
            pkt = cam.read()
            if pkt is None or pkt.image is None:
                LOGGER.warning("Frame grab failed; stopping.")
                break
            frame_times.append(pkt.t_capture_ns)
            delta_ms = None
            if last_ts is not None:
                delta_ms = (pkt.t_capture_ns - last_ts) / 1e6
            last_ts = pkt.t_capture_ns
            LOGGER.info(
                "Frame %d ts_ns=%d delta_ms=%s size=%s backend=%s",
                pkt.frame_id,
                pkt.t_capture_ns,
                f"{delta_ms:.3f}" if delta_ms is not None else "n/a",
                getattr(pkt.image, "shape", None),
                pkt.backend,
            )
    finally:
        cam.close()
    elapsed = time.perf_counter() - start
    if elapsed > 0 and frame_times:
        fps = len(frame_times) / elapsed
        LOGGER.info("Captured %d frames in %.3f s (%.2f FPS)", len(frame_times), elapsed, fps)
    return 0


if __name__ == "__main__":
    sys.exit(main())
