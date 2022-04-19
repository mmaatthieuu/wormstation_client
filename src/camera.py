import picamera
import time

from src.cam_lib import *
from parameters import Parameters


class Camera(picamera.PiCamera):
    def __init__(self, parameters):

        try:
            framerate = 1000000 / parameters["shutter_speed"]
        except ZeroDivisionError:
            framerate = 20

        if framerate > 20:
            framerate = 20

        super(Camera, self).__init__(resolution='3296x2464', framerate=framerate)

        self.iso = parameters["ISO"]
        #self.framerate = 1000000 / (parameters["shutter_speed"])
        #self.framerate = 0.1
        picamera.PiCamera.CAPTURE_TIMEOUT = parameters["capture_timeout"]



        if parameters["verbosity_level"] > 0:
            log("Starting camera...")
        #time.sleep(1)

        self.exposure_mode = "off"
        #g = self.awb_gains
        self.awb_mode = "off"
        self.awb_gains = 1

        # fix the shutter speed
        self.shutter_speed = parameters["shutter_speed"]

        set_analog_gain(self, 1)
        set_digital_gain(self, 1)

        #time.sleep(0.5)
        self.brightness = parameters["brightness"]
        #print(self.brightness)

        log("Camera successfully started")
        log(f"Actual shutter speed : {self.shutter_speed}")

    def __del__(self):
        log("Closing camera")
        self.close()
