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

from threading import Thread, Lock
import multiprocessing

import psutil
import pathlib

from src.camera import Camera
from src.tlc5940.tlc import tlc5940
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

        self.git_version = git_version



        #print(self.git_version)

        #self.output = None
        self.output_lock = None
        if self.parameters["average"] != 1:
            self.output_lock = Lock()

        subprocess.run(['cpulimit', '-P', '/usr/bin/gzip', '-l', '10', '-b', '-q'])

        # TODO pool instead of single process
        self.compress_process = None
        self.save_process = None

    def __del__(self):
        self.logger.log("Closing recorder")
        subprocess.run(['pkill', 'cpulimit'])
        del self.camera

    def start_recording(self):
        """
        Main recording function
        """
        # TODO : save json config
        # TODO : add git number to json file and maybe add check if git version is the same as current one ?
        # TODO : confirm parameters & check if folder already exists
        # TODO : check if samba config is working

        # Go to home directory
        self.go_to_tmp_recording_folder()

        # Compute the total number of frame from the recording time and time interval between frames

        self.logger.log(json.dumps(self.parameters, indent=4))

        self.camera.pre_callback = self.annotate_frame

        self.camera.start()

        self.initial_time = time.time()

        #self.create_output_folder()

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

                    #self.annotate_frame()

                    #self.async_frame_capture()
                    #print("before capture")
                    #print(self.get_last_save_path())

                    #self.camera.pre_callback = self.annotate_frame


                    self.camera.capture_file(self.get_last_save_path())

                    #self.camera.capture_file("/home/matthieu/test.jpg")

                    #print(self.camera.capture_metadata())

                    # request = self.camera.capture_request()
                    # request.save("main", self.get_last_save_path())
                    # print(request.get_metadata())  # this is the metadata for this image
                    # request.release()

                    #print("after capture")
                    #time.sleep(0.5) #still usefull ?

            # except picamera.exc.PiCameraRuntimeError as error:
            #     self.logger.log("Error 1 on frame %d" % self.current_frame_number)
            #     self.logger.log("Timeout Error : Frame %d skipped" % self.current_frame_number, begin="\n    WARNING    ", end="\n")
            #     self.logger.log(error)
            #     self.skip_frame = True
            #     if self.number_of_skipped_frames == 0:
            #         self.number_of_skipped_frames += 1
            #         continue
            #     # Already one frame has been skipped -> camera probably stuck
            #     else:
            #         self.logger.log("Warning : Camera seems stuck... Trying to restart it")
            #         del self.camera
            #         self.camera = Camera(parameters=self.parameters)
            #         #raise CrashTimeOutException(self.current_frame_number)
            #     # sys.exit()
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
                        self.start_async_compression_and_upload()

                    if self.parameters["use_samba"]:
                        self.async_smbupload(file_to_upload=self.logger.get_log_file_path(),
                                             filename_at_destination=self.logger.get_log_filename())
                        self.async_smbupload(file_to_upload=self.logger.get_log_file_path(),
                                             filename_at_destination=self.logger.get_log_filename())
                #create link to last frame
                self.create_symlink_to_last_frame()



    def wait_or_catchup_by_skipping_frames(self):
        # Wait
        # Check if the current frame is on time
        self.delay = time.time() - (self.initial_time +
                                    self.current_frame_number * self.parameters["time_interval"]) + \
                     self.parameters["start_frame"] * self.parameters["time_interval"]

        # If too early, wait until it is time to record
        print(self.delay)
        if self.delay < 0:
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

            string_time = (datetime.now()).strftime('%Y-%m-%d %H:%M:%S')
            string_to_overlay = "%s | %s | %s | %s" % (gethostname(), self.get_filename(), string_time, name)

            with MappedArray(request, "main") as m:
                cv2.putText(m.array, string_to_overlay, origin, font, scale, colour, thickness)

            #self.camera.annotate_text = string_to_overlay

    def save_pic_to_frame(self, new_pic):
        #self.output_lock.acquire()
        self.current_frame = self.current_frame + new_pic // self.parameters["average"]
        #self.output_lock.release()

    def async_frame_capture(self):
        output = npi.NPImage()
        if self.parameters["average"] == 1:
            #self.camera.capture(output, 'yuv', use_video_port=False)
            #self.current_frame = output.get_data()
            self.current_frame = self.camera.capture_array
        else:
            #self.output_lock = Lock()

            # TODO repalce threads by processes
            threads = [None] * self.parameters["average"]
            for i, fname in enumerate(
                    self.camera.capture_continuous(output,
                                                   'yuv', use_video_port=False, burst=False)):

                # Send the computation and saving of the new pic to separated thread
                # TODO : maybe shortcut that if avg == 1
                threads[i] = Thread(target=self.save_pic_to_frame, args=(output.get_data(),))
                print(f"start {i} {fname}")
                threads[i].start()
                print(threads[i])

                # Frame has been taken so we can reinitialize the number of skipped frames
                self.number_of_skipped_frames = 0

                if i == self.parameters["average"] - 1:
                    break
            for t in threads:
                t.join()

    def save_frame(self):
        """
        Convert numpy array to image and save it locally
        """
        image = im.fromarray(self.current_frame)

        save_path = self.get_last_save_path()
        image.save(save_path, quality=self.parameters["quality"])

        self.write_extended_attributes(save_path=save_path)



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


    def start_async_compression_and_upload(self):
        dir_to_compress = self.get_current_dir()
        self.logger.log("Dir_to_compress : %s" % dir_to_compress)
        #log("Dest path : %s " % output_folder)
        #self.save_process.join()
        self.compress_process = multiprocessing.Process(target=self.compress_and_upload, args=(dir_to_compress,))
        self.compress_process.start()

    def compress_and_upload(self,folder_name):
        print("start compression")
        self.compress(folder_name=folder_name)
        if self.parameters["use_samba"] is True:
            file_to_upload = f'{folder_name}.tgz'
            #print(f"#DEBUG uploading {file_to_upload}")
            while self.upload_failed(file_to_upload):
                ok = self.smbupload(file_to_upload=file_to_upload)
                print("ok")

            #if ok is True:
            subprocess.run(['rm', '-rf', '%s' % folder_name])
            #subprocess.run(['rm', '-rf', '%s.tgz' % folder_name])
            #else:
                # TODO handle that better
                #log("something went wrong wile uploading")
                #raise Exception

        print("compression done")

    def upload_failed(self, uploaded_file):
        out_str = self.smbcommand("ls").stdout.decode("utf-8")
        return uploaded_file not in out_str


    def compress(self, folder_name):
        pid = psutil.Process(os.getpid())

        pid.nice(19)
        self.logger.log("Starting compression of %s" % folder_name)

        call_args = ['tar', '--xattrs', '-czf', '%s.tgz' % folder_name, '-C', '%s' % folder_name, '.']
        subprocess.run(call_args)

        self.logger.log("Compression of %s done" % folder_name,begin="\n")

    def async_smbupload(self, file_to_upload, filename_at_destination=""):
        upload_proc = multiprocessing.Process(target=self.smbupload,
                                                  args=(file_to_upload, filename_at_destination))
        upload_proc.start()

    def smbupload(self, file_to_upload, filename_at_destination=""):
        if file_to_upload is not None:
            command = f'put {file_to_upload} {filename_at_destination}'
            ok = self.smbcommand(command)

            return ok
        return True

    def create_smb_tree_structure(self):
        try:
            folder1 = f'{(datetime.now()).strftime("%Y%m%d_%H%M")}{self.parameters["recording_name"]}'
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

    # def get_local_save_dir(self):
    #     try:
    #         if self.parameters["use_samba"] is False:
    #             # The local dir is the final output
    #             path = self.parameters["local_output_dir"]
    #         else:
    #             # write frames in the tmp local dir, and wait for compression and upload
    #             path = self.parameters["local_tmp_dir"]
    #         #return path
    #         return self.parameters["local_tmp_dir"]
    #     except TypeError:
    #         return None
    #
    # def create_output_folder(self):
    #     pass
    #     # try:
    #     #     os.mkdir(self.get_local_save_dir())
    #     #     print(f'#DEBUG {os.getcwd()}/{self.get_local_save_dir()} created')
    #     # except FileExistsError:
    #     #     print(f'#DEBUG {self.get_local_save_dir()} already exists')
    #     #     pass


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
        return True

