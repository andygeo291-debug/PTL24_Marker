"""Camera backend factory for OpenCV (default) and optional Basler."""


def add_camera_cli_args(parser):
    parser.add_argument(
        "--camera-backend",
        choices=["opencv", "basler"],
        default="opencv",
        help="Camera backend (default: opencv).",
    )
    parser.add_argument("--basler-serial", default=None, help="Basler serial number.")
    parser.add_argument("--basler-name", default=None, help="Basler name (user/model).")
    parser.add_argument(
        "--basler-pixel-format",
        default="Mono8",
        help="Basler pixel format (default: Mono8).",
    )
    parser.add_argument("--basler-exposure-us", type=float, default=None, help="Exposure time (us).")
    parser.add_argument("--basler-gain", type=float, default=None, help="Analog gain.")
    parser.add_argument("--basler-offset-x", type=int, default=None, help="ROI offset X.")
    parser.add_argument("--basler-offset-y", type=int, default=None, help="ROI offset Y.")
    parser.add_argument("--basler-packet-size", type=int, default=None, help="GevSCPSPacketSize.")
    parser.add_argument(
        "--basler-interpacket-delay",
        type=int,
        default=None,
        help="GevSCPD interpacket delay.",
    )
    parser.add_argument(
        "--basler-stream-buffer-count",
        type=int,
        default=None,
        help="Stream buffer count (MaxNumBuffer) if supported.",
    )
    parser.add_argument(
        "--basler-timeout-ms",
        type=int,
        default=1000,
        help="Retrieve timeout in ms.",
    )


def _create_opencv_capture(args):
    # Reuse existing Phase B v1 capture helpers to avoid behavior drift.
    from phase_b.v1 import phase_b_tags as v1

    video = getattr(args, "video", None)
    if video is None:
        raise ValueError("args.video is required for opencv backend")

    video_opt = str(video).lower() if isinstance(video, str) else video
    if video_opt == "auto":
        cap, _ = v1._auto_select_camera(args)  # pylint: disable=protected-access
        return cap
    video_source = v1.parse_video_source(video)
    return v1._open_capture_with_settings(video_source, args)  # pylint: disable=protected-access


def create_camera_from_args(args):
    backend = getattr(args, "camera_backend", "opencv")
    if backend == "basler":
        # Import lazily so pypylon is optional when Basler is unused.
        from common.camera.basler_cam import BaslerGigECam

        cam = BaslerGigECam(
            serial=getattr(args, "basler_serial", None),
            name=getattr(args, "basler_name", None),
            width=getattr(args, "width", None),
            height=getattr(args, "height", None),
            offset_x=getattr(args, "basler_offset_x", None),
            offset_y=getattr(args, "basler_offset_y", None),
            fps=getattr(args, "fps", None),
            pixel_format=getattr(args, "basler_pixel_format", "Mono8"),
            exposure_us=getattr(args, "basler_exposure_us", None),
            gain=getattr(args, "basler_gain", None),
            packet_size=getattr(args, "basler_packet_size", None),
            interpacket_delay=getattr(args, "basler_interpacket_delay", None),
            stream_buffer_count=getattr(args, "basler_stream_buffer_count", None),
            timeout_ms=getattr(args, "basler_timeout_ms", 1000),
        )
        cam.open()
        return cam
    return _create_opencv_capture(args)
