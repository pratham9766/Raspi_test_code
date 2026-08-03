"""Live combined terminal view — BNO085 + BMP388 simultaneously."""

from __future__ import annotations

import math
import time

from config import AppConfig
from hardware.bmp388 import BMP388Reading, BMP388Sensor
from hardware.bno085 import BNO085Reading, BNO085Sensor
from utils.helpers import HardwareError, get_system_info
from utils.logger import ToolkitLogger

# ── ANSI ─────────────────────────────────────────────────────────────────────
_CYAN    = "\033[96m"
_WHITE   = "\033[97m"
_GREEN   = "\033[92m"
_YELLOW  = "\033[93m"
_ORANGE  = "\033[38;5;214m"
_BLUE    = "\033[94m"
_MAGENTA = "\033[95m"
_RED     = "\033[91m"
_DIM     = "\033[2m"
_BOLD    = "\033[1m"
_RESET   = "\033[0m"

_CLEAR   = "\033[2J\033[H"
_HIDE    = "\033[?25l"
_SHOW    = "\033[?25h"

_W = 56   # panel width


def _bar(value: float, lo: float, hi: float, width: int = 22, color: str = _CYAN) -> str:
    ratio  = max(0.0, min(1.0, (value - lo) / (hi - lo)))
    filled = round(ratio * width)
    return f"{color}{'█' * filled}{'░' * (width - filled)}{_RESET}"


def _fmt3(vec: tuple | None) -> str:
    if vec is None:
        return f"{_DIM}  N/A{_RESET}"
    x, y, z = vec
    return (
        f"{_DIM}X{_RESET}{_WHITE}{x:+8.3f}{_RESET} "
        f"{_DIM}Y{_RESET}{_WHITE}{y:+8.3f}{_RESET} "
        f"{_DIM}Z{_RESET}{_WHITE}{z:+8.3f}{_RESET}"
    )


def _cal_dots(status: int | None) -> str:
    n = status or 0
    color = _GREEN if n >= 3 else (_YELLOW if n >= 1 else _RED)
    return f"{color}{'●' * n}{'○' * (4 - n)}{_RESET} {_DIM}({n}/4){_RESET}"


def _quat_to_euler(w: float, x: float, y: float, z: float) -> tuple[float, float, float]:
    roll  = math.degrees(math.atan2(2*(w*x + y*z), 1 - 2*(x*x + y*y)))
    sinp  = 2*(w*y - z*x)
    pitch = math.degrees(math.copysign(math.pi / 2, sinp) if abs(sinp) >= 1 else math.asin(sinp))
    yaw   = math.degrees(math.atan2(2*(w*z + x*y), 1 - 2*(y*y + z*z)))
    return roll, pitch, yaw


def _divider(label: str, color: str) -> str:
    pad = _W - len(label) - 4
    return f"  {color}{_BOLD}── {label} {'─' * pad}{_RESET}"


