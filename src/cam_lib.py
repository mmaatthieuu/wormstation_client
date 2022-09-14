# import pathlib
# import time
import datetime
# import numpy as np
# from PIL import Image as im
# import threading
# import multiprocessing
# import subprocess
#
# import psutil
# import sys
# import shutil
# import tarfile
# import os
# import picamera


# from .set_picamera_gain import set_analog_gain, set_digital_gain



def get_folder_name(in_string: str):
    if '/' in in_string:
        folder_name = "/".join(in_string.split('/')[0:-1])
        # log(folder_name)
        return folder_name
    else:
        log("Output files need to be in a folder")
        # args.compress = None
        return None


def get_file_name(in_string: str):
    return in_string.split('/')[-1]


def log(log_msg, begin="", end="\n"):
    print("%s[%s] : %s" %  (begin, str(datetime.datetime.now()), log_msg), end=end)



