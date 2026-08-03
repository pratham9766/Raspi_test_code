"""BNO085 SPI IMU tests."""

from __future__ import annotations

import math
import time

from config import AppConfig
from hardware.bno085 import BNO085Reading, BNO085Sensor
from utils.colors import Color
from utils.helpers import HardwareError
from utils.logger import ToolkitLogger

# ── ANSI helpers ─────────────────────────────────────────────────────────────
_CYAN   = "\033[96m"
_WHITE  = "\033[97m"
_GREEN  = "\033[92m"
_YELLOW = "\033[93m"
_BLUE   = "\033[94m"
_MAGENTA= "\033[95m"
_DIM    = "\033[2m"
_BOLD   = "\033[1m"
_RESET  = "\033[0m"

_CLEAR  = "\033[2J\033[H"        # clear screen + home cursor
_HIDE   = "\033[?25l"            # hide cursor
_SHOW   = "\033[?25h"            # show cursor


def _bar(value: float, lo: float, hi: float, width: int = 20, color: str = _CYAN) -> str:
    """Return a filled ASCII progress bar."""
    ratio = max(0.0, min(1.0, (value - lo) / (hi - lo)))
    filled = round(ratio * width)
    bar = "█" * filled + "░" * (width - filled)
    return f"{color}{bar}{_RESET}"


def _fmt3(vec: tuple | None, unit: str = "") -> str:
    if vec is None:
        return f"{_DIM}N/A{_RESET}"
    x, y, z = vec
    return (
        f"{_WHITE}X{_RESET} {x:+8.3f}  "
        f"{_WHITE}Y{_RESET} {y:+8.3f}  "
        f"{_WHITE}Z{_RESET} {z:+8.3f}"
        + (f"  {_DIM}{unit}{_RESET}" if unit else "")
    )


def _cal_dots(status: int | None) -> str:
    filled = status or 0
    dots = "●" * filled + "○" * (4 - filled)
    color = _GREEN if filled >= 3 else (_YELLOW if filled >= 1 else _DIM)
    return f"{color}{dots}{_RESET}  {_DIM}({filled}/4){_RESET}"


def _quat_to_euler(w: float, x: float, y: float, z: float) -> tuple[float, float, float]:
    """Convert quaternion to Roll / Pitch / Yaw in degrees."""
    roll  = math.degrees(math.atan2(2*(w*x + y*z), 1 - 2*(x*x + y*y)))
    sinp  = 2*(w*y - z*x)
    pitch = math.degrees(math.copysign(math.pi/2, sinp) if abs(sinp) >= 1 else math.asin(sinp))
    yaw   = math.degrees(math.atan2(2*(w*z + x*y), 1 - 2*(y*y + z*z)))
    return roll, pitch, yaw


def _render(reading: BNO085Reading, elapsed: float, hz: int) -> str:
    lines: list[str] = []
    add = lines.append

    add(f"{_BOLD}{_MAGENTA}╔══════════════════════════════════════════════════════╗{_RESET}")
    add(f"{_BOLD}{_MAGENTA}║        BNO085 IMU  —  Live Sensor Readings           ║{_RESET}")
    add(f"{_BOLD}{_MAGENTA}╚══════════════════════════════════════════════════════╝{_RESET}")
    add(f"  {_DIM}Refresh: {hz} Hz   Uptime: {elapsed:.1f}s   Press Ctrl+C to stop{_RESET}")
    add("")

    # ── Accelerometer ──────────────────────────────────────────────────────
    add(f"  {_BOLD}{_CYAN}▸ Accelerometer{_RESET}  {_DIM}(m/s²){_RESET}")
    add(f"    {_fmt3(reading.acceleration)}")
    if reading.acceleration:
        mag = math.sqrt(sum(v**2 for v in reading.acceleration))
        add(f"    Magnitude  {_bar(mag, 0, 20)}  {_WHITE}{mag:.3f} m/s²{_RESET}")
    add("")

    # ── Gyroscope ──────────────────────────────────────────────────────────
    add(f"  {_BOLD}{_BLUE}▸ Gyroscope{_RESET}  {_DIM}(rad/s){_RESET}")
    add(f"    {_fmt3(reading.gyroscope)}")
    add("")

    # ── Magnetometer ───────────────────────────────────────────────────────
    add(f"  {_BOLD}{_GREEN}▸ Magnetometer{_RESET}  {_DIM}(µT){_RESET}")
    add(f"    {_fmt3(reading.magnetometer)}")
    add("")

    # ── Quaternion + Euler ─────────────────────────────────────────────────
    add(f"  {_BOLD}{_YELLOW}▸ Orientation{_RESET}")
    if reading.quaternion:
        w, x, y, z = reading.quaternion
        add(f"    Quaternion  W {_WHITE}{w:+.4f}{_RESET}  X {_WHITE}{x:+.4f}{_RESET}  "
            f"Y {_WHITE}{y:+.4f}{_RESET}  Z {_WHITE}{z:+.4f}{_RESET}")
        roll, pitch, yaw = _quat_to_euler(w, x, y, z)
        add(f"    Roll  {_WHITE}{roll:+7.2f}°{_RESET}  {_bar(roll, -180, 180, 16, _YELLOW)}")
        add(f"    Pitch {_WHITE}{pitch:+7.2f}°{_RESET}  {_bar(pitch, -90, 90, 16, _CYAN)}")
        add(f"    Yaw   {_WHITE}{yaw:+7.2f}°{_RESET}  {_bar(yaw, -180, 180, 16, _BLUE)}")
    else:
        add(f"    {_DIM}N/A{_RESET}")
    add("")

    # ── Calibration ────────────────────────────────────────────────────────
    add(f"  {_BOLD}▸ Calibration{_RESET}  {_cal_dots(reading.calibration_status)}")
    add("")

    return "\n".join(lines)


def run(logger: ToolkitLogger, config: AppConfig) -> bool:
    """Continuously print BNO085 readings at the configured refresh rate."""
    sensor   = BNO085Sensor(config.bno085)
    interval = 1.0 / config.bno085.refresh_hz
    start    = time.time()
    print(_HIDE, end="", flush=True)
    try:
        logger.info("BNO085 SPI stream running. Press CTRL+C to stop.")
        while True:
            reading = sensor.read()
            print(_CLEAR + _render(reading, time.time() - start, config.bno085.refresh_hz),
                  end="", flush=True)
            time.sleep(interval)
    except KeyboardInterrupt:
        print(_SHOW)
        logger.info("BNO085 stream stopped")
        return True
    except HardwareError as exc:
        print(_SHOW)
        logger.error(str(exc))
        return False
    finally:
        print(_SHOW, end="")
        sensor.close()


def quick_check(logger: ToolkitLogger, config: AppConfig) -> bool:
    """Read one BNO085 sample."""
    sensor = BNO085Sensor(config.bno085)
    try:
        reading = sensor.read()
        logger.success(
            f"BNO085 read OK: Quaternion={reading.quaternion}, "
            f"Calibration={reading.calibration_status}"
        )
        return True
    except HardwareError as exc:
        logger.error(str(exc))
        return False
    finally:
        sensor.close()
