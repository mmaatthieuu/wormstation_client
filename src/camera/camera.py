import time
from concurrent.futures import ThreadPoolExecutor
from picamera2 import Picamera2
from picamera2.controls import Controls
from parameters import Parameters


class Camera(Picamera2):
    def __init__(self, parameters):
        self.initialized = False
        # Create a thread pool with two threads
        self.executor = ThreadPoolExecutor(max_workers=2)

        # Initialize the camera in parallel using the thread pool
        self.init_future = self.executor.submit(self._init_camera, parameters)

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

    def __del__(self):
        self.executor.shutdown(wait=True)