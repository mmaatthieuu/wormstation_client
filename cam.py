#!/usr/bin/python3 -u
import pathlib
import sys

import numpy as np
import time
import picamera
import argparse
import os.path
import subprocess
from multiprocessing.pool import ThreadPool
from multiprocessing import Process
from threading import Thread,Lock
from queue import Queue

import src.NPImage as npi
from src.tlc5940.tlc import tlc5940

import datetime

from src.cam_lib import *

from src.CrashTimeOutException import CrashTimeOutException

parser = argparse.ArgumentParser()

parser.add_argument("-v", "--verbose", help="increase output verbosity",
                    action="store_true")
parser.add_argument("-vv", "--vverbose", help="increase more output verbosity",
                    action="store_true")
parser.add_argument("-p", "--preview", help="display camera preview",
                    action='store_true')
parser.add_argument("-t", "--timeout", help="time (in s) before takes picture and shuts down",
                    default=10, nargs='?', type=int)
parser.add_argument("-ti", "--time-interval", help="time interval between frames in seconds",
                    default=5, nargs='?', type=float)
parser.add_argument("-avg", "--average", help="number of pictures to average at each frame",
                    default=3, nargs='?', type=int)
parser.add_argument("-o","--output", help="output filename",
                    nargs=1, type=str)
parser.add_argument("-q", "--quality", help="set jpeg quality <0 to 100>",
                    nargs='?', type=int, default=75)
parser.add_argument("-iso", "--iso", help="sets the apparent ISO setting of the camera",
                    nargs='?', type=int, default=0)
parser.add_argument("-ss", "--shutter-speed", help="sets the shutter speed of the camera in microseconds",
                    type=int, default=0)
parser.add_argument("-br", "--brightness",
                    help="brightness level of the camera as an integer between 0 and 100 (default 50)",
                    type=int, default=50)
parser.add_argument("-x", "--compress", help="compress the output in tgz archive, with <N> pictures per archive (default 1000)",
                    nargs='?', type=int, const=1000)
parser.add_argument("-sf", "--start-frame", help="input the frame number to start to (default = 0)",
                    type=int, default=0)
parser.add_argument("-nfo", "--save-nfo", help="Save an nfo file with all recording parameters",
                    action="store_true")
parser.add_argument("-l", "--led-intensity", help="set light intensity 0-4095", type=int, default=4095)
parser.add_argument("-r", type=float)
parser.add_argument("-th", type=int)

args = parser.parse_args()



local_tmp_dir = ".campy_local_save/"
if args.output is not None:
    absolute_output_folder = pathlib.Path(get_folder_name(args.output[0])).absolute()
    output_filename = get_file_name(args.output[0])

# print(absolute_output_folder)
# print(output_filename)


git_check = subprocess.run(['git', '--git-dir=/home/matthieu/piworm/.git', 'rev-list',
                            '--all', '--abbrev-commit', '-n', '1'], text=True, capture_output=True)
version = git_check.stdout



def init():



    if args.vverbose:
        args.verbose = True

    if args.verbose:
        print(print_args(args))

    if args.compress is not None:
        try:
            os.mkdir(local_tmp_dir)
            log("Folder ", local_tmp_dir, " created")
        except FileExistsError:
            pass
            # os.remove(".campy_local_save/*")
        os.chdir(local_tmp_dir)

def leds_on(stop_leds):
    leds = tlc5940(blankpin=27,
                   progpin=22,
                   latchpin=17,
                   gsclkpin=18,
                   serialpin=23,
                   clkpin=24)

    leds.initialise()

    print(args.led_intensity)

    while True:
        for led in range(0, 16):
            leds.set_grey(led, args.led_intensity)
            leds.set_dot(led,1)

        leds.write_dot_values()
        leds.write_grey_values()
        leds.pulse_clk()

        if stop_leds():
            break

    leds.blank(1)
    leds.cleanup()

def save_info(args, version):

    x = datetime.datetime.now()

    #nfo_filename = "%s.nfo" % datetime.now()
    nfo_filename = x.strftime("%Y%m%d_%H%M.nfo")
    log(nfo_filename)
    if args.output is not None:
        nfo_path = pathlib.Path.joinpath(absolute_output_folder, nfo_filename)
    else:
        nfo_path = pathlib.Path("./%s" % nfo_filename)

    with open(nfo_path, 'w') as f:
        f.write("git commit : %s" % version)
        f.write(print_args(args))

    return nfo_path

# Function to parallelize the computation of the new frame
# save 0.2 to 0.3 seconds on capture time
def save_pic_to_frame(new_pic, n, lock):
    lock.acquire()
    global current_frame
    current_frame = current_frame + new_pic // n
    lock.release()


