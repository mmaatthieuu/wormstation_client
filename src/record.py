import numpy as np
import time
from datetime import datetime
from socket import gethostname
from PIL import Image as im


# import picamera
import json
from picamera2 import MappedArray
import cv2

from math import log10, ceil

#from threading import Thread, Lock
import multiprocessing

import psutil
import pathlib

from src.camera import Camera
from src.led_controller import LED
# from src.tlc5940.tlc import tlc5940
import os
import subprocess
from pathlib import Path

import src.NPImage as npi
from src.log import Logger

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

        # Remark : the directory is created on the NAS before initializing the camera
        # If the camera is initialized first, it produces only black frames...
        # It is weird, but at least it works like that
        if self.parameters["use_samba"]:
            self.smb_output = self.create_smb_tree_structure()

        # Create the camera object with the input parameters
        self.camera = Camera(parameters=self.parameters)

        self.logger = Logger(verbosity_level=parameters["verbosity_level"], save_log=self.is_it_useful_to_save_logs())

        self.current_frame = None
        self.current_frame_number = 0
        self.number_of_skipped_frames = 0
        self.n_frames_total = self.compute_total_number_of_frames()

        self.compress_step = self.parameters["compress"]

        self.skip_frame = False

        self.output_filename = self.read_output_filename()

        self.initial_time = 0
        self.delay = 0
        self.start_time_current_frame = 0

        self.optogenetic = self.parameters["optogenetic"]
        self.pulse_duration = self.parameters["pulse_duration"]
        self.pulse_interval = self.parameters["pulse_interval"]

        self.git_version = git_version

        self.leds = LED(_control_gpio_pin=17)
        if self.optogenetic:
            self.opto_leds = LED(_control_gpio_pin=18)

        #subprocess.run(['cpulimit', '-P', '/usr/bin/gzip', '-l', '10', '-b', '-q'])

        # TODO pool instead of single process
        self.compress_process = None
        self.save_process = None

    def __del__(self):
        self.logger.log("Closing recorder")
        #subprocess.run(['pkill', 'cpulimit'])
        del self.camera

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

        # Compute the total number of frame from the recording time and time interval between frames

        self.logger.log(json.dumps(self.parameters, indent=4))

        self.camera.pre_callback = self.annotate_frame

        self.camera.start()

        if not self.preview_only():
            # If one does an actual recording and not just a preview (i.e. timeout=0)
            # sync all raspberry pi by acquiring frames every even second
            self.wait_until_next_even_second()

        self.initial_time = time.time()

        if self.optogenetic:
            self.opto_leds.start_program(time_on=self.pulse_duration, period=self.pulse_interval,
                                         time_out=self.parameters["timeout"], initial_time=self.initial_time)

        #self.create_output_folder()

        avg_time = 0;

        # Main recording loop
        for self.current_frame_number in range(self.parameters["start_frame"], self.n_frames_total):
            self.skip_frame = False

            # (Re)Initialize the current frame
            #self.current_frame = np.empty((3040, 4056, 3), dtype=np.uint8)

            # If in advance, wait, otherwise skip frames
            self.wait_or_catchup_by_skipping_frames()

            self.start_time_current_frame = time.time()

            try:
                if not self.skip_frame:
                    self.log_progress()

                    ## That was randomly crashing so I used the next method
                    # self.camera.capture_file(self.get_last_save_path())

                    ##DEBUG
                    #start_time = time.time()

                    self.leds.turn_on_with_timer_in_ms(self.parameters["shutter_speed"]/1000*4)
                    #self.do_optostimulation_if_necessary()

                    ## That is the new method, not crashing
                    capture_request = self.camera.capture_request()
                    capture_request.save("main", self.get_last_save_path())
                    # self.logger.log(capture_request.get_metadata(), log_level=2)
                    #end_time = time.time()
                    #self.leds.turn_off()
                    capture_request.release()

                    ## DEBUG :
                    #end_time = time.time()
                    #execution_time = end_time - start_time
                    #print("Execution time:", execution_time, "seconds")


                    ## DEBUG
                    # avg_time = avg_time + execution_time
                    #
                    # if self.current_frame_number == 0:
                    #     min_time = execution_time
                    #     max_time = execution_time
                    # else:
                    #     if execution_time<min_time:min_time=execution_time
                    #     if execution_time>max_time:max_time=execution_time

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

                #TODO : write doc about why this check is useful
                if self.get_last_save_path() is not None:
                    # new process for saving
                    # self.save_process = multiprocessing.Process(target=self.save_frame)
                    # self.save_process.start()
                    #self.save_frame()

                    if self.is_time_for_compression():
                        self.logger.log("time for compression")
                        self.start_async_compression_and_upload(format="mkv")

                    if self.parameters["use_samba"] and self.is_it_useful_to_save_logs():
                        self.async_smbupload(file_to_upload=self.logger.get_log_file_path(),
                                             filename_at_destination=self.logger.get_log_filename())
                #create link to last frame
                self.create_symlink_to_last_frame()

        ## DEBUG
        # avg_time = avg_time / float(self.n_frames_total)
        #
        # print("average time over " + str(self.n_frames_total) + " frames is " + str(avg_time) +
        #       "\nMin : " + str(min_time) + "\nMax : " + str(max_time))

    def wait_or_catchup_by_skipping_frames(self):
        # Wait
        # Check if the current frame is on time
        self.delay = time.time() - (self.initial_time +
                                    self.current_frame_number * self.parameters["time_interval"]) + \
                     self.parameters["start_frame"] * self.parameters["time_interval"]

        # If too early, wait until it is time to record
        print(self.delay)
        if self.delay < 0:
            try:
                time.sleep(-self.delay)
            except BlockingIOError:
                self.logger.log("\n\n it failed but still trying")
                time.sleep(-self.delay)
            if self.parameters["verbosity_level"] >= 2:
                self.logger.log("Waiting for %fs" % -self.delay)
        elif self.delay < 0.01:  # We need some tolerance in this world...
            pass # And go on directly with frame capture
        else:
            # Frame late : log delay
            if self.parameters["verbosity_level"] >= 1:
                # log('Frame %fs late' % -diff_time, begin="\n")
                self.logger.log('Delay : %fs' % self.delay)

        # Catch up
        # It the frame has more than one time interval of delay, it just skips the frame and directly
        # goes to the next one
        # The condition on current_frame_number is useful if one just wants one frame and does not care about time sync
        if self.delay >= self.parameters["time_interval"] and \
                self.current_frame_number < (self.n_frames_total - 1):
            self.skip_frame = True
            self.logger.log(f"Delay too long : Frame {self.current_frame_number} skipped", begin="\n    WARNING    ")

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

        zero_array = np.zeros((self.camera.camera_properties["PixelArraySize"])[::-1]+(3,), dtype=np.uint8)
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
            print(e)
        except ZeroDivisionError as e:
            return False


    def start_async_compression_and_upload(self, format):
        dir_to_compress = self.get_current_dir()
        self.logger.log("Dir_to_compress : %s" % dir_to_compress)
        #log("Dest path : %s " % output_folder)
        #self.save_process.join()
        self.compress_process = multiprocessing.Process(target=self.compress_and_upload,
                                                        args=(dir_to_compress, format,))
        self.compress_process.start()

    def compress_and_upload(self, folder_name, format):
        print("start compression")
        compressed_file = self.compress(folder_name=folder_name, format=format)
        if self.parameters["use_samba"] is True:
            file_to_upload = compressed_file
            #print(f"#DEBUG uploading {file_to_upload}")
            ok = False
            n_trials = 0
            try:
                while self.upload_failed(file_to_upload):
                    ok = self.smbupload(file_to_upload=file_to_upload)
                    n_trials = n_trials+1

                    if n_trials > 5:
                        raise TimeoutError("Uplaod failed")

                subprocess.run(['rm', '-rf', '%s' % folder_name])
                subprocess.run(['rm', '-rf', '%s.%s' % (folder_name, format)])
            except TimeoutError as e:
                self.logger.log(e)


                # TODO : handle files that have not been uploaded
            #subprocess.run(['rm', '-rf', '%s.tgz' % folder_name])
            #else:
                # TODO handle that better
                #log("something went wrong wile uploading")
                #raise Exception

        print("compression done")

    def upload_failed(self, uploaded_file):
        out_str = self.smbcommand("ls").stdout.decode("utf-8")
        return uploaded_file not in out_str


    def compress(self, folder_name, format = "tgz"):
        pid = psutil.Process(os.getpid())

        pid.nice(19)
        self.logger.log("Starting compression of %s" % folder_name)

        if format == "tgz":
            output_file = '%s.tgz' % folder_name
            call_args = ['tar', '--xattrs', '-czf', output_file , '-C', '%s' % folder_name, '.']
        else:
            input_files = str(pathlib.Path(folder_name).absolute()) + '/*.jpg'
            output_file = '%s.mkv' % folder_name
            call_args = ['ffmpeg', '-r', '25', '-pattern_type', 'glob', '-i',
                         input_files, '-vcodec', 'libx264',
                         '-crf', '22', '-y',
                         '-refs', '2', '-preset', 'veryfast', '-profile:v',
                         'main', '-threads', '4', '-hide_banner',
                         '-loglevel', 'warning', output_file]

        subprocess.run(call_args, stdout=subprocess.DEVNULL)

        self.logger.log("Compression of %s done" % folder_name, begin="\n")

        return output_file


    def async_smbupload(self, file_to_upload, filename_at_destination=""):
        upload_proc = multiprocessing.Process(target=self.smbupload,
                                                  args=(file_to_upload, filename_at_destination))
        upload_proc.start()

    def smbupload(self, file_to_upload, filename_at_destination=""):
        if file_to_upload is not None:
            command = f'put {file_to_upload} {filename_at_destination}'
            ok = self.smbcommand(command)

            extension = pathlib.Path(file_to_upload).suffix

            if ok and extension == ".tgz":
                #print(ok)
                try:
                    os.remove(file_to_upload)
                except OSError as e:
                    print("Error: %s - %s." % (e.filename, e.strerror))

            return ok
        return True

    def create_smb_tree_structure(self):
        try:
            folder1 = f'{(datetime.now()).strftime("%Y%m%d_%H%M")}_{self.parameters["recording_name"]}'
        except:
            folder1 = (datetime.now()).strftime("%Y%m%d_%H%M")
        folder2 = gethostname()
        self.smbcommand(command=f'mkdir {folder1}', working_dir=self.parameters["smb_dir"])
        self.smbcommand(command=f'mkdir {folder1}/{folder2}', working_dir=self.parameters["smb_dir"])

        return f'{self.parameters["smb_dir"]}/{folder1}/{folder2}'

    def smbcommand(self, command, working_dir=None):
        if working_dir is None:
            working_dir = self.smb_output

        ok = False
        try:
            ok = subprocess.run(
                ['smbclient',
                 f'{self.parameters["smb_service"]}',
                 '-W', f'{self.parameters["workgroup"]}',
                 '-A', f'{self.parameters["credentials_file"]}',
                 '-D', f'{working_dir}',
                 '-c', f'{command}'],
                capture_output=True)
        except Exception as e:
            print(e)
        return ok

    def create_symlink_to_last_frame(self):
        # TODO : check if really necessary and remove or adapt
        subprocess.run(['ln', '-sf', '%s' % pathlib.Path(self.get_last_save_path()).absolute(), '/home/matthieu/tmp/last_frame.jpg'])

