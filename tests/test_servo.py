"""Test Servo motor."""
import time
from hardware.pca9685_driver import PCA9685Driver
from hardware.servo import ServoController

def get_servo(config):
    drv = PCA9685Driver(address=config.pca9685.address, frequency_hz=config.pca9685.frequency_hz, oe_gpio=config.pca9685.oe_gpio)
    return ServoController(config=config.servo, driver=drv)

def quick_check(logger, config) -> bool:
    try:
        servo = get_servo(config)
        servo.center()
        time.sleep(0.5)
        servo.close()
        logger.success("Servo centered successfully.")
        return True
    except Exception as e:
        logger.error(str(e))
        return False

def run(logger, config):
    servo = get_servo(config)
    try:
        while True:
            print("\n\033[1;36m=== Servo Test Menu ===\033[0m")
            print("1 Move to 0°")
            print("2 Move to 45°")
            print("3 Move to 90°")
            print("4 Move to 135°")
            print("5 Move to 180°")
            print("6 Sweep")
            print("7 Continuous Sweep (3 cycles)")
            print("8 Center")
            print("0 Back")
            choice = input("Select option: ").strip()
            
            if choice == '1': servo.move_to(0)
            elif choice == '2': servo.move_to(45)
            elif choice == '3': servo.move_to(90)
            elif choice == '4': servo.move_to(135)
            elif choice == '5': servo.move_to(180)
            elif choice == '6': servo.sweep()
            elif choice == '7': servo.continuous_sweep(3)
            elif choice == '8': servo.center()
            elif choice == '0': break
            else: logger.warning("Invalid choice.")
    except Exception as e:
        logger.error(f"Servo error: {e}")
    finally:
        servo.close()
