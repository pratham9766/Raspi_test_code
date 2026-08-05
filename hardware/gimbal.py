"""Two-axis gimbal: Servo X (ch0/yaw) + Servo Y (ch1/pitch) via PCA9685.

Both axes are controlled by servos on PCA9685 channels 0 and 1.
Supports manual control, BNO085-driven stabilisation, and keyboard mode.

Stabilisation mode:
    - Reads Roll  from BNO085 → maps to X servo (channel 0, yaw)
    - Reads Pitch from BNO085 → maps to Y servo (channel 1, pitch)
    - Runs continuously until Ctrl+C

Angle mapping (both axes 0..180 deg servo range):
    Roll  -90..+90  →  servo 0..180  (centre = 90)
    Pitch -90..+90  →  servo 0..180  (centre = 90)
"""

from __future__ import annotations

import math
import sys
import time
import tty
import termios
from dataclasses import dataclass, field

from hardware.pca9685_driver import PCA9685Driver
from hardware.servo import ServoConfig, ServoController
from utils.helpers import HardwareError

# ── ANSI ─────────────────────────────────────────────────────────────────────
_CYAN    = "\033[96m"
_WHITE   = "\033[97m"
_GREEN   = "\033[92m"
_YELLOW  = "\033[93m"
_MAGENTA = "\033[95m"
_DIM     = "\033[2m"
_BOLD    = "\033[1m"
_RESET   = "\033[0m"
_CLEAR   = "\033[2J\033[H"
_HIDE    = "\033[?25l"
_SHOW    = "\033[?25h"


@dataclass(frozen=True)
class GimbalConfig:
    """Configuration for the dual-servo BNO085-driven gimbal."""

    x_channel: int           # PCA9685 channel for X axis (yaw)   — default 0
    y_channel: int           # PCA9685 channel for Y axis (pitch)  — default 1
    min_angle: float         # minimum servo angle in degrees
    max_angle: float         # maximum servo angle in degrees
    center_angle: float      # neutral/center position
    sweep_step_deg: float    # step size for sweep operations
    sweep_delay_s: float     # delay between sweep steps
    min_pulse_us: int        # minimum PWM pulse width (µs)
    max_pulse_us: int        # maximum PWM pulse width (µs)
    settle_seconds: float    # time to wait after each move


def _quat_to_euler(
    w: float, x: float, y: float, z: float
) -> tuple[float, float, float]:
    """Convert quaternion (w, x, y, z) to (roll, pitch, yaw) in degrees."""
    roll  = math.degrees(math.atan2(2 * (w * x + y * z), 1 - 2 * (x * x + y * y)))
    sinp  = 2 * (w * y - z * x)
    pitch = math.degrees(
        math.copysign(math.pi / 2, sinp) if abs(sinp) >= 1 else math.asin(sinp)
    )
    yaw   = math.degrees(math.atan2(2 * (w * z + x * y), 1 - 2 * (y * y + z * z)))
    return roll, pitch, yaw


def _map_angle(value: float, in_min: float, in_max: float,
               out_min: float, out_max: float) -> float:
    """Linearly map value from one range to another, clamped."""
    ratio = (value - in_min) / (in_max - in_min)
    return out_min + max(0.0, min(1.0, ratio)) * (out_max - out_min)


def _bar(value: float, lo: float, hi: float, width: int = 20,
         color: str = _CYAN) -> str:
    """ASCII progress bar."""
    ratio  = max(0.0, min(1.0, (value - lo) / (hi - lo)))
    filled = round(ratio * width)
    return f"{color}{'█' * filled}{'░' * (width - filled)}{_RESET}"


