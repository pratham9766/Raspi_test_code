"""Two-axis gimbal controller: X-axis (28BYJ-48 stepper) + Y-axis (PCA9685 servo ch0).

Safety Design
─────────────
• OE pin starts HIGH (servo outputs DISABLED). Call enable_servo_output() to arm.
• Stepper position is tracked as ``relative_x_steps`` — NOT absolute mechanical position.
  The 28BYJ-48 has no encoder; position tracking is reset to 0 on initialize().
• All moves are range-checked before execution; out-of-range moves are rejected.
• emergency_stop() and close() are idempotent — safe to call multiple times.
• close() is always called in a finally block by test_gimbal.py.

BNO085 Axis-Mapping Assumptions
─────────────────────────────────
The BNO085 quaternion→Euler convention used here:
    Roll  : rotation around the sensor X-axis
    Pitch : rotation around the sensor Y-axis
    Yaw   : rotation around the sensor Z-axis

This mapping depends entirely on how the sensor is physically mounted.
X (stepper) feedback is DISABLED by default (bno_roll_to_x: false).
Y (servo)   feedback uses Pitch → servo correction with deadband + Kp.

Hardware connections (configured in config.yaml → gimbal:):
    X axis — 28BYJ-48 via ULN2003 → IN1-IN4 (GPIO 18,23,24,25)
    Y axis — Servo → PCA9685 channel 0
    OE     — GPIO4, active-LOW by default
"""
from __future__ import annotations

import math
import sys
import time
from dataclasses import dataclass, field
from typing import Any

from hardware.pca9685_driver import PCA9685Driver
from hardware.stepper import HALF_STEP_SEQUENCE, StepperConfig, StepperMotor
from utils.helpers import HardwareError

# ── ANSI colour shortcuts ─────────────────────────────────────────────────────
_C  = "\033[96m"   # cyan
_W  = "\033[97m"   # white
_G  = "\033[92m"   # green
_Y  = "\033[93m"   # yellow
_M  = "\033[95m"   # magenta
_R  = "\033[91m"   # red
_D  = "\033[2m"    # dim
_B  = "\033[1m"    # bold
_N  = "\033[0m"    # reset
_CL = "\033[2J\033[H"  # clear + home
_HI = "\033[?25l"      # hide cursor
_SH = "\033[?25h"      # show cursor

# Full-step sequence (reserved for future use via sequence: full_step)
FULL_STEP_SEQUENCE = [
    [1, 1, 0, 0],
    [0, 1, 1, 0],
    [0, 0, 1, 1],
    [1, 0, 0, 1],
]


# ── Config dataclasses (nested under GimbalConfig) ────────────────────────────

@dataclass(frozen=True)
class GimbalServoConfig:
    """Y-axis servo configuration."""

    channel: int          # PCA9685 channel number
    center_angle: float   # Default / safe-center position (degrees)
    min_angle: float      # Soft lower limit (degrees)
    max_angle: float      # Soft upper limit (degrees)
    step_angle: float     # Increment per keyboard step command
    min_pulse_us: int     # PWM minimum pulse width (µs)
    max_pulse_us: int     # PWM maximum pulse width (µs)
    settle_s: float       # Seconds to wait after commanding a move


@dataclass(frozen=True)
class GimbalOEConfig:
    """Output-enable pin configuration for the PCA9685 servo driver board."""

    oe_gpio: int          # BCM GPIO number wired to the OE/~OE pin
    active_low: bool      # True  → GPIO LOW  = outputs enabled (most boards)
                          # False → GPIO HIGH = outputs enabled


@dataclass(frozen=True)
class GimbalStepperConfig:
    """X-axis 28BYJ-48 stepper configuration."""

    motor: str              # Descriptive label (e.g. "28BYJ-48")
    driver_ic: str          # Descriptive label (e.g. "ULN2003")
    in1_gpio: int
    in2_gpio: int
    in3_gpio: int
    in4_gpio: int
    sequence: str           # "half_step" (default) or "full_step"
    step_delay_ms: float    # Delay between steps — do NOT set below 2 ms
    direction_inverted: bool  # Swap +/- direction without rewiring
    max_relative_steps: int   # Hard limit: |relative_x_steps| never exceeds this


@dataclass(frozen=True)
class GimbalBNO085Config:
    """BNO085 usage parameters for the gimbal."""

    enabled: bool                  # Whether the BNO085 is physically present
    feedback_enabled: bool         # Enable closed-loop orientation correction
    refresh_hz: int                # Monitor / control loop rate
    bno_roll_to_x: bool            # Use BNO Roll  → X stepper correction
                                   #   (DISABLED by default — axis mapping uncertain)
    bno_pitch_to_y: bool           # Use BNO Pitch → Y servo correction
    kp_y: float                    # Proportional gain for Y axis
    deadband_deg: float            # Ignore orientation errors smaller than this
    max_servo_correction_deg: float  # Cap per-loop servo correction magnitude


