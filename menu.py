"""Main interactive menu."""
from config import AppConfig
from utils.logger import ToolkitLogger
from utils.system_info import get_system_info, print_system_info
from hardware.i2c_scan import scan_i2c, print_scan_results
from tests import test_pca9685, test_servo, test_stepper, test_gimbal, test_camera, test_all
from hardware.bno085 import BNO085Sensor
from hardware.bmp388 import BMP388Sensor

def show_menu():
    print("""
\033[1;36m╔═══════════════════════════════════════╗
║   RASPBERRY PI 5 TEST UTILITY  v2.0  ║
║         Avionics Test Suite          ║
╚═══════════════════════════════════════╝\033[0m

 \033[1;33m1\033[0m  Scan I2C Bus
 \033[1;33m2\033[0m  Test BNO085 (IMU)
 \033[1;33m3\033[0m  Test BMP388 (Pressure)
 \033[1;33m4\033[0m  Test PCA9685 (PWM Driver)
 \033[1;33m5\033[0m  Test Servo
 \033[1;33m6\033[0m  Test Stepper Motor
 \033[1;33m7\033[0m  Test Gimbal
 \033[1;33m8\033[0m  Camera Preview
 \033[1;33m9\033[0m  Capture Image
\033[1;33m10\033[0m  Capture Video
\033[1;33m11\033[0m  System Information
\033[1;33m12\033[0m  Test Everything
 \033[1;31m0\033[0m  Exit
""")

def test_bno085(logger: ToolkitLogger, config: AppConfig):
    try:
        sensor = BNO085Sensor(config.bno085)
        reading = sensor.read()
        logger.success("BNO085 Read Success!")
        print(f"Accel: {reading.acceleration}")
        print(f"Gyro:  {reading.gyroscope}")
        print(f"Mag:   {reading.magnetometer}")
        print(f"Quat:  {reading.quaternion}")
        sensor.close()
    except Exception as e:
        logger.error(str(e))

def test_bmp388(logger: ToolkitLogger, config: AppConfig):
    try:
        sensor = BMP388Sensor(config.bmp388)
        reading = sensor.read()
        logger.success("BMP388 Read Success!")
        print(f"Temp:     {reading.temperature_c:.2f} °C")
        print(f"Pressure: {reading.pressure_hpa:.2f} hPa")
        print(f"Altitude: {reading.altitude_m:.2f} m")
        sensor.close()
    except Exception as e:
        logger.error(str(e))

def run_menu(logger: ToolkitLogger, config: AppConfig):
    while True:
        show_menu()
        choice = input("Select an option: ").strip()
        
        if choice == '1':
            devices = scan_i2c(config.board.i2c_bus)
            print_scan_results(devices)
        elif choice == '2': test_bno085(logger, config)
        elif choice == '3': test_bmp388(logger, config)
        elif choice == '4': test_pca9685.run(logger, config)
        elif choice == '5': test_servo.run(logger, config)
        elif choice == '6': test_stepper.run(logger, config)
        elif choice == '7': test_gimbal.run(logger, config)
        elif choice == '8': 
            try:
                from hardware.camera import PiCameraSensor
                cam = PiCameraSensor(config.camera)
                cam.preview()
                cam.close()
            except Exception as e: logger.error(str(e))
        elif choice == '9':
            try:
                from hardware.camera import PiCameraSensor
                cam = PiCameraSensor(config.camera)
                logger.success(f"Saved: {cam.capture_image()}")
                cam.close()
            except Exception as e: logger.error(str(e))
        elif choice == '10':
            try:
                from hardware.camera import PiCameraSensor
                cam = PiCameraSensor(config.camera)
                logger.success(f"Saved: {cam.capture_video()}")
                cam.close()
            except Exception as e: logger.error(str(e))
        elif choice == '11':
            info = get_system_info()
            print_system_info(info)
        elif choice == '12': test_all.run(logger, config)
        elif choice == '0':
            logger.info("Exiting Toolkit.")
            break
        else:
            logger.warning("Invalid selection. Try again.")
