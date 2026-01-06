import logging
from typing import Optional, Tuple

import cv2
import numpy as np

from common.camera.base import CameraBase, FramePacket

LOGGER = logging.getLogger(__name__)


class OpenCVCaptureAdapter(CameraBase):
    """Adapter to present an existing cv2.VideoCapture as a CameraBase."""

    backend_name = "opencv"

    def __init__(self, cap: cv2.VideoCapture, frame_format: str = "bgr") -> None:
        self.cap = cap
        self.frame_format = frame_format
        self._frame_id = 0

    def open(self) -> bool:
        if self.cap is None:
            LOGGER.error("OpenCV capture handle is None.")
            return False
        if hasattr(self.cap, "isOpened"):
            try:
                if not self.cap.isOpened():
                    LOGGER.error("OpenCV capture is not opened.")
                    return False
            except Exception:  # pylint: disable=broad-except
                LOGGER.warning("Unable to query capture state; continuing anyway.")
        return True

    def read(self) -> Optional[FramePacket]:
        ret, frame = self.cap.read()
        if not ret or frame is None:
            return None

        image = self._convert_frame(frame)
        packet = FramePacket(
            image=image,
            t_capture_ns=self.now_ns(),
            frame_id=self._frame_id,
            backend=self.backend_name,
            extra={},
        )
        self._frame_id += 1
        return packet

    def close(self) -> None:
        if self.cap is not None:
            try:
                self.cap.release()
            except Exception:  # pylint: disable=broad-except
                LOGGER.exception("Failed to release OpenCV capture.")

    def _convert_frame(self, frame: np.ndarray) -> np.ndarray:
        if self.frame_format == "gray":
            if frame.ndim == 2:
                return frame
            try:
                return cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            except Exception:  # pylint: disable=broad-except
                LOGGER.exception("Failed to convert frame to grayscale; returning original.")
                return frame
        return frame