@dataclass(frozen=True)
class GimbalSafetyConfig:
    """Safety and clean-up policy."""

    require_confirmation: bool    # Ask user to press Enter before any movement
    disable_outputs_on_exit: bool # Always drive OE to disabled state on close()


@dataclass(frozen=True)
class GimbalConfig:
    """Top-level gimbal configuration (loaded from config.yaml → gimbal:)."""

    servo: GimbalServoConfig
    servo_driver: GimbalOEConfig
    stepper: GimbalStepperConfig
    bno085: GimbalBNO085Config
    safety: GimbalSafetyConfig


# ── Internal helpers ──────────────────────────────────────────────────────────

def _quat_to_euler(
    w: float, x: float, y: float, z: float
) -> tuple[float, float, float]:
    """Convert quaternion (w, x, y, z) to (roll, pitch, yaw) in degrees.

    Uses ZYX Tait-Bryan convention consistent with most AHRS firmware.
    """
    roll  = math.degrees(math.atan2(2 * (w * x + y * z), 1 - 2 * (x * x + y * y)))
    sinp  = 2 * (w * y - z * x)
    pitch = math.degrees(
        math.copysign(math.pi / 2, sinp) if abs(sinp) >= 1 else math.asin(sinp)
    )
    yaw   = math.degrees(math.atan2(2 * (w * z + x * y), 1 - 2 * (y * y + z * z)))
    return roll, pitch, yaw


def _angle_to_pulse_us(angle: float, cfg: GimbalServoConfig) -> float:
    """Convert angle (degrees) to PWM pulse width (µs)."""
    clamped    = max(cfg.min_angle, min(cfg.max_angle, angle))
    span_angle = cfg.max_angle - cfg.min_angle
    span_pulse = cfg.max_pulse_us - cfg.min_pulse_us
    return cfg.min_pulse_us + (clamped - cfg.min_angle) / span_angle * span_pulse


def _bar(value: float, lo: float, hi: float,
         width: int = 20, color: str = _C) -> str:
    """Return a fixed-width ASCII progress bar."""
    denom = hi - lo
    ratio  = max(0.0, min(1.0, (value - lo) / denom if denom else 0.0))
    filled = round(ratio * width)
    return f"{color}{'█' * filled}{'░' * (width - filled)}{_N}"


def _build_stepper_from_gimbal_cfg(gcfg: GimbalStepperConfig) -> StepperMotor:
    """Create a StepperMotor instance from GimbalStepperConfig."""
    sc = StepperConfig(
        in1_gpio=gcfg.in1_gpio,
        in2_gpio=gcfg.in2_gpio,
        in3_gpio=gcfg.in3_gpio,
        in4_gpio=gcfg.in4_gpio,
        step_delay_ms=gcfg.step_delay_ms,
        steps_per_revolution=4096,   # 28BYJ-48 in half-step mode
    )
    return StepperMotor(config=sc)


# ── Main Gimbal class ─────────────────────────────────────────────────────────

