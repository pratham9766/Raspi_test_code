"""Two-axis gimbal: Stepper (X/yaw) + Servo on PCA9685 (Y/pitch)."""
from __future__ import annotations
import sys
import time
import tty
import termios
from dataclasses import dataclass, field
from hardware.stepper import StepperMotor, StepperConfig
from hardware.servo import ServoController, ServoConfig
from hardware.pca9685_driver import PCA9685Driver
from utils.helpers import HardwareError

@dataclass(frozen=True)
class GimbalConfig:
    x_steps_per_degree: float
    y_min_angle: float
    y_max_angle: float
    y_center_angle: float
    sweep_step_deg: float
    sweep_delay_s: float

@dataclass
class Gimbal:
    """Two-axis gimbal controller."""
    stepper: StepperMotor
    servo: ServoController
    config: GimbalConfig
    _y_angle: float = field(default=90.0, init=False)

    def connect(self) -> None:
        """Initialize both X and Y motors."""
        self.stepper.connect()
        self.servo.connect()

    def center(self) -> None:
        """Move Y to center, X is considered center relative to startup."""
        self.move_y(self.config.y_center_angle)

    def move_x(self, degrees: float, clockwise: bool = True) -> None:
        """Rotate the gimbal base (X axis)."""
        self.stepper.rotate_degrees(degrees, clockwise)

    def move_y(self, angle: float) -> None:
        """Tilt the gimbal (Y axis)."""
        clamped = max(self.config.y_min_angle, min(self.config.y_max_angle, angle))
        self.servo.move_to(clamped)
        self._y_angle = clamped

    def move_y_relative(self, delta: float) -> None:
        """Tilt the gimbal relative to its current position."""
        self.move_y(self._y_angle + delta)

    def sweep_x(self, degrees: float = 90.0) -> None:
        """Sweep X axis left and right."""
        self.move_x(degrees, True)
        self.move_x(degrees * 2, False)
        self.move_x(degrees, True)

    def sweep_y(self) -> None:
        """Sweep Y axis full range."""
        self.servo.sweep(self.config.sweep_step_deg, self.config.sweep_delay_s)
        self.center()

    def figure_eight(self) -> None:
        """Demo pattern."""
        self.center()
        self.move_x(45, True)
        self.move_y(135)
        self.move_x(90, False)
        self.move_y(45)
        self.move_x(90, True)
        self.center()

    def square_demo(self) -> None:
        """Draw a square."""
        self.center()
        self.move_x(30, True)
        self.move_y(120)
        self.move_x(60, False)
        self.move_y(60)
        self.move_x(60, True)
        self.center()

    def continuous_scan(self, cycles: int = 3) -> None:
        """Scan left and right continuously."""
        for _ in range(cycles):
            self.sweep_x(45)

    def keyboard_mode(self) -> None:
        """Interactive keyboard control."""
        def _getch() -> str:
            fd = sys.stdin.fileno()
            old = termios.tcgetattr(fd)
            try:
                tty.setraw(fd)
                return sys.stdin.read(1)
            finally:
                termios.tcsetattr(fd, termios.TCSADRAIN, old)

        print("\n\033[1;36m=== Gimbal Keyboard Mode ===\033[0m")
        print("W/S : Pitch Up/Down (Y axis)")
        print("A/D : Yaw Left/Right (X axis)")
        print("C   : Center")
        print("Q   : Quit")
        
        self.center()
        
        while True:
            char = _getch().upper()
            if char == 'Q':
                break
            elif char == 'W':
                self.move_y_relative(5)
            elif char == 'S':
                self.move_y_relative(-5)
            elif char == 'A':
                self.move_x(5, False)
            elif char == 'D':
                self.move_x(5, True)
            elif char == 'C':
                self.center()

    def close(self) -> None:
        """De-energize motors."""
        self.stepper.close()
        self.servo.close()
