#!/usr/bin/python3 -u
import pathlib
import sys

import numpy as np
import time
import picamera
import argparse
import os.path
import subprocess

import NPImage as npi

import datetime

from cam_lib import *

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
                    default=5, nargs='?', type=int)
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



def main():
    init()
    if args.save_nfo:
        nfo_path = save_info(args, version)

    nPicsPerFrames = args.average
    try:
        n_frames_total = args.timeout // args.time_interval
    except ZeroDivisionError:
        n_frames_total = 1
    try:
        delay = 0
        subprocess.run(['cpulimit', '-P', '/usr/bin/gzip', '-l', '10','-b'])
        with picamera.PiCamera(resolution='3296x2464') as camera:

            cam_init(camera, iso=args.iso, shutter_speed=args.shutter_speed, brightness=args.brightness,
                     verbose=args.verbose)
            #camera.CAPTURE_TIMEOUT = 10

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

            for k in range(args.start_frame, n_frames_total):
                start_time = time.time()
                pictures_to_average = np.empty((2464, 3296), dtype=np.uint8)

                if args.vverbose:
                    log("Starting capture of frame %d / %d" % (k+1, n_frames_total))
                elif args.verbose:
                    print("\r[%s] : Starting capture of frame %d / %d" %
                          (str(datetime.datetime.now()),k + 1, n_frames_total), end="")

                for i in range(nPicsPerFrames):
                    output = npi.NPImage()
                    try:

                        camera.capture(output, 'yuv', use_video_port=False)
                        time.sleep(0.05)
                        #pictures_to_average = pictures_to_average + \
                        #                      cl.compressor(output.get_data(),args.r,args.th) // args.average
                        pictures_to_average = pictures_to_average + output.get_data()// args.average
                        #print(np.max(pictures_to_average))
                    except picamera.exc.PiCameraRuntimeError as error:
                        log("Error 1 on frame %d" % k)
                        log(error)
                        sys.exit()
                    except RuntimeError:
                        log("Error 2 on frame %d" % k)

                if args.output is not None:
                    save_image(pictures_to_average, k, absolute_output_folder,
                                  output_filename, args.compress, n_frames_total, args.quality, args.average, version)



                execTime = (time.time() - start_time)
                if args.vverbose:
                    log("Finished capture of frame %d in %fs" % (k + 1, execTime))

                diff_time = args.time_interval - execTime
                if diff_time - delay > 0:
                    sleep_time = args.time_interval - execTime - delay
                    if args.vverbose:
                        log("Waiting for %fs" % sleep_time)
                    time.sleep(sleep_time)
                    delay = 0
                else:
                    delay -= diff_time
                    if args.verbose:
                        log('\nFrame %fs late' % -diff_time)
                        log('Delay : %fs' % delay)
    except KeyboardInterrupt:
        log("\nScript interrupted by user")
    # else:
    #     log("\nOops... Something went wrong.\n")
    finally:

        subprocess.run(['pkill', 'cpulimit'])

        if args.verbose:
            log("Closing camera...")
        camera.close()

        if args.verbose:
            log("Over.")

if __name__ == "__main__":
    main()