@dataclass
class Gimbal:
    """Two-axis gimbal: X = stepper (28BYJ-48), Y = servo (PCA9685 ch0).

    Lifecycle
    ─────────
    1. Construct with driver + stepper + config (no hardware access yet).
    2. Call initialize(logger) — connects hardware, OE starts DISABLED.
    3. Call enable_servo_output() when ready to move the Y servo.
    4. Use set_y_angle(), move_x_steps(), center_y(), etc.
    5. Call close() when done (or on any exception).

    The close() and emergency_stop() methods are idempotent.
    """

    driver:  PCA9685Driver   # Must be created with oe_gpio=None — OE is managed here
    stepper: StepperMotor    # Existing stepper driver (reused, not duplicated)
    config:  GimbalConfig

    # ── internal state ────────────────────────────────────────────────────────
    _y_angle: float         = field(default=None, init=False, repr=False)  # type: ignore[assignment]
    _relative_x_steps: int  = field(default=0,    init=False, repr=False)
    _servo_enabled: bool    = field(default=False, init=False, repr=False)
    _oe_gpio_ref: Any       = field(default=None,  init=False, repr=False)
    _initialized: bool      = field(default=False, init=False, repr=False)
    _closed: bool           = field(default=False, init=False, repr=False)

    def __post_init__(self) -> None:
        self._y_angle = self.config.servo.center_angle

    # ── OE pin management ─────────────────────────────────────────────────────

    def _oe_level(self, enable: bool) -> int:
        """Return the GPIO level (0 or 1) that achieves the requested state."""
        if self.config.servo_driver.active_low:
            return 0 if enable else 1   # active-LOW: 0=enable, 1=disable
        else:
            return 1 if enable else 0   # active-HIGH: 1=enable, 0=disable

    def _init_oe_pin(self) -> None:
        """Set up OE GPIO as output, starting in DISABLED state."""
        oe = self.config.servo_driver.oe_gpio
        try:
            import RPi.GPIO as GPIO  # type: ignore
            GPIO.setmode(GPIO.BCM)
            GPIO.setwarnings(False)
            GPIO.setup(oe, GPIO.OUT)
            GPIO.output(oe, self._oe_level(False))   # DISABLED at start
            self._oe_gpio_ref = GPIO
        except ImportError as exc:
            raise HardwareError(
                "RPi.GPIO is required for the OE pin. "
                "Run: pip install RPi.GPIO"
            ) from exc
        except Exception as exc:
            raise HardwareError(
                f"Failed to configure OE pin GPIO{oe}: {exc}"
            ) from exc

    def enable_servo_output(self) -> None:
        """Drive OE to the ENABLED state — servo pulses will now reach the motor.

        Must be called explicitly after initialize().
        """
        if self._oe_gpio_ref is None:
            return
        self._oe_gpio_ref.output(
            self.config.servo_driver.oe_gpio,
            self._oe_level(True)
        )
        self._servo_enabled = True

    def disable_servo_output(self) -> None:
        """Drive OE to the DISABLED state — all servo channels go high-impedance."""
        if self._oe_gpio_ref is None:
            return
        try:
            self._oe_gpio_ref.output(
                self.config.servo_driver.oe_gpio,
                self._oe_level(False)
            )
        except Exception:
            pass
        self._servo_enabled = False

    # ── Initialization ────────────────────────────────────────────────────────

    def initialize(self, logger: Any = None) -> None:
        """Connect all hardware. OE is left DISABLED until enable_servo_output().

        This method is idempotent — calling it twice has no effect.
        """
        if self._initialized:
            return

        def _log(msg: str) -> None:
            if logger:
                logger.info(msg)

        _log("Initializing gimbal")

        # 1. OE pin — start DISABLED
        self._init_oe_pin()
        pol = "active-LOW" if self.config.servo_driver.active_low else "active-HIGH"
        _log(
            f"OE GPIO{self.config.servo_driver.oe_gpio} ({pol}) — "
            f"servo output DISABLED (safe start)"
        )

        # 2. PCA9685 (driver created with oe_gpio=None so driver doesn't manage OE)
        self.driver.connect()
        _log(f"PCA9685 detected at 0x{self.driver.address:02X}, "
             f"{self.driver.frequency_hz} Hz")
        _log(f"Servo Y-axis: PCA9685 channel {self.config.servo.channel}")

        # 3. Stepper
        self.stepper.connect()
        scfg = self.config.stepper
        _log(
            f"Stepper X-axis ({scfg.motor} via {scfg.driver_ic}): "
            f"GPIO {scfg.in1_gpio},{scfg.in2_gpio},{scfg.in3_gpio},{scfg.in4_gpio}"
        )
        _log(
            f"Sequence: {scfg.sequence}, "
            f"delay: {scfg.step_delay_ms} ms, "
            f"max: ±{scfg.max_relative_steps} steps"
        )

        # 4. Summary
        sv = self.config.servo
        _log(
            f"Servo safe range: {sv.min_angle}°–{sv.max_angle}°, "
            f"center: {sv.center_angle}°"
        )
        _log("Gimbal ready — call enable_servo_output() before moving Y axis")

        self._initialized = True

    # ── Y axis (servo) ────────────────────────────────────────────────────────

    def _raw_send_y(self, angle: float) -> None:
        """Send PWM pulse to servo without warnings or guards. Internal only."""
        pulse = _angle_to_pulse_us(angle, self.config.servo)
        self.driver.set_channel_pulse_us(self.config.servo.channel, pulse)
        self._y_angle = angle
        time.sleep(self.config.servo.settle_s)

    def set_y_angle(self, angle: float) -> float:
        """Command Y servo to an absolute angle, enforcing configured limits.

        Out-of-range angles are clamped with a warning printed.
        Returns the actual angle commanded.
        """
        sv = self.config.servo
        if angle < sv.min_angle or angle > sv.max_angle:
            print(
                f"{_Y}[WARN]{_N} Y angle {angle:.1f}° outside safe range "
                f"[{sv.min_angle}°–{sv.max_angle}°]. Clamping."
            )
        clamped = max(sv.min_angle, min(sv.max_angle, angle))
        self._raw_send_y(clamped)
        return clamped

    def center_y(self) -> None:
        """Move Y servo to the configured center angle."""
        self._raw_send_y(self.config.servo.center_angle)

    def move_y_relative(self, delta_deg: float) -> float:
        """Move Y servo by delta degrees from the current position."""
        return self.set_y_angle(self._y_angle + delta_deg)

    # ── X axis (stepper) ──────────────────────────────────────────────────────

    def move_x_steps(self, steps: int) -> int:
        """Move X stepper by N steps (+/- for direction).

        Direction inversion is applied transparently.
        Returns the number of steps actually taken (0 if limit would be exceeded).
        """
        scfg = self.config.stepper
        actual = -steps if scfg.direction_inverted else steps
        projected = self._relative_x_steps + actual

        if abs(projected) > scfg.max_relative_steps:
            print(
                f"{_Y}[WARN]{_N} Move of {actual:+d} steps rejected — "
                f"would exceed ±{scfg.max_relative_steps} limit "
                f"(current relative position: {self._relative_x_steps:+d})"
            )
            return 0

        if actual > 0:
            self.stepper.forward(actual)
        elif actual < 0:
            self.stepper.backward(abs(actual))

        self._relative_x_steps = projected
        return actual

    def reset_x_position(self) -> None:
        """Reset the relative X step counter to 0 WITHOUT moving the motor.

        Use after manually repositioning the gimbal to a known reference.
        """
        self._relative_x_steps = 0

    @property
    def relative_x_steps(self) -> int:
        """Current X position as a software-relative step count.

        ⚠ This is NOT an absolute mechanical angle. The 28BYJ-48 has no
        absolute position feedback. This counter resets to 0 on initialize().
        """
        return self._relative_x_steps

    @property
    def y_angle(self) -> float:
        """Current Y servo angle in degrees."""
        return self._y_angle

    # ── Stop / Emergency ──────────────────────────────────────────────────────

    def stop(self) -> None:
        """Stop the stepper immediately. Servo holds its current position."""
        try:
            self.stepper.stop()
        except Exception:
            pass

    def emergency_stop(self, logger: Any = None) -> None:
        """Full emergency stop — idempotent and safe to call at any time.

        Actions (in order):
        1. De-energize all stepper coils (set IN1-IN4 LOW)
        2. Disable servo output via OE pin
        """
        def _log(msg: str) -> None:
            if logger:
                logger.warning(msg)
            else:
                print(f"{_R}{_B}[E-STOP]{_N} {msg}")

        _log("EMERGENCY STOP activated")

        try:
            self.stepper.stop()
            _log("Stepper coils de-energized")
        except Exception as exc:
            _log(f"Stepper stop error (continuing): {exc}")

        try:
            self.disable_servo_output()
            _log("Servo output DISABLED via OE")
        except Exception as exc:
            _log(f"OE disable error (continuing): {exc}")

    # ── Cleanup ────────────────────────────────────────────────────────────────

    def close(self, logger: Any = None) -> None:
        """Release all hardware resources. Safe to call multiple times."""
        if self._closed:
            return
        self._closed = True

        def _log(msg: str) -> None:
            if logger:
                logger.info(msg)

        # Stop stepper, de-energize coils
        try:
            self.stepper.stop()
        except Exception:
            pass

        # Clean up stepper GPIO
        try:
            self.stepper.close()
            _log("Stepper GPIO released")
        except Exception:
            pass

        # Disable servo output
        if self.config.safety.disable_outputs_on_exit:
            try:
                self.disable_servo_output()
                _log("Servo output disabled")
            except Exception:
                pass

        # Disable PCA9685 servo channel
        try:
            self.driver.disable_channel(self.config.servo.channel)
        except Exception:
            pass

        # Deinitialise PCA9685 chip (driver has oe_gpio=None so won't touch OE)
        try:
            self.driver.close()
            _log("PCA9685 released")
        except Exception:
            pass

        # Clean up OE GPIO
        try:
            if self._oe_gpio_ref is not None:
                self._oe_gpio_ref.cleanup(self.config.servo_driver.oe_gpio)
                self._oe_gpio_ref = None
                _log(f"OE GPIO{self.config.servo_driver.oe_gpio} released")
        except Exception:
            pass


# ── Factory function ──────────────────────────────────────────────────────────

def build_gimbal(config: Any) -> Gimbal:
    """Build a Gimbal from AppConfig.

    The PCA9685Driver is constructed with oe_gpio=None so that the driver
    does NOT touch the OE pin — the Gimbal manages it exclusively.

    Args:
        config: AppConfig instance (from config.py).

    Returns:
        Uninitialised Gimbal ready for initialize().
    """
    gcfg = config.gimbal

    # PCA9685 driver — oe_gpio=None so driver never touches OE
    pca_driver = PCA9685Driver(
        address=config.pca9685.address,
        frequency_hz=config.pca9685.frequency_hz,
        oe_gpio=None,
    )

    # Stepper — built from GimbalStepperConfig, reusing existing StepperMotor
    stepper = _build_stepper_from_gimbal_cfg(gcfg.stepper)

    return Gimbal(driver=pca_driver, stepper=stepper, config=gcfg)
