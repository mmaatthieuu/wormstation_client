import numpy as np
import time
import datetime
from socket import gethostname
from PIL import Image as im

from .utils import *

# import picamera
import json
from picamera2 import MappedArray
import cv2

from math import log10, ceil

# from threading import Thread, Lock
import multiprocessing

import psutil
import pathlib

from src.camera import Camera
from src.led_controller import LightController
# from src.tlc5940.tlc import tlc5940
import os
import subprocess
from subprocess import TimeoutExpired
from pathlib import Path

import src.NPImage as npi
from src.log import Logger
from src.upload_manager import SMBManager, SSHManager, EmptyUploader
from src.analyse import Analyser

'''
Verbosity levels:
0: No log
1: Only errors
2: Errors and warnings
3: Errors, warnings and info
4: Errors, warnings, info and debug
5: Errors, warnings, info, debug and trace
6: Errors, warnings, info, debug, trace and verbose
7: Errors, warnings, info, debug, trace, verbose and very verbose
8: Errors, warnings, info, debug, trace, verbose, very verbose and ultra verbose
'''


class Recorder:
    """
    Class Recorder
    """

    def __init__(self, parameters, git_version):
        """
        Constructor
        """
        # Get parameter as argument or create new instance that load json ??
        self.parameters = parameters

        self.logger = Logger(verbosity_level=parameters["verbosity_level"], save_log=self.is_it_useful_to_save_logs())

        self.logger.log("Initializing recorder", log_level=5)
        self.logger.log("Git version : %s" % git_version, log_level=3)

        tmp_folder = self.get_tmp_folder() # Path to the temporary folder
        self.status_file_path = f'{tmp_folder}/status.txt' # Path to the status file

        # Log parameters
        self.logger.log(json.dumps(self.parameters, indent=4), log_level=0)

        # Remark : the directory is created on the NAS before initializing the camera
        # If the camera is initialized first, it produces only black frames...
        # It is weird, but at least it works like that

        self.uploader = EmptyUploader()
        if self.parameters["use_samba"]:
            self.uploader = SMBManager(nas_server=self.parameters["nas_server"],
                                       share_name=self.parameters["share_name"],
                                       credentials_file=self.parameters["credentials_file"],
                                       working_dir=self.parameters["smb_dir"],
                                       recording_name=self.parameters["recording_name"],
                                       logger=self.logger)

            self.uploader.start()

        elif self.parameters["use_ssh"]:
            # Not implemented yet, print some warning and quit
            self.logger.log("SSH upload not implemented yet", log_level=1)
            print("SSH upload not implemented yet")

            return
            # self.uploader = SSHManager(ssh_server=self.parameters["ssh_server"],
            #                            ssh_user=self.parameters["ssh_user"],
            #                            ssh_password=self.parameters["ssh_password"],
            #                            working_dir=self.ssh_output,
            #                            logger=self.logger)





        # Create the camera object with the input parameters
        self.camera = Camera(parameters=self.parameters)

        self.current_frame = None

        self.pause_mode = self.get_pause_mode()
        self.pause_number = 0
        self.pause_time = self.parameters["record_every_h"] * 3600 - self.parameters["record_for_s"]

        self.current_frame_number = 0
        self.number_of_skipped_frames = 0
        self.n_frames_total = self.compute_total_number_of_frames()

        self.compress_step = self.parameters["compress"]

        self.skip_frame = False

        self.output_filename = self.read_output_filename()

        self.initial_time = 0  # will be redefined at the beginning of recording
        # self.delay = 0
        self.start_time_current_frame = 0

        self.optogenetic = self.parameters["optogenetic"]
        self.pulse_duration = self.parameters["pulse_duration"]
        self.pulse_interval = self.parameters["pulse_interval"]

        self.git_version = git_version

        # Initialize the LEDs
        self.lights = LightController(logger=self.logger)


        # subprocess.run(['cpulimit', '-P', '/usr/bin/gzip', '-l', '10', '-b', '-q'])

        # TODO pool instead of single process
        self.compress_process = None
        self.save_process = None

        self.logger.log("Recorder initialized", log_level=5)

    def __del__(self):
        self.stop()

    def stop(self):

        # Turn off all LEDs
        self.lights.turn_off_all_leds()

        self.logger.log("Stopping recording", log_level=3)

        self.update_status('Not Running')

        time.sleep(0.2)
        self.logger.log("Terminated", log_level=3)

    def start_recording(self):
        """
        Main recording function
        """
        # TODO : save json config
        # TODO : add git number to json file and maybe add check if git version is the same as current one ?
        # TODO : confirm parameters & check if folder already exists
        # TODO : check if samba config is working
        # TODO : clean tmp local dir

        # Go to home directory
        self.go_to_tmp_recording_folder()

        self.update_status('Recording')

        # Compute the total number of frame from the recording time and time interval between frames

        self.camera.pre_callback = self.annotate_frame

        self.camera.start()



        if not self.preview_only():
            # If one does an actual recording and not just a preview (i.e. timeout=0)

            # Todo check that
            #print("#DEBUG Starting LED timer with duration %f, period %f, timeout %f" % (self.parameters["illumination_pulse"]/1000,
            #                                                                      self.parameters["time_interval"],
            #                                                                      self.parameters["timeout"]))

            self.lights["IR"].run_led_timer(duration=self.parameters["illumination_pulse"] / 1000,
                                       period=self.parameters["time_interval"],
                                       timeout=self.parameters["timeout"])

            #self.ir_leds.turn_on()

            # wait_time, _ = get_remaining_time_to_next_seconds(time.time(),4)
            # time.sleep(wait_time)
            wait_until_next_even_second()

        else:
            # In case of preview, turn on IR LED to see something
            # self.ir_leds.turn_on()
            self.lights["IR"].turn_on()

        self.initial_time = time.time()

        if self.optogenetic:
            self.lights["Orange"].run_led_timer(duration=self.parameters["pulse_duration"],
                                         period=self.parameters["pulse_interval"],
                                         timeout=self.parameters["timeout"],
                                         blinking=True,
                                         blinking_period=self.parameters["time_interval"])

        # self.create_output_folder()

        if self.parameters["use_samba"] and self.is_it_useful_to_save_logs():
            self.upload_logs()

        # Main recording loop
        for self.current_frame_number in range(self.parameters["start_frame"], self.n_frames_total):
            self.skip_frame = False
            # print(f'frame {self.current_frame_number}')

            if self.is_it_pause_time(self.current_frame_number):
                # pause_time = self.parameters["record_every_h"]*60 - self.parameters["record_for_s"]
                self.pause_recording_in_s(self.pause_time)

            # (Re)Initialize the current frame
            # self.current_frame = np.empty((3040, 4056, 3), dtype=np.uint8)

            # If in advance, wait, otherwise skip frames
            self.wait_or_catchup_by_skipping_frames()

            self.start_time_current_frame = time.time()
            # print(f'frame {self.current_frame_number} start: {self.start_time_current_frame - self.initial_time}')

            try:
                if not self.skip_frame:
                    self.log_progress()

                    ## That was randomly crashing so I used the next method
                    # self.camera.capture_file(self.get_last_save_path())

                    self.capture_frame()

                    ### From the documentation :
                    '''
                    https://datasheets.raspberrypi.com/camera/picamera2-manual.pdf

                    Moving processing out of the camera thread
                    Normally when we use a function like Picamera2.capture_file, 
                    the processing to capture the image, compress it as (for
                    example) a JPEG, and save it to file happens in the usual camera 
                    processing loop. While this happens, the handling of
                    camera events is blocked and the camera system is likely to drop 
                    some frames. In many cases this is not terribly
                    important, but there are occasions when we might prefer all the 
                    processing to happen somewhere else.

                    Just as an example, if we were recording a video and wanted to capture
                     a JPEG simultaneously whilst minimising the
                    risk of dropping any video frames, then it would be beneficial 
                    to move that processing out of the camera loop.

                    This is easily accomplished simply by capturing a request and calling
                     request.save as we saw above. Camera events can
                    still be handled in parallel (though this is somewhat at the mercy of 
                    Python’s multi-tasking abilities), and the only
                    downside is that camera system has to make do with one less set of 
                    buffers until that request is finally released.
                    However, this can in turn always be mitigated by allocating one or 
                    more extra sets of buffers via the camera
                    configuration’s buffer_count parameter.
                    '''
                else:
                    # If frame is skipped, save a black frame to keep continuous numbering
                    self.save_black_frame(self.get_last_save_path())

            except RuntimeError:
                # Never occurs actually
                self.logger.log("Error 2 on frame %d" % self.current_frame_number)

            finally:

                # TODO : write doc about why this check is useful
                if self.get_last_save_path() is not None:
                    # new process for saving
                    # self.save_process = multiprocessing.Process(target=self.save_frame)
                    # self.save_process.start()
                    # self.save_frame()

                    if self.is_time_for_compression():
                        # self.logger.log("time for compression")
                        self.logger.log("Time for compression", log_level=3)
                        self.uploader.start_async_compression_and_upload(dir_to_compress=self.get_current_dir(),
                                                                         format="mkv")

                        if self.parameters["use_samba"] and self.is_it_useful_to_save_logs():
                            # This is overwhelming for pour NAS CPU if done too often
                            self.upload_logs()



                # print(f'end: {datetime.now() - self.initial_datetime}')

        # End of recording
        # Wait for the end of compression

        self.uploader.wait_for_compression()

        self.uploader.upload_remaining_files(self.go_to_tmp_recording_folder())

        self.logger.log("Recording done (Timeout reached)",begin='\n\n', end='\n\n\n',log_level=3)

        # After recording is finished
        self.update_status('Not Running')

        self.upload_logs()





    def capture_frame(self):
        # That is the new method, not crashing
        capture_request = self.camera.capture_request()
        capture_request.save("main", self.get_last_save_path())
        capture_request.release()

        # create link to last frame
        self.create_symlink_to_last_frame()

    def wait_or_catchup_by_skipping_frames(self):
        # Wait
        # Check if the current frame is on time

        delay = self.get_delay()

        # If too early, wait until it is time to record
        # print(delay)
        # print(f'current: {current_timedelta}, exp: {expected_timedelta_for_current_frame}, delay: {delay}')
        if delay < 0:
            try:
                time.sleep(-delay)
            except BlockingIOError:
                self.logger.log("\n\n it failed but still trying")
                time.sleep(-delay)
            if self.parameters["verbosity_level"] >= 2:
                self.logger.log("Waiting for %fs" % -delay)
        elif delay < 0.005:  # We need some tolerance in this world...
            pass  # And go on directly with frame capture
        else:
            # Frame late : log delay
            if self.parameters["verbosity_level"] >= 1:
                # log('Frame %fs late' % -diff_time, begin="\n")
                self.logger.log('Delay : %fs' % delay)

        # Catch up
        # It the frame has more than one time interval of delay, it just skips the frame and directly
        # goes to the next one
        # The condition on current_frame_number is useful if one just wants one frame and does not care about time sync
        if delay >= self.parameters["time_interval"] and \
                self.current_frame_number < (self.n_frames_total - 1) and self.pause_mode is False:
            self.skip_frame = True
            self.logger.log(f"Delay too long : Frame {self.current_frame_number} skipped", begin="\n    WARNING    ")

    def get_delay(self):
        delay = 0
        if self.pause_mode is False:
            delay = time.time() - (self.initial_time +
                                   self.current_frame_number * self.parameters["time_interval"]) + \
                    self.parameters["start_frame"] * self.parameters["time_interval"]

        else:
            delay = time.time() - (self.initial_time +
                                   self.current_frame_number * self.parameters["time_interval"] +
                                   self.pause_number * self.pause_time)

        return delay

    def log_progress(self):
        if self.parameters["verbosity_level"] >= 2:
            self.logger.log(f"Starting capture of frame {self.current_frame_number + 1}"
                            f" / {self.n_frames_total}")
        elif self.parameters["verbosity_level"] == 1:

            self.logger.log(f"Starting capture of frame {self.current_frame_number + 1} "
                            f"/ {self.n_frames_total}", begin="\r", end="")

    def annotate_frame(self, request):
        if self.parameters["annotate_frames"]:

            name = self.parameters["recording_name"]

            colour = (0, 255, 0)
            origin = (0, 40)
            font = cv2.FONT_HERSHEY_SIMPLEX
            scale = 1
            thickness = 2

            string_time = (datetime.now()).strftime('%Y-%m-%d %H:%M:%S.%f')
            string_to_overlay = "%s | %s | %s | %s" % (gethostname(), self.get_filename(), string_time, name)

            try:
                with MappedArray(request, "main") as m:
                    cv2.putText(m.array, string_to_overlay, origin, font, scale, colour, thickness)
            except AttributeError:
                # In case the function is called for a black frame, so the request is actually a np.array and
                # not a picam2 request
                return cv2.putText(request, string_to_overlay, origin, font, scale, colour, thickness)

    def save_frame(self):
        """
        Convert numpy array to image and save it locally
        """
        image = im.fromarray(self.current_frame)

        save_path = self.get_last_save_path()
        image.save(save_path, quality=self.parameters["quality"])

        self.write_extended_attributes(save_path=save_path)

    def save_black_frame(self, path):

        # Create array with the right size, i.e. sensor resolution. The [::-1] reverse the tuple order, otherwise
        # the picture is in portrait mode rather than landscape.
        # The +(3,) is used to append 3 (i.e. the number of RGB channels) to create a RGB image

        zero_array = np.zeros((self.camera.camera_properties["PixelArraySize"])[::-1] + (3,), dtype=np.uint8)
        zero_array = self.annotate_frame(zero_array)
        image = im.fromarray(zero_array)
        image.save(path)

    def is_time_for_compression(self):
        """
        Check if it is time to compress (step number is reached or end of recording and return a bool
        """
        try:
            if self.current_frame_number % self.compress_step == self.compress_step - 1 or \
                    (self.current_frame_number == self.n_frames_total - 1 and self.n_frames_total > 1):
                return True
            else:
                return False
        except TypeError as e:
            self.logger.log(e)
        except ZeroDivisionError as e:
            return False





    def delete_local_files(self, folder_name):
        subprocess.run(['rm', '-rf', '%s' % folder_name])
        subprocess.run(['rm', '-rf', '%s.tgz' % folder_name])


    def get_tmp_folder(self):
        # get name of current user
        user = os.getlogin()
        tmp_folder = f'/home/{user}/tmp'

        return tmp_folder

    def create_symlink_to_last_frame(self):

        tmp_folder = self.get_tmp_folder()

        # check if tmp folder exists
        if not os.path.exists(tmp_folder):
            subprocess.run(['mkdir', '-p', tmp_folder])

        subprocess.run(
            ['ln', '-sf', '%s' % pathlib.Path(self.get_last_save_path()).absolute(), f'{tmp_folder}/last_frame.jpg'])

    ### Other utility functions

    def go_to_tmp_recording_folder(self):
        os.chdir(Path.home())

        # Created directory to save locally the files before upload
        try:
            os.mkdir(self.parameters["local_tmp_dir"])
        except FileExistsError:
            # os.remove(self.parameters["local_tmp_dir"])
            # os.mkdir(self.parameters["local_tmp_dir"])
            pass

        os.chdir(self.parameters["local_tmp_dir"])
        return os.getcwd()

    def get_pause_mode(self):
        if self.parameters["record_for_s"] == 0 or self.parameters["record_every_h"] == 0:
            return False
        else:
            return True

    def is_it_pause_time(self, frame_number):
        if self.pause_mode is False:
            return False
        number_of_frames_per_batch = self.parameters["record_for_s"] // self.parameters["time_interval"]
        if frame_number % number_of_frames_per_batch == 0 and frame_number != 0:
            return True
        else:
            return False

    def pause_recording_in_s(self, time_to_pause):
        """Pause recording for a specified amount of time."""
        self.update_status('Paused')  # Update status to Paused
        self.logger.log(f"Pausing recording for {time_to_pause} seconds ({time_to_pause / 3600} hours)")

        if time_to_pause > 10:
            # If the pause is longer than 10 seconds, turn off the LEDs and pause the LED blinking
            self.lights.turn_off_all_leds()
            self.lights.pause_all_leds()


            # Do the pause and wait for the remaining time minus 3 seconds
            time.sleep(time_to_pause - 3)

            # 5 seconds before the end of the pause, turn the LEDs back on
            self.lights.resume_all_leds()
                # No need to turn them back on here, the process will do it

            self.update_status('Recording')  # Update status back to Recording
            time.sleep(3)  # Wait for the remaining 3 seconds
            self.pause_number += 1
        else:
            # no need to stop the LEDs for a short pause
            time.sleep(time_to_pause)
            self.update_status('Recording')  # Update status back to Recording


        self.logger.log("Recording resumed")


    def update_status(self, status):
        """Update the status file with the current recording status."""
        with open(self.status_file_path, 'w') as f:
            f.write(status)

    def capture_frame_during_pause(self):
        """Capture a new frame during a recording pause."""
        self.logger.log("Capturing a new frame during pause", log_level=3)
        if self.current_frame_number < self.n_frames_total:
            # self.ir_leds.turn_on()
            self.lights["IR"].turn_on()
            time.sleep(0.25)
            self.capture_frame()
            # self.ir_leds.turn_off()
            self.lights["IR"].turn_off()
            self.logger.log(f"Captured frame {self.current_frame_number} during pause", log_level=3)
        else:
            self.logger.log("No frames left to capture", log_level=2)

    def compute_total_number_of_frames(self):
        n_frames = 0
        try:
            if not self.pause_mode:
                n_frames = int(self.parameters["timeout"] / self.parameters["time_interval"])
                if n_frames == 0:
                    n_frames = 1
            else:
                numer_of_acquisitions = int(self.parameters["timeout"] / (self.parameters["record_every_h"] * 3600))

                n_frames = int(
                    self.parameters["record_for_s"] / self.parameters["time_interval"]) * numer_of_acquisitions
                #print(f'number of frames : {n_frames}')
                if n_frames == 0:
                    n_frames = 1
        except ZeroDivisionError:
            n_frames = 1
        finally:
            #print(f'number of frames : {n_frames}')
            return n_frames

    def read_output_filename(self):
        f = self.parameters["output_filename"]
        #print("entered read_output_filename")
        if f == "auto":
            return self.get_needed_output_format()
        else:
            return f

    def get_needed_output_format(self):
        #print("entered get_needed_output_format")
        #print(self.n_frames_total)
        digits = int(ceil(log10(self.n_frames_total)))
        #print(digits)
        if digits == 0:
            digits += 1
        return f'%0{digits}d.jpg'

    def get_last_save_path(self):
        try:
            return os.path.join(self.get_current_dir(), self.get_filename())
        except TypeError:
            return None

    def get_filename(self):
        try:
            # if automatic filename, i.e. filename is %0Xd.jpg
            filename = self.output_filename % self.current_frame_number
        except TypeError:
            filename = self.output_filename
        return filename

    def write_extended_attributes(self, save_path):
        os.setxattr(save_path, 'user.datetime', (str(datetime.now())).encode('utf-8'))
        os.setxattr(save_path, 'user.index', ("%06d" % self.current_frame_number).encode('utf-8'))
        os.setxattr(save_path, 'user.hostname', (os.uname()[1]).encode('utf-8'))
        os.setxattr(save_path, 'user.jpg_quality', ("%02d" % self.parameters["quality"]).encode('utf-8'))
        os.setxattr(save_path, 'user.averaged', ("%d" % self.parameters["average"]).encode('utf-8'))
        os.setxattr(save_path, 'user.git_version', self.git_version.encode('utf-8'))
        os.setxattr(save_path, 'user.skipped', ("%d" % int(self.skip_frame)).encode('utf-8'))

    def get_current_dir(self):

        if self.compress_step > 0:
            part = self.current_frame_number // self.compress_step
            current_dir = "part%02d" % part

            try:
                os.mkdir(current_dir)
            except FileExistsError:
                pass

            return current_dir
        else:
            return "."

    def is_it_useful_to_save_logs(self):
        if self.parameters["timeout"] == 0:
            return False
        try:
            if self.parameters["save_logs"] is False:
                return False
        except KeyError:
            pass
        return True

    def preview_only(self):
        if self.parameters["timeout"] == 0:
            return True
        return False

    def upload_logs(self):
        try:
            self.uploader.upload(file_to_upload=self.logger.get_log_file_path(),
                             filename_at_destination=self.logger.get_log_filename())
        except TypeError:
            pass



