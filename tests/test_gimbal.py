"""Gimbal test module — 2-axis (stepper X + servo Y) with BNO085 integration.

Menu
────
1. Center Gimbal
2. Test Y Axis Servo
3. Test X Axis Stepper
4. Manual Gimbal Control  (keyboard: W/S/A/D/C/X/Q)
5. Run X-Y Movement Pattern
6. BNO085 Orientation Monitor
7. BNO085 Assisted Gimbal Test
8. Emergency Stop
0. Exit

Safety
──────
• No movement happens on module import.
• No movement happens immediately after selecting "Test Gimbal" in the main menu.
• quick_check() initialises hardware but does NOT move any motors.
• Every movement sub-menu warns the user and (if require_confirmation=true) waits
  for an explicit Enter press before any motor command is sent.
• Ctrl+C at any point calls emergency_stop() + close() before returning.
"""
from __future__ import annotations

import math
import sys
import time
import tty
import termios
from typing import Any

from config import AppConfig
from hardware.bno085 import BNO085Sensor
from hardware.gimbal import (
    Gimbal,
    GimbalConfig,
    _quat_to_euler,
    _bar,
    build_gimbal,
)
from utils.helpers import HardwareError
from utils.logger import ToolkitLogger

# ── ANSI ─────────────────────────────────────────────────────────────────────
_C  = "\033[96m"
_W  = "\033[97m"
_G  = "\033[92m"
_Y  = "\033[93m"
_M  = "\033[95m"
_R  = "\033[91m"
_D  = "\033[2m"
_B  = "\033[1m"
_N  = "\033[0m"
_CL = "\033[2J\033[H"
_HI = "\033[?25l"
_SH = "\033[?25h"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _confirm(prompt: str, config: AppConfig) -> bool:
    """If require_confirmation is set, ask the user to confirm before proceeding."""
    if not config.gimbal.safety.require_confirmation:
        return True
    ans = input(f"  {_Y}{prompt} [Enter to continue, q to cancel]{_N}: ").strip().lower()
    return ans != "q"


def _getch() -> str:
    """Read a single raw keypress without echoing (Linux / Pi OS)."""
    fd  = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        return sys.stdin.read(1)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


def _status_line(gimbal: Gimbal) -> str:
    """Return a compact status string."""
    return (
        f"  Relative X: {_C}{gimbal.relative_x_steps:+d} steps{_N}  "
        f"Y angle: {_Y}{gimbal.y_angle:.1f}°{_N}"
    )


def _warn_movement(gcfg: GimbalConfig) -> None:
    """Print a pre-movement safety reminder."""
    sv = gcfg.servo
    st = gcfg.stepper
    print(f"\n  {_Y}⚠ Pre-movement check{_N}")
    print(f"  Y servo safe range : {sv.min_angle}°–{sv.max_angle}°  center: {sv.center_angle}°")
    print(f"  X stepper limit    : ±{st.max_relative_steps} relative steps")
    print(f"  Step delay         : {st.step_delay_ms} ms  (direction_inverted: {st.direction_inverted})")
    print(f"  Servo OE GPIO      : {gcfg.servo_driver.oe_gpio}  active_low: {gcfg.servo_driver.active_low}")


# ── Sub-menus ─────────────────────────────────────────────────────────────────

def _menu_center(gimbal: Gimbal, logger: ToolkitLogger, config: AppConfig) -> None:
    """1. Center Gimbal — move Y to center_angle, show X relative position."""
    _warn_movement(config.gimbal)
    if not _confirm("Center gimbal now?", config):
        return
    print(f"\n  Moving Y servo to {config.gimbal.servo.center_angle}° …")
    gimbal.center_y()
    logger.success(f"Y servo centered at {gimbal.y_angle:.1f}°")
    print(_status_line(gimbal))


