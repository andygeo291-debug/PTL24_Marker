#!/usr/bin/env python3
"""Enumerate Basler devices with serial/model/IP where available."""

from __future__ import annotations

import sys


def _safe_get(info, method_name: str) -> str:
    method = getattr(info, method_name, None)
    if method is None:
        return ""
    try:
        return method()
    except Exception:
        return ""


def main() -> int:
    try:
        from pypylon import pylon
    except Exception as exc:
        print(f"import_error: {exc}")
        return 1

    tl_factory = pylon.TlFactory.GetInstance()
    devices = tl_factory.EnumerateDevices()
    if not devices:
        print("No devices found")
        return 1

    print("Basler devices:")
    for info in devices:
        serial = _safe_get(info, "GetSerialNumber")
        user = _safe_get(info, "GetUserDefinedName")
        model = _safe_get(info, "GetModelName")
        ip = (
            _safe_get(info, "GetIpAddress")
            or _safe_get(info, "GetIpAddressString")
            or _safe_get(info, "GetAddress")
        )
        print(f"  serial={serial} user={user} model={model} ip={ip}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
