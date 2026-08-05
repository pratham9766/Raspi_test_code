"""Servo motor control via PCA9685 PWM driver."""
from __future__ import annotations
import time
from dataclasses import dataclass, field
from hardware.pca9685_driver import PCA9685Driver
from utils.helpers import HardwareError

@dataclass(frozen=True)
class ServoConfig:
    pca9685_channel: int
    min_pulse_us: int
    max_pulse_us: int
    min_angle: int
    max_angle: int
    settle_seconds: float

@dataclass
class ServoController:
    """Control a servo via PCA9685 channel."""
    config: ServoConfig
    driver: PCA9685Driver

    def connect(self) -> None:
        """Initialize PCA9685 driver."""
        self.driver.connect()

    def angle_to_pulse_us(self, angle: float) -> float:
        """Convert angle in degrees to PWM pulse in microseconds."""
        clamped_angle = max(self.config.min_angle, min(self.config.max_angle, angle))
        angle_range = self.config.max_angle - self.config.min_angle
        pulse_range = self.config.max_pulse_us - self.config.min_pulse_us
        return self.config.min_pulse_us + (clamped_angle - self.config.min_angle) * (pulse_range / angle_range)

    def move_to(self, angle: float) -> None:
        """Move servo to specific angle."""
        pulse = self.angle_to_pulse_us(angle)
        self.driver.set_channel_pulse_us(self.config.pca9685_channel, pulse)
        time.sleep(self.config.settle_seconds)

    def center(self) -> None:
        """Move servo to center (90 degrees)."""
        self.move_to((self.config.max_angle - self.config.min_angle) / 2)

    def sweep(self, step_deg: float = 10.0, delay: float = 0.05) -> None:
        """Sweep servo from min to max and back."""
        for angle in range(self.config.min_angle, self.config.max_angle + 1, int(step_deg)):
            self.move_to(angle)
            time.sleep(delay)
        for angle in range(self.config.max_angle, self.config.min_angle - 1, -int(step_deg)):
            self.move_to(angle)
            time.sleep(delay)

    def continuous_sweep(self, cycles: int = 3) -> None:
        """Sweep servo continuously for N cycles."""
        for _ in range(cycles):
            self.sweep()
            
    def close(self) -> None:
        """Disable PWM channel."""
        self.driver.disable_channel(self.config.pca9685_channel)
