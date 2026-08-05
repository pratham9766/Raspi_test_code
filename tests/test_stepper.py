"""Test Stepper motor."""
from hardware.stepper import StepperMotor

def quick_check(logger, config) -> bool:
    stepper = StepperMotor(config=config.stepper)
    try:
        stepper.rotate_degrees(45, True)
        stepper.rotate_degrees(45, False)
        logger.success("Stepper motor quick check passed.")
        return True
    except Exception as e:
        logger.error(str(e))
        return False
    finally:
        stepper.close()

def run(logger, config):
    stepper = StepperMotor(config=config.stepper)
    try:
        while True:
            print("\n\033[1;36m=== Stepper Motor Menu ===\033[0m")
            print("1 Forward 100 steps")
            print("2 Backward 100 steps")
            print("3 Rotate 90°")
            print("4 Rotate 180°")
            print("5 Rotate 360°")
            print("6 Continuous Rotation (5 cycles, Ctrl+C to stop)")
            print("7 Stop")
            print("0 Back")
            choice = input("Select option: ").strip()
            
            if choice == '1': stepper.forward(100)
            elif choice == '2': stepper.backward(100)
            elif choice == '3': stepper.rotate_degrees(90)
            elif choice == '4': stepper.rotate_degrees(180)
            elif choice == '5': stepper.rotate_degrees(360)
            elif choice == '6':
                try:
                    for _ in range(5):
                        stepper.rotate_degrees(360)
                except KeyboardInterrupt:
                    pass
            elif choice == '7': stepper.stop()
            elif choice == '0': break
            else: logger.warning("Invalid choice.")
    except Exception as e:
        logger.error(f"Stepper error: {e}")
    finally:
        stepper.close()
