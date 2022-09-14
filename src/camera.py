#import picamera
import time

from picamera2 import Picamera2
from picamera2.controls import Controls

from src.cam_lib import *
from parameters import Parameters


class Camera(Picamera2):
    def __init__(self, parameters):

        try:
            framerate = 1000000 / parameters["shutter_speed"]
        except ZeroDivisionError:
            framerate = 20

        if framerate > 20:
            framerate = 20

        super(Camera, self).__init__()

        config = self.create_still_configuration()



        self.configure(config)

        ctrls = Controls(self)
        ctrls.AnalogueGain = 1.0
        # ctrls.DigitalGain = 1.0
        ctrls.ExposureTime = 10000
        ctrls.AeEnable = False
        ctrls.AwbEnable = False
        ctrls.ColourGains = (1.0, 1.0)

        self.set_controls(ctrls)

        #self.pre_callback = apply_timestamp


    def __del__(self):
        log("Closing camera")
        self.close()


