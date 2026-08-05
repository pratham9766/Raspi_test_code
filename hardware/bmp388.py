"""Bosch BMP388 barometric pressure and temperature sensor — I2C interface."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from utils.helpers import HardwareError


@dataclass(frozen=True)
class BMP388Config:
    """Configuration for BMP388 over I2C."""

    interface: str
    address: int           # 0x76 default; 0x77 if SDO pulled high
    sda_gpio: int
    scl_gpio: int
    sea_level_pressure_hpa: float
    refresh_hz: int


@dataclass(frozen=True)
class BMP388Reading:
    """One pressure sensor sample."""

    temperature_c: float
    pressure_hpa: float
    altitude_m: float


@dataclass
class BMP388Sensor:
    """Read temperature, pressure, and altitude from BMP388 over I2C."""

    config: BMP388Config
    _sensor: Any = field(default=None, init=False, repr=False)

    def connect(self) -> None:
        """Initialize the BMP388 I2C sensor."""
        if self._sensor is not None:
            return
        try:
            import board
            import busio
            from adafruit_bmp3xx import BMP3XX_I2C
        except ImportError as exc:
            raise HardwareError(
                "BMP388 dependencies missing. "
                "Run: pip install adafruit-circuitpython-bmp3xx"
            ) from exc

        try:
            i2c = busio.I2C(board.SCL, board.SDA)
            self._sensor = BMP3XX_I2C(i2c, address=self.config.address)
            self._sensor.sea_level_pressure = self.config.sea_level_pressure_hpa
        except Exception as exc:
            raise HardwareError(
                f"BMP388 not detected on I2C address 0x{self.config.address:02X}: {exc}"
            ) from exc

    def read(self) -> BMP388Reading:
        """Return one BMP388 sensor sample."""
        self.connect()
        try:
            return BMP388Reading(
                temperature_c=float(self._sensor.temperature),
                pressure_hpa=float(self._sensor.pressure),
                altitude_m=float(self._sensor.altitude),
            )
        except Exception as exc:
            raise HardwareError(f"Failed to read BMP388: {exc}") from exc

    def close(self) -> None:
        """Release the I2C sensor reference."""
        self._sensor = None