### Other utility functions

    def go_to_tmp_recording_folder(self):
        os.chdir(Path.home())

        # Created directory to save locally the files before upload
        try:
            os.mkdir(self.parameters["local_tmp_dir"])
        except FileExistsError:
            #os.remove(self.parameters["local_tmp_dir"])
            #os.mkdir(self.parameters["local_tmp_dir"])
            pass


        os.chdir(self.parameters["local_tmp_dir"])

    def compute_total_number_of_frames(self):
        n_frames = 0
        try:
            n_frames = int(self.parameters["timeout"] / self.parameters["time_interval"])
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
        if digits == 0:
            digits+=1
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

    def wait_until_next_even_second(self):
        # Actually it is not the next even second but the next second multiple of 4.
        # It increases the chances that all the device start simultaneously and are not splitted

        # Get the current time
        current_time = datetime.now()

        # Calculate the number of milliseconds until the next second multiple of 4
        useconds_until_next_even_second = 1000000 - current_time.microsecond + ((current_time.second + 1) % 4) * 1000000

        # Sleep until the next even second
        time.sleep(useconds_until_next_even_second / 1000000)
"""
    def is_it_time_for_opto_simulation(self):
        current_time = time.time()
        time_from_start = int(current_time - self.initial_time)

        if self.optogenetic == False:
            return False

        if (time_from_start % self.pulse_interval) <= (time_from_start % self.pulse_duration):
            return True
        else:
            return False

    def do_optostimulation_if_necessary(self):
        print(self.is_it_time_for_opto_simulation())
        if self.is_it_time_for_opto_simulation():
            self.opto_leds.turn_on()
        else:
            self.opto_leds.turn_off()
"""