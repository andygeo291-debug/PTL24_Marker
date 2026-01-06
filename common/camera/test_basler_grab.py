import argparse
import sys
import time

import numpy as np
from pypylon import genicam, pylon


def _safe_get(info, method_name):
    method = getattr(info, method_name, None)
    if method is None:
        return ""
    try:
        return method()
    except Exception:
        return ""


def _device_matches(info, serial, name):
    if serial:
        if _safe_get(info, "GetSerialNumber") != serial:
            return False
    if name:
        candidates = []
        for method in ("GetUserDefinedName", "GetModelName", "GetFriendlyName", "GetFullName"):
            value = _safe_get(info, method)
            if value:
                candidates.append(value)
        if not candidates:
            return False
        if not any(name == value for value in candidates) and not any(name in value for value in candidates):
            return False
    return True


def _print_devices(devices):
    if not devices:
        print("No devices found")
        return
    print("Available devices:")
    for info in devices:
        serial = _safe_get(info, "GetSerialNumber")
        user = _safe_get(info, "GetUserDefinedName")
        model = _safe_get(info, "GetModelName")
        print(f"  serial={serial} user={user} model={model}")


def _set_enum(node_map, name, value):
    if value is None:
        return False
    try:
        node = node_map.GetNode(name)
    except Exception:
        return False
    if node is None or not genicam.IsWritable(node):
        return False
    try:
        entry = node.GetEntryByName(value)
        if entry is None or not genicam.IsAvailable(entry) or not genicam.IsReadable(entry):
            print(f"could not set {name} to {value}", file=sys.stderr)
            return False
        node.SetIntValue(entry.GetValue())
        return True
    except Exception as exc:
        print(f"could not set {name} to {value}: {exc}", file=sys.stderr)
        return False


def _set_value(node_map, name, value, cast):
    if value is None:
        return False
    try:
        node = node_map.GetNode(name)
    except Exception:
        return False
    if node is None or not genicam.IsWritable(node):
        return False
    try:
        node.SetValue(cast(value))
        return True
    except Exception as exc:
        print(f"could not set {name} to {value}: {exc}", file=sys.stderr)
        return False


def _read_node(node_map, name):
    try:
        node = node_map.GetNode(name)
    except Exception:
        return None
    if node is None or not genicam.IsReadable(node):
        return None
    try:
        return node.ToString()
    except Exception:
        try:
            return node.GetValue()
        except Exception:
            return None


def _apply_settings(camera, args):
    node_map = camera.GetNodeMap()

    _set_enum(node_map, "PixelFormat", args.pixel_format)
    _set_value(node_map, "Width", args.width, int)
    _set_value(node_map, "Height", args.height, int)
    _set_value(node_map, "OffsetX", args.offset_x, int)
    _set_value(node_map, "OffsetY", args.offset_y, int)

    if args.fps is not None:
        _set_value(node_map, "AcquisitionFrameRateEnable", True, bool)
        _set_value(node_map, "AcquisitionFrameRate", args.fps, float)

    _set_value(node_map, "ExposureTime", args.exposure_us, float)
    _set_value(node_map, "Gain", args.gain, float)

    _set_value(node_map, "GevSCPSPacketSize", args.packet_size, int)
    _set_value(node_map, "GevSCPD", args.interpacket_delay, int)

    readback_keys = [
        "PixelFormat",
        "Width",
        "Height",
        "OffsetX",
        "OffsetY",
        "AcquisitionFrameRateEnable",
        "AcquisitionFrameRate",
        "ExposureTime",
        "Gain",
        "GevSCPSPacketSize",
        "GevSCPD",
    ]
    readback = {}
    for key in readback_keys:
        value = _read_node(node_map, key)
        if value is not None:
            readback[key] = value
    print(f"Readback settings: {readback}")


def _print_frame_stats(index, array, host_ts):
    print(
        f"frame {index}: shape={array.shape} dtype={array.dtype} "
        f"min={int(array.min())} max={int(array.max())} host_ts={host_ts:.6f}"
    )


