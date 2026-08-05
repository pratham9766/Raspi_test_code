"""Configuration loader — reads config.yaml and builds typed config objects."""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Any
import yaml

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG_PATH = BASE_DIR / "config.yaml"

class ConfigurationError(ValueError): ...

from hardware.bno085 import BNO085Config
from hardware.bmp388 import BMP388Config
from hardware.pca9685_driver import PCA9685Config
from hardware.servo import ServoConfig
from hardware.stepper import StepperConfig
from hardware.gimbal import GimbalConfig
from hardware.camera import CameraConfig

@dataclass(frozen=True)
class LoggingConfig:
    save_logs: bool
    level: str
    log_dir: Path
    csv_enabled: bool
    csv_filename: str

@dataclass(frozen=True)
class BoardConfig:
    pin_numbering: str
    i2c_bus: int
    spi_bus: int
    spi_device: int

@dataclass(frozen=True)
class AppConfig:
    board: BoardConfig
    bno085: BNO085Config
    bmp388: BMP388Config
    pca9685: PCA9685Config
    servo: ServoConfig
    stepper: StepperConfig
    gimbal: GimbalConfig
    camera: CameraConfig
    logging: LoggingConfig

def _path(v: str | Path, base: Path) -> Path:
    p = Path(v)
    return p if p.is_absolute() else base / p

def _addr(v: Any) -> int:
    if isinstance(v, int): return v
    return int(str(v), 0)

def load_config(path: str | Path = DEFAULT_CONFIG_PATH) -> AppConfig:
    """Load and validate config.yaml, return typed AppConfig."""
    cfg_path = Path(path)
    if not cfg_path.exists():
        raise ConfigurationError(f"config.yaml not found: {cfg_path}")
    with cfg_path.open('r', encoding='utf-8') as f:
        raw: dict[str, Any] = yaml.safe_load(f) or {}

    try:
        board = BoardConfig(**raw.get('board', {}))
        
        b = raw.get('bno085', {})
        bno085 = BNO085Config(
            interface=b.get('interface', 'i2c'),
            address=_addr(b.get('address', 0x4A)),
            sda_gpio=b.get('sda_gpio', 2),
            scl_gpio=b.get('scl_gpio', 3),
            refresh_hz=b.get('refresh_hz', 10)
        )
        
        bmp = raw.get('bmp388', {})
        bmp388 = BMP388Config(
            interface=bmp.get('interface', 'i2c'),
            address=_addr(bmp.get('address', 0x76)),
            sda_gpio=bmp.get('sda_gpio', 2),
            scl_gpio=bmp.get('scl_gpio', 3),
            sea_level_pressure_hpa=bmp.get('sea_level_pressure_hpa', 1013.25),
            refresh_hz=bmp.get('refresh_hz', 5)
        )
        
        p = raw.get('pca9685', {})
        pca9685 = PCA9685Config(
            interface=p.get('interface', 'i2c'),
            address=_addr(p.get('address', 0x40)),
            frequency_hz=p.get('frequency_hz', 50),
            oe_gpio=p.get('oe_gpio', None),
        )
        
        s = raw.get('servo', {})
        servo = ServoConfig(
            pca9685_channel=s.get('pca9685_channel', 0),
            min_pulse_us=s.get('min_pulse_us', 500),
            max_pulse_us=s.get('max_pulse_us', 2500),
            min_angle=s.get('min_angle', 0),
            max_angle=s.get('max_angle', 180),
            settle_seconds=s.get('settle_seconds', 0.3)
        )
        
        st = raw.get('stepper', {})
        stepper = StepperConfig(**st)
        
        g = raw.get('gimbal', {})
        gimbal = GimbalConfig(
            x_channel=g.get('x_channel', 0),
            y_channel=g.get('y_channel', 1),
            min_angle=g.get('min_angle', 0),
            max_angle=g.get('max_angle', 180),
            center_angle=g.get('center_angle', 90),
            sweep_step_deg=g.get('sweep_step_deg', 5),
            sweep_delay_s=g.get('sweep_delay_s', 0.05),
            min_pulse_us=g.get('min_pulse_us', 500),
            max_pulse_us=g.get('max_pulse_us', 2500),
            settle_seconds=g.get('settle_seconds', 0.05),
        )
        
        c = raw.get('camera', {})
        camera = CameraConfig(
            resolution=tuple(c.get('resolution', [1920, 1080])),
            preview_seconds=c.get('preview_seconds', 5),
            image_dir=_path(c.get('image_dir', 'captures/images'), BASE_DIR),
            video_dir=_path(c.get('video_dir', 'captures/videos'), BASE_DIR),
            video_seconds=c.get('video_seconds', 10),
            timelapse_interval_seconds=c.get('timelapse_interval_seconds', 2.0)
        )
        
        l = raw.get('logging', {})
        logging = LoggingConfig(
            save_logs=l.get('save_logs', True),
            level=l.get('level', 'INFO'),
            log_dir=_path(l.get('log_dir', 'logs'), BASE_DIR),
            csv_enabled=l.get('csv_enabled', True),
            csv_filename=l.get('csv_filename', 'sensor_data.csv')
        )
        
        return AppConfig(board, bno085, bmp388, pca9685, servo, stepper, gimbal, camera, logging)
    except Exception as e:
        raise ConfigurationError(f"Error parsing config.yaml: {e}")
