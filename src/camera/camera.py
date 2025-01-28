import time
from concurrent.futures import ThreadPoolExecutor
from picamera2 import Picamera2, MappedArray
from picamera2.controls import Controls
from src.parameters import Parameters
import os
import subprocess
from socket import gethostname
from datetime import datetime
import cv2
import select
import threading
import signal


class Camera(Picamera2):
    def __init__(self, parameters, partial_init=False):
        self.initialized = False
        # Create a thread pool with two threads
        self.executor = ThreadPoolExecutor(max_workers=2)

        self.recording_name = parameters["recording_name"]

        # Initialize the camera in parallel using the thread pool
        self.init_future = self.executor.submit(self._init_camera, parameters)

        # Wait for the camera to initialize
        self.wait_for_init()

        if not partial_init:
            # start the camera
            self.start()

    def _init_camera(self, parameters):
        # Submit tasks to configure the camera and set controls concurrently
        config_future = self.executor.submit(self._init_config)
        control_future = self.executor.submit(self._set_controls, parameters)

        # Wait for both tasks to complete
        config_future.result()
        control_future.result()

        self.initialized = True

    def _init_config(self):
        super(Camera, self).__init__()
        config = self.create_still_configuration()
        self.configure(config)

    def _set_controls(self, parameters):
        try:
            framerate = 1000000 / parameters["shutter_speed"]
        except ZeroDivisionError:
            framerate = 20

        framerate = min(framerate, 20)

        ctrls = Controls(self)
        ctrls.AnalogueGain = 1.0
        ctrls.ExposureTime = parameters["shutter_speed"]
        ctrls.AeEnable = False
        ctrls.AwbEnable = False
        ctrls.ColourGains = (1.0, 1.0)
        self.set_controls(ctrls)

    def wait_for_init(self):
        # Ensure the camera initialization is complete
        self.init_future.result()

    def capture_frame(self, save_path):
        if not self.initialized:
            raise RuntimeError("Camera is not initialized")

        # print(f"Capturing frame to {save_path}...")
            # That is the new method, not crashing
        capture_request = self.capture_request()
        # print(f"Capture request: {capture_request}")

        self.annotate_frame(capture_request, save_path, self.recording_name)

        capture_request.save("main", save_path)
        # print(f"Capture request saved to {save_path}")
        capture_request.release()

        # print(f"Frame saved to {save_path}.")

        self.create_symlink_to_last_frame(save_path)

        # print(f"Symlink created to {save_path}")

    def capture_empty_frame_instance(self, save_path):
        Camera.capture_empty_frame(save_path, self.get_frame_dimensions(), self.recording_name)

    @staticmethod
    def capture_empty_frame(save_path, frame_dimensions, recording_name):
        import numpy as np
        from PIL import Image as im

        zero_array = np.zeros((frame_dimensions)[::-1] + (3,), dtype=np.uint8)
        zero_array = Camera.annotate_frame(zero_array, save_path, recording_name)
        image = im.fromarray(zero_array)
        image.save(save_path)

    @staticmethod
    def annotate_frame(request, filepath, recording_name):

        filename = os.path.basename(filepath)

        # Text overlay settings
        colour = (0, 255, 0)
        origin = (0, 40)
        font = cv2.FONT_HERSHEY_SIMPLEX
        scale = 1
        thickness = 2

        # Generate overlay text
        string_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')
        string_to_overlay = f"{gethostname()} | {filename} | {string_time} | {recording_name}"

        try:
            # Access the array data with MappedArray
            with MappedArray(request, "main") as m:
                # Directly add text using OpenCV
                cv2.putText(m.array, string_to_overlay, origin, font, scale, colour, thickness)

        except AttributeError:
            # Fallback if request is already a numpy array (e.g., black frame)
            cv2.putText(request, string_to_overlay, origin, font, scale, colour, thickness)
            return request

    def get_frame_dimensions(self):
        return self.camera_properties["PixelArraySize"]

    @staticmethod
    def get_tmp_folder():
        # get name of current user
        user = os.getlogin()
        tmp_folder = f'/home/{user}/tmp'

        return tmp_folder

    @staticmethod
    def create_symlink_to_last_frame(saved_path):

        # print(f"Creating symlink to {saved_path}")

        tmp_folder = Camera.get_tmp_folder()

        # check if tmp folder exists
        if not os.path.exists(tmp_folder):
            subprocess.run(['mkdir', '-p', tmp_folder])

        subprocess.run(
            ['ln', '-sf', '%s' % os.path.abspath(saved_path), f'{tmp_folder}/last_frame.jpg'])

    @staticmethod
    def is_connected():
        try:
            result = subprocess.run(['libcamera-hello', '-t', '1', "-n"],
                                    stderr=subprocess.DEVNULL,
                                    text=True)
            if result.returncode == 0:
                # print("[INFO] Camera is working.")
                return True
            else:
                # print(f"[WARN] Camera not available.")
                return False
        except Exception as e:
            print(f"[ERROR] Failed to run libcamera-hello: {e}")
            return False

    def __del__(self):
        self.executor.shutdown(wait=True)


