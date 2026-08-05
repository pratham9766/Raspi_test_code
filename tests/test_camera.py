"""Test Camera."""
from hardware.camera import PiCameraSensor

def quick_check(logger, config) -> bool:
    try:
        cam = PiCameraSensor(config=config.camera)
        cam.connect()
        cam.close()
        logger.success("Camera detected and initialized.")
        return True
    except Exception as e:
        logger.error(str(e))
        return False

def run(logger, config):
    cam = PiCameraSensor(config=config.camera)
    try:
        while True:
            print("\n\033[1;36m=== Camera Menu ===\033[0m")
            print("1 Camera Preview")
            print("2 Capture Image")
            print("3 Capture Video")
            print("4 Timelapse (Ctrl+C to stop)")
            print("0 Back")
            choice = input("Select option: ").strip()
            
            if choice == '1':
                logger.info(f"Showing preview for {config.camera.preview_seconds}s...")
                cam.preview()
            elif choice == '2':
                fp = cam.capture_image()
                logger.success(f"Image saved to {fp}")
            elif choice == '3':
                fp = cam.capture_video()
                logger.success(f"Video saved to {fp}")
            elif choice == '4':
                cam.timelapse()
            elif choice == '0': break
            else: logger.warning("Invalid choice.")
    except Exception as e:
        logger.error(f"Camera error: {e}")
    finally:
        cam.close()