def _render(
    imu: BNO085Reading | None,
    bmp: BMP388Reading | None,
    imu_err: str,
    bmp_err: str,
    elapsed: float,
    cpu_temp: float | None,
) -> str:
    lines: list[str] = []
    add = lines.append

    # ── Header ────────────────────────────────────────────────────────────
    add(f"{_BOLD}{_CYAN}╔{'═' * (_W - 2)}╗{_RESET}")
    add(f"{_BOLD}{_CYAN}║{'  Raspberry Pi — Live Sensor Monitor':^{_W - 2}}║{_RESET}")
    add(f"{_BOLD}{_CYAN}╚{'═' * (_W - 2)}╝{_RESET}")
    cpu_str = f"  CPU {_YELLOW}{cpu_temp:.1f}°C{_RESET}" if cpu_temp is not None else ""
    add(f"  {_DIM}Uptime: {elapsed:.1f}s   Ctrl+C to stop{_RESET}{cpu_str}")
    add("")

    # ══ BNO085 IMU ═══════════════════════════════════════════════════════
    add(_divider("BNO085 IMU", _MAGENTA))
    add("")

    if imu_err and imu is None:
        add(f"  {_RED}✖  {imu_err}{_RESET}")
        add("")
    else:
        # Accelerometer
        add(f"  {_BOLD}{_CYAN}Accelerometer{_RESET}  {_DIM}m/s²{_RESET}")
        add(f"  {_fmt3(imu.acceleration if imu else None)}")
        if imu and imu.acceleration:
            mag = math.sqrt(sum(v**2 for v in imu.acceleration))
            add(f"  {_bar(mag, 0, 20)}  {_WHITE}{mag:.2f}{_RESET} {_DIM}m/s²{_RESET}")
        add("")

        # Gyroscope
        add(f"  {_BOLD}{_BLUE}Gyroscope{_RESET}  {_DIM}rad/s{_RESET}")
        add(f"  {_fmt3(imu.gyroscope if imu else None)}")
        add("")

        # Magnetometer
        add(f"  {_BOLD}{_GREEN}Magnetometer{_RESET}  {_DIM}µT{_RESET}")
        add(f"  {_fmt3(imu.magnetometer if imu else None)}")
        add("")

        # Orientation
        add(f"  {_BOLD}{_YELLOW}Orientation{_RESET}")
        if imu and imu.quaternion:
            w, x, y, z = imu.quaternion
            roll, pitch, yaw = _quat_to_euler(w, x, y, z)
            add(f"  Roll  {_WHITE}{roll:+7.2f}°{_RESET}  {_bar(roll,  -180, 180, 20, _YELLOW)}")
            add(f"  Pitch {_WHITE}{pitch:+7.2f}°{_RESET}  {_bar(pitch,  -90,  90, 20, _CYAN)}")
            add(f"  Yaw   {_WHITE}{yaw:+7.2f}°{_RESET}  {_bar(yaw,   -180, 180, 20, _BLUE)}")
        else:
            add(f"  {_DIM}N/A{_RESET}")
        add("")

        # Calibration
        add(f"  {_BOLD}Calibration{_RESET}  {_cal_dots(imu.calibration_status if imu else None)}")
        add("")

    # ══ BMP388 ════════════════════════════════════════════════════════════
    add(_divider("BMP388 Pressure & Altitude", _ORANGE))
    add("")

    if bmp_err and bmp is None:
        add(f"  {_RED}✖  {bmp_err}{_RESET}")
    else:
        t = bmp.temperature_c if bmp else 0.0
        p = bmp.pressure_hpa  if bmp else 0.0
        a = bmp.altitude_m    if bmp else 0.0

        add(f"  {_BOLD}{_YELLOW}Temperature{_RESET}  {_WHITE}{t:+7.2f} °C{_RESET}")
        add(f"  {_bar(t, -10, 85, 28, _YELLOW)}  {_DIM}-10…85 °C{_RESET}")
        add("")
        add(f"  {_BOLD}{_CYAN}Pressure{_RESET}     {_WHITE}{p:8.2f} hPa{_RESET}")
        add(f"  {_bar(p, 900, 1100, 28, _CYAN)}  {_DIM}900…1100 hPa{_RESET}")
        add("")
        add(f"  {_BOLD}{_GREEN}Altitude{_RESET}     {_WHITE}{a:8.2f} m{_RESET}")
        add(f"  {_bar(a, -100, 3000, 28, _GREEN)}  {_DIM}-100…3000 m{_RESET}")

    add("")
    return "\n".join(lines)


def run(logger: ToolkitLogger, config: AppConfig) -> bool:
    """Stream live readings from both BNO085 and BMP388."""
    imu_sensor = BNO085Sensor(config.bno085)
    bmp_sensor = BMP388Sensor(config.bmp388)
    interval   = 1.0 / max(config.bno085.refresh_hz, config.bmp388.refresh_hz, 1)
    start      = time.time()
    cpu_temp: float | None = None
    last_sys   = 0.0

    print(_HIDE, end="", flush=True)
    logger.info("Live monitor running. Press Ctrl+C to stop.")

    try:
        while True:
            imu_reading: BNO085Reading | None = None
            bmp_reading: BMP388Reading | None = None
            imu_err = bmp_err = ""

            try:
                imu_reading = imu_sensor.read()
            except HardwareError as exc:
                imu_err = str(exc)

            try:
                bmp_reading = bmp_sensor.read()
            except HardwareError as exc:
                bmp_err = str(exc)

            # Refresh CPU temp every 5 s
            if time.time() - last_sys >= 5:
                try:
                    cpu_temp = get_system_info().cpu_temperature_c
                except Exception:
                    pass
                last_sys = time.time()

            print(
                _CLEAR + _render(
                    imu_reading, bmp_reading,
                    imu_err, bmp_err,
                    time.time() - start,
                    cpu_temp,
                ),
                end="", flush=True,
            )
            time.sleep(interval)

    except KeyboardInterrupt:
        print(_SHOW)
        logger.info("Live monitor stopped.")
        return True
    except Exception as exc:
        print(_SHOW)
        logger.error(str(exc))
        return False
    finally:
        print(_SHOW, end="")
        imu_sensor.close()
        bmp_sensor.close()
