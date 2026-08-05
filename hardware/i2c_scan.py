"""Scan the I2C bus and identify known devices."""
from __future__ import annotations
import dataclasses
import typing
from dataclasses import dataclass

KNOWN_DEVICES = {
    0x40: "PCA9685 PWM Driver",
    0x48: "ADS1115 ADC",
    0x4A: "BNO085 IMU",
    0x4B: "BNO085 IMU (alt)",
    0x60: "MPL3115A2",
    0x68: "MPU-6050 / DS3231 RTC",
    0x76: "BMP280/BMP388",
    0x77: "BMP280/BMP388 (alt)",
}

@dataclass(frozen=True)
class I2CDevice:
    """Represents an I2C device found on the bus."""
    address: int
    name: str
    
    @property
    def hex_address(self) -> str:
        return f"0x{self.address:02X}"

def scan_i2c(bus: int = 1) -> list[I2CDevice]:
    """Scan the I2C bus and identify connected devices."""
    devices = []
    try:
        import smbus2
        bus_obj = smbus2.SMBus(bus)
        for addr in range(0x03, 0x78):
            try:
                bus_obj.read_byte(addr)
                name = KNOWN_DEVICES.get(addr, "Unknown Device")
                devices.append(I2CDevice(address=addr, name=name))
            except OSError:
                pass
        bus_obj.close()
    except ImportError:
        try:
            import board
            import busio
            i2c = busio.I2C(board.SCL, board.SDA)
            if i2c.try_lock():
                addresses = i2c.scan()
                i2c.unlock()
                for addr in addresses:
                    name = KNOWN_DEVICES.get(addr, "Unknown Device")
                    devices.append(I2CDevice(address=addr, name=name))
        except Exception:
            pass
    return sorted(devices, key=lambda d: d.address)

def print_scan_results(devices: list[I2CDevice]) -> None:
    """Print the results of an I2C scan beautifully."""
    print("\n\033[1;35m=== I2C Bus Scan Results ===\033[0m")
    if not devices:
        print("\033[31mNo I2C devices found.\033[0m")
        return
        
    for dev in devices:
        addr_str = f"\033[36m{dev.hex_address}\033[0m"
        if dev.name == "Unknown Device":
            name_str = f"\033[2m{dev.name}\033[0m"
        else:
            name_str = f"\033[32m{dev.name}\033[0m"
        print(f" Found: {addr_str} -> {name_str}")
        
    print(f"\033[1mTotal devices found: {len(devices)}\033[0m\n")