class CameraController:
    def __init__(self, parameters_path, logger, safe_mode=False):
        """
        Initialize the camera controller.
        :param parameters_path: Path to the recording parameters file.
        :param logger: Logger object for logging messages.
        :param safe_mode: If True, the controller is able to store back frames if camera process is not responding
        """
        # get current path
        current_path = os.path.abspath(os.path.dirname(os.path.realpath(__file__)))
        script_path = f'{current_path}/camera_process.py'

        self.logger = logger

        # print(f"script_path: {script_path}")

        self.script_path = script_path
        self.parameters_path = parameters_path
        self.process = None

        self.camera_available = False

        self.command_thread = None

        self.safe_mode = safe_mode


        self.frame_dimensions = None
        self.parameters = Parameters(parameters_path)
        if self.safe_mode:
            with Camera(self.parameters, partial_init=True) as camera:
                self.frame_dimensions = camera.get_frame_dimensions()
                camera.close()


    def start(self):
        """Start the camera script."""
        cmd = ["python", "-u", self.script_path]
        if self.parameters_path:
            cmd.append(self.parameters_path)
        self.logger.log(f"Starting camera script with command: {' '.join(cmd)}", log_level=3)
        self.process = subprocess.Popen(cmd,
                                        stdin=subprocess.PIPE,
                                        stdout=subprocess.PIPE,
                                        stderr=subprocess.PIPE,
                                        text=True,
                                        universal_newlines=True,
                                        bufsize=1,
                                        preexec_fn=os.setsid)
        self.camera_available = True
        # print("[Main Script] Camera script started.")
        self.logger.log("Camera script successfully started.", log_level=3)


    def send_command(self, command, timeout=10):
        """Send a command to the camera script in a dedicated thread with a timeout."""
        response = {"success": False, "error": None}  # Shared dictionary for response
        self.command_thread = threading.Thread(target=self._send_command_thread, args=(command, response))
        self.command_thread.start()

        # Wait for the thread to complete or timeout
        self.command_thread.join(timeout)

        if self.command_thread.is_alive():
            # print(f"Timeout reached. Command '{command}' did not complete in {timeout} seconds.")
            # Optionally, terminate the process or handle the timeout case
            response["error"] = TimeoutError(f"Command '{command}' timed out.")
            self.command_thread.join(1)  # Ensure the thread finishes execution
            self.logger.log(f"Command thread terminated due to timeout.", log_level=5)
            # print(f"Thread terminated.")

        # Return the response from the thread
        if response["error"]:
            if isinstance(response["error"], TimeoutError):
                # print(f"TimeoutError: {response['error']}. Restarting camera script.")
                self.logger.log(f"TimeoutError: {response['error']}."
                                f" Restarting camera script.", log_level=1)
                self.restart()

            raise response["error"]
        return response["success"]

    def _send_command_thread(self, command, response, timeout=4):
        """Send a command to the camera script and wait for a response."""
        if not self.process:
            raise RuntimeError("Camera script is not running.")

        # print(f"[Main Script] Sending command to camera script: {command}")
        try:
            # Write the command
            self.process.stdout.flush()
            self.process.stdin.write(command + "\n")
            self.process.stdin.flush()

            # Wait for response
            start_time = time.time()
            while True:
                # print(f'Elapsed time : {time.time() - start_time}')
                if self.process.stdout.readable():

                    line = self.process.stdout.readline().strip()
                    if line:
                        # print(f"[Main Script] Camera script response: {line}")
                        # print(f"[Main Script] Camera script response: {line}")
                        if line.startswith("SUCCESS"):
                            # print(f"[Main Script] Command successful: {line}")
                            # print(f'Elapsed time success: {time.time() - start_time}')
                            response["success"] = True
                            return True
                        elif line.startswith("ERROR"):
                            # print(f'Elapsed time error: {time.time() - start_time}')
                            response["error"] = RuntimeError(f"Camera script error: {line}")
                            # raise RuntimeError(f"Camera script error: {line}")
                            return False


                if time.time() - start_time > timeout:
                    # print(f'Elapsed time wait: {time.time() - start_time}')
                    response["error"] = TimeoutError("Camera script response timed out.")
                    return False
                    # raise TimeoutError("Camera script response timed out.")

        except Exception as e:
            # print(f"[Main Script] Error sending command: {e}")
            response["error"] = e
            raise

    def capture_frame(self, save_path):
        """Capture a frame and ensure the action is completed."""
        try:
            if not self.camera_available:
                # print("[Main Script] Camera not available. Capturing empty frame.")
                self.capture_empty_frame(save_path)
                raise RuntimeError("Camera not available.")

            if self.command_thread and self.command_thread.is_alive():
                # print("[Main Script] The previous command is still running. Getting empty frame")
                self.capture_empty_frame(save_path)
                raise RuntimeError("The previous request is still running.")

            ok = self.send_command(f"capture {save_path}", timeout=2)
            # print(f"[Main Script] Frame successfully saved to {save_path}")
            return ok
        except Exception:
            # print(f"[Main Script] Error capturing frame: {e}")
            raise

    def capture_empty_frame(self, save_path):
        """Capture an empty frame using the camera script."""
        if self.camera_available:
            try:
                self.send_command(f"empty {save_path}")
            except Exception as e:
                # print(f"[Main Script] Error capturing empty frame: {e}")
                self.logger.log(f"Error capturing empty frame: {e}", log_level=1)
                raise
        elif self.safe_mode:
            try:
                Camera.capture_empty_frame(save_path, self.frame_dimensions, self.parameters["recording_name"])
            except Exception as e:
                # print(f"[Main Script] Error capturing empty frame: {e}")
                self.logger.log(f"Error capturing empty frame: {e}", log_level=1)


    def stop(self):
        """Stop the camera script."""
        # print("[CamerController] Stopping camera script...")
        self.camera_available = False
        self.logger.log("Stopping camera script...", log_level=3)
        if self.process:
            # print("[Main Script] Stopping camera script...")
            self.logger.log("Stopping camera script...", log_level=3)
            try:
                os.killpg(os.getpgid(self.process.pid), signal.SIGTERM)
            except:
                # print("[Main Script] Error stopping camera script.")
                self.logger.log("Error stopping camera script.", log_level=1)
            # self.process.terminate()
            try:
                self.process.wait(timeout=5)
                # print("[Main Script] Camera script stopped.")
            except subprocess.TimeoutExpired:
                # print("[Main Script] Force killing camera script.")
                self.logger.log("Force killing camera script.", log_level=2)
                self.process.kill()

        self.logger.log("Camera script stopped.", log_level=2)

    def restart(self):
        """Restart the camera script."""
        # print("[Main Script] Restarting camera script...")
        self.logger.log("Restarting camera script...", log_level=2)
        self.stop()
        self.wait_for_camera()

    def wait_for_camera(self):
        """Wait for the camera script to complete."""
        thread = threading.Thread(target=self._wait_for_camera_thread)
        thread.start()


    def _wait_for_camera_thread(self):
        """Wait for the camera script to complete."""
        while not self.check_camera():
            time.sleep(4)
        self.logger.log("Camera script is back !.", log_level=3)
        self.start()

    @staticmethod
    def check_camera():
        """Check if the camera is available."""
        return Camera.is_connected()
