#!/usr/bin/python3 -u
import pathlib
import sys

import numpy as np
import time
import picamera
import argparse
import os.path
import subprocess
import socket
from multiprocessing.pool import ThreadPool
from multiprocessing import Process
from threading import Thread,Lock
from queue import Queue

from parameters import Parameters
import sys
import json

import src.NPImage as npi
from src.tlc5940.tlc import tlc5940

import datetime

from src.cam_lib import *
from src.record import Recorder

from src.CrashTimeOutException import CrashTimeOutException

# parser = argparse.ArgumentParser()
#
# parser.add_argument("-v", "--verbose", help="increase output verbosity",
#                     action="store_true")
# parser.add_argument("-vv", "--vverbose", help="increase more output verbosity",
#                     action="store_true")
# parser.add_argument("-p", "--preview", help="display camera preview",
#                     action='store_true')
# parser.add_argument("-t", "--timeout", help="time (in s) before takes picture and shuts down",
#                     default=10, nargs='?', type=int)
# parser.add_argument("-ti", "--time-interval", help="time interval between frames in seconds",
#                     default=5, nargs='?', type=float)
# parser.add_argument("-avg", "--average", help="number of pictures to average at each frame",
#                     default=3, nargs='?', type=int)
# parser.add_argument("-o","--output", help="output filename",
#                     nargs=1, type=str)
# parser.add_argument("-q", "--quality", help="set jpeg quality <0 to 100>",
#                     nargs='?', type=int, default=75)
# parser.add_argument("-iso", "--iso", help="sets the apparent ISO setting of the camera",
#                     nargs='?', type=int, default=0)
# parser.add_argument("-ss", "--shutter-speed", help="sets the shutter speed of the camera in microseconds",
#                     type=int, default=0)
# parser.add_argument("-br", "--brightness",
#                     help="brightness level of the camera as an integer between 0 and 100 (default 50)",
#                     type=int, default=50)
# parser.add_argument("-x", "--compress", help="compress the output in tgz archive, with <N> pictures per archive (default 1000)",
#                     nargs='?', type=int, const=1000)
# parser.add_argument("-sf", "--start-frame", help="input the frame number to start to (default = 0)",
#                     type=int, default=0)
# parser.add_argument("-nfo", "--save-nfo", help="Save an nfo file with all recording parameters",
#                     action="store_true")
# parser.add_argument("-a", "--annotate-frames", help="bool, overlay date, time and device name on frames",
#                      action="store_true")
# parser.add_argument("-l", "--led-intensity", help="set light intensity 0-4095", type=int, default=4095)
# parser.add_argument("-r", type=float)
# parser.add_argument("-th", type=int)
#
# args = parser.parse_args()


# local_tmp_dir = ".campy_local_save/"
# if args.output is not None:
#     absolute_output_folder = pathlib.Path(get_folder_name(args.output[0])).absolute()
#     output_filename = get_file_name(args.output[0])

# print(absolute_output_folder)
# print(output_filename)

# TODO make that git check better
git_check = subprocess.run(['git', '--git-dir=/home/matthieu/piworm/.git', 'rev-list',
                            '--all', '--abbrev-commit', '-n', '1'], text=True, capture_output=True)
version = git_check.stdout


def get_git_version():
    # TODO make that git check better
    folder_path = os.path.dirname(os.path.realpath(__file__))
    git_check = subprocess.run(['git', f'--git-dir={folder_path}/.git', 'rev-list',
                                '--all', '--abbrev-commit', '-n', '1'], text=True, capture_output=True)
    version = git_check.stdout
    return version


def parse_input():
    parser = argparse.ArgumentParser()

    parser.add_argument("-f", "--file", help="input JSON file", type=str)
    parser.add_argument("-s", "--string", help="input JSON string", type=str)

    args = parser.parse_args()






def main():
    # TODO : take json config as input
    print("yo")
    parameters = Parameters(sys.argv[1])

    recorder = Recorder(parameters=parameters, git_version=get_git_version())

    print("recorder created")

    # TODO : save json config

    picamera.PiCamera.CAPTURE_TIMEOUT = 3

    try:


        print("Start recording")
        recorder.start_recording()
        print("end")


    except KeyboardInterrupt:
        log("\nScript interrupted by user")

        del recorder

        if parameters["verbosity_level"]>0:
            log("Over.")

    # else:
    #     log("\nOops... Something went wrong.\n")
    except CrashTimeOutException as e:
        print("#DEBUG Crash time out exception")

    else:

        del recorder

        if parameters["verbosity_level"]>0:
            log("Over.")

if __name__ == "__main__":
    main()
