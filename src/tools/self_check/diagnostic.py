import shutil
import os
import subprocess
import time

from src.led_control.led_controller import LightController
from src.parameters import Parameters
from src.camera.camera import Camera
from src.upload_manager import SMBManager
from src.log import Logger

class Diagnostic:
    def __init__(self, parameter_filepath):
        self.parameter_filepath = parameter_filepath
        self.parameters = Parameters(parameter_filepath)
        self.logger = Logger(verbosity_level=0)
        self.uploader = None
        self.lights = None

    def NAS_status(self):
        """Check NAS accessibility and mount status."""

        if not hasattr(self, 'uploader') or self.uploader is None:
            # ✅ Create uploader only if not already initialized
            self.uploader = SMBManager(
                nas_server=self.parameters["nas_server"],
                share_name=self.parameters["share_name"],
                credentials_file=self.parameters["credentials_file"],
                working_dir=self.parameters["smb_dir"],
                recording_name=self.parameters["recording_name"],
                logger=self.logger
            )

        nas_accessible = self.uploader.is_accessible()
        nas_mounted = self.uploader.is_mounted()

        return nas_accessible, nas_mounted  # ✅ No need to return uploader

    def mount_NAS(self):
        """Mount the NAS if it's accessible but not already mounted."""

        nas_accessible, nas_mounted = self.NAS_status()

        if nas_mounted:
            return True

        if nas_accessible and not nas_mounted:
            self.uploader.mount()  # ✅ Uses self.uploader directly
            return True
        return False

    def tmp_files(self):
        home_folder = os.path.expanduser("~")
        folder = os.path.join(home_folder, self.parameters["local_tmp_dir"])
        try:
            files = os.listdir(folder)
            return files
        except FileNotFoundError:
            return None

    def running_status(self):
        """Check if there is an active 'picam' process running."""
        result = subprocess.run(["pgrep", "-x", "picam"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return result.returncode == 0  # ✅ Returns True if process exists, False otherwise


    @staticmethod
    def disk_space():
        """
        Get the available disk space on the Raspberry Pi's SD card.

        Returns:
            dict: {
                "total": Total disk space in GB,
                "used": Used disk space in GB,
                "free": Free disk space in GB,
                "percent_free": Free space percentage
            }
        """
        path = "/"  # Root partition (SD card)

        try:
            total, used, free = shutil.disk_usage(path)

            # Convert bytes to GB
            total_gb = round(total / (1024 ** 3), 2)
            used_gb = round(used / (1024 ** 3), 2)
            free_gb = round(free / (1024 ** 3), 2)
            percent_free = round((free / total) * 100, 2)

            return {
                "total": total_gb,
                "used": used_gb,
                "free": free_gb,
                "percent_free": percent_free
            }

        except Exception as e:
            print(f"Error retrieving disk space: {e}")
            return None

    def light_pcb(self):
        if not hasattr(self, 'lights') or self.lights is None:
            # ✅ Create lights only if not already initialized
            self.lights = LightController(parameters=self.parameters, logger=self.logger)
            self.lights.wait_until_ready()

        return self.lights.device_connected

    def LED_test(self, delay=0):
        duration = 0.5
        period = 1
        timeout = 5
        blinking = False
        if self.light_pcb():
            time.sleep(delay)
            for led in self.lights.leds.values():
                led.run_led_timer(duration, period, timeout, blinking)
                led.wait_end_of_led_timer()
            return True
        return False

    def auto_LED_test(self, threshold=50):
        """
        Automatically test LEDs by capturing images and checking brightness levels.

        :param threshold: The minimum average pixel value to consider the LED as ON.
        :return: A dictionary with LED names and their detected states (ON/OFF).
        """

        import numpy as np
        from PIL import Image

        connected = self.light_pcb()
        camera = Camera(parameters=self.parameters)

        hostname = subprocess.check_output(['hostname']).decode().strip()

        colors = ["Orange", "Blue"]
        results = {}

        for color in colors:
            if connected and self.lights[color]:
                self.lights[color].turn_on()

            time.sleep(0.5)  # Allow time for the light to turn on
            image_path = f"test_{color}.jpg"
            camera.capture_frame(image_path)
            time.sleep(0.5)

            # Compute the average of the pixel values
            try:
                image = Image.open(image_path).convert("L")  # Convert to grayscale
                pixel_array = np.array(image)
                avg_pixel_value = np.mean(pixel_array)

                # Determine if the LED is ON or OFF based on the threshold
                led_status = "ON" if avg_pixel_value > threshold else "OFF"
                results[color] = led_status

                self.logger.log(f"LED {color}: Avg Pixel Value = {avg_pixel_value:.2f}, Status = {led_status}",
                                log_level=3)

                # Remove the image file
                os.remove(image_path)

            except Exception as e:
                self.logger.log(f"Error processing image {image_path}: {e}", log_level=1)
                results[color] = "ERROR"

            if connected and self.lights[color]:
                self.lights[color].turn_off()

            time.sleep(0.1)  # Allow time for the light to turn off

        return {"device": hostname, "results": results}




    def camera_status(self):
        # camera = Camera(parameters=self.parameters, partial_init=True)
        return Camera.is_connected()

    def run_all(self):
        results = {
            "NAS_status": self.NAS_status(),
            "disk_space": self.disk_space(),
            "device_running": self.running_status(),
            "tmp_files": self.tmp_files(),
            "light_pcb_connected": self.light_pcb(),
            "camera_connected": self.camera_status(),
            "LED_test": self.LED_test()
        }
        return results