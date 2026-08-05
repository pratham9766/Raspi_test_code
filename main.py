"""Main entry point for Raspberry Pi 5 Hardware Test Utility."""
import sys
from config import load_config, ConfigurationError
from utils.logger import build_logger
from menu import run_menu

def main():
    try:
        config = load_config()
    except ConfigurationError as e:
        print(f"\033[31mConfiguration Error:\033[0m {e}")
        sys.exit(1)
        
    logger = build_logger(config)
    try:
        run_menu(logger, config)
    except KeyboardInterrupt:
        print("\n")
        logger.info("Program interrupted by user.")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
