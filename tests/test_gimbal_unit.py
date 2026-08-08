"""Unit tests for the Gimbal module — no hardware required.

Run with:
    python -m pytest tests/test_gimbal_unit.py -v
or:
    python tests/test_gimbal_unit.py

All tests use mock objects so no GPIO or I2C hardware is needed.
"""
from __future__ import annotations

import sys
import types
import unittest
from dataclasses import dataclass, field
from typing import Any
from unittest.mock import MagicMock, call, patch


# ── Stub out RPi.GPIO before importing anything from hardware ─────────────────
_mock_gpio = MagicMock()
_mock_gpio.BCM   = 11
_mock_gpio.OUT   = 0
_mock_gpio.HIGH  = 1
_mock_gpio.LOW   = 0
sys.modules.setdefault("RPi",       types.ModuleType("RPi"))
sys.modules.setdefault("RPi.GPIO",  _mock_gpio)

# Stub out board/busio/adafruit libs so we can import hardware.gimbal
for _mod in [
    "board", "busio",
    "adafruit_pca9685",
    "adafruit_bno08x", "adafruit_bno08x.i2c",
]:
    sys.modules.setdefault(_mod, MagicMock())


# ── Now safe to import ────────────────────────────────────────────────────────
from hardware.gimbal import (          # noqa: E402
    GimbalBNO085Config,
    GimbalConfig,
    GimbalOEConfig,
    GimbalSafetyConfig,
    GimbalServoConfig,
    GimbalStepperConfig,
    Gimbal,
    _angle_to_pulse_us,
    _quat_to_euler,
    build_gimbal,
)


# ── Test fixtures ─────────────────────────────────────────────────────────────

def _make_servo_cfg(**overrides) -> GimbalServoConfig:
    defaults = dict(
        channel=0, center_angle=90.0, min_angle=30.0, max_angle=150.0,
        step_angle=5.0, min_pulse_us=500, max_pulse_us=2500, settle_s=0.0,
    )
    defaults.update(overrides)
    return GimbalServoConfig(**defaults)


def _make_oe_cfg(**overrides) -> GimbalOEConfig:
    defaults = dict(oe_gpio=4, active_low=True)
    defaults.update(overrides)
    return GimbalOEConfig(**defaults)


def _make_stepper_cfg(**overrides) -> GimbalStepperConfig:
    defaults = dict(
        motor="28BYJ-48", driver_ic="ULN2003",
        in1_gpio=18, in2_gpio=23, in3_gpio=24, in4_gpio=25,
        sequence="half_step", step_delay_ms=0.0,
        direction_inverted=False, max_relative_steps=500,
    )
    defaults.update(overrides)
    return GimbalStepperConfig(**defaults)


def _make_bno_cfg(**overrides) -> GimbalBNO085Config:
    defaults = dict(
        enabled=True, feedback_enabled=False, refresh_hz=10,
        bno_roll_to_x=False, bno_pitch_to_y=True,
        kp_y=0.3, deadband_deg=2.0, max_servo_correction_deg=10.0,
    )
    defaults.update(overrides)
    return GimbalBNO085Config(**defaults)


def _make_safety_cfg(**overrides) -> GimbalSafetyConfig:
    defaults = dict(require_confirmation=False, disable_outputs_on_exit=True)
    defaults.update(overrides)
    return GimbalSafetyConfig(**defaults)


def _make_gimbal_cfg(**overrides) -> GimbalConfig:
    return GimbalConfig(
        servo=overrides.get("servo", _make_servo_cfg()),
        servo_driver=overrides.get("servo_driver", _make_oe_cfg()),
        stepper=overrides.get("stepper", _make_stepper_cfg()),
        bno085=overrides.get("bno085", _make_bno_cfg()),
        safety=overrides.get("safety", _make_safety_cfg()),
    )


