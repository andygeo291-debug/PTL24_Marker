import abc
import logging
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

import numpy as np

LOGGER = logging.getLogger(__name__)


@dataclass
class FramePacket:
    """Container for a single captured frame."""

    image: np.ndarray
    t_capture_ns: int
    frame_id: int
    backend: str
    extra: Dict[str, Any]


class CameraBase(abc.ABC):
    """Minimal camera interface for plugging in different backends."""

    backend_name: str = "unknown"

    @abc.abstractmethod
    def open(self) -> bool:
        """Initialize the camera connection and start streaming."""

    @abc.abstractmethod
    def read(self) -> Optional[FramePacket]:
        """Return the next frame packet, or None on timeout/failure."""

    @abc.abstractmethod
    def close(self) -> None:
        """Release the camera and associated resources."""

    def read_frame(self) -> Tuple[bool, Optional[np.ndarray]]:
        """Convenience method to match cv2.VideoCapture.read() signature."""

        packet = self.read()
        if packet is None:
            return False, None
        return True, packet.image

    def now_ns(self) -> int:
        """Wall-clock timestamp helper for implementations."""

        return time.time_ns()

