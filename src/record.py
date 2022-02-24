import numpy as np
import time
from datetime import datetime
from socket import gethostname

import picamera


from threading import Thread,Lock


from src.camera import Camera
from src.tlc5940.tlc import tlc5940
import os
import sys
from pathlib import Path
from src.utils import log

import src.NPImage as npi
from src.CrashTimeOutException import CrashTimeOutException



class Recorder:
    """
    Class Recorder
    """
    def __init__(self, parameters):
        """
        Constructor
        """
        # Get parameter as argument or create new instance that load json ??
        self.parameters = parameters

        # Create the camera object with the input parameters
        self.camera = Camera(parameters=self.parameters)


        self.leds = tlc5940(blankpin=27,
                            progpin=22,
                            latchpin=17,
                            gsclkpin=18,
                            serialpin=23,
                            clkpin=24)

        self.leds.initialise()

        self.current_frame = None
        self.current_frame_number = 0
        self.number_of_skipped_frames = 0
        self.n_frames_total = 0
        self.skip_frame = False

        self.initial_time = 0
        self.delay = 0
        self.start_time_current_frame = 0

        #self.output = None
        self.output_lock = Lock()



    def start_recording(self):
        """
        Main recording function
        """

        # Go to home directory
        self.go_to_tmp_recording_folder()

        # Compute the total number of frame from the recording time and time interval between frames
        try:
            self.n_frames_total = int(self.parameters["timeout"]/self.parameters["time_interval"])
            if self.n_frames_total == 0:
                self.n_frames_total = 1
        except ZeroDivisionError:
            self.n_frames_total = 1

        self.initial_time = time.time()



        # Main recording loop
        for self.current_frame_number in range(self.parameters["start_frame"], self.n_frames_total):
            self.skip_frame = False

            # (Re)Initialize the current frame
            self.current_frame = np.empty((2464, 3296), dtype=np.uint8)

            # If in advance, wait, otherwise skip frames
            self.wait_or_catchup_by_skipping_frames()

            self.start_time_current_frame = time.time()
            try:
                if not self.skip_frame:
                    self.log_progress()

                    self.annotate_frame()

                    self.capture_frame()

            except picamera.exc.PiCameraRuntimeError as error:
                log("Error 1 on frame %d" % self.current_frame_number)
                log("Timeout Error : Frame %d skipped" % self.current_frame_number, begin="\n    WARNING    ")
                log(error)
                skip_frame = True
                if self.number_of_skipped_frames == 0:
                    self.number_of_skipped_frames += 1
                    continue
                else:
                    log("Warning : Camera seems stuck... Trying to restart it")
                    raise CrashTimeOutException(self.current_frame_number)
                # sys.exit()



    def wait_or_catchup_by_skipping_frames(self):
        # Wait
        # Check if the current frame is on time
        self.delay = time.time() - (self.initial_time + self.current_frame_number * self.parameters["time_interval"])

        # If too early, wait until it is time to record
        if self.delay < 0:
            time.sleep(-self.delay)
            if self.parameters["verbosity_level"] >= 2:
                log("Waiting for %fs" % -self.delay)
        elif self.delay < 0.01:  # We need some tolerance in this world...
            pass
        else:
            if self.parameters["verbosity_level"] >= 1:
                # log('Frame %fs late' % -diff_time, begin="\n")
                log('Delay : %fs' % self.delay)

        # Catch up
        # It the frame has more than one time interval of delay, it just skips the frame and directly
        # goes to the next one
        # The condition on k is useful if one just want one frame and does not care about time sync
        if self.delay >= self.parameters["time_interval"] and \
                self.current_frame_number < (self.n_frames_total - 1):
            self.skip_frame = True
            log(f"Delay too long : Frame {self.current_frame_number} skipped", begin="\n    WARNING    ")

    def log_progress(self):
        if self.parameters["verbosity_level"] >= 2:
            log(f"Starting capture of frame {self.current_frame_number + 1}"
                f" / {self.n_frames_total}")
        elif self.parameters["verbosity_level"] == 1:
            # print("\r[%s] : Starting capture of frame %d / %d" %
            #      (str(datetime.datetime.now()), k + 1, n_frames_total), end="")
            log(f"Starting capture of frame {self.current_frame_number + 1} "
                f"/ {self.n_frames_total}", begin="\r", end="")


    def annotate_frame(self):
        if self.parameters["annotate_frames"]:
            string_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            string_to_overlay = "%s | %s" % (gethostname(), string_time)

            self.camera.annotate_text = string_to_overlay

    def save_pic_to_frame(self, new_pic):
        self.output_lock.acquire()
        self.current_frame = self.current_frame + new_pic // self.parameters["average"]
        self.output_lock.release()

    def capture_frame(self):
        output = npi.NPImage()
        self.output_lock = Lock()

        threads = [None] * self.parameters["average"]
        for i, fname in enumerate(
                self.camera.capture_continuous(output,
                                               'yuv', use_video_port=False, burst=False)):

            # Send the computation and saving of the new pic to separated thread
            threads[i] = Thread(target=self.save_pic_to_frame, args=(output.get_data()))
            threads[i].start()
            # print(threads[i])

            # Frame has been taken so we can reinitialize the number of skipped frames
            self.number_of_skipped_frames = 0

            if i == self.parameters["average"] - 1:
                break
        for t in threads:
            t.join()



### Other utility functions

    def go_to_tmp_recording_folder(self):
        os.chdir(Path.home())

        # Created directory to save locally the files before upload
        try:
            os.mkdir(self.parameters["local_tmp_dir"])
            print("dir created")
        except FileExistsError:
            pass

        os.chdir(self.parameters["local_tmp_dir"])