import logging
import time
from typing import Any, Dict, Optional

import cv2
import numpy as np

from common.camera.base import CameraBase, FramePacket

LOGGER = logging.getLogger(__name__)


class BaslerGigECam(CameraBase):
    """Basler GigE camera backend using pypylon."""

    backend_name = "basler"

    def __init__(
        self,
        serial: Optional[str] = None,
        name: Optional[str] = None,
        frame_format: str = "bgr",
        timeout_ms: int = 5000,
        packet_size: Optional[int] = None,
        inter_packet_delay: Optional[int] = None,
        enable_chunk_ts: bool = True,
        pixel_format: Optional[str] = "Mono8",
        exposure_us: Optional[float] = None,
        gain: Optional[float] = None,
        offset_x: Optional[int] = 0,
        offset_y: Optional[int] = 0,
        width: Optional[int] = None,
        height: Optional[int] = None,
        fps: Optional[float] = None,
    ) -> None:
        self.serial = str(serial) if serial else None
        self.name = name
        self.frame_format = frame_format
        self.timeout_ms = int(timeout_ms)
        self.packet_size = packet_size
        self.inter_packet_delay = inter_packet_delay
        self.enable_chunk_ts = enable_chunk_ts
        self.pixel_format = pixel_format
        self.exposure_us = exposure_us
        self.gain = gain
        self.offset_x = offset_x
        self.offset_y = offset_y
        self.width = width
        self.height = height
        self.fps = fps

        self._pylon = None
        self._camera = None
        self._converter = None
        self._frame_id = 0
        self._opened = False
        self._warned_unknown_bayer = False

    def open(self) -> bool:
        if self._opened:
            return True

        try:
            from pypylon import pylon  # type: ignore
        except ImportError as exc:
            LOGGER.error("pypylon is not installed; Basler backend unavailable: %s", exc)
            return False

        self._pylon = pylon
        factory = pylon.TlFactory.GetInstance()
        devices = factory.EnumerateDevices()
        if not devices:
            LOGGER.error("No Basler cameras detected.")
            return False

        device = self._select_device(devices)
        if device is None:
            return False

        camera = pylon.InstantCamera(factory.CreateDevice(device))
        try:
            camera.Open()
        except Exception as exc:  # pylint: disable=broad-except
            LOGGER.exception("Failed to open Basler camera: %s", exc)
            return False

        node_map = camera.GetNodeMap()
        self._apply_requested_settings(node_map)
        self._apply_networking(node_map)
        self._configure_chunk_timestamp(node_map)

        converter = pylon.ImageFormatConverter()
        try:
            converter.OutputPixelFormat = pylon.PixelType_BGR8packed
            converter.OutputBitAlignment = pylon.OutputBitAlignment_MsbAligned
        except Exception:  # pylint: disable=broad-except
            LOGGER.warning("Failed to configure Basler image converter; using raw arrays.")
            converter = None

        try:
            camera.StartGrabbing(pylon.GrabStrategy_LatestImageOnly)
        except Exception as exc:  # pylint: disable=broad-except
            LOGGER.exception("Failed to start grabbing: %s", exc)
            camera.Close()
            return False

        self._camera = camera
        self._converter = converter
        self._opened = True
        settings = self._read_settings_info(camera)
        LOGGER.info(
            "Basler settings: PixelFormat=%s ROI=%sx%s offset=%s,%s fps=%s exp_us=%s gain=%s GevSCPD=%s",
            settings.get("pixel_format"),
            settings.get("width"),
            settings.get("height"),
            settings.get("offset_x"),
            settings.get("offset_y"),
            settings.get("fps"),
            settings.get("exposure_us"),
            settings.get("gain"),
            settings.get("gev_scpd"),
        )
        LOGGER.info(
            "Basler camera opened (serial=%s name=%s) chunk_ts=%s",
            self.serial or "auto",
            self.name or "auto",
            "on" if self.enable_chunk_ts else "off",
        )
        return True

    def read(self) -> Optional[FramePacket]:
        if not self._opened or self._camera is None or self._pylon is None:
            LOGGER.error("Basler camera not opened.")
            return None

        host_time_ns = time.time_ns()
        try:
            grab_result = self._camera.RetrieveResult(
                self.timeout_ms, self._pylon.TimeoutHandling_Return
            )
        except Exception as exc:  # pylint: disable=broad-except
            LOGGER.exception("RetrieveResult failed: %s", exc)
            return None

        if grab_result is None:
            LOGGER.warning("RetrieveResult returned None (timeout after %d ms).", self.timeout_ms)
            return None

        try:
            if not grab_result.GrabSucceeded():
                LOGGER.warning(
                    "Basler grab failed: %s (%s)",
                    getattr(grab_result, "ErrorDescription", "unknown"),
                    getattr(grab_result, "ErrorCode", "n/a"),
                )
                return None

            pixel_format = None
            if self._camera is not None:
                try:
                    pixel_format = str(self._camera.PixelFormat.Value)
                except Exception:  # pylint: disable=broad-except
                    pixel_format = None
            if not pixel_format:
                pixel_format = self._detect_pixel_format(grab_result)
            image = self._convert_result(grab_result, pixel_format)
            if image is None:
                return None

            chunk_ts_raw = getattr(grab_result, "ChunkTimestamp", None)
            time_stamp_raw = getattr(grab_result, "TimeStamp", None)
            capture_ns = self._select_capture_ns(host_time_ns, chunk_ts_raw)
            packet = FramePacket(
                image=image,
                t_capture_ns=capture_ns,
                frame_id=self._frame_id,
                backend=self.backend_name,
                extra={
                    "basler_block_id": getattr(grab_result, "BlockID", None),
                    "basler_chunk_ts_raw": chunk_ts_raw,
                    "basler_time_stamp_raw": time_stamp_raw,
                    "basler_pixel_format": pixel_format,
                },
            )
            self._frame_id += 1
            return packet
        finally:
            try:
                grab_result.Release()
            except Exception:  # pylint: disable=broad-except
                LOGGER.debug("Failed to release grab result.")

    def close(self) -> None:
        if self._camera is None:
            return
        try:
            if self._camera.IsGrabbing():
                self._camera.StopGrabbing()
        except Exception:  # pylint: disable=broad-except
            LOGGER.debug("Error while stopping Basler grabbing.", exc_info=True)
        try:
            self._camera.Close()
        except Exception:  # pylint: disable=broad-except
            LOGGER.debug("Error while closing Basler camera.", exc_info=True)
        self._opened = False
        self._camera = None
        self._converter = None
        self._pylon = None

    def _select_device(self, devices) -> Optional[Any]:
        if self.serial:
            for device in devices:
                try:
                    if device.GetSerialNumber() == self.serial:
                        return device
                except Exception:  # pylint: disable=broad-except
                    continue
            LOGGER.warning("No Basler device found with serial %s.", self.serial)
        if self.name:
            for device in devices:
                try:
                    if device.GetUserDefinedName() == self.name:
                        return device
                except Exception:  # pylint: disable=broad-except
                    continue
            LOGGER.warning("No Basler device found with name %s.", self.name)
        LOGGER.warning("Falling back to first detected Basler device.")
        return devices[0] if devices else None

    def _apply_networking(self, node_map) -> None:
        if self.packet_size is not None:
            self._set_int_node(node_map, "GevSCPSPacketSize", self.packet_size)
        if self.inter_packet_delay is not None:
            self._set_int_node(node_map, "GevSCPD", self.inter_packet_delay)

    def _apply_requested_settings(self, node_map) -> None:
        if self.pixel_format is not None:
            self._set_enum_node(node_map, "PixelFormat", self.pixel_format)
        if self.offset_x is not None:
            self._set_int_node(node_map, "OffsetX", self.offset_x)
        if self.offset_y is not None:
            self._set_int_node(node_map, "OffsetY", self.offset_y)
        if self.width is not None:
            self._set_int_node(node_map, "Width", self.width)
        if self.height is not None:
            self._set_int_node(node_map, "Height", self.height)
        if self.fps is not None:
            self._set_bool_node(node_map, "AcquisitionFrameRateEnable", True)
            if not self._set_float_node(node_map, "AcquisitionFrameRate", self.fps):
                self._set_float_node(node_map, "AcquisitionFrameRateAbs", self.fps)
        if self.exposure_us is not None:
            self._set_enum_node(node_map, "ExposureAuto", "Off")
            if not self._set_float_node(node_map, "ExposureTime", self.exposure_us):
                self._set_float_node(node_map, "ExposureTimeAbs", self.exposure_us)
        if self.gain is not None:
            self._set_enum_node(node_map, "GainAuto", "Off")
            if not self._set_float_node(node_map, "Gain", self.gain):
                self._set_float_node(node_map, "GainAbs", self.gain)

    def _configure_chunk_timestamp(self, node_map) -> None:
        if not self.enable_chunk_ts:
            return
        self._set_bool_node(node_map, "ChunkModeActive", True)
        self._set_enum_node(node_map, "ChunkSelector", "Timestamp")
        self._set_bool_node(node_map, "ChunkEnable", True)

    def _convert_result(self, grab_result, pixel_format: Optional[str]) -> Optional[np.ndarray]:
        image = None
        if self._converter is not None:
            try:
                converted = self._converter.Convert(grab_result)
                image = converted.GetArray()
            except Exception:  # pylint: disable=broad-except
                LOGGER.warning("Basler conversion failed; using raw array.")
                image = None
        if image is None:
            try:
                image = grab_result.GetArray()
            except Exception as exc:  # pylint: disable=broad-except
                LOGGER.exception("Failed to extract Basler image array: %s", exc)
                return None

        if image.ndim == 2:
            if pixel_format:
                bayer = self._bayer_code(pixel_format, gray=(self.frame_format == "gray"))
            else:
                bayer = None
            if bayer is not None:
                try:
                    return cv2.cvtColor(image, bayer)
                except Exception:  # pylint: disable=broad-except
                    LOGGER.exception("Failed to debayer Basler frame; returning raw array.")
                    return image
            if not self._warned_unknown_bayer and self.frame_format != "gray":
                LOGGER.warning("Unknown Basler Bayer format; returning raw 2D array.")
                self._warned_unknown_bayer = True
            if self.frame_format == "gray":
                return image
            try:
                return cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
            except Exception:  # pylint: disable=broad-except
                LOGGER.exception("Failed to convert Basler gray to BGR; returning raw array.")
                return image

        if self.frame_format == "gray":
            try:
                return cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            except Exception:  # pylint: disable=broad-except
                LOGGER.exception("Failed to convert Basler frame to gray; returning raw array.")
                return image
        return image

    def _select_capture_ns(self, host_time_ns: int, chunk_ts_raw: Any) -> int:
        if isinstance(chunk_ts_raw, int) and chunk_ts_raw > 1e11:
            return chunk_ts_raw
        return host_time_ns

    def _read_settings_info(self, camera) -> Dict[str, Any]:
        def read_value(name: str) -> Optional[Any]:
            try:
                return getattr(camera, name).Value
            except Exception:  # pylint: disable=broad-except
                return None

        info: Dict[str, Any] = {}
        info["pixel_format"] = read_value("PixelFormat")
        info["width"] = read_value("Width")
        info["height"] = read_value("Height")
        info["offset_x"] = read_value("OffsetX")
        info["offset_y"] = read_value("OffsetY")
        info["fps"] = read_value("AcquisitionFrameRate")
        if info["fps"] is None:
            info["fps"] = read_value("AcquisitionFrameRateAbs")
        info["exposure_us"] = read_value("ExposureTime")
        if info["exposure_us"] is None:
            info["exposure_us"] = read_value("ExposureTimeAbs")
        info["gain"] = read_value("Gain")
        if info["gain"] is None:
            info["gain"] = read_value("GainAbs")
        if info["gain"] is None:
            info["gain"] = read_value("GainRaw")
        info["gev_scpd"] = read_value("GevSCPD")
        return info

    def _detect_pixel_format(self, grab_result) -> Optional[str]:
        pixel_type = None
        if hasattr(grab_result, "GetPixelType"):
            try:
                pixel_type = grab_result.GetPixelType()
            except Exception:  # pylint: disable=broad-except
                pixel_type = None
        elif hasattr(grab_result, "PixelType"):
            try:
                pixel_type = grab_result.PixelType
            except Exception:  # pylint: disable=broad-except
                pixel_type = None

        if isinstance(pixel_type, str):
            return pixel_type
        if isinstance(pixel_type, int) and self._pylon is not None:
            for name in ("PixelType_BayerRG8", "PixelType_BayerBG8", "PixelType_BayerGR8", "PixelType_BayerGB8"):
                val = getattr(self._pylon, name, None)
                if val is not None and pixel_type == val:
                    return name.replace("PixelType_", "")

        if self._camera is not None:
            try:
                return str(self._camera.PixelFormat.Value)
            except Exception:  # pylint: disable=broad-except
                return None
        return None

    def _bayer_code(self, pixel_format: str, gray: bool) -> Optional[int]:
        if "BayerRG8" in pixel_format:
            return cv2.COLOR_BAYER_RG2GRAY if gray else cv2.COLOR_BAYER_RG2BGR
        if "BayerBG8" in pixel_format:
            return cv2.COLOR_BAYER_BG2GRAY if gray else cv2.COLOR_BAYER_BG2BGR
        if "BayerGR8" in pixel_format:
            return cv2.COLOR_BAYER_GR2GRAY if gray else cv2.COLOR_BAYER_GR2BGR
        if "BayerGB8" in pixel_format:
            return cv2.COLOR_BAYER_GB2GRAY if gray else cv2.COLOR_BAYER_GB2BGR
        return None

    def _set_int_node(self, node_map, name: str, value: int) -> None:
        try:
            node = node_map.GetNode(name)
        except Exception:  # pylint: disable=broad-except
            node = None
        if node is None:
            LOGGER.warning("Basler node %s not found; skipping.", name)
            return
        try:
            node.SetValue(int(value))
            LOGGER.info("Set Basler parameter %s=%s", name, int(value))
        except Exception as exc:  # pylint: disable=broad-except
            LOGGER.warning("Unable to set Basler parameter %s; continuing.", name)
            LOGGER.debug("Basler set %s error: %s", name, exc, exc_info=True)

    def _set_float_node(self, node_map, name: str, value: float) -> bool:
        try:
            node = node_map.GetNode(name)
        except Exception:  # pylint: disable=broad-except
            node = None
        if node is None:
            LOGGER.warning("Basler node %s not found; skipping.", name)
            return False
        try:
            node.SetValue(float(value))
            LOGGER.info("Set Basler parameter %s=%s", name, float(value))
            return True
        except Exception as exc:  # pylint: disable=broad-except
            LOGGER.warning("Unable to set Basler parameter %s; continuing.", name)
            LOGGER.debug("Basler set %s error: %s", name, exc, exc_info=True)
            return False

    def _set_bool_node(self, node_map, name: str, value: bool) -> None:
        try:
            node = node_map.GetNode(name)
        except Exception:  # pylint: disable=broad-except
            node = None
        if node is None:
            LOGGER.warning("Basler node %s not found; skipping.", name)
            return
        try:
            node.SetValue(bool(value))
            LOGGER.info("Set Basler parameter %s=%s", name, bool(value))
        except Exception as exc:  # pylint: disable=broad-except
            LOGGER.warning("Unable to set Basler parameter %s; continuing.", name)
            LOGGER.debug("Basler set %s error: %s", name, exc, exc_info=True)

    def _set_enum_node(self, node_map, name: str, value: str) -> None:
        try:
            node = node_map.GetNode(name)
        except Exception:  # pylint: disable=broad-except
            node = None
        if node is None:
            LOGGER.warning("Basler node %s not found; skipping.", name)
            return
        try:
            if hasattr(node, "FromString"):
                node.FromString(str(value))
            else:
                node.SetValue(str(value))
            LOGGER.info("Set Basler parameter %s=%s", name, value)
        except Exception as exc:  # pylint: disable=broad-except
            LOGGER.warning("Unable to set Basler parameter %s; continuing.", name)
            LOGGER.debug("Basler set %s error: %s", name, exc, exc_info=True)