def record(args, camera):


    global current_frame





    nPicsPerFrames = args.average
    try:
        n_frames_total = int(args.timeout / args.time_interval)
        if n_frames_total == 0:
            n_frames_total = 1
    except ZeroDivisionError:
        n_frames_total = 1

    number_of_skipped_frames = 0



    # Main loop for recording
    for k in range(args.start_frame, n_frames_total):

        skip_frame = False
        # (Re)Initialize the current frame
        current_frame = np.empty((2464, 3296), dtype=np.uint8)

        # Check if the current frame is on time
        delay = time.time() - (initial_time + (k) * args.time_interval)

        # If too early, wait until it is time to record
        if delay < 0:
            time.sleep(-delay)
            if args.vverbose:
                log("Waiting for %fs" % -delay)
        elif delay < 0.01:     # We need some tolerance in this world...
            pass
        else:
            if args.verbose:
                #log('Frame %fs late' % -diff_time, begin="\n")
                log('Delay : %fs' % delay)

        # It the frame has more than one time interval of delay, it just skips the frame and directly
        # goes to the next one
        # The condition on k is useful if one just want one frame and does not care about time sync
        if delay >= args.time_interval and k < (n_frames_total-1) :
            skip_frame = True
            log("Delay too long : Frame %d skipped" % (k), begin="\n    WARNING    ")

        start_time = time.time()  # Starting time of the current frame
        try:
            if not skip_frame:

                if args.vverbose:
                    log("Starting capture of frame %d / %d" % (k + 1, n_frames_total))
                elif args.verbose:
                    print("\r[%s] : Starting capture of frame %d / %d" %
                          (str(datetime.datetime.now()), k + 1, n_frames_total), end="")

                output = npi.NPImage()
                lock = Lock()


                threads = [None]*nPicsPerFrames
                for i, fname in enumerate(camera.capture_continuous(output, 'yuv', use_video_port=False, burst=False)):

                    # Send the computation and saving of the new pic to separated thread
                    threads[i] = Thread(target=save_pic_to_frame, args=(output.get_data(), nPicsPerFrames, lock))
                    threads[i].start()
                    #print(threads[i])

                    # Frame has been taken so we can reinitialize the number of skipped frames
                    number_of_skipped_frames = 0

                    if i == nPicsPerFrames-1:
                        break
                for t in threads:
                    t.join()
                    #print(t)
                # print(np.max(pictures_to_average))

            # That is some weird error that occurs randomly...
        except picamera.exc.PiCameraRuntimeError as error:
            log("Error 1 on frame %d" % k)
            log("Timeout Error : Frame %d skipped" % (k), begin="\n    WARNING    ")
            log(error)
            skip_frame = True
            if number_of_skipped_frames == 0:
                number_of_skipped_frames+=1
                continue
            else:
                log("Warning : Camera seems stuck... Trying to restart it")
                raise CrashTimeOutException(k)
            # sys.exit()
        except RuntimeError:
            log("Error 2 on frame %d" % k)

        finally:
            if args.output is not None:
                save_image(current_frame, k, absolute_output_folder,
                           output_filename, args.compress, n_frames_total, args.quality, args.average, version,
                           skip_frame)

        execTime = (time.time() - start_time)
        if args.vverbose:
            log("Finished capture of frame %d in %fs" % (k + 1, execTime))




def main():
    init()

    stop_leds = False
    led_thread = Thread(target=leds_on, args=(lambda: stop_leds,))
    led_thread.start()

    if args.save_nfo:
        nfo_path = save_info(args, version)

    picamera.PiCamera.CAPTURE_TIMEOUT = 3

    try:

        subprocess.run(['cpulimit', '-P', '/usr/bin/gzip', '-l', '10', '-b', '-q'])

        camera = cam_init(iso=args.iso, shutter_speed=args.shutter_speed, brightness=args.brightness,
                 verbose=args.verbose)




        if args.preview:
            camera.start_preview()


        #time.sleep(2)  # let the camera warm up and set gain/white balance

        gain_str = "A/D gains: {}, {}".format(camera.analog_gain, camera.digital_gain)

        if args.save_nfo:
            with open(nfo_path,'a') as file:
                file.write(gain_str + '\n')

        if args.verbose:
            log("Camera successfully started")
            log(gain_str)

        global initial_time
        initial_time = time.time()

        record(args=args, camera=camera)
        print("shutter speed : %d" % camera.exposure_speed)

    except KeyboardInterrupt:
        log("\nScript interrupted by user")

        subprocess.run(['pkill', 'cpulimit'])

        if args.verbose:
            log("Closing camera...")
        camera.close()

        if args.verbose:
            log("Over.")

    # else:
    #     log("\nOops... Something went wrong.\n")
    except CrashTimeOutException as e:

        camera.close()
        log("Camera closed")
        camera = cam_init(iso=args.iso, shutter_speed=args.shutter_speed, brightness=args.brightness,
                 verbose=args.verbose)
        log("Camera up again")
        args.start_frame = int(e.frame_number)

        log("Restart record at frame %d" % args.start_frame)
        record(args=args, camera=camera)
        #picamera.PiCamera.CAPTURE_TIMEOUT = 10

    else:

        subprocess.run(['pkill', 'cpulimit'])

        stop_leds = True
        led_thread.join()
        print('thread killed')

        if args.verbose:
            log("Closing camera...")
        camera.close()

        if args.verbose:
            log("Over.")

if __name__ == "__main__":
    main()
