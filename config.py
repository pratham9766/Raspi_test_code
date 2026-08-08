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
from hardware.gimbal import (
    GimbalConfig,
    GimbalServoConfig,
    GimbalOEConfig,
    GimbalStepperConfig,
    GimbalBNO085Config,
    GimbalSafetyConfig,
)
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
        
        g   = raw.get('gimbal', {})
        gs  = g.get('servo', {})
        god = g.get('servo_driver', {})
        gst = g.get('stepper', {})
        gb  = g.get('bno085', {})
        gsa = g.get('safety', {})

        gimbal = GimbalConfig(
            servo=GimbalServoConfig(
                channel=int(gs.get('channel', 0)),
                center_angle=float(gs.get('center_angle', 90)),
                min_angle=float(gs.get('min_angle', 30)),
                max_angle=float(gs.get('max_angle', 150)),
                step_angle=float(gs.get('step_angle', 5)),
                min_pulse_us=int(gs.get('min_pulse_us', 500)),
                max_pulse_us=int(gs.get('max_pulse_us', 2500)),
                settle_s=float(gs.get('settle_s', 0.3)),
            ),
            servo_driver=GimbalOEConfig(
                oe_gpio=int(god.get('oe_gpio', 4)),
                active_low=bool(god.get('active_low', True)),
            ),
            stepper=GimbalStepperConfig(
                motor=gst.get('motor', '28BYJ-48'),
                driver_ic=gst.get('driver_ic', 'ULN2003'),
                in1_gpio=int(gst.get('in1_gpio', 18)),
                in2_gpio=int(gst.get('in2_gpio', 23)),
                in3_gpio=int(gst.get('in3_gpio', 24)),
                in4_gpio=int(gst.get('in4_gpio', 25)),
                sequence=gst.get('sequence', 'half_step'),
                step_delay_ms=float(gst.get('step_delay_ms', 4)),
                direction_inverted=bool(gst.get('direction_inverted', False)),
                max_relative_steps=int(gst.get('max_relative_steps', 2000)),
            ),
            bno085=GimbalBNO085Config(
                enabled=bool(gb.get('enabled', True)),
                feedback_enabled=bool(gb.get('feedback_enabled', False)),
                refresh_hz=int(gb.get('refresh_hz', 10)),
                bno_roll_to_x=bool(gb.get('bno_roll_to_x', False)),
                bno_pitch_to_y=bool(gb.get('bno_pitch_to_y', True)),
                kp_y=float(gb.get('kp_y', 0.3)),
                deadband_deg=float(gb.get('deadband_deg', 2.0)),
                max_servo_correction_deg=float(gb.get('max_servo_correction_deg', 10.0)),
            ),
            safety=GimbalSafetyConfig(
                require_confirmation=bool(gsa.get('require_confirmation', True)),
                disable_outputs_on_exit=bool(gsa.get('disable_outputs_on_exit', True)),
            ),
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
