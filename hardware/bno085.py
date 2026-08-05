"""Bosch/Hillcrest BNO085 IMU — I2C interface.

Supports: Accelerometer, Gyroscope, Magnetometer,
          Quaternion, Rotation Vector, Calibration Status.
"""
from __future__ import annotations

import contextlib
import io
from dataclasses import dataclass, field
from typing import Any

from utils.helpers import HardwareError


@dataclass(frozen=True)
class BNO085Reading:
    """One complete sample from the BNO085 sensor."""
    acceleration: tuple[float, float, float] | None
    gyroscope: tuple[float, float, float] | None
    magnetometer: tuple[float, float, float] | None
    quaternion: tuple[float, float, float, float] | None
    rotation_vector: tuple[float, float, float, float] | None
    calibration_status: int | None


@dataclass(frozen=True)
class BNO085Config:
    """Configuration for BNO085."""
    interface: str
    address: int
    sda_gpio: int
    scl_gpio: int
    refresh_hz: int


@dataclass
class BNO085Sensor:
    """Read motion data from a BNO085 over I2C."""
    config: BNO085Config
    _sensor: Any = field(default=None, init=False, repr=False)

    def connect(self) -> None:
        """Initialize the BNO085 I2C sensor."""
        if self._sensor is not None:
            return
        try:
            import board
            import busio
            from adafruit_bno08x import (
                BNO_REPORT_ACCELEROMETER,
                BNO_REPORT_GYROSCOPE,
                BNO_REPORT_MAGNETOMETER,
                BNO_REPORT_ROTATION_VECTOR,
            )
            from adafruit_bno08x.i2c import BNO08X_I2C
        except ImportError as exc:
            raise HardwareError(
                "BNO085 I2C dependencies not installed. "
                "Run: pip install adafruit-circuitpython-bno08x"
            ) from exc

        try:
            i2c = busio.I2C(board.SCL, board.SDA)
            with contextlib.redirect_stdout(io.StringIO()):
                sensor = BNO08X_I2C(i2c, address=self.config.address)
                sensor.enable_feature(BNO_REPORT_ACCELEROMETER)
                sensor.enable_feature(BNO_REPORT_GYROSCOPE)
                sensor.enable_feature(BNO_REPORT_MAGNETOMETER)
                sensor.enable_feature(BNO_REPORT_ROTATION_VECTOR)
            self._sensor = sensor
        except Exception as exc:
            raise HardwareError(
                f"BNO085 not detected on I2C address 0x{self.config.address:02X}: {exc}"
            ) from exc

    def read(self) -> BNO085Reading:
        """Return one complete BNO085 sensor sample."""
        self.connect()
        try:
            return BNO085Reading(
                acceleration=self._sensor.acceleration,
                gyroscope=self._sensor.gyro,
                magnetometer=self._sensor.magnetic,
                quaternion=self._sensor.quaternion,
                rotation_vector=getattr(self._sensor, 'rotation_vector', None),
                calibration_status=getattr(self._sensor, 'calibration_status', None),
            )
        except Exception as exc:
            raise HardwareError(f"Failed to read BNO085: {exc}") from exc

    def close(self) -> None:
        """Release sensor reference."""
        self._sensor = None
