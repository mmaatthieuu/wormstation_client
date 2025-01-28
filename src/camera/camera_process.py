import sys
import os
import signal
import time

# Dynamically add the project root directory to the Python module search path
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(current_dir, "../../"))
sys.path.insert(0, project_root)


from camera import Camera
from src.parameters import Parameters



def signal_handler(sig, frame):
    """Handle SIGTERM for graceful shutdown."""
    print("[Camera Script] Received termination signal. Exiting...")
    sys.exit(0)


def main():

    # print("[Camera Script] Camera script started.")
    # print("set up the SIGTERM handler")
    # Set up the SIGTERM handler
    signal.signal(signal.SIGTERM, signal_handler)
    # print("load the parameters")
    # Load parameters
    parameters = Parameters(sys.argv[1])

    # Initialize the camera
    # print("[Camera Script] Initializing camera with parameters:", parameters)
    camera = Camera(parameters)

    # print("[Camera Script] Camera initialized. Ready to capture frames.")

    # Wait for commands from the user
    while True:
        try:
            command = input("[Camera Script] Enter command (capture <path> or exit): ").strip()
            if command.lower() == "exit":
                # print("[Camera Script] Exiting.")
                break
            elif command.startswith("capture"):
                _, save_path = command.split(maxsplit=1)
                # print(f"[Camera Script] Capturing frame to {save_path}...")
                camera.capture_frame(save_path)
                # print()
                # Note: \n is crucial for the parent process to read the output
                print(f"\nSUCCESS: Frame saved to {save_path}", flush=True)
                # sys.stdout.flush()
                # print(f"[Camera Script] Frame saved to {save_path}.")
            elif command.startswith("empty"):
                _, save_path = command.split(maxsplit=1)
                print(f"[Camera Script] Capturing empty frame to {save_path}...")
                camera.capture_empty_frame_instance(save_path)
                print(f"\nSUCCESS: Empty frame saved to {save_path}.", flush=True)
            else:
                print("\nERROR: Unknown command.", flush=True)
        except Exception as e:
            print(f"\nERROR: {e}", flush=True)
            break


if __name__ == "__main__":
    main()