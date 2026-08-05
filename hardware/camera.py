"""Camera abstraction via Picamera2."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from utils.helpers import HardwareError, ensure_directory, timestamp_slug


@dataclass(frozen=True)
class CameraConfig:
    """Configuration for the Raspberry Pi camera."""

    resolution: tuple[int, int]
    preview_seconds: float
    image_dir: Path
    video_dir: Path
    video_seconds: float
    timelapse_interval_seconds: float


@dataclass
class PiCameraSensor:
    """Control the official Raspberry Pi Camera Module via Picamera2."""

    config: CameraConfig
    _picam2: Any = field(default=None, init=False, repr=False)

    def connect(self) -> None:
        """Initialize Picamera2, with a clear error if no camera is found."""
        if self._picam2 is not None:
            return
        try:
            from picamera2 import Picamera2
        except ImportError as exc:
            raise HardwareError(
                "picamera2 is not installed. Run: sudo apt install -y python3-picamera2"
            ) from exc

        # Check how many cameras are available before trying to open one
        try:
            cameras = Picamera2.global_camera_info()
        except Exception:
            cameras = []

        if not cameras:
            raise HardwareError(
                "No camera detected. Check:\n"
                "  1. Cable is firmly seated in the CSI connector\n"
                "  2. Camera is enabled: sudo raspi-config -> Interface -> Camera\n"
                "  3. Run: libcamera-hello --list-cameras"
            )

        try:
            picam2 = Picamera2(0)
            still_cfg = picam2.create_still_configuration(
                main={"size": self.config.resolution}
            )
            picam2.configure(still_cfg)
            self._picam2 = picam2
        except Exception as exc:
            raise HardwareError(f"Camera initialisation failed: {exc}") from exc

    def preview(self) -> None:
        """Show a camera preview for preview_seconds."""
        self.connect()
        try:
            self._picam2.start()
            print(f"  Preview running for {self.config.preview_seconds:.0f}s ...")
            time.sleep(self.config.preview_seconds)
        except Exception as exc:
            raise HardwareError(f"Preview failed: {exc}") from exc
        finally:
            try:
                self._picam2.stop()
            except Exception:
                pass

    def capture_image(self) -> Path:
        """Capture a single JPEG image and return its path."""
        self.connect()
        ensure_directory(self.config.image_dir)
        filepath = self.config.image_dir / f"img_{timestamp_slug()}.jpg"
        try:
            self._picam2.start()
            time.sleep(0.3)          # brief warm-up for AEC/AWB to settle
            self._picam2.capture_file(str(filepath))
        except Exception as exc:
            raise HardwareError(f"Image capture failed: {exc}") from exc
        finally:
            try:
                self._picam2.stop()
            except Exception:
                pass
        return filepath

    def capture_video(self) -> Path:
        """Record a video clip and return its path."""
        self.connect()
        ensure_directory(self.config.video_dir)
        filepath = self.config.video_dir / f"vid_{timestamp_slug()}.h264"

        try:
            from picamera2.encoders import H264Encoder
            from picamera2.outputs import FileOutput
        except ImportError as exc:
            raise HardwareError("Picamera2 encoder support unavailable.") from exc

        try:
            video_cfg = self._picam2.create_video_configuration(
                main={"size": self.config.resolution}
            )
            self._picam2.configure(video_cfg)
            encoder = H264Encoder()
            self._picam2.start_recording(encoder, FileOutput(str(filepath)))
            print(f"  Recording {self.config.video_seconds:.0f}s ...")
            time.sleep(self.config.video_seconds)
        except Exception as exc:
            raise HardwareError(f"Video recording failed: {exc}") from exc
        finally:
            try:
                self._picam2.stop_recording()
            except Exception:
                pass
            # Restore still config for next capture
            try:
                still_cfg = self._picam2.create_still_configuration(
                    main={"size": self.config.resolution}
                )
                self._picam2.configure(still_cfg)
            except Exception:
                pass
        return filepath

    def timelapse(self) -> None:
        """Capture images at a fixed interval until Ctrl+C."""
        self.connect()
        ensure_directory(self.config.image_dir)
        interval = self.config.timelapse_interval_seconds
        print(f"  Timelapse: 1 image every {interval:.1f}s -- Ctrl+C to stop.")
        count = 0
        try:
            while True:
                fp = self.capture_image()
                count += 1
                print(f"  [{count:04d}] Saved: {fp.name}")
                time.sleep(interval)
        except KeyboardInterrupt:
            print(f"\n  Timelapse stopped. {count} images saved to {self.config.image_dir}")
        except Exception as exc:
            raise HardwareError(f"Timelapse failed: {exc}") from exc

    def close(self) -> None:
        """Release all camera resources."""
        if self._picam2 is not None:
            try:
                self._picam2.stop()
            except Exception:
                pass
            try:
                self._picam2.close()
            except Exception:
                pass
            self._picam2 = None
