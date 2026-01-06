import argparse
import logging
from typing import Optional

LOGGER = logging.getLogger(__name__)


def add_camera_cli_args(parser: argparse.ArgumentParser) -> None:
    """Add shared camera CLI arguments."""

    parser.add_argument(
        "--camera-backend",
        choices=["opencv", "basler"],
        default="opencv",
        help="Camera backend to use (default: opencv).",
    )
    parser.add_argument(
        "--frame-format",
        choices=["bgr", "gray"],
        default="bgr",
        help="Frame format delivered to the pipeline (default: bgr).",
    )
    parser.add_argument("--basler-serial", help="Basler camera serial number.")
    parser.add_argument("--basler-name", help="Basler user-defined camera name.")
    parser.add_argument(
        "--basler-timeout-ms",
        type=int,
        default=5000,
        help="Basler grab timeout in milliseconds (default: 5000).",
    )
    parser.add_argument(
        "--basler-packet-size",
        type=int,
        help="Basler GVSP packet size (bytes).",
    )
    parser.add_argument(
        "--basler-interpacket-delay",
        type=int,
        help="Basler inter-packet delay in ticks.",
    )
    parser.add_argument(
        "--basler-no-chunk-ts",
        action="store_true",
        help="Disable Basler chunk timestamp; use host clock.",
    )
    parser.add_argument(
        "--basler-pixel-format",
        default="Mono8",
        help='Basler pixel format (default: "Mono8").',
    )
    parser.add_argument("--basler-exposure-us", type=float, help="Basler exposure time (microseconds).")
    parser.add_argument("--basler-gain", type=float, help="Basler gain value.")
    parser.add_argument("--basler-offset-x", type=int, default=0, help="Basler ROI offset X (default: 0).")
    parser.add_argument("--basler-offset-y", type=int, default=0, help="Basler ROI offset Y (default: 0).")


def create_basler_from_args(args: argparse.Namespace) -> "BaslerGigECam":
    """Instantiate a BaslerGigECam from parsed CLI args."""

    from common.camera.basler_cam import BaslerGigECam  # local import to keep optional dependency

    enable_chunk_ts = not getattr(args, "basler_no_chunk_ts", False)
    serial: Optional[str] = getattr(args, "basler_serial", None)
    name: Optional[str] = getattr(args, "basler_name", None)
    timeout_ms: int = getattr(args, "basler_timeout_ms", 5000)
    packet_size: Optional[int] = getattr(args, "basler_packet_size", None)
    interpacket_delay: Optional[int] = getattr(args, "basler_interpacket_delay", None)
    frame_format: str = getattr(args, "frame_format", "bgr")
    pixel_format: Optional[str] = getattr(args, "basler_pixel_format", "Mono8")
    exposure_us: Optional[float] = getattr(args, "basler_exposure_us", None)
    gain: Optional[float] = getattr(args, "basler_gain", None)
    offset_x: Optional[int] = getattr(args, "basler_offset_x", 0)
    offset_y: Optional[int] = getattr(args, "basler_offset_y", 0)
    width: Optional[int] = getattr(args, "width", None)
    height: Optional[int] = getattr(args, "height", None)
    fps: Optional[float] = getattr(args, "fps", None)

    LOGGER.debug(
        "Creating BaslerGigECam serial=%s name=%s timeout_ms=%s frame_format=%s",
        serial,
        name,
        timeout_ms,
        frame_format,
    )

    return BaslerGigECam(
        serial=serial,
        name=name,
        frame_format=frame_format,
        timeout_ms=timeout_ms,
        packet_size=packet_size,
        inter_packet_delay=interpacket_delay,
        enable_chunk_ts=enable_chunk_ts,
        pixel_format=pixel_format,
        exposure_us=exposure_us,
        gain=gain,
        offset_x=offset_x,
        offset_y=offset_y,
        width=width,
        height=height,
        fps=fps,
    )
