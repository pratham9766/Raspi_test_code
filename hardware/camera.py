"""Camera abstraction via Picamera2."""
from __future__ import annotations
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from utils.helpers import HardwareError, timestamp_slug, ensure_directory

@dataclass(frozen=True)
class CameraConfig:
    resolution: tuple[int, int]
    preview_seconds: float
    image_dir: Path
    video_dir: Path
    video_seconds: float
    timelapse_interval_seconds: float

@dataclass
class PiCameraSensor:
    """Control the official Raspberry Pi Camera Module."""
    config: CameraConfig
    _picam2: Any = field(default=None, init=False, repr=False)

    def connect(self) -> None:
        """Initialize the camera."""
        if self._picam2 is not None:
            return
        try:
            from picamera2 import Picamera2
            self._picam2 = Picamera2()
        except ImportError as exc:
            raise HardwareError("picamera2 not installed.") from exc
        except Exception as exc:
            raise HardwareError(f"Failed to connect to camera: {exc}") from exc

    def preview(self) -> None:
        """Show camera preview."""
        self.connect()
        try:
            self._picam2.start_preview(
                preview={'main': {'size': self.config.resolution}}
            )
            time.sleep(self.config.preview_seconds)
            self._picam2.stop_preview()
        except Exception as exc:
            raise HardwareError(f"Preview failed: {exc}") from exc

    def capture_image(self) -> Path:
        """Capture a single image and save it."""
        self.connect()
        ensure_directory(self.config.image_dir)
        filepath = self.config.image_dir / f"img_{timestamp_slug()}.jpg"
        try:
            self._picam2.capture_file(str(filepath))
            return filepath
        except Exception as exc:
            raise HardwareError(f"Image capture failed: {exc}") from exc

    def capture_video(self) -> Path:
        """Capture a video clip."""
        self.connect()
        ensure_directory(self.config.video_dir)
        filepath = self.config.video_dir / f"vid_{timestamp_slug()}.h264"
        try:
            self._picam2.start_recording(str(filepath))
            time.sleep(self.config.video_seconds)
            self._picam2.stop_recording()
            return filepath
        except Exception as exc:
            raise HardwareError(f"Video capture failed: {exc}") from exc

    def timelapse(self) -> None:
        """Run a timelapse indefinitely until interrupted."""
        self.connect()
        ensure_directory(self.config.image_dir)
        print(f"Started timelapse (1 image every {self.config.timelapse_interval_seconds}s). Press Ctrl+C to stop.")
        try:
            while True:
                fp = self.capture_image()
                print(f"Captured: {fp.name}")
                time.sleep(self.config.timelapse_interval_seconds)
        except KeyboardInterrupt:
            print("\nTimelapse stopped by user.")
        except Exception as exc:
            raise HardwareError(f"Timelapse failed: {exc}") from exc

    def close(self) -> None:
        """Release camera resources."""
        if self._picam2:
            try:
                self._picam2.stop()
            except Exception:
                pass
            self._picam2 = None
