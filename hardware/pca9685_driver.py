"""PCA9685 16-channel PWM driver via I2C.

OE (Output Enable) pin is active-LOW:
    GPIO LOW  → outputs ENABLED
    GPIO HIGH → outputs disabled (high-impedance)

The OE pin is driven LOW on connect() and HIGH on close().
"""
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
    oe_gpio: int | None = None   # Output Enable GPIO (active LOW). None = not wired.


@dataclass
class PCA9685Driver:
    """Control PCA9685 via I2C with optional OE pin management."""

    address: int = 0x40
    frequency_hz: int = 50
    oe_gpio: int | None = None   # GPIO number for OE pin (BCM). None = not used.

    _pca: Any = field(default=None, init=False, repr=False)
    _gpio: Any = field(default=None, init=False, repr=False)

    def _setup_oe(self) -> None:
        """Configure OE GPIO as output and drive LOW (enable outputs)."""
        if self.oe_gpio is None:
            return
        try:
            import RPi.GPIO as GPIO
            self._gpio = GPIO
            GPIO.setmode(GPIO.BCM)
            GPIO.setwarnings(False)
            GPIO.setup(self.oe_gpio, GPIO.OUT)
            GPIO.output(self.oe_gpio, GPIO.LOW)   # active LOW → enable
        except ImportError as exc:
            raise HardwareError(
                "RPi.GPIO not installed — needed for PCA9685 OE pin. "
                "Run: pip install RPi.GPIO"
            ) from exc
        except Exception as exc:
            raise HardwareError(
                f"Failed to configure OE pin GPIO{self.oe_gpio}: {exc}"
            ) from exc

    def _release_oe(self) -> None:
        """Drive OE HIGH (disable outputs) and clean up GPIO."""
        if self._gpio is None or self.oe_gpio is None:
            return
        try:
            self._gpio.output(self.oe_gpio, self._gpio.HIGH)  # disable outputs
            self._gpio.cleanup(self.oe_gpio)
        except Exception:
            pass
        self._gpio = None

    def connect(self) -> None:
        """Initialize the PCA9685 over I2C and enable outputs via OE pin."""
        if self._pca is not None:
            return

        try:
            import board
            import busio
            from adafruit_pca9685 import PCA9685
        except ImportError as exc:
            raise HardwareError(
                "PCA9685 dependencies not installed. "
                "Run: pip install adafruit-circuitpython-pca9685"
            ) from exc

        try:
            i2c = busio.I2C(board.SCL, board.SDA)
            self._pca = PCA9685(i2c, address=self.address)
            self._pca.frequency = self.frequency_hz
        except Exception as exc:
            raise HardwareError(
                f"Failed to connect PCA9685 at 0x{self.address:02X}: {exc}"
            ) from exc

        # Enable outputs via OE pin AFTER I2C init
        self._setup_oe()

    def enable_outputs(self) -> None:
        """Drive OE LOW to enable all PWM outputs (active-LOW logic)."""
        if self._gpio is not None and self.oe_gpio is not None:
            self._gpio.output(self.oe_gpio, self._gpio.LOW)

    def disable_outputs(self) -> None:
        """Drive OE HIGH to tri-state all PWM outputs (safe mode)."""
        if self._gpio is not None and self.oe_gpio is not None:
            self._gpio.output(self.oe_gpio, self._gpio.HIGH)

    def set_channel_duty(self, channel: int, duty: float) -> None:
        """Set a channel's duty cycle (0.0 = off, 1.0 = full on)."""
        if self._pca is None:
            self.connect()
        try:
            clamped = max(0.0, min(1.0, duty))
            self._pca.channels[channel].duty_cycle = int(clamped * 65535)
        except Exception as exc:
            raise HardwareError(
                f"Error setting PCA9685 channel {channel} duty: {exc}"
            ) from exc

    def set_channel_pulse_us(self, channel: int, pulse_us: float) -> None:
        """Set a channel's pulse width in microseconds."""
        period_us = 1_000_000.0 / self.frequency_hz
        duty = pulse_us / period_us
        self.set_channel_duty(channel, duty)

    def disable_channel(self, channel: int) -> None:
        """Set a single channel's duty cycle to 0 (off)."""
        self.set_channel_duty(channel, 0.0)

    def close(self) -> None:
        """Disable outputs via OE pin, then deinitialize PCA9685."""
        self._release_oe()
        if self._pca is not None:
            try:
                if hasattr(self._pca, "deinit"):
                    self._pca.deinit()
            except Exception:
                pass
            self._pca = None
