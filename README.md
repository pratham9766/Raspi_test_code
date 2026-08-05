# Raspberry Pi 5 Hardware Test Utility

![Python 3.13](https://img.shields.io/badge/python-3.13-blue.svg)
![Platform Pi 5](https://img.shields.io/badge/platform-Raspberry_Pi_5-red.svg)
![License MIT](https://img.shields.io/badge/license-MIT-green.svg)

## Overview
Avionics-grade test toolkit for Raspberry Pi 5 hardware validation. This repository contains structured, production-ready code to validate sensors, motor controllers, and cameras.

## Hardware

| Device | Interface | Pins | Address/Channel |
|--------|-----------|------|-----------------|
| BNO085 | I2C | SDA=2, SCL=3 | 0x4A |
| BMP388 | SPI | SCK=11, MOSI=10, MISO=9, CS=22 | CS GPIO22 |
| PCA9685 | I2C | SDA=2, SCL=3 | 0x40 |
| Servo | PCA9685 | Channel 0 | Ch 0 |
| Stepper | GPIO | 18, 23, 24, 25 | N/A |
| Camera | MIPI | CSI Port | N/A |

## Wiring Table

Detailed wiring maps exactly to the Hardware table. Please review `config.yaml` to customize pins as needed.

## Installation

1. Clone repo
2. Create venv: `python3 -m venv venv && source venv/bin/activate`
3. `pip install -r requirements.txt`
4. Enable I2C and SPI via `sudo raspi-config`
5. `python main.py`

## Configuration
Edit `config.yaml` to adjust the settings. The new architecture abstracts all logic into cleanly separated configuration dataclasses.

## Usage
Simply run `python main.py` and interact with the 13-option CLI menu to test individual components or run the automated test suite.

## Project Structure
- `config.yaml` / `config.py`: Core configuration loading
- `hardware/`: Drivers for PCA9685, BNO085, BMP388, Servo, Stepper, Camera, Gimbal
- `utils/`: System info and logging abstractions
- `tests/`: Module-specific unit tests integrated with the interactive menu
- `main.py` / `menu.py`: Execution entrypoints

## Architecture Notes
Note: designed for future rocket avionics integration. Clean hardware abstraction layers allow components to be easily reused in flight software.
