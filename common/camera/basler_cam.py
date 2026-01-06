import time

import numpy as np


class BaslerGigECam:
    def __init__(
        self,
        serial,
        name,
        width,
        height,
        offset_x,
        offset_y,
        fps,
        pixel_format="Mono8",
        exposure_us=None,
        gain=None,
        packet_size=None,
        interpacket_delay=None,
        timeout_ms=1000,
    ):
        self.serial = serial
        self.name = name
        self.width = width
        self.height = height
        self.offset_x = offset_x
        self.offset_y = offset_y
        self.fps = fps
        self.pixel_format = pixel_format
        self.exposure_us = exposure_us
        self.gain = gain
        self.packet_size = packet_size
        self.interpacket_delay = interpacket_delay
        self.timeout_ms = timeout_ms

        self.last_timestamp_s = None
        self.device_info = {}
        self.readback_settings = {}

        self._pylon = None
        self._genicam = None
        self._camera = None
        self._converter = None

    def _import_pypylon(self):
        if self._pylon is None or self._genicam is None:
            from pypylon import genicam, pylon

            self._pylon = pylon
            self._genicam = genicam

    def _safe_get(self, info, method_name):
        method = getattr(info, method_name, None)
        if method is None:
            return ""
        try:
            return method()
        except Exception:
            return ""

    def _device_matches(self, info):
        if self.serial:
            if self._safe_get(info, "GetSerialNumber") != self.serial:
                return False
        if self.name:
            candidates = []
            for method in ("GetUserDefinedName", "GetModelName", "GetFriendlyName", "GetFullName"):
                value = self._safe_get(info, method)
                if value:
                    candidates.append(value)
            if not candidates:
                return False
            if not any(self.name == value for value in candidates) and not any(
                self.name in value for value in candidates
            ):
                return False
        return True

    def _get_node(self, node_map, name):
        try:
            return node_map.GetNode(name)
        except Exception:
            return None

    def _set_enum(self, node_map, name, value):
        if value is None:
            return False
        node = self._get_node(node_map, name)
        if node is None or not self._genicam.IsWritable(node):
            return False
        try:
            entry = node.GetEntryByName(value)
            if (
                entry is None
                or not self._genicam.IsAvailable(entry)
                or not self._genicam.IsReadable(entry)
            ):
                return False
            node.SetIntValue(entry.GetValue())
            return True
        except Exception:
            return False

    def _set_value(self, node_map, name, value, cast):
        if value is None:
            return False
        node = self._get_node(node_map, name)
        if node is None or not self._genicam.IsWritable(node):
            return False
        try:
            node.SetValue(cast(value))
            return True
        except Exception:
            return False

    def _read_node(self, node_map, name):
        node = self._get_node(node_map, name)
        if node is None or not self._genicam.IsReadable(node):
            return None
        try:
            return node.ToString()
        except Exception:
            try:
                return node.GetValue()
            except Exception:
                return None

    def _apply_settings(self, node_map):
        self._set_enum(node_map, "PixelFormat", self.pixel_format)
        self._set_value(node_map, "Width", self.width, int)
        self._set_value(node_map, "Height", self.height, int)
        self._set_value(node_map, "OffsetX", self.offset_x, int)
        self._set_value(node_map, "OffsetY", self.offset_y, int)

        if self.fps is not None:
            self._set_value(node_map, "AcquisitionFrameRateEnable", True, bool)
            self._set_value(node_map, "AcquisitionFrameRate", self.fps, float)

        self._set_value(node_map, "ExposureTime", self.exposure_us, float)
        self._set_value(node_map, "Gain", self.gain, float)

        self._set_value(node_map, "GevSCPSPacketSize", self.packet_size, int)
        self._set_value(node_map, "GevSCPD", self.interpacket_delay, int)

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
            value = self._read_node(node_map, key)
            if value is not None:
                readback[key] = value
        self.readback_settings = readback

    def open(self):
        if self._camera is not None:
            return
        self._import_pypylon()
        tl_factory = self._pylon.TlFactory.GetInstance()
        devices = tl_factory.EnumerateDevices()
        if not devices:
            raise RuntimeError("No devices found")

        selected = None
        for info in devices:
            if self._device_matches(info):
                selected = info
                break
        if selected is None:
            raise RuntimeError("No matching device found")

        camera = self._pylon.InstantCamera(tl_factory.CreateDevice(selected))
        camera.Open()

        info = camera.GetDeviceInfo()
        self.device_info = {
            "serial": self._safe_get(info, "GetSerialNumber"),
            "user": self._safe_get(info, "GetUserDefinedName"),
            "model": self._safe_get(info, "GetModelName"),
        }

        node_map = camera.GetNodeMap()
        self._apply_settings(node_map)

        converter = self._pylon.ImageFormatConverter()
        converter.OutputPixelFormat = self._pylon.PixelType_Mono8
        converter.OutputBitAlignment = self._pylon.OutputBitAlignment_MsbAligned

        camera.StartGrabbing(self._pylon.GrabStrategy_LatestImageOnly)

        self._camera = camera
        self._converter = converter

    def read(self):
        if self._camera is None:
            return False, None
        grab_result = self._camera.RetrieveResult(
            self.timeout_ms, self._pylon.TimeoutHandling_Return
        )
        if grab_result is None:
            return False, None
        try:
            if not grab_result.GrabSucceeded():
                return False, None
            image = self._converter.Convert(grab_result)
            array = image.GetArray()
            if array.dtype != np.uint8:
                array = array.astype(np.uint8, copy=False)
            self.last_timestamp_s = time.time()
            return True, array
        finally:
            grab_result.Release()

    def release(self):
        if self._camera is None:
            return
        try:
            if self._camera.IsGrabbing():
                self._camera.StopGrabbing()
        except Exception:
            pass
        try:
            if self._camera.IsOpen():
                self._camera.Close()
        except Exception:
            pass
        self._camera = None
        self._converter = None
