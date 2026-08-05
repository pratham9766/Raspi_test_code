"""Bosch BMP388 barometric pressure and temperature sensor — SPI interface."""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any
from utils.helpers import HardwareError

@dataclass(frozen=True)
class BMP388Config:
    """Configuration for BMP388."""
    interface: str
    sck_gpio: int
    mosi_gpio: int
    miso_gpio: int
    cs_gpio: int
    int_gpio: int
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
    """Read temperature, pressure, altitude from BMP388 over SPI."""
    config: BMP388Config
    _sensor: Any = field(default=None, init=False, repr=False)

    def connect(self) -> None:
        """Initialize the BMP388 SPI sensor."""
        if self._sensor is not None:
            return
        try:
            import board
            import busio
            import digitalio
            from adafruit_bmp3xx import BMP3XX_SPI
        except ImportError as exc:
            raise HardwareError(
                "BMP388 dependencies missing. Run: pip install adafruit-circuitpython-bmp3xx"
            ) from exc

        try:
            cs = digitalio.DigitalInOut(getattr(board, f"D{self.config.cs_gpio}"))
            spi = busio.SPI(
                getattr(board, f"D{self.config.sck_gpio}"),
                getattr(board, f"D{self.config.mosi_gpio}"),
                getattr(board, f"D{self.config.miso_gpio}")
            )
            self._sensor = BMP3XX_SPI(spi, cs)
            self._sensor.sea_level_pressure = self.config.sea_level_pressure_hpa
        except Exception as exc:
            raise HardwareError(f"Failed to connect to BMP388 via SPI: {exc}") from exc

    def read(self) -> BMP388Reading:
        """Read a sample from the BMP388."""
        self.connect()
        try:
            return BMP388Reading(
                temperature_c=self._sensor.temperature,
                pressure_hpa=self._sensor.pressure,
                altitude_m=self._sensor.altitude
            )
        except Exception as exc:
            raise HardwareError(f"Failed to read BMP388: {exc}") from exc

    def close(self) -> None:
        """Release the SPI sensor."""
        self._sensor = None
