import argparse, statistics as stats, os, time
import numpy as np

def try_make_detector(family: str):
    try:
        from pupil_apriltags import Detector
        return ("pupil_apriltags", Detector(families=family))
    except Exception:
        pass
    try:
        import apriltag
        return ("apriltag", apriltag.Detector(apriltag.DetectorOptions(families=family)))
    except Exception:
        pass
    raise RuntimeError("No AprilTag detector found. Try: pip install pupil-apriltags")

def _set_first(nm, names, value):
    for name in names:
        try:
            n = nm.GetNode(name)
            if n and hasattr(n, "SetValue"):
                n.SetValue(value)
                return name
        except Exception:
            pass
    return None

def _get_first(nm, names):
    for name in names:
        try:
            n = nm.GetNode(name)
            if n and hasattr(n, "GetValue"):
                return name, n.GetValue()
        except Exception:
            pass
    return None, None

def open_basler(args):
    from pypylon import pylon
    tl = pylon.TlFactory.GetInstance()
    devs = tl.EnumerateDevices()
    if not devs:
        raise RuntimeError("No Basler devices found. Check cable/IP (169.254.x.x) and CLOSE Pylon Viewer.")

    chosen = None
    # Prefer serial match if provided
    if args.serial:
        for d in devs:
            try:
                if d.GetSerialNumber() == args.serial:
                    chosen = d; break
            except Exception:
                pass
    # Else match user-defined name
    if chosen is None and args.cam:
        for d in devs:
            try:
                if d.GetUserDefinedName() == args.cam:
                    chosen = d; break
            except Exception:
                pass
    if chosen is None:
        chosen = devs[0]

    cam = pylon.InstantCamera(tl.CreateDevice(chosen))
    cam.Open()
    nm = cam.GetNodeMap()

    # Ensure continuous free-run
    _set_first(nm, ["AcquisitionMode"], "Continuous")
    _set_first(nm, ["TriggerMode"], "Off")

    # PixelFormat / ROI
    _set_first(nm, ["PixelFormat"], args.pixel_format)
    _set_first(nm, ["Width"], int(args.width))
    _set_first(nm, ["Height"], int(args.height))
    _set_first(nm, ["OffsetX"], int(args.offx))
    _set_first(nm, ["OffsetY"], int(args.offy))

    # FPS (Abs fallback)
    _set_first(nm, ["AcquisitionFrameRateEnable"], True)
    fps_node = _set_first(nm, ["AcquisitionFrameRate", "AcquisitionFrameRateAbs"], float(args.fps))

    # Exposure / Gain (try common Basler node variants)
    _set_first(nm, ["ExposureAuto"], "Off")
    exp_node = _set_first(nm, ["ExposureTime", "ExposureTimeAbs", "ExposureTimeRaw"], float(args.exposure_us))

    _set_first(nm, ["GainAuto"], "Off")
    gain_node = _set_first(nm, ["Gain", "GainAbs", "GainRaw"], float(args.gain))

    # Transport
    pkt_node = _set_first(nm, ["GevSCPSPacketSize"], int(args.packet_size))
    ipd_node = _set_first(nm, ["GevSCPD"], int(args.interpacket_delay))

    # Stream buffers (best effort)
    try:
        cam.MaxNumBuffer = int(args.stream_buffer_count)
    except Exception:
        pass

    cam.StartGrabbing(pylon.GrabStrategy_LatestImageOnly)
    return cam, {"fps_node": fps_node, "exp_node": exp_node, "gain_node": gain_node, "pkt_node": pkt_node, "ipd_node": ipd_node}

