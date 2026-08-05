"""Test Gimbal."""
from hardware.gimbal import Gimbal
from hardware.stepper import StepperMotor
from hardware.servo import ServoController
from hardware.pca9685_driver import PCA9685Driver

def get_gimbal(config):
    stepper = StepperMotor(config=config.stepper)
    drv = PCA9685Driver(address=config.pca9685.address, frequency_hz=config.pca9685.frequency_hz)
    servo = ServoController(config=config.servo, driver=drv)
    return Gimbal(stepper=stepper, servo=servo, config=config.gimbal)

def quick_check(logger, config) -> bool:
    try:
        gimbal = get_gimbal(config)
        gimbal.connect()
        gimbal.center()
        gimbal.close()
        logger.success("Gimbal centered successfully.")
        return True
    except Exception as e:
        logger.error(str(e))
        return False

def run(logger, config):
    gimbal = get_gimbal(config)
    try:
        gimbal.connect()
        while True:
            print("\n\033[1;36m=== Gimbal Menu ===\033[0m")
            print("1 Center Gimbal")
            print("2 Move X Left 45°")
            print("3 Move X Right 45°")
            print("4 Move Y Up (pitch 135°)")
            print("5 Move Y Down (pitch 45°)")
            print("6 Set X Angle (input)")
            print("7 Set Y Angle (input)")
            print("8 Sweep X")
            print("9 Sweep Y")
            print("10 Figure-8 Demo")
            print("11 Square Demo")
            print("12 Continuous Scan")
            print("13 Keyboard Mode (W/S/A/D/C/Q)")
            print("0 Back")
            choice = input("Select option: ").strip()
            
            if choice == '1': gimbal.center()
            elif choice == '2': gimbal.move_x(45, False)
            elif choice == '3': gimbal.move_x(45, True)
            elif choice == '4': gimbal.move_y(135)
            elif choice == '5': gimbal.move_y(45)
            elif choice == '6':
                try:
                    deg = float(input("Degrees to move X (positive=right, negative=left): "))
                    gimbal.move_x(abs(deg), deg > 0)
                except ValueError: pass
            elif choice == '7':
                try:
                    deg = float(input("Absolute angle for Y (0-180): "))
                    gimbal.move_y(deg)
                except ValueError: pass
            elif choice == '8': gimbal.sweep_x()
            elif choice == '9': gimbal.sweep_y()
            elif choice == '10': gimbal.figure_eight()
            elif choice == '11': gimbal.square_demo()
            elif choice == '12': gimbal.continuous_scan()
            elif choice == '13': gimbal.keyboard_mode()
            elif choice == '0': break
            else: logger.warning("Invalid choice.")
    except Exception as e:
        logger.error(f"Gimbal error: {e}")
    finally:
        gimbal.close()
