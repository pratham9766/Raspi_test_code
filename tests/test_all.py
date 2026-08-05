"""Run all hardware validation checks and generate a test report."""
import time
from pathlib import Path
from utils.helpers import ensure_directory, timestamp_slug

def run(logger, config):
    from hardware.i2c_scan import scan_i2c
    from tests import test_pca9685, test_servo, test_stepper, test_gimbal, test_camera
    from hardware.bno085 import BNO085Sensor
    from hardware.bmp388 import BMP388Sensor
    
    logger.info("Starting Full Hardware Validation Suite...")
    results = {}
    
    # I2C
    try:
        devices = scan_i2c(config.board.i2c_bus)
        results["I2C_Scan"] = len(devices) > 0
        if results["I2C_Scan"]: logger.success(f"Found {len(devices)} I2C devices.")
        else: logger.warning("No I2C devices found.")
    except Exception:
        results["I2C_Scan"] = False
        
    # BNO085
    try:
        sensor = BNO085Sensor(config.bno085)
        sensor.read()
        sensor.close()
        results["BNO085"] = True
        logger.success("BNO085 reading successful.")
    except Exception as e:
        logger.error(f"BNO085: {e}")
        results["BNO085"] = False
        
    # BMP388
    try:
        sensor = BMP388Sensor(config.bmp388)
        sensor.read()
        sensor.close()
        results["BMP388"] = True
        logger.success("BMP388 reading successful.")
    except Exception as e:
        logger.error(f"BMP388: {e}")
        results["BMP388"] = False
        
    # PCA9685
    results["PCA9685"] = test_pca9685.quick_check(logger, config)
    results["Servo"] = test_servo.quick_check(logger, config)
    results["Stepper"] = test_stepper.quick_check(logger, config)
    results["Gimbal"] = test_gimbal.quick_check(logger, config)
    results["Camera"] = test_camera.quick_check(logger, config)
    
    # Generate Report
    report = [
        "=====================================",
        "      AVIONICS HARDWARE TEST REPORT",
        "=====================================",
        f"Date: {time.strftime('%Y-%m-%d %H:%M:%S')}",
        ""
    ]
    all_pass = True
    for k, v in results.items():
        status = "PASS" if v else "FAIL"
        if not v: all_pass = False
        report.append(f"{k.ljust(15)} ....... {status}")
    
    report.append("")
    report.append(f"Overall ........ {'PASS' if all_pass else 'FAIL'}")
    report.append("=====================================")
    
    report_text = "\n".join(report)
    print(f"\n\033[1;35m{report_text}\033[0m")
    
    if config.logging.save_logs:
        ensure_directory(config.logging.log_dir)
        fp = config.logging.log_dir / f"test_report_{timestamp_slug()}.txt"
        fp.write_text(report_text, encoding="utf-8")
        logger.success(f"Report saved to {fp}")
    
    # Log to CSV
    logger.log_sensor_data("Test_All_Report", results)
