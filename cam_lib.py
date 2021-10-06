import pathlib

import numpy as np
from PIL import Image as im
import threading
import sys
import shutil
import tarfile
import os.path


def get_folder_name(in_string: str):
    if '/' in in_string:
        folder_name = "/".join(in_string.split('/')[0:-1])
        # print(folder_name)
        return folder_name
    else:
        print("Output files need to be in a folder")
        # args.compress = None
        return None


def get_file_name(in_string: str):
    return in_string.split('/')[-1]




def save_image(picture_array, k, output_folder, output_filename, compress_step, n_frames_total, quality):
    image = im.fromarray(picture_array)

    try:
        filename = output_filename % k
    except TypeError:
        filename = output_filename

    if compress_step is None:
        image.save(os.path.join(output_folder, filename), quality=quality)

    else:
        part = k // compress_step
        current_dir = "part%02d" % part

        if k % compress_step == 0:
            try:
                os.mkdir(current_dir)
                print("\n%s created" % current_dir)
            except FileExistsError:
                print("\n%s already exists" % current_dir)

        image.save(os.path.join(current_dir, filename), quality=quality)

        if k % compress_step == compress_step - 1 or k == n_frames_total - 1:
            print(threading.enumerate())
            #dir_to_compress = "part%02d" % part
            dir_to_compress = current_dir
            print("Dir_to_compress : %s" % dir_to_compress)
            print("Dest path : %s " % output_folder)
            compress_task = threading.Thread(target=compress, args=(dir_to_compress, output_folder))
            compress_task.start()
            print(threading.enumerate())


def print_args(args):

    nPicsPerFrames = args.average
    n_frames_total = args.timeout // args.time_interval

    h = args.timeout // 3600
    mins = (args.timeout - h * 3600) // 60
    s = args.timeout - h * 3600 - mins * 60

    print("Verbosity turned on")
    print("Taking frames every %ds" % args.time_interval)
    print("Averaging %d pictures at each frame" % nPicsPerFrames)
    print("Timeout : %ds (%dh%dmin%ds)" % (args.timeout, h, mins, s))
    print("Capturing %d frames" % n_frames_total)
    if args.output is not None:
        print("Writing file to : %s" % args.output[0])
    else:
        print("Output files NOT saved to disk")
    print("JPG quality set to : %d" % args.quality)
    print("ISO : %d" % args.iso)
    if args.shutter_speed is not None:
        print("Shutter speed : %d" % args.shutter_speed)
    else:
        print("Shutter speed set automatically")

    print(args.compress)
    print("Starting at frame %d" % args.start_frame)

    print("\n")


def compress(folder_name, dest_path):
    print("Starting compression of %s" % folder_name)
    with tarfile.open(folder_name + ".tgz", "w:gz") as tar:
        for file in os.listdir(pathlib.Path(folder_name)):
            tar.add(os.path.join(folder_name, file), arcname=file)

    try:
        shutil.move(folder_name+".tgz", "%s/%s.tgz" % (dest_path, folder_name))
        shutil.rmtree(folder_name)
    except OSError as error:
        print("Failed to move and/or delete folder")
        print(error)

    print("\nCompression of %s done" % folder_name)


def compressor(x, ratio, threshold):
    y1 = np.copy(x)
    y2 = np.copy(x)
    y1[y1>=threshold] = 0
    #y2[y2<threshold] = 0
    y2 = np.array(ratio * y2 + threshold * (1 - ratio), dtype=np.uint8)
    y2[y1<threshold]=0
    return y1+y2