def get_readbacks(cam):
    nm = cam.GetNodeMap()
    rb = {}
    for k, names in {
        "PixelFormat": ["PixelFormat"],
        "Width": ["Width"], "Height": ["Height"],
        "OffsetX": ["OffsetX"], "OffsetY": ["OffsetY"],
        "AcqFPS": ["AcquisitionFrameRate", "AcquisitionFrameRateAbs"],
        "ResultFPS": ["ResultingFrameRate", "ResultingFrameRateAbs"],
        "Packet": ["GevSCPSPacketSize"],
        "IPD": ["GevSCPD"],
        "Exposure": ["ExposureTime", "ExposureTimeAbs", "ExposureTimeRaw"],
        "Gain": ["Gain", "GainAbs", "GainRaw"],
    }.items():
        _, v = _get_first(nm, names)
        rb[k] = v
    return rb

def save_frame(img, outpath):
    # optional: save a PNG for debugging visibility
    try:
        import imageio.v2 as imageio
        imageio.imwrite(outpath, img)
        return True
    except Exception:
        pass
    try:
        import cv2
        cv2.imwrite(outpath, img)
        return True
    except Exception:
        return False

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cam", default="StaticCam")
    ap.add_argument("--serial", default="")
    ap.add_argument("--family", default="tag36h11")
    ap.add_argument("--frames", type=int, default=180)
    ap.add_argument("--min-tags", type=int, default=5)
    ap.add_argument("--save-n", type=int, default=0)   # save first N frames to PNG

    ap.add_argument("--pixel-format", default="Mono8")
    ap.add_argument("--width", type=int, default=960)
    ap.add_argument("--height", type=int, default=720)
    ap.add_argument("--offx", type=int, default=320)
    ap.add_argument("--offy", type=int, default=200)
    ap.add_argument("--fps", type=float, default=30)
    ap.add_argument("--exposure-us", type=float, default=15000)
    ap.add_argument("--gain", type=float, default=0)
    ap.add_argument("--packet-size", type=int, default=8192)
    ap.add_argument("--interpacket-delay", type=int, default=3500)
    ap.add_argument("--stream-buffer-count", type=int, default=64)
    ap.add_argument("--timeout-ms", type=int, default=2000)
    args = ap.parse_args()

    det_name, detector = try_make_detector(args.family)
    print(f"[detector] {det_name} families={args.family}")

    cam, applied = open_basler(args)
    rb = get_readbacks(cam)
    print("[applied_nodes]", applied)
    print("[readback]", rb)

    counts, grab_fails, means = [], 0, []
    from pypylon import pylon

    outdir = None
    if args.save_n > 0:
        outdir = os.path.join("basler_test_runs", f"tagcheck_{time.strftime('%Y%m%d_%H%M%S')}")
        os.makedirs(outdir, exist_ok=True)
        print(f"[save] dir={outdir}")

    for i in range(args.frames):
        res = cam.RetrieveResult(int(args.timeout_ms), pylon.TimeoutHandling_Return)
        if not res.GrabSucceeded():
            grab_fails += 1
            counts.append(0)
            means.append(0.0)
            continue
        img = res.Array
        res.Release()

        means.append(float(np.mean(img)))

        if outdir and i < args.save_n:
            ok = save_frame(img, os.path.join(outdir, f"frame_{i:03d}.png"))
            if not ok:
                print("[save] warning: could not save png (no imageio/cv2)")

        if det_name == "pupil_apriltags":
            tags = detector.detect(img, estimate_tag_pose=False)
        else:
            tags = detector.detect(img)
        counts.append(len(tags))

    cam.StopGrabbing(); cam.Close()

    pct = 100.0 * sum(c >= args.min_tags for c in counts) / max(1, len(counts))
    p50 = float(np.percentile(counts, 50))
    p90 = float(np.percentile(counts, 90))

    bmean = float(np.mean(means)) if means else 0.0
    bp50 = float(np.percentile(means, 50)) if means else 0.0

    print(f"[brightness] mean={bmean:.1f} p50={bp50:.1f} (Mono8 scale 0..255)")
    print(f"[tag_counts] frames={len(counts)} grab_fails={grab_fails}")
    print(f"[tag_counts] mean={stats.mean(counts):.2f} p50={p50:.1f} p90={p90:.1f} min={min(counts)} max={max(counts)} pct_>={args.min_tags}={pct:.1f}%")

if __name__ == "__main__":
    main()