def _menu_test_y(gimbal: Gimbal, logger: ToolkitLogger, config: AppConfig) -> None:
    """2. Test Y Axis Servo — slow sweep through a set of configurable angles."""
    sv = config.gimbal.servo
    _warn_movement(config.gimbal)
    print(f"\n  Y servo test angles (center → +step → center → -step → center):")
    test_angles = [
        sv.center_angle,
        sv.center_angle + sv.step_angle * 2,
        sv.center_angle,
        sv.center_angle - sv.step_angle * 2,
        sv.center_angle,
    ]
    print(f"  Sequence: {[f'{a:.0f}°' for a in test_angles]}")
    if not _confirm("Run Y servo test?", config):
        return

    for angle in test_angles:
        logger.info(f"Y → {angle:.1f}°")
        actual = gimbal.set_y_angle(angle)
        print(f"  {_G}✓{_N} Y = {actual:.1f}°")
        time.sleep(0.5)

    # Slow sweep between safe limits
    if _confirm("Run slow Y sweep (min → max → center)?", config):
        logger.info(f"Sweeping Y {sv.min_angle}° → {sv.max_angle}° → {sv.center_angle}°")
        step  = sv.step_angle
        angle = sv.min_angle
        while angle <= sv.max_angle:
            gimbal.set_y_angle(angle)
            angle += step
        while angle >= sv.min_angle:
            gimbal.set_y_angle(angle)
            angle -= step
        gimbal.center_y()
        logger.success("Y sweep complete, servo at center")

    print(_status_line(gimbal))


def _menu_test_x(gimbal: Gimbal, logger: ToolkitLogger, config: AppConfig) -> None:
    """3. Test X Axis Stepper — small movements only."""
    st = config.gimbal.stepper
    _warn_movement(config.gimbal)
    print(f"\n  X stepper test:")
    print(f"  Planned: +100 steps → pause → -100 steps → +500 → -500")
    if not _confirm("Run X stepper test?", config):
        return

    for n_steps in [100, -100, 500, -500]:
        direction = "forward" if n_steps > 0 else "backward"
        logger.info(f"X stepper: {n_steps:+d} steps ({direction})")
        taken = gimbal.move_x_steps(n_steps)
        print(f"  {_G}✓{_N} Moved {taken:+d} steps  (relative position: {gimbal.relative_x_steps:+d})")
        time.sleep(0.8)

    logger.success("X stepper test complete")
    print(_status_line(gimbal))


def _menu_manual(gimbal: Gimbal, logger: ToolkitLogger, config: AppConfig) -> None:
    """4. Manual Gimbal Control — single-keypress, no Enter needed."""
    sv = config.gimbal.servo
    st = config.gimbal.stepper
    x_step = max(10, int(st.max_relative_steps * 0.01))   # ~1 % of max
    y_step = sv.step_angle

    _warn_movement(config.gimbal)
    print(f"\n  {_B}{_C}=== Manual Gimbal Control ==={_N}")
    print(f"  {_W}W{_N}/{_W}S{_N}  — Y servo  +{y_step:.0f}° / -{y_step:.0f}°")
    print(f"  {_W}A{_N}/{_W}D{_N}  — X stepper -{x_step} / +{x_step} steps")
    print(f"  {_W}C{_N}     — Center Y servo")
    print(f"  {_W}X{_N}     — Emergency stop")
    print(f"  {_W}R{_N}     — Reset relative X position counter")
    print(f"  {_W}Q{_N}     — Quit manual mode")
    print(f"\n  {_Y}⚠ Servo output will be ENABLED when you start. Press Q to disable.{_N}")
    if not _confirm("Enter manual mode?", config):
        return

    gimbal.enable_servo_output()
    logger.info("Servo output ENABLED")
    print(f"\n  {_status_line(gimbal)}")

    try:
        while True:
            char = _getch().upper()

            if char == "Q":
                break
            elif char == "W":
                gimbal.move_y_relative(+y_step)
            elif char == "S":
                gimbal.move_y_relative(-y_step)
            elif char == "A":
                gimbal.move_x_steps(-x_step)
            elif char == "D":
                gimbal.move_x_steps(+x_step)
            elif char == "C":
                gimbal.center_y()
            elif char == "X":
                gimbal.emergency_stop(logger)
                break
            elif char == "R":
                gimbal.reset_x_position()

            print(f"\r  {_status_line(gimbal)}   ", end="", flush=True)

    except KeyboardInterrupt:
        pass
    finally:
        print()
        gimbal.disable_servo_output()
        logger.info("Servo output DISABLED (manual mode exited)")