def _parse_args():
    parser = argparse.ArgumentParser(description="Standalone Basler grab test")
    parser.add_argument("--serial", default=None, help="Camera serial number")
    parser.add_argument("--name", default=None, help="Camera name (user/model/friendly/full)")
    parser.add_argument("--pixel-format", default="Mono8", help="Pixel format (default: Mono8)")
    parser.add_argument("--width", type=int, default=None, help="ROI width")
    parser.add_argument("--height", type=int, default=None, help="ROI height")
    parser.add_argument("--offset-x", type=int, default=None, help="ROI offset X")
    parser.add_argument("--offset-y", type=int, default=None, help="ROI offset Y")
    parser.add_argument("--fps", type=float, default=None, help="Acquisition frame rate")
    parser.add_argument("--exposure-us", type=float, default=None, help="Exposure time in us")
    parser.add_argument("--gain", type=float, default=None, help="Gain")
    parser.add_argument("--packet-size", type=int, default=None, help="GevSCPSPacketSize")
    parser.add_argument("--interpacket-delay", type=int, default=None, help="GevSCPD")
    parser.add_argument("--timeout-ms", type=int, default=1000, help="Retrieve timeout in ms")
    parser.add_argument("--frames", type=int, default=20, help="Number of frames to grab")
    parser.add_argument(
        "--use-wrapper",
        action="store_true",
        help="Use BaslerGigECam wrapper instead of direct pypylon calls",
    )
    return parser.parse_args()


def main():
    args = _parse_args()

    try:
        if args.use_wrapper:
            from common.camera.basler_cam import BaslerGigECam

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
                timeout_ms=args.timeout_ms,
            )
            try:
                cam.open()
                info = cam.device_info
                print(
                    "Opened device: serial={serial} user={user} model={model}".format(
                        serial=info.get("serial", ""),
                        user=info.get("user", ""),
                        model=info.get("model", ""),
                    )
                )
                print(f"Readback settings: {cam.readback_settings}")

                grabbed = 0
                targets = {1, 10, args.frames}
                for _ in range(args.frames):
                    ok, frame = cam.read()
                    if not ok:
                        continue
                    grabbed += 1
                    if grabbed in targets:
                        host_ts = cam.last_timestamp_s or time.time()
                        _print_frame_stats(grabbed, frame, host_ts)
            finally:
                cam.release()

            print(f"grabbed {grabbed}/{args.frames}")
            if grabbed < args.frames:
                return 1
            return 0

        tl_factory = pylon.TlFactory.GetInstance()
        devices = tl_factory.EnumerateDevices()
        if not devices:
            _print_devices(devices)
            return 1

        selected = None
        for info in devices:
            if _device_matches(info, args.serial, args.name):
                selected = info
                break

        if selected is None:
            print("No matching device found")
            _print_devices(devices)
            return 1

        camera = pylon.InstantCamera(tl_factory.CreateDevice(selected))
        try:
            camera.Open()
            info = camera.GetDeviceInfo()
            serial = _safe_get(info, "GetSerialNumber")
            user = _safe_get(info, "GetUserDefinedName")
            model = _safe_get(info, "GetModelName")
            print(f"Opened device: serial={serial} user={user} model={model}")

            _apply_settings(camera, args)

            converter = pylon.ImageFormatConverter()
            converter.OutputPixelFormat = pylon.PixelType_Mono8
            converter.OutputBitAlignment = pylon.OutputBitAlignment_MsbAligned

            camera.StartGrabbing(pylon.GrabStrategy_LatestImageOnly)
            grabbed = 0
            targets = {1, 10, args.frames}
            for _ in range(args.frames):
                grab_result = camera.RetrieveResult(args.timeout_ms, pylon.TimeoutHandling_Return)
                if grab_result is None:
                    continue
                try:
                    if grab_result.GrabSucceeded():
                        grabbed += 1
                        image = converter.Convert(grab_result)
                        array = image.GetArray()
                        if array.dtype != np.uint8:
                            array = array.astype(np.uint8, copy=False)
                        if grabbed in targets:
                            _print_frame_stats(grabbed, array, time.time())
                finally:
                    grab_result.Release()

            camera.StopGrabbing()
        finally:
            if camera.IsOpen():
                camera.Close()

        print(f"grabbed {grabbed}/{args.frames}")
        if grabbed < args.frames:
            return 1
        return 0
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
