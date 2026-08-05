"""Comprehensive system information for Raspberry Pi 5."""
from __future__ import annotations
import os, platform, shutil, socket, subprocess
from dataclasses import dataclass
from pathlib import Path

@dataclass(frozen=True)
class SystemInfo:
    hostname: str
    ip_address: str
    os_version: str
    python_version: str
    cpu_temperature_c: float | None
    cpu_usage_percent: float | None
    ram_used_mb: float
    ram_total_mb: float
    disk_used_gb: float
    disk_total_gb: float
    i2c_enabled: bool
    spi_enabled: bool
    camera_detected: bool
    uptime_seconds: float | None

def _cpu_temp() -> float | None:
    try:
        with open("/sys/class/thermal/thermal_zone0/temp", "r") as f:
            return float(f.read().strip()) / 1000.0
    except Exception:
        return None

def _cpu_usage() -> float | None:
    try:
        with open("/proc/stat", "r") as f:
            fields = [float(column) for column in f.readline().strip().split()[1:]]
        idle, total = fields[3], sum(fields)
        return 100.0 * (1.0 - idle / total)
    except Exception:
        return None

def _ram() -> tuple[float, float]:
    try:
        total, used = 0.0, 0.0
        with open("/proc/meminfo", "r") as f:
            for line in f:
                if line.startswith("MemTotal:"):
                    total = float(line.split()[1]) / 1024.0
                elif line.startswith("MemAvailable:"):
                    avail = float(line.split()[1]) / 1024.0
                    used = total - avail
        return used, total
    except Exception:
        return 0.0, 0.0

def _disk() -> tuple[float, float]:
    try:
        total, used, free = shutil.disk_usage("/")
        return used / (1024**3), total / (1024**3)
    except Exception:
        return 0.0, 0.0

def _i2c_enabled() -> bool:
    return os.path.exists("/dev/i2c-1")

def _spi_enabled() -> bool:
    return os.path.exists("/dev/spidev0.0")

def _camera_detected() -> bool:
    try:
        subprocess.check_output(["libcamera-hello", "--list-cameras"], stderr=subprocess.STDOUT)
        return True
    except Exception:
        return False

def _uptime() -> float | None:
    try:
        with open("/proc/uptime", "r") as f:
            return float(f.readline().split()[0])
    except Exception:
        return None

def _ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"

def get_system_info() -> SystemInfo:
    """Retrieve full system information."""
    ram_u, ram_t = _ram()
    disk_u, disk_t = _disk()
    
    os_ver = "Unknown"
    try:
        with open("/etc/os-release", "r") as f:
            for line in f:
                if line.startswith("PRETTY_NAME="):
                    os_ver = line.split("=")[1].strip().strip('"')
    except Exception:
        os_ver = platform.system() + " " + platform.release()

    return SystemInfo(
        hostname=socket.gethostname(),
        ip_address=_ip(),
        os_version=os_ver,
        python_version=platform.python_version(),
        cpu_temperature_c=_cpu_temp(),
        cpu_usage_percent=_cpu_usage(),
        ram_used_mb=ram_u,
        ram_total_mb=ram_t,
        disk_used_gb=disk_u,
        disk_total_gb=disk_t,
        i2c_enabled=_i2c_enabled(),
        spi_enabled=_spi_enabled(),
        camera_detected=_camera_detected(),
        uptime_seconds=_uptime()
    )

def print_system_info(info: SystemInfo) -> None:
    """Pretty print system info."""
    print("\n\033[1;36m=== SYSTEM INFORMATION ===\033[0m")
    print(f"Hostname:    {info.hostname}")
    print(f"IP Address:  {info.ip_address}")
    print(f"OS Version:  {info.os_version}")
    print(f"Python:      {info.python_version}")
    print(f"Uptime:      {info.uptime_seconds:.1f}s" if info.uptime_seconds else "Uptime: N/A")
    
    temp = f"{info.cpu_temperature_c:.1f}°C" if info.cpu_temperature_c else "N/A"
    print(f"CPU Temp:    {temp}")
    
    cpu = f"{info.cpu_usage_percent:.1f}%" if info.cpu_usage_percent else "N/A"
    print(f"CPU Usage:   {cpu}")
    
    print(f"RAM Usage:   {info.ram_used_mb:.1f} MB / {info.ram_total_mb:.1f} MB")
    print(f"Disk Usage:  {info.disk_used_gb:.1f} GB / {info.disk_total_gb:.1f} GB")
    
    i2c = "\033[32mYes\033[0m" if info.i2c_enabled else "\033[31mNo\033[0m"
    spi = "\033[32mYes\033[0m" if info.spi_enabled else "\033[31mNo\033[0m"
    cam = "\033[32mYes\033[0m" if info.camera_detected else "\033[31mNo\033[0m"
    
    print(f"I2C Enabled: {i2c}")
    print(f"SPI Enabled: {spi}")
    print(f"Camera:      {cam}")
    print("==========================\n")