def _menu_pattern(gimbal: Gimbal, logger: ToolkitLogger, config: AppConfig) -> None:
    """5. Run X-Y Movement Pattern — coordinated 2-axis test."""
    sv = config.gimbal.servo
    _warn_movement(config.gimbal)
    print(f"\n  Pattern:")
    pattern = [
        ("Center Y",          None,  sv.center_angle),
        ("X +100",           +100,   None),
        ("Y +10°",            None,  sv.center_angle + 10),
        ("X -200",           -200,   None),
        ("Y -20°",            None,  sv.center_angle - 20),
        ("X +100",           +100,   None),
        ("Y +10°",            None,  sv.center_angle + 10),
        ("Return Y center",   None,  sv.center_angle),
    ]
    for label, x_steps, y_angle in pattern:
        desc = (
            f"X {x_steps:+d} steps" if x_steps is not None
            else f"Y {y_angle:.1f}°"
        )
        print(f"    {label:25s} ({desc})")

    if not _confirm("Run movement pattern?", config):
        return

    gimbal.enable_servo_output()
    logger.info("Servo output ENABLED for pattern run")

    try:
        for label, x_steps, y_angle in pattern:
            logger.info(label)
            if x_steps is not None:
                taken = gimbal.move_x_steps(x_steps)
                print(f"  {_G}✓{_N} {label}: {taken:+d} steps  (relative: {gimbal.relative_x_steps:+d})")
            else:
                actual = gimbal.set_y_angle(y_angle)
                print(f"  {_G}✓{_N} {label}: Y = {actual:.1f}°")
            time.sleep(0.6)
    except KeyboardInterrupt:
        logger.warning("Pattern interrupted by user")
    finally:
        gimbal.disable_servo_output()
        logger.info("Servo output DISABLED")

    logger.success("Pattern complete")
    print(_status_line(gimbal))


def _menu_bno_monitor(
    gimbal: Gimbal, imu: BNO085Sensor, logger: ToolkitLogger, config: AppConfig
) -> None:
    """6. BNO085 Orientation Monitor — display only, no motor movement."""
    gcfg  = config.gimbal
    hz    = gcfg.bno085.refresh_hz
    interval = 1.0 / hz

    print(f"\n  {_D}Motors are NOT moved in this mode. Ctrl+C to stop.{_N}")
    if not _confirm("Start BNO085 monitor?", config):
        return

    print(_HI, end="", flush=True)
    try:
        while True:
            reading = imu.read()
            roll = pitch = yaw = 0.0
            if reading.quaternion:
                w, x, y, z = reading.quaternion
                roll, pitch, yaw = _quat_to_euler(w, x, y, z)

            cal = reading.calibration_status or 0
            cal_color = _G if cal >= 3 else _Y

            print(
                _CL
                + f"{_B}{_M}╔══════════════════════════════════════════════╗{_N}\n"
                + f"{_B}{_M}║       BNO085 Orientation Monitor             ║{_N}\n"
                + f"{_B}{_M}╚══════════════════════════════════════════════╝{_N}\n"
                + f"  {_D}Ctrl+C to stop   Refresh: {hz} Hz{_N}\n\n"
                + f"  {_B}{_C}Roll  {_N} {_W}{roll:+8.2f}°{_N}  {_bar(roll,  -90, 90, 22, _C)}\n"
                + f"  {_B}{_Y}Pitch {_N} {_W}{pitch:+8.2f}°{_N}  {_bar(pitch, -90, 90, 22, _Y)}\n"
                + f"  {_B}{_D}Yaw   {_N} {_W}{yaw:+8.2f}°{_N}  {_bar(yaw,   -180,180,22,_M)}\n\n"
                + f"  Calibration  {cal_color}{'●' * cal}{'○' * (4 - cal)}{_N}  {_D}({cal}/4){_N}\n\n"
                + f"  Relative X : {_C}{gimbal.relative_x_steps:+d} steps{_N}\n"
                + f"  Y angle    : {_Y}{gimbal.y_angle:.1f}°{_N}\n",
                end="", flush=True,
            )
            time.sleep(interval)
    except KeyboardInterrupt:
        pass
    finally:
        print(_SH, end="", flush=True)
        print()


