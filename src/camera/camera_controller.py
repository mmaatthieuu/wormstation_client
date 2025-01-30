import os
import signal
import subprocess
import threading
import time

from src.camera.camera import Camera
from src.parameters import Parameters


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

            ok = self.send_command(f"capture {save_path}", timeout=5)
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
