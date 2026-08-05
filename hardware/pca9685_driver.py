"""PCA9685 16-channel PWM driver via I2C."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any
from utils.helpers import HardwareError

@dataclass(frozen=True)
class PCA9685Config:
    """Configuration for PCA9685 PWM Driver."""
    interface: str
    address: int
    frequency_hz: int

@dataclass
class PCA9685Driver:
    """Control PCA9685 via I2C."""
    address: int = 0x40
    frequency_hz: int = 50
    _pca: Any | None = field(default=None, init=False, repr=False)

    def connect(self) -> None:
        """Initialize the PCA9685 over I2C."""
        if self._pca is not None:
            return
            
        try:
            import board
            import busio
            from adafruit_pca9685 import PCA9685
        except ImportError as exc:
            raise HardwareError(
                "PCA9685 dependencies not installed. Run: pip install adafruit-circuitpython-pca9685"
            ) from exc

        try:
            i2c = busio.I2C(board.SCL, board.SDA)
            self._pca = PCA9685(i2c, address=self.address)
            self._pca.frequency = self.frequency_hz
        except Exception as exc:
            raise HardwareError(f"Failed to connect PCA9685 at 0x{self.address:02X}: {exc}") from exc

    def set_channel_duty(self, channel: int, duty: float) -> None:
        """Set a channel's duty cycle from 0.0 to 1.0."""
        if not self._pca:
            self.connect()
        try:
            duty = max(0.0, min(1.0, duty))
            self._pca.channels[channel].duty_cycle = int(duty * 65535)
        except Exception as exc:
            raise HardwareError(f"Error setting PCA9685 channel {channel} duty: {exc}") from exc

    def set_channel_pulse_us(self, channel: int, pulse_us: float) -> None:
        """Set a channel's pulse width in microseconds."""
        period_us = 1_000_000.0 / self.frequency_hz
        duty = pulse_us / period_us
        self.set_channel_duty(channel, duty)

    def disable_channel(self, channel: int) -> None:
        """Disable a channel (0 duty cycle)."""
        self.set_channel_duty(channel, 0.0)

    def close(self) -> None:
        """Deinitialize PCA9685 hardware."""
        if self._pca:
            try:
                if hasattr(self._pca, 'deinit'):
                    self._pca.deinit()
            except Exception:
                pass
            self._pca = None