def _menu_bno_assisted(
    gimbal: Gimbal, imu: BNO085Sensor, logger: ToolkitLogger, config: AppConfig
) -> None:
    """7. BNO085 Assisted Gimbal Test — conservative proportional correction.

    ⚠ This is a TEST mode, not a flight-control algorithm.

    Y axis only (pitch → servo) unless bno_roll_to_x is explicitly enabled.
    Uses a proportional gain + deadband. No integrator. No derivative.

    Axis mapping assumption (documented):
        BNO085 Pitch (sensor Y rotation) → Y servo correction
        BNO085 Roll  (sensor X rotation) → X stepper (DISABLED by default)

    The mapping depends on physical sensor mounting — verify before enabling.
    """
    gcfg  = config.gimbal
    bcfg  = gcfg.bno085

    if not bcfg.feedback_enabled:
        print(
            f"\n  {_Y}[INFO]{_N} BNO085 feedback is DISABLED in config "
            f"(feedback_enabled: false).\n"
            f"  Set feedback_enabled: true in config.yaml to use this mode."
        )
        return

    print(f"\n  {_B}BNO085 Assisted Mode{_N}")
    print(f"  Target: Roll=0° Pitch=0°  (stabilise to level)")
    print(f"  Kp_y = {bcfg.kp_y}  Deadband = {bcfg.deadband_deg}°")
    print(f"  Max correction/loop = {bcfg.max_servo_correction_deg}°")
    print(f"  X feedback: {'ENABLED' if bcfg.bno_roll_to_x else _Y+'DISABLED (safe default)'+_N}")
    print(f"\n  {_D}Press Ctrl+C to stop.{_N}")
    if not _confirm("Start BNO085 assisted mode?", config):
        return

    _warn_movement(gcfg)
    gimbal.enable_servo_output()
    logger.info("Servo output ENABLED for BNO085 assisted mode")

    hz       = bcfg.refresh_hz
    interval = 1.0 / hz
    print(_HI, end="", flush=True)

    try:
        while True:
            reading = imu.read()
            roll = pitch = 0.0
            if reading.quaternion:
                w, x, y, z = reading.quaternion
                roll, pitch, _ = _quat_to_euler(w, x, y, z)

            # ── Y axis correction (pitch → servo) ──────────────────────────
            y_correction = 0.0
            if bcfg.bno_pitch_to_y:
                pitch_error = 0.0 - pitch          # target is 0 (level)
                if abs(pitch_error) > bcfg.deadband_deg:
                    raw_corr    = bcfg.kp_y * pitch_error
                    y_correction = max(
                        -bcfg.max_servo_correction_deg,
                        min(bcfg.max_servo_correction_deg, raw_corr),
                    )
                    gimbal.move_y_relative(y_correction)

            # ── X axis correction (roll → stepper) — DISABLED by default ──
            x_steps_taken = 0
            if bcfg.bno_roll_to_x:
                roll_error = 0.0 - roll
                if abs(roll_error) > bcfg.deadband_deg:
                    raw_steps   = int(bcfg.kp_y * roll_error * 5)  # ×5 to get steps
                    capped      = max(-20, min(20, raw_steps))
                    x_steps_taken = gimbal.move_x_steps(capped)

            # Terminal display
            cal = reading.calibration_status or 0
            cal_color = _G if cal >= 3 else _Y
            print(
                _CL
                + f"{_B}{_M}╔══════════════════════════════════════════════╗{_N}\n"
                + f"{_B}{_M}║     BNO085 Assisted Gimbal Test (Live)       ║{_N}\n"
                + f"{_B}{_M}╚══════════════════════════════════════════════╝{_N}\n"
                + f"  {_D}Ctrl+C to stop   {hz} Hz{_N}\n\n"
                + f"  {_B}{_C}Roll  {_N} {_W}{roll:+8.2f}°{_N}  err={-roll:+.2f}°  "
                + f"{'(X disabled)' if not bcfg.bno_roll_to_x else f'X={x_steps_taken:+d}'}\n"
                + f"  {_B}{_Y}Pitch {_N} {_W}{pitch:+8.2f}°{_N}  err={-pitch:+.2f}°  "
                + f"corr={y_correction:+.2f}°\n\n"
                + f"  Relative X : {_C}{gimbal.relative_x_steps:+d} steps{_N}\n"
                + f"  Y angle    : {_Y}{gimbal.y_angle:.1f}°{_N}\n"
                + f"  Cal        : {cal_color}{'●' * cal}{'○' * (4-cal)}{_N}  ({cal}/4)\n",
                end="", flush=True,
            )
            time.sleep(interval)

    except KeyboardInterrupt:
        pass
    finally:
        print(_SH, end="", flush=True)
        print()
        gimbal.disable_servo_output()
        logger.info("Servo output DISABLED (assisted mode exited)")


