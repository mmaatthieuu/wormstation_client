from concurrent.futures import ThreadPoolExecutor
from picamera2 import Picamera2, MappedArray
from picamera2.controls import Controls
import os
import subprocess
from socket import gethostname
from datetime import datetime
import cv2


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


