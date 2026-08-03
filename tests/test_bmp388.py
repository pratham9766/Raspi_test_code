"""BMP388 pressure sensor tests."""

from __future__ import annotations

import time

from config import AppConfig
from hardware.bmp388 import BMP388Reading, BMP388Sensor
from utils.helpers import HardwareError
from utils.logger import ToolkitLogger

# ── ANSI helpers ─────────────────────────────────────────────────────────────
_CYAN    = "\033[96m"
_WHITE   = "\033[97m"
_GREEN   = "\033[92m"
_YELLOW  = "\033[93m"
_ORANGE  = "\033[38;5;214m"
_BLUE    = "\033[94m"
_MAGENTA = "\033[95m"
_DIM     = "\033[2m"
_BOLD    = "\033[1m"
_RESET   = "\033[0m"

_CLEAR   = "\033[2J\033[H"
_HIDE    = "\033[?25l"
_SHOW    = "\033[?25h"


def _bar(value: float, lo: float, hi: float, width: int = 24, color: str = _CYAN) -> str:
    ratio  = max(0.0, min(1.0, (value - lo) / (hi - lo)))
    filled = round(ratio * width)
    return f"{color}{'█' * filled}{'░' * (width - filled)}{_RESET}"


def _render(reading: BMP388Reading, elapsed: float, hz: int) -> str:
    lines: list[str] = []
    add = lines.append

    add(f"{_BOLD}{_ORANGE}╔══════════════════════════════════════════════════════╗{_RESET}")
    add(f"{_BOLD}{_ORANGE}║      BMP388  —  Pressure & Altitude  (Live)          ║{_RESET}")
    add(f"{_BOLD}{_ORANGE}╚══════════════════════════════════════════════════════╝{_RESET}")
    add(f"  {_DIM}Refresh: {hz} Hz   Uptime: {elapsed:.1f}s   Press Ctrl+C to stop{_RESET}")
    add("")

    # ── Temperature ────────────────────────────────────────────────────────
    add(f"  {_BOLD}{_YELLOW}▸ Temperature{_RESET}")
    add(f"    {_WHITE}{reading.temperature_c:+7.2f} °C{_RESET}")
    add(f"    {_bar(reading.temperature_c, -10, 85, 30, _YELLOW)}  "
        f"{_DIM}(-10 … 85 °C){_RESET}")
    add("")

    # ── Pressure ───────────────────────────────────────────────────────────
    add(f"  {_BOLD}{_CYAN}▸ Pressure{_RESET}")
    add(f"    {_WHITE}{reading.pressure_hpa:8.2f} hPa{_RESET}")
    add(f"    {_bar(reading.pressure_hpa, 900, 1100, 30, _CYAN)}  "
        f"{_DIM}(900 … 1100 hPa){_RESET}")
    add("")

    # ── Altitude ───────────────────────────────────────────────────────────
    add(f"  {_BOLD}{_GREEN}▸ Altitude{_RESET}")
    add(f"    {_WHITE}{reading.altitude_m:8.2f} m{_RESET}")
    add(f"    {_bar(reading.altitude_m, -100, 3000, 30, _GREEN)}  "
        f"{_DIM}(-100 … 3000 m){_RESET}")
    add("")

    return "\n".join(lines)


def run(logger: ToolkitLogger, config: AppConfig) -> bool:
    """Continuously print BMP388 readings at the configured refresh rate."""
    sensor   = BMP388Sensor(config.bmp388)
    interval = 1.0 / config.bmp388.refresh_hz
    start    = time.time()
    print(_HIDE, end="", flush=True)
    try:
        logger.info("BMP388 stream running. Press CTRL+C to stop.")
        while True:
            reading = sensor.read()
            print(_CLEAR + _render(reading, time.time() - start, config.bmp388.refresh_hz),
                  end="", flush=True)
            time.sleep(interval)
    except KeyboardInterrupt:
        print(_SHOW)
        logger.info("BMP388 stream stopped")
        return True
    except HardwareError as exc:
        print(_SHOW)
        logger.error(str(exc))
        return False
    finally:
        print(_SHOW, end="")
        sensor.close()


def quick_check(logger: ToolkitLogger, config: AppConfig) -> bool:
    """Read one BMP388 sample."""
    sensor = BMP388Sensor(config.bmp388)
    try:
        reading = sensor.read()
        logger.success(
            f"BMP388 read OK: {reading.temperature_c:.2f} C, {reading.pressure_hpa:.2f} hPa"
        )
        return True
    except HardwareError as exc:
        logger.error(str(exc))
        return False
    finally:
        sensor.close()
