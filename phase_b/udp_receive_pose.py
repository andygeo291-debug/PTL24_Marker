#!/usr/bin/env python3
"""Simple UDP listener for Phase B pose streaming."""

import argparse
import json
import socket


def main() -> None:
    parser = argparse.ArgumentParser(description="UDP pose receiver for Phase B streaming.")
    parser.add_argument("--port", type=int, default=6006, help="UDP port to listen on (default: 6006).")
    args = parser.parse_args()

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("0.0.0.0", args.port))
    print(f"Listening on UDP :{args.port}")

    while True:
        data, addr = sock.recvfrom(65535)
        try:
            msg = json.loads(data.decode("utf-8"))
        except Exception:
            print("Bad packet from", addr)
            continue

        frame = msg.get("frame")
        used = msg.get("used_ids")
        cam_t = msg.get("cam", {}).get("t_m")
        tilt = msg.get("tilt_cam_deg")
        print(f"frame={frame} used={used} cam_t={cam_t} tilt_cam={tilt}")


if __name__ == "__main__":
    main()
