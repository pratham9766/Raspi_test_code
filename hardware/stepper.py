"""28BYJ-48 stepper motor driver via ULN2003."""
from __future__ import annotations
import time
from dataclasses import dataclass, field
from typing import Any
from utils.helpers import HardwareError

HALF_STEP_SEQUENCE = [
    [1,0,0,0],
    [1,1,0,0],
    [0,1,0,0],
    [0,1,1,0],
    [0,0,1,0],
    [0,0,1,1],
    [0,0,0,1],
    [1,0,0,1],
]

@dataclass(frozen=True)
class StepperConfig:
    in1_gpio: int
    in2_gpio: int
    in3_gpio: int
    in4_gpio: int
    step_delay_ms: float
    steps_per_revolution: int

@dataclass
class StepperMotor:
    """Control a 28BYJ-48 stepper motor via ULN2003."""
    config: StepperConfig
    _pins: list[Any] = field(default_factory=list, init=False, repr=False)
    _step_index: int = field(default=0, init=False, repr=False)
    _gpio: Any = field(default=None, init=False, repr=False)

    def connect(self) -> None:
        """Initialize GPIO pins for stepper."""
        if self._pins:
            return
        try:
            import RPi.GPIO as GPIO
            self._gpio = GPIO
            GPIO.setmode(GPIO.BCM)
            GPIO.setwarnings(False)
            
            pins = [
                self.config.in1_gpio,
                self.config.in2_gpio,
                self.config.in3_gpio,
                self.config.in4_gpio
            ]
            
            for pin in pins:
                GPIO.setup(pin, GPIO.OUT)
                GPIO.output(pin, 0)
                
            self._pins = pins
        except ImportError as exc:
            raise HardwareError("RPi.GPIO not installed.") from exc
        except Exception as exc:
            raise HardwareError(f"Failed to setup stepper GPIO: {exc}") from exc

    def _step(self, direction: int = 1) -> None:
        """Advance motor one half-step."""
        if not self._pins:
            self.connect()
            
        self._step_index = (self._step_index + direction) % len(HALF_STEP_SEQUENCE)
        seq = HALF_STEP_SEQUENCE[self._step_index]
        
        for pin, val in zip(self._pins, seq):
            self._gpio.output(pin, val)
            
        time.sleep(self.config.step_delay_ms / 1000.0)

    def forward(self, steps: int) -> None:
        """Step forward by N steps."""
        for _ in range(steps):
            self._step(1)
        self.stop()

    def backward(self, steps: int) -> None:
        """Step backward by N steps."""
        for _ in range(steps):
            self._step(-1)
        self.stop()

    def rotate_degrees(self, degrees: float, clockwise: bool = True) -> None:
        """Rotate by the given number of degrees."""
        steps = int(abs(degrees) / 360.0 * self.config.steps_per_revolution)
        if clockwise:
            self.forward(steps)
        else:
            self.backward(steps)

    def stop(self) -> None:
        """De-energize all coils."""
        if self._pins and self._gpio:
            for pin in self._pins:
                self._gpio.output(pin, 0)

    def close(self) -> None:
        """Release GPIO."""
        self.stop()
        if self._pins and self._gpio:
            self._gpio.cleanup(self._pins)
            self._pins = []