def _make_gimbal_instance(**cfg_overrides) -> Gimbal:
    """Return a Gimbal with mocked driver and stepper."""
    mock_driver  = MagicMock()
    mock_stepper = MagicMock()
    gcfg = _make_gimbal_cfg(**cfg_overrides)
    g = Gimbal(driver=mock_driver, stepper=mock_stepper, config=gcfg)
    # Inject a mock RPi.GPIO reference so OE tests work without real GPIO
    g._oe_gpio_ref = _mock_gpio
    g._initialized = True  # Skip hardware init for unit tests
    return g


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestServoPulseCalculation(unittest.TestCase):
    """Verify angle → pulse_us conversion."""

    def setUp(self):
        self.cfg = _make_servo_cfg(
            min_angle=0, max_angle=180, min_pulse_us=500, max_pulse_us=2500
        )

    def test_center_angle(self):
        pulse = _angle_to_pulse_us(90.0, self.cfg)
        self.assertAlmostEqual(pulse, 1500.0, places=1)

    def test_min_angle(self):
        pulse = _angle_to_pulse_us(0.0, self.cfg)
        self.assertAlmostEqual(pulse, 500.0, places=1)

    def test_max_angle(self):
        pulse = _angle_to_pulse_us(180.0, self.cfg)
        self.assertAlmostEqual(pulse, 2500.0, places=1)

    def test_below_min_clamped(self):
        pulse = _angle_to_pulse_us(-10.0, self.cfg)
        self.assertAlmostEqual(pulse, 500.0, places=1)

    def test_above_max_clamped(self):
        pulse = _angle_to_pulse_us(200.0, self.cfg)
        self.assertAlmostEqual(pulse, 2500.0, places=1)


class TestServoAngleLimits(unittest.TestCase):
    """set_y_angle() must clamp to [min_angle, max_angle]."""

    def setUp(self):
        self.gimbal = _make_gimbal_instance(
            servo=_make_servo_cfg(min_angle=30.0, max_angle=150.0)
        )

    def test_within_range_accepted(self):
        actual = self.gimbal.set_y_angle(90.0)
        self.assertEqual(actual, 90.0)

    def test_below_min_clamped(self):
        actual = self.gimbal.set_y_angle(10.0)
        self.assertEqual(actual, 30.0)

    def test_above_max_clamped(self):
        actual = self.gimbal.set_y_angle(200.0)
        self.assertEqual(actual, 150.0)

    def test_y_angle_property_updated(self):
        self.gimbal.set_y_angle(120.0)
        self.assertAlmostEqual(self.gimbal.y_angle, 120.0)

    def test_center_y_uses_center_angle(self):
        self.gimbal.center_y()
        self.assertAlmostEqual(self.gimbal.y_angle, 90.0)

    def test_move_y_relative(self):
        self.gimbal.set_y_angle(90.0)
        self.gimbal.move_y_relative(+20.0)
        self.assertAlmostEqual(self.gimbal.y_angle, 110.0)


class TestStepperLimits(unittest.TestCase):
    """move_x_steps() must enforce ±max_relative_steps."""

    def setUp(self):
        self.gimbal = _make_gimbal_instance(
            stepper=_make_stepper_cfg(max_relative_steps=500, direction_inverted=False)
        )

    def test_within_limit_accepted(self):
        taken = self.gimbal.move_x_steps(100)
        self.assertEqual(taken, 100)
        self.assertEqual(self.gimbal.relative_x_steps, 100)

    def test_exceeds_positive_limit_rejected(self):
        taken = self.gimbal.move_x_steps(600)
        self.assertEqual(taken, 0)
        self.assertEqual(self.gimbal.relative_x_steps, 0)

    def test_cumulative_limit_enforced(self):
        self.gimbal.move_x_steps(400)
        taken = self.gimbal.move_x_steps(200)   # would reach 600 > 500
        self.assertEqual(taken, 0)
        self.assertEqual(self.gimbal.relative_x_steps, 400)

    def test_negative_steps_accepted(self):
        taken = self.gimbal.move_x_steps(-300)
        self.assertEqual(taken, -300)
        self.assertEqual(self.gimbal.relative_x_steps, -300)

    def test_reset_position(self):
        self.gimbal.move_x_steps(400)
        self.gimbal.reset_x_position()
        self.assertEqual(self.gimbal.relative_x_steps, 0)

    def test_zero_steps_noop(self):
        taken = self.gimbal.move_x_steps(0)
        self.assertEqual(taken, 0)
        self.gimbal.stepper.forward.assert_not_called()
        self.gimbal.stepper.backward.assert_not_called()


