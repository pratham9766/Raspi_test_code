"""Logging utility with terminal colors and CSV export support."""
import csv
import logging
import sys
from pathlib import Path
from utils.helpers import ensure_directory, timestamp_slug

class CSVLogger:
    """Logs data to a CSV file."""
    def __init__(self, filepath: Path):
        self.filepath = filepath
        self.headers_written = False
        ensure_directory(self.filepath.parent)

    def log(self, label: str, data: dict):
        """Append a row of data to CSV."""
        import time
        row = {'timestamp': time.time(), 'label': label}
        row.update(data)
        
        mode = 'a' if self.filepath.exists() else 'w'
        try:
            with self.filepath.open(mode, newline='') as f:
                writer = csv.DictWriter(f, fieldnames=list(row.keys()))
                if not self.headers_written and mode == 'w':
                    writer.writeheader()
                    self.headers_written = True
                writer.writerow(row)
        except Exception:
            pass

class ToolkitLogger:
    """Console logger with colors and CSV integration."""
    def __init__(self, name: str, csv_path: Path | None = None):
        self.logger = logging.getLogger(name)
        self.logger.setLevel(logging.DEBUG)
        if not self.logger.handlers:
            ch = logging.StreamHandler(sys.stdout)
            ch.setLevel(logging.DEBUG)
            formatter = logging.Formatter('%(asctime)s - %(message)s', datefmt='%H:%M:%S')
            ch.setFormatter(formatter)
            self.logger.addHandler(ch)
        
        self.csv_logger = CSVLogger(csv_path) if csv_path else None

    def info(self, msg: str):
        self.logger.info(f"\033[34m{msg}\033[0m")
        
    def success(self, msg: str):
        self.logger.info(f"\033[32m[SUCCESS]\033[0m {msg}")

    def warning(self, msg: str):
        self.logger.warning(f"\033[33m[WARNING]\033[0m {msg}")

    def error(self, msg: str):
        self.logger.error(f"\033[31m[ERROR]\033[0m {msg}")
        
    def log_sensor_data(self, label: str, data: dict):
        if self.csv_logger:
            self.csv_logger.log(label, data)

def build_logger(config) -> ToolkitLogger:
    """Build logger based on config."""
    csv_path = None
    if config.logging.csv_enabled:
        csv_path = config.logging.log_dir / config.logging.csv_filename
    return ToolkitLogger("HardwareTest", csv_path)
