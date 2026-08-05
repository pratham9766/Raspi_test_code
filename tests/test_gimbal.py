"""Gimbal tests — dual servo (ch0=X/yaw, ch1=Y/pitch) with BNO085 stabilisation."""

from __future__ import annotations

from config import AppConfig
from hardware.bno085 import BNO085Sensor
from hardware.gimbal import Gimbal
from hardware.pca9685_driver import PCA9685Driver
from utils.helpers import HardwareError
from utils.logger import ToolkitLogger

# ── ANSI ─────────────────────────────────────────────────────────────────────
_CYAN    = "\033[96m"
_YELLOW  = "\033[93m"
_GREEN   = "\033[92m"
_BOLD    = "\033[1m"
_RESET   = "\033[0m"


def _make_gimbal(config: AppConfig) -> Gimbal:
    """Build a Gimbal instance from AppConfig."""
    driver = PCA9685Driver(
        address=config.pca9685.address,
        frequency_hz=config.pca9685.frequency_hz,
        oe_gpio=config.pca9685.oe_gpio,
    )
    return Gimbal(driver=driver, config=config.gimbal)


def quick_check(logger: ToolkitLogger, config: AppConfig) -> bool:
    """Center both gimbal axes as a quick functional check."""
    gimbal = _make_gimbal(config)
    try:
        gimbal.connect()
        gimbal.center()
        logger.success(
            f"Gimbal centered — X ch{config.gimbal.x_channel}, "
            f"Y ch{config.gimbal.y_channel}"
        )
        return True
    except HardwareError as exc:
        logger.error(str(exc))
        return False
    finally:
        gimbal.close()


def run(logger: ToolkitLogger, config: AppConfig) -> bool:
    """Interactive gimbal test menu."""
    gimbal = _make_gimbal(config)

    try:
        gimbal.connect()
        logger.success(
            f"Gimbal ready — X servo ch{config.gimbal.x_channel}, "
            f"Y servo ch{config.gimbal.y_channel}"
        )

        while True:
            print(f"\n{_BOLD}{_CYAN}=== Gimbal Menu ==={_RESET}")
            print(f"  {_CYAN}Axes:{_RESET}  X = PCA9685 ch{config.gimbal.x_channel} (yaw)   "
                  f"Y = PCA9685 ch{config.gimbal.y_channel} (pitch)")
            print()
            print("  1  Center (both axes → 90°)")
            print("  2  Move X Left  (−15°)")
            print("  3  Move X Right (+15°)")
            print("  4  Move Y Up    (+15°)")
            print("  5  Move Y Down  (−15°)")
            print("  6  Set X angle  (manual input)")
            print("  7  Set Y angle  (manual input)")
            print("  8  Sweep X axis")
            print("  9  Sweep Y axis")
            print(" 10  Figure-8 Demo")
            print(" 11  Square Demo")
            print(" 12  Continuous Scan (X, 3 cycles)")
            print(" 13  Keyboard Mode  (W/S/A/D/C/Q)")
            print(f" {_YELLOW}14  BNO085 Stabilise Mode  ★{_RESET}  (IMU drives gimbal live)")
            print(f" {_GREEN}15  BNO085 Follow Mode{_RESET}        (gimbal follows IMU tilt)")
            print("  0  Back")
            print()

            choice = input("Select: ").strip()

            if choice == "1":
                gimbal.center()
                logger.success("Gimbal centered")

            elif choice == "2":
                gimbal.move_x_relative(-15)
                logger.success(f"X → {gimbal._x_angle:.1f}°")

            elif choice == "3":
                gimbal.move_x_relative(+15)
                logger.success(f"X → {gimbal._x_angle:.1f}°")

            elif choice == "4":
                gimbal.move_y_relative(+15)
                logger.success(f"Y → {gimbal._y_angle:.1f}°")

            elif choice == "5":
                gimbal.move_y_relative(-15)
                logger.success(f"Y → {gimbal._y_angle:.1f}°")

            elif choice == "6":
                try:
                    ang = float(input("  X angle (0–180): ").strip())
                    gimbal.move_x(ang)
                    logger.success(f"X → {gimbal._x_angle:.1f}°")
                except ValueError:
                    logger.warning("Invalid angle")

            elif choice == "7":
                try:
                    ang = float(input("  Y angle (0–180): ").strip())
                    gimbal.move_y(ang)
                    logger.success(f"Y → {gimbal._y_angle:.1f}°")
                except ValueError:
                    logger.warning("Invalid angle")

            elif choice == "8":
                logger.info("Sweeping X axis …")
                gimbal.sweep_x()
                logger.success("X sweep complete")

            elif choice == "9":
                logger.info("Sweeping Y axis …")
                gimbal.sweep_y()
                logger.success("Y sweep complete")

            elif choice == "10":
                logger.info("Figure-8 demo …")
                gimbal.figure_eight()
                logger.success("Figure-8 complete")

            elif choice == "11":
                logger.info("Square demo …")
                gimbal.square_demo()
                logger.success("Square demo complete")

            elif choice == "12":
                logger.info("Continuous scan (3 cycles) …")
                gimbal.continuous_scan(3)
                logger.success("Scan complete")

            elif choice == "13":
                gimbal.keyboard_mode()

            elif choice == "14":
                # BNO085 stabilise — IMU-driven live control
                imu = BNO085Sensor(config.bno085)
                logger.info("Connecting BNO085 for stabilise mode …")
                try:
                    imu.connect()
                    logger.success("BNO085 connected. Stabilise mode starting … Ctrl+C to stop")
                    gimbal.stabilise(imu, loop_hz=20)
                    logger.info("Stabilise mode stopped")
                except HardwareError as exc:
                    logger.error(f"BNO085 error: {exc}")
                finally:
                    imu.close()

            elif choice == "15":
                # BNO085 follow mode
                imu = BNO085Sensor(config.bno085)
                logger.info("Connecting BNO085 for follow mode …")
                try:
                    imu.connect()
                    logger.success("BNO085 connected. Follow mode starting … Ctrl+C to stop")
                    gimbal.follow(imu, loop_hz=20)
                    logger.info("Follow mode stopped")
                except HardwareError as exc:
                    logger.error(f"BNO085 error: {exc}")
                finally:
                    imu.close()

            elif choice == "0":
                return True

            else:
                logger.warning("Invalid option")

    except HardwareError as exc:
        logger.error(str(exc))
        return False
    finally:
        gimbal.close()

    return True
