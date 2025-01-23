import datetime
import json

from math import log10, ceil

from src.camera.camera import CameraController
from src.led_control.led_controller import LightController
from src.parameters import Parameters

import os
import subprocess

from src.log import Logger
from src.upload_manager import SMBManager, EmptyUploader
from src.utils import *

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

    def __init__(self, parameter_file, git_version):
        """
        Constructor
        """
        # Get parameter as argument or create new instance that load json ??
        self.parameter_file = parameter_file
        self.parameters = Parameters(parameter_file)

        self.logger = Logger(verbosity_level=self.parameters["verbosity_level"], save_log=self.is_it_useful_to_save_logs())

        self.logger.log("Initializing recorder", log_level=5)
        self.logger.log("Git version : %s" % git_version, log_level=3)

        self.status_file_path = f'{self.get_tmp_folder()}/status.txt' # Path to the status file

        # Log parameters
        self.logger.log(json.dumps(self.parameters, indent=4), log_level=0)

        # Create the camera object with the input parameters
        # self.camera = Camera(parameters=self.parameters)
        safe_mode = True
        if self.preview_only():
            safe_mode = False
        self.camera = CameraController(parameters_path=parameter_file, logger=self.logger, safe_mode=safe_mode)
        self.camera.start()

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






        self.pause_mode = self.get_pause_mode()
        self.pause_number = 0
        self.pause_time = self.parameters["record_every_h"] * 3600 - self.parameters["record_for_s"]

        self.current_frame_number = 0
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
        self.lights = LightController(parameters=self.parameters, logger=self.logger, enable_legacy_gpio_mode=True)


        # TODO pool instead of single process
        self.compress_process = None
        self.save_process = None

        self.logger.log("Recorder initialized", log_level=5)

    def __del__(self):
        self.stop()

    def stop(self):

        # Turn off all LEDs
        #self.lights.turn_off_all_leds()

        self.camera.stop()

        self.logger.log("Stopping recording", log_level=3)

        self.update_status('Not Running')

        self.lights.close()

        time.sleep(0.2)
        self.logger.log("Terminated", log_level=3)

    def start_recording(self):
        """
        Main recording function
        """
        # TODO : confirm parameters & check if folder already exists
        # TODO : clean tmp local dir


        # Go to home directory
        self.go_to_tmp_recording_folder()

        self.update_status('Recording')

        self.lights.wait_until_ready()

        if not self.preview_only():
            # If one does an actual recording and not just a preview (i.e. timeout=0)

            self.lights.start()


            wait_until_next_even_second()

        else:
            # In case of preview, turn on IR LED to see something
            try:
                self.lights["IR"].turn_on()
            except AttributeError:
                self.logger.log("Illumination board not connected", log_level=2)

        self.initial_time = time.time()


        self.upload_logs()

        # Main recording loop
        for self.current_frame_number in range(self.parameters["start_frame"], self.n_frames_total):
            self.skip_frame = False

            if self.is_it_pause_time(self.current_frame_number):
                self.pause_recording_in_s(self.pause_time)

            # If in advance, wait, otherwise skip frames
            self.wait_or_catchup_by_skipping_frames()

            self.start_time_current_frame = time.time()

            capture_ok = False

            try:
                if not self.skip_frame:
                    self.log_progress()

                    capture_ok = self.camera.capture_frame(self.get_last_save_path())

            except RuntimeError as e:

                self.logger.log(f"RuntimeError on frame {self.current_frame_number}: {e}",
                                log_level=1)
            except TimeoutError as e:
                self.logger.log(f"TimeoutError on frame {self.current_frame_number}: {e}",
                                log_level=1)

            finally:
                if not capture_ok:
                    self.logger.log(f"Frame {self.current_frame_number} could not be captured. "
                                    f" Saving as empty frame.",
                                    log_level=2)
                    self.camera.capture_empty_frame(self.get_last_save_path())
                else:
                    self.logger.log(f"Frame {self.current_frame_number} captured."
                                    f" ({self.current_frame_number + 1}/{self.n_frames_total})",
                                    log_level=5)

                # TODO : write doc about why this check is useful
                if self.get_last_save_path() is not None:

                    if self.is_time_for_compression():
                        # self.logger.log("time for compression")
                        self.logger.log("Time for compression", log_level=3)
                        self.uploader.start_async_compression_and_upload(dir_to_compress=self.get_current_dir(),
                                                                         format="mkv")


                        self.upload_logs()



                # print(f'end: {datetime.now() - self.initial_datetime}')

        # End of recording
        # Wait for the end of compression


        # Terminate LED programs
        self.logger.log("Terminating LED programs", log_level=5)
        self.lights.close()

        self.uploader.wait_for_compression()

        self.uploader.upload_remaining_files(self.go_to_tmp_recording_folder())

        self.logger.log("Recording done (Timeout reached)",begin='\n\n', end='\n\n\n',log_level=0)
        


        # After recording is finished
        self.update_status('Not Running')

        self.upload_logs()

        # print("Recording done")
        self.stop()




    def wait_or_catchup_by_skipping_frames(self):
        # Wait
        # Check if the current frame is on time

        delay = self.get_delay()

        # If too early, wait until it is time to record
        # print(delay)
        # print(f'current: {current_timedelta}, exp: {expected_timedelta_for_current_frame}, delay: {delay}')
        if delay < 0:
            # Recording on time. Wait for the next frame

            self.logger.log("Waiting for %fs before next frame" % -delay, log_level=5)
            try:
                time.sleep(-delay)
            except BlockingIOError:
                self.logger.log("\n\n it failed but still trying", log_level=2)
                time.sleep(-delay)
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
            self.logger.log(f"Delay too long : Frame {self.current_frame_number} skipped", log_level=2)

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
        self.logger.log(f"Starting capture of frame {self.current_frame_number}"
                        f"  ({self.current_frame_number + 1}/{self.n_frames_total})",
                        log_level=3)


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


    ### Other utility functions

    def go_to_tmp_recording_folder(self):
        tmp_rec_folder = self.get_tmp_recording_folder()

        # Created directory to save locally the files before upload
        try:
            os.makedirs(tmp_rec_folder)
        except FileExistsError:
            pass

        os.chdir(tmp_rec_folder)
        return os.getcwd()

    def get_tmp_recording_folder(self):
        # get home path
        home = os.path.expanduser("~")
        return f'{home}/{self.parameters["local_tmp_dir"]}'

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
            self.camera.capture_frame(self.get_last_save_path())
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
                if n_frames == 0:
                    n_frames = 1
        except ZeroDivisionError:
            n_frames = 1
        finally:
            return n_frames

    def read_output_filename(self):
        f = self.parameters["output_filename"]
        if f == "auto":
            return self.get_needed_output_format()
        else:
            return f

    def get_needed_output_format(self):

        digits = int(ceil(log10(self.n_frames_total)))
        #print(digits)
        if digits == 0:
            digits += 1
        return f'%0{digits}d.jpg'

    def get_last_save_path(self):
        try:
            return os.path.abspath(os.path.join(self.get_current_dir(), self.get_filename()))
        except TypeError:
            return None

    def get_filename(self):
        try:
            # if automatic filename, i.e. filename is %0Xd.jpg
            filename = self.output_filename % self.current_frame_number
        except TypeError:
            filename = self.output_filename
        return filename


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
        if self.parameters["use_samba"] and self.is_it_useful_to_save_logs():
            try:
                self.uploader.upload(file_to_upload=self.logger.get_log_file_path(),
                                 filename_at_destination=self.logger.get_log_filename())
            except TypeError:
                pass



