import picamera
import time

from src.cam_lib import *
from parameters import Parameters


class Camera(picamera.PiCamera):
    def __init__(self, parameters):
        super(Camera, self).__init__(resolution='3296x2464')

        self.iso = parameters["ISO"]

        picamera.PiCamera.CAPTURE_TIMEOUT = parameters["capture_timeout"]

        if parameters["verbosity_level"] > 0:
            log("Starting camera...")
        time.sleep(1)

        g = self.awb_gains
        self.awb_mode = "off"
        self.awb_gains = g

        # fix the shutter speed
        self.shutter_speed = parameters["shutter_speed"]

        set_analog_gain(self, 1)
        set_digital_gain(self, 1)

        time.sleep(0.5)
        self.brightness = parameters["brightness"]
        #print(self.brightness)

        log("Camera successfully started")

    def __del__(self):
        log("Closing camera")
        self.close()