@dataclass
class Gimbal:
    """Two-axis gimbal: X servo (yaw, ch0) + Y servo (pitch, ch1) via PCA9685.

    Both servos share the same PCA9685 driver instance.
    X axis = channel 0  (yaw)
    Y axis = channel 1  (pitch)
    """

    driver: PCA9685Driver
    config: GimbalConfig
    _x_angle: float = field(default=None, init=False, repr=False)  # type: ignore[assignment]
    _y_angle: float = field(default=None, init=False, repr=False)  # type: ignore[assignment]

    def __post_init__(self) -> None:
        self._x_angle = self.config.center_angle
        self._y_angle = self.config.center_angle

    # ── Internal helpers ─────────────────────────────────────────────────────

    def _angle_to_pulse(self, angle: float) -> float:
        """Convert angle (degrees) to PWM pulse width (µs)."""
        clamped = max(self.config.min_angle, min(self.config.max_angle, angle))
        span    = self.config.max_angle - self.config.min_angle
        pulse   = self.config.min_pulse_us + (
            (clamped - self.config.min_angle) / span
        ) * (self.config.max_pulse_us - self.config.min_pulse_us)
        return pulse

    def _set_x(self, angle: float) -> None:
        """Send angle to X servo (channel 0)."""
        clamped = max(self.config.min_angle, min(self.config.max_angle, angle))
        self.driver.set_channel_pulse_us(self.config.x_channel, self._angle_to_pulse(clamped))
        self._x_angle = clamped

    def _set_y(self, angle: float) -> None:
        """Send angle to Y servo (channel 1)."""
        clamped = max(self.config.min_angle, min(self.config.max_angle, angle))
        self.driver.set_channel_pulse_us(self.config.y_channel, self._angle_to_pulse(clamped))
        self._y_angle = clamped

    # ── Public API ───────────────────────────────────────────────────────────

    def connect(self) -> None:
        """Initialize PCA9685 driver."""
        self.driver.connect()

    def center(self) -> None:
        """Move both axes to center position."""
        self._set_x(self.config.center_angle)
        self._set_y(self.config.center_angle)
        time.sleep(self.config.settle_seconds)

    def move_x(self, angle: float) -> None:
        """Move X axis (yaw) to an absolute angle (0–180°)."""
        self._set_x(angle)
        time.sleep(self.config.settle_seconds)

    def move_y(self, angle: float) -> None:
        """Move Y axis (pitch) to an absolute angle (0–180°)."""
        self._set_y(angle)
        time.sleep(self.config.settle_seconds)

    def move_x_relative(self, delta: float) -> None:
        """Move X axis relative to current position."""
        self.move_x(self._x_angle + delta)

    def move_y_relative(self, delta: float) -> None:
        """Move Y axis relative to current position."""
        self.move_y(self._y_angle + delta)

    def sweep_x(self) -> None:
        """Sweep X axis from min to max and back."""
        step  = self.config.sweep_step_deg
        delay = self.config.sweep_delay_s
        angle = self.config.min_angle
        while angle <= self.config.max_angle:
            self._set_x(angle)
            time.sleep(delay)
            angle += step
        while angle >= self.config.min_angle:
            self._set_x(angle)
            time.sleep(delay)
            angle -= step
        self.center()

    def sweep_y(self) -> None:
        """Sweep Y axis from min to max and back."""
        step  = self.config.sweep_step_deg
        delay = self.config.sweep_delay_s
        angle = self.config.min_angle
        while angle <= self.config.max_angle:
            self._set_y(angle)
            time.sleep(delay)
            angle += step
        while angle >= self.config.min_angle:
            self._set_y(angle)
            time.sleep(delay)
            angle -= step
        self.center()

    def figure_eight(self) -> None:
        """Figure-8 demo pattern across both axes."""
        self.center()
        waypoints = [
            (135, 90), (90, 135), (45, 90), (90, 45),
            (135, 90), (90, 90),
        ]
        for x_ang, y_ang in waypoints:
            self._set_x(x_ang)
            self._set_y(y_ang)
            time.sleep(self.config.sweep_delay_s * 3)
        self.center()

    def square_demo(self) -> None:
        """Square corner demo pattern."""
        self.center()
        corners = [(60, 60), (120, 60), (120, 120), (60, 120), (90, 90)]
        for x_ang, y_ang in corners:
            self._set_x(x_ang)
            self._set_y(y_ang)
            time.sleep(0.4)
        self.center()

    def continuous_scan(self, cycles: int = 3) -> None:
        """Sweep X axis back and forth for N cycles."""
        for _ in range(cycles):
            self.sweep_x()

    # ── BNO085 Stabilisation Mode ────────────────────────────────────────────

    def stabilise(self, imu_sensor: object, loop_hz: int = 20) -> None:
        """Continuously drive gimbal to counteract IMU-measured roll/pitch.

        Reads BNO085 quaternion, converts to Roll/Pitch, and maps:
            Roll  (-90°..+90°) → X servo  (0°..180°, centre=90°)
            Pitch (-90°..+90°) → Y servo  (0°..180°, centre=90°)

        This creates a stabilisation effect — the gimbal compensates for
        platform movement to keep the payload level.

        Press Ctrl+C to exit.

        Args:
            imu_sensor: Connected BNO085Sensor instance.
            loop_hz:    Control loop update rate in Hz.
        """
        interval = 1.0 / loop_hz
        print(_HIDE, end="", flush=True)
        try:
            while True:
                reading = imu_sensor.read()

                roll_deg  = 0.0
                pitch_deg = 0.0

                if reading.quaternion:
                    w, x, y, z = reading.quaternion
                    roll_deg, pitch_deg, _ = _quat_to_euler(w, x, y, z)

                # Map ±90° IMU range → 0–180° servo range
                x_angle = _map_angle(roll_deg,  -90, 90, self.config.min_angle, self.config.max_angle)
                y_angle = _map_angle(pitch_deg, -90, 90, self.config.min_angle, self.config.max_angle)

                self._set_x(x_angle)
                self._set_y(y_angle)

                # Terminal display
                cal = reading.calibration_status or 0
                cal_color = _GREEN if cal >= 3 else _YELLOW
                print(
                    _CLEAR
                    + f"{_BOLD}{_MAGENTA}╔══════════════════════════════════════════════╗{_RESET}\n"
                    + f"{_BOLD}{_MAGENTA}║       BNO085 Gimbal Stabiliser  (Live)       ║{_RESET}\n"
                    + f"{_BOLD}{_MAGENTA}╚══════════════════════════════════════════════╝{_RESET}\n"
                    + f"  {_DIM}Ctrl+C to stop   Loop: {loop_hz} Hz{_RESET}\n\n"
                    + f"  {_BOLD}{_CYAN}IMU Roll{_RESET}   {_WHITE}{roll_deg:+7.2f}°{_RESET}  "
                    + f"{_bar(roll_deg, -90, 90, 22, _CYAN)}\n"
                    + f"  {_BOLD}{_YELLOW}IMU Pitch{_RESET}  {_WHITE}{pitch_deg:+7.2f}°{_RESET}  "
                    + f"{_bar(pitch_deg, -90, 90, 22, _YELLOW)}\n\n"
                    + f"  {_BOLD}X Servo (ch{self.config.x_channel}){_RESET}  "
                    + f"{_WHITE}{x_angle:6.1f}°{_RESET}  "
                    + f"{_bar(x_angle, self.config.min_angle, self.config.max_angle, 22, _MAGENTA)}\n"
                    + f"  {_BOLD}Y Servo (ch{self.config.y_channel}){_RESET}  "
                    + f"{_WHITE}{y_angle:6.1f}°{_RESET}  "
                    + f"{_bar(y_angle, self.config.min_angle, self.config.max_angle, 22, _GREEN)}\n\n"
                    + f"  Calibration  {cal_color}{'●' * cal}{'○' * (4 - cal)}{_RESET}  {_DIM}({cal}/4){_RESET}\n",
                    end="", flush=True,
                )
                time.sleep(interval)

        except KeyboardInterrupt:
            pass
        finally:
            print(_SHOW, end="", flush=True)

    # ── Follow Mode (gimbal follows IMU orientation) ─────────────────────────

    def follow(self, imu_sensor: object, loop_hz: int = 20) -> None:
        """Gimbal follows the IMU orientation (instead of compensating for it).

        Same as stabilise() but angles are NOT inverted — the gimbal points
        in the same direction the IMU is tilted.

        Press Ctrl+C to exit.
        """
        interval = 1.0 / loop_hz
        print(_HIDE, end="", flush=True)
        try:
            while True:
                reading = imu_sensor.read()
                roll_deg = pitch_deg = 0.0
                if reading.quaternion:
                    w, x, y, z = reading.quaternion
                    roll_deg, pitch_deg, _ = _quat_to_euler(w, x, y, z)

                x_angle = _map_angle(roll_deg,  -90, 90, self.config.min_angle, self.config.max_angle)
                y_angle = _map_angle(pitch_deg, -90, 90, self.config.min_angle, self.config.max_angle)

                self._set_x(x_angle)
                self._set_y(y_angle)
                time.sleep(interval)
        except KeyboardInterrupt:
            pass
        finally:
            print(_SHOW, end="", flush=True)

    # ── Keyboard Mode ────────────────────────────────────────────────────────

    def keyboard_mode(self) -> None:
        """Interactive keyboard control of both axes.

        Controls:
            W / S  → Y axis up / down
            A / D  → X axis left / right
            C      → Center both axes
            Q      → Quit
        """
        def _getch() -> str:
            fd  = sys.stdin.fileno()
            old = termios.tcgetattr(fd)
            try:
                tty.setraw(fd)
                return sys.stdin.read(1)
            finally:
                termios.tcsetattr(fd, termios.TCSADRAIN, old)

        print(f"\n{_BOLD}{_CYAN}=== Gimbal Keyboard Mode ==={_RESET}")
        print(f"  {_WHITE}W{_RESET} / {_WHITE}S{_RESET}  — Y axis  Up / Down  (pitch, ch{self.config.y_channel})")
        print(f"  {_WHITE}A{_RESET} / {_WHITE}D{_RESET}  — X axis  Left / Right (yaw, ch{self.config.x_channel})")
        print(f"  {_WHITE}C{_RESET}      — Center both axes")
        print(f"  {_WHITE}Q{_RESET}      — Quit")
        print(f"\n  X={self._x_angle:.1f}°  Y={self._y_angle:.1f}°\n")

        self.center()

        while True:
            char = _getch().upper()
            if char == "Q":
                break
            elif char == "W":
                self.move_y_relative(+self.config.sweep_step_deg)
            elif char == "S":
                self.move_y_relative(-self.config.sweep_step_deg)
            elif char == "A":
                self.move_x_relative(-self.config.sweep_step_deg)
            elif char == "D":
                self.move_x_relative(+self.config.sweep_step_deg)
            elif char == "C":
                self.center()
            # Live angle readout after each keypress
            print(f"\r  X={self._x_angle:6.1f}°  Y={self._y_angle:6.1f}°   ", end="", flush=True)

        print()

    def close(self) -> None:
        """Disable both servo channels."""
        try:
            self.driver.disable_channel(self.config.x_channel)
            self.driver.disable_channel(self.config.y_channel)
        except Exception:
            pass
        self.driver.close()