# ── Public API ────────────────────────────────────────────────────────────────

def quick_check(logger: ToolkitLogger, config: AppConfig) -> bool:
    """Initialise hardware without moving any motors. Used by test_all.

    Returns True if initialisation succeeds, False on any hardware error.
    Reports READY / NOT READY without commanding movement.
    """
    gimbal = build_gimbal(config)
    try:
        gimbal.initialize(logger)
        logger.success(
            f"Gimbal READY — "
            f"Y servo ch{config.gimbal.servo.channel} / "
            f"X stepper GPIO"
            f"{config.gimbal.stepper.in1_gpio},"
            f"{config.gimbal.stepper.in2_gpio},"
            f"{config.gimbal.stepper.in3_gpio},"
            f"{config.gimbal.stepper.in4_gpio}"
        )
        return True
    except HardwareError as exc:
        logger.error(f"Gimbal NOT READY: {exc}")
        return False
    finally:
        gimbal.close(logger)


def run(logger: ToolkitLogger, config: AppConfig) -> None:
    """Interactive gimbal test menu. No movement on menu entry."""
    gcfg   = config.gimbal
    gimbal = build_gimbal(config)
    imu    = BNO085Sensor(config.bno085) if gcfg.bno085.enabled else None

    # Track whether BNO085 is connected
    bno_ready = False

    print(f"\n{_B}{_C}Initialising gimbal hardware …{_N}")
    try:
        gimbal.initialize(logger)
    except HardwareError as exc:
        logger.error(f"Gimbal initialization failed: {exc}")
        return

    # Attempt BNO085 connection (non-fatal)
    if imu is not None:
        try:
            imu.connect()
            bno_ready = True
            logger.success("BNO085 connected")
        except HardwareError as exc:
            logger.warning(f"BNO085 not available: {exc}")
            imu = None

    try:
        while True:
            print(f"""
{_B}{_C}╔══════════════════════════════════╗
║           GIMBAL TEST            ║
╚══════════════════════════════════╝{_N}
  {_D}OE GPIO{gcfg.servo_driver.oe_gpio}  active_low={gcfg.servo_driver.active_low}
  Y servo ch{gcfg.servo.channel}  X stepper {gcfg.stepper.motor}{_N}
  BNO085: {"connected ✓" if bno_ready else _Y+"not connected"+_N}

  {_W}1{_N}  Center Gimbal
  {_W}2{_N}  Test Y Axis Servo
  {_W}3{_N}  Test X Axis Stepper
  {_W}4{_N}  Manual Gimbal Control  (W/S/A/D/C/X/Q)
  {_W}5{_N}  Run X-Y Movement Pattern
  {_W}6{_N}  BNO085 Orientation Monitor
  {_W}7{_N}  BNO085 Assisted Gimbal Test
  {_R}8{_N}  Emergency Stop
  {_W}0{_N}  Exit
""")

            choice = input("Select: ").strip()

            if choice == "1":
                gimbal.enable_servo_output()
                _menu_center(gimbal, logger, config)
                gimbal.disable_servo_output()

            elif choice == "2":
                gimbal.enable_servo_output()
                _menu_test_y(gimbal, logger, config)
                gimbal.disable_servo_output()

            elif choice == "3":
                _menu_test_x(gimbal, logger, config)

            elif choice == "4":
                _menu_manual(gimbal, logger, config)

            elif choice == "5":
                _menu_pattern(gimbal, logger, config)
                gimbal.disable_servo_output()

            elif choice == "6":
                if imu is None:
                    logger.error("BNO085 not connected — cannot run monitor")
                else:
                    _menu_bno_monitor(gimbal, imu, logger, config)

            elif choice == "7":
                if imu is None:
                    logger.error("BNO085 not connected — cannot run assisted mode")
                else:
                    _menu_bno_assisted(gimbal, imu, logger, config)

            elif choice == "8":
                gimbal.emergency_stop(logger)

            elif choice == "0":
                break

            else:
                logger.warning("Invalid option")

    except KeyboardInterrupt:
        print()
        logger.warning("Gimbal test interrupted by user")
        gimbal.emergency_stop(logger)

    finally:
        if imu is not None:
            try:
                imu.close()
            except Exception:
                pass
        gimbal.close(logger)
        logger.info("Gimbal closed, resources released")
