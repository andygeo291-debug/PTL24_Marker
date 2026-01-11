#!/usr/bin/env python3
import argparse
import json
import time
from pathlib import Path
from typing import List, Optional, Tuple

import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))


def parse_int_list(value: str) -> List[int]:
    return [int(v.strip()) for v in value.split(",") if v.strip()]


def parse_float_list(value: str) -> List[float]:
    return [float(v.strip()) for v in value.split(",") if v.strip()]


def run_trial(
    serial: Optional[str],
    name: Optional[str],
    width: int,
    height: int,
    offset_x: int,
    offset_y: int,
    fps: float,
    pixel_format: str,
    exposure_us: float,
    gain: float,
    packet_size: Optional[int],
    interpacket_delay: Optional[int],
    stream_buffer_count: Optional[int],
    timeout_ms: int,
    frames: int,
) -> Tuple[int, int, str]:
    try:
        from common.camera.basler_cam import BaslerGigECam
    except Exception as exc:
        return 0, frames, f"import_error: {exc}"

    cam = BaslerGigECam(
        serial=serial,
        name=name,
        width=width,
        height=height,
        offset_x=offset_x,
        offset_y=offset_y,
        fps=fps,
        pixel_format=pixel_format,
        exposure_us=exposure_us,
        gain=gain,
        packet_size=packet_size,
        interpacket_delay=interpacket_delay,
        stream_buffer_count=stream_buffer_count,
        timeout_ms=timeout_ms,
    )

    ok = 0
    fail = 0
    error = ""
    try:
        cam.open()
        for _ in range(frames):
            success, _ = cam.read()
            if success:
                ok += 1
            else:
                fail += 1
    except Exception as exc:
        error = str(exc)
        fail = frames
        ok = 0
    finally:
        try:
            cam.release()
        except Exception:
            pass

    return ok, fail, error


def read_gige_params(
    serial: Optional[str],
    name: Optional[str],
    width: int,
    height: int,
    offset_x: int,
    offset_y: int,
    fps: float,
    pixel_format: str,
    exposure_us: float,
    gain: float,
    timeout_ms: int,
    stream_buffer_count: Optional[int],
) -> Tuple[dict, str]:
    try:
        from common.camera.basler_cam import BaslerGigECam
    except Exception as exc:
        return {}, f"import_error: {exc}"

    cam = BaslerGigECam(
        serial=serial,
        name=name,
        width=width,
        height=height,
        offset_x=offset_x,
        offset_y=offset_y,
        fps=fps,
        pixel_format=pixel_format,
        exposure_us=exposure_us,
        gain=gain,
        packet_size=None,
        interpacket_delay=None,
        stream_buffer_count=stream_buffer_count,
        timeout_ms=timeout_ms,
    )
    error = ""
    readback = {}
    try:
        cam.open()
        readback = dict(cam.readback_settings)
    except Exception as exc:
        error = str(exc)
    finally:
        try:
            cam.release()
        except Exception:
            pass
    return readback, error


def main() -> int:
    parser = argparse.ArgumentParser(description="Basler stream diagnosis and autotune.")
    parser.add_argument("--serial", default=None)
    parser.add_argument("--name", default=None)
    parser.add_argument("--width", type=int, required=True)
    parser.add_argument("--height", type=int, required=True)
    parser.add_argument("--offset-x", type=int, default=0)
    parser.add_argument("--offset-y", type=int, default=0)
    parser.add_argument("--fps", type=float, default=15.0)
    parser.add_argument("--pixel-format", default="Mono8")
    parser.add_argument("--exposure-us", type=float, default=15000.0)
    parser.add_argument("--gain", type=float, default=0.0)
    parser.add_argument("--stream-buffer-count", type=int, default=None)
    parser.add_argument("--frames", type=int, default=300)
    parser.add_argument("--fail-threshold", type=float, default=0.01)
    parser.add_argument(
        "--packet-size-candidates",
        type=parse_int_list,
        default=[1500, 1440, 1400, 1300, 1200],
    )
    parser.add_argument(
        "--interpacket-delay-candidates",
        type=parse_int_list,
        default=[3500, 8000, 12000],
    )
    parser.add_argument(
        "--timeout-candidates",
        type=parse_int_list,
        default=[1000, 2000],
    )
    parser.add_argument("--out-json", required=True)
    parser.add_argument("--out-env", required=True)

    args = parser.parse_args()

    readback, readback_error = read_gige_params(
        args.serial,
        args.name,
        args.width,
        args.height,
        args.offset_x,
        args.offset_y,
        args.fps,
        args.pixel_format,
        args.exposure_us,
        args.gain,
        max(args.timeout_candidates) if args.timeout_candidates else 1000,
        args.stream_buffer_count,
    )
    if readback:
        print("Current GigE params:", readback)
    if readback_error:
        print(f"Warning: readback failed: {readback_error}")

    results = []
    best = None

    for packet_size in args.packet_size_candidates:
        for ipd in args.interpacket_delay_candidates:
            for timeout_ms in args.timeout_candidates:
                ok, fail, error = run_trial(
                    args.serial,
                    args.name,
                    args.width,
                    args.height,
                    args.offset_x,
                    args.offset_y,
                    args.fps,
                    args.pixel_format,
                    args.exposure_us,
                    args.gain,
                    packet_size,
                    ipd,
                    args.stream_buffer_count,
                    timeout_ms,
                    args.frames,
                )
                total = ok + fail
                fail_rate = fail / total if total else 1.0
                result = {
                    "packet_size": packet_size,
                    "interpacket_delay": ipd,
                    "timeout_ms": timeout_ms,
                    "ok": ok,
                    "fail": fail,
                    "fail_rate": fail_rate,
                    "error": error,
                }
                results.append(result)

                key = (
                    fail_rate,
                    -packet_size,
                    ipd,
                    timeout_ms,
                )
                if best is None or key < best["key"]:
                    best = {"key": key, "result": result}

    if best is None:
        raise SystemExit("No candidates evaluated.")

    best_result = best["result"]
    payload = {
        "timestamp": time.time(),
        "inputs": {
            "serial": args.serial,
            "name": args.name,
            "width": args.width,
            "height": args.height,
            "offset_x": args.offset_x,
            "offset_y": args.offset_y,
            "fps": args.fps,
            "pixel_format": args.pixel_format,
            "exposure_us": args.exposure_us,
            "gain": args.gain,
            "stream_buffer_count": args.stream_buffer_count,
            "frames": args.frames,
            "fail_threshold": args.fail_threshold,
            "packet_size_candidates": args.packet_size_candidates,
            "interpacket_delay_candidates": args.interpacket_delay_candidates,
            "timeout_candidates": args.timeout_candidates,
        },
        "readback": readback,
        "readback_error": readback_error,
        "results": results,
        "best": best_result,
    }

    out_json = Path(args.out_json)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(payload, indent=2) + "\n")

    out_env = Path(args.out_env)
    out_env.write_text(
        "\n".join(
            [
                f"export BASLER_PACKET_SIZE={best_result['packet_size']}",
                f"export IPD={best_result['interpacket_delay']}",
                f"export TIMEOUT_MS={best_result['timeout_ms']}",
                f"export BASLER_FAIL_RATE={best_result['fail_rate']:.6f}",
            ]
        )
        + "\n"
    )

    print(
        "Best stream config: packet=%d ipd=%d timeout=%d fail_rate=%.6f"
        % (
            best_result["packet_size"],
            best_result["interpacket_delay"],
            best_result["timeout_ms"],
            best_result["fail_rate"],
        )
    )

    if best_result["fail_rate"] > args.fail_threshold:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
