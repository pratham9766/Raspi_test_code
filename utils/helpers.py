"""General helper functions for hardware interfacing."""
import os
import subprocess
import time
from pathlib import Path

class HardwareError(Exception):
    """Custom exception for hardware failures."""
    pass

def ensure_directory(path: str | Path) -> None:
    """Ensure a directory exists."""
    Path(path).mkdir(parents=True, exist_ok=True)

def timestamp_slug() -> str:
    """Generate a slugified timestamp."""
    return time.strftime("%Y%m%d_%H%M%S")

def list_spi_devices() -> list[str]:
    """List available SPI devices in /dev."""
    if not os.path.exists("/dev"):
        return []
    return [f"/dev/{d}" for d in os.listdir("/dev") if d.startswith("spidev")]

def run_command(cmd: list[str]) -> str:
    """Run a system command and return output."""
    try:
        return subprocess.check_output(cmd, text=True, stderr=subprocess.STDOUT).strip()
    except subprocess.CalledProcessError as e:
        return e.output.strip()
