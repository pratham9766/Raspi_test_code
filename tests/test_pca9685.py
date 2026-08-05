"""Test PCA9685 PWM driver."""
from hardware.pca9685_driver import PCA9685Driver

def quick_check(logger, config) -> bool:
    try:
        drv = PCA9685Driver(address=config.pca9685.address, frequency_hz=config.pca9685.frequency_hz, oe_gpio=config.pca9685.oe_gpio)
        drv.connect()
        drv.close()
        logger.success(f"PCA9685 detected at {hex(config.pca9685.address)}")
        return True
    except Exception as e:
        logger.error(str(e))
        return False

def run(logger, config):
    try:
        drv = PCA9685Driver(address=config.pca9685.address, frequency_hz=config.pca9685.frequency_hz, oe_gpio=config.pca9685.oe_gpio)
        drv.connect()
        logger.info("PCA9685 Initialized. Press enter to test channel 0 sweep or Ctrl+C to exit.")
        input()
        for i in range(101):
            drv.set_channel_duty(0, i / 100.0)
            import time; time.sleep(0.01)
        drv.disable_channel(0)
        drv.close()
        logger.success("PCA9685 test complete.")
    except Exception as e:
        logger.error(f"PCA9685 Test Failed: {e}")