class TestStepperDirectionInversion(unittest.TestCase):
    """direction_inverted=True must flip actual motor direction."""

    def _gimbal(self, inverted: bool) -> Gimbal:
        return _make_gimbal_instance(
            stepper=_make_stepper_cfg(direction_inverted=inverted, max_relative_steps=1000)
        )

    def test_not_inverted_positive_calls_forward(self):
        g = self._gimbal(False)
        g.move_x_steps(50)
        g.stepper.forward.assert_called_once_with(50)

    def test_not_inverted_negative_calls_backward(self):
        g = self._gimbal(False)
        g.move_x_steps(-50)
        g.stepper.backward.assert_called_once_with(50)

    def test_inverted_positive_calls_backward(self):
        g = self._gimbal(True)
        g.move_x_steps(50)
        g.stepper.backward.assert_called_once_with(50)

    def test_inverted_negative_calls_forward(self):
        g = self._gimbal(True)
        g.move_x_steps(-50)
        g.stepper.forward.assert_called_once_with(50)

    def test_relative_x_steps_tracks_requested_direction(self):
        """relative_x_steps records the requested value (before inversion)."""
        g = self._gimbal(True)
        g.move_x_steps(+100)
        # actual motor runs backward, but counter tracks the *inverted* actual
        self.assertEqual(g.relative_x_steps, -100)


class TestOEPolarity(unittest.TestCase):
    """OE enable/disable levels depend on active_low setting."""

    def _gimbal(self, active_low: bool) -> Gimbal:
        return _make_gimbal_instance(servo_driver=_make_oe_cfg(oe_gpio=4, active_low=active_low))

    def test_active_low_enable_drives_low(self):
        g = _make_gimbal_instance(servo_driver=_make_oe_cfg(active_low=True))
        g.enable_servo_output()
        _mock_gpio.output.assert_called_with(4, 0)   # LOW = enabled

    def test_active_low_disable_drives_high(self):
        g = _make_gimbal_instance(servo_driver=_make_oe_cfg(active_low=True))
        g.disable_servo_output()
        _mock_gpio.output.assert_called_with(4, 1)   # HIGH = disabled

    def test_active_high_enable_drives_high(self):
        g = _make_gimbal_instance(servo_driver=_make_oe_cfg(active_low=False))
        g.enable_servo_output()
        _mock_gpio.output.assert_called_with(4, 1)   # HIGH = enabled

    def test_active_high_disable_drives_low(self):
        g = _make_gimbal_instance(servo_driver=_make_oe_cfg(active_low=False))
        g.disable_servo_output()
        _mock_gpio.output.assert_called_with(4, 0)   # LOW = disabled


class TestEmergencyStop(unittest.TestCase):
    """emergency_stop() must de-energize stepper and disable OE."""

    def test_stop_called(self):
        g = _make_gimbal_instance()
        g.emergency_stop()
        g.stepper.stop.assert_called()

    def test_oe_disabled_after_estop(self):
        g = _make_gimbal_instance(servo_driver=_make_oe_cfg(active_low=True))
        g._servo_enabled = True
        g.emergency_stop()
        self.assertFalse(g._servo_enabled)

    def test_estop_idempotent(self):
        g = _make_gimbal_instance()
        g.emergency_stop()
        g.emergency_stop()   # should not raise
        g.stepper.stop.assert_called()


class TestCloseIdempotency(unittest.TestCase):
    """close() must be safe to call multiple times."""

    def test_double_close_no_exception(self):
        g = _make_gimbal_instance()
        g.close()
        g.close()   # must not raise

    def test_close_calls_stepper_stop(self):
        g = _make_gimbal_instance()
        g.close()
        g.stepper.stop.assert_called()

    def test_close_disables_output_when_policy_set(self):
        g = _make_gimbal_instance(
            safety=_make_safety_cfg(disable_outputs_on_exit=True),
            servo_driver=_make_oe_cfg(active_low=True),
        )
        g._servo_enabled = True
        g.close()
        self.assertFalse(g._servo_enabled)


class TestQuaternionToEuler(unittest.TestCase):
    """_quat_to_euler() basic sanity checks."""

    def test_identity_quaternion_gives_zero_angles(self):
        roll, pitch, yaw = _quat_to_euler(1.0, 0.0, 0.0, 0.0)
        self.assertAlmostEqual(roll,  0.0, places=5)
        self.assertAlmostEqual(pitch, 0.0, places=5)
        self.assertAlmostEqual(yaw,   0.0, places=5)

    def test_90deg_roll(self):
        import math
        # Quaternion for 90° roll around X axis: w=cos45°, x=sin45°, y=0, z=0
        a = math.pi / 4
        roll, pitch, yaw = _quat_to_euler(math.cos(a), math.sin(a), 0.0, 0.0)
        self.assertAlmostEqual(roll, 90.0, places=4)

    def test_90deg_pitch(self):
        import math
        a = math.pi / 4
        roll, pitch, yaw = _quat_to_euler(math.cos(a), 0.0, math.sin(a), 0.0)
        self.assertAlmostEqual(pitch, 90.0, places=4)


if __name__ == "__main__":
    unittest.main(verbosity=2)
