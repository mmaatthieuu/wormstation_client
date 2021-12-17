import pathlib
import time
import datetime
import numpy as np
from PIL import Image as im
# import threading
import multiprocessing
import subprocess

import psutil
import sys
import shutil
import tarfile
import os
import picamera


from set_picamera_gain import set_analog_gain, set_digital_gain



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


def cam_init(iso, shutter_speed, brightness, verbose):

    cam = picamera.PiCamera(resolution='3296x2464')
    cam.iso = iso

    if verbose:
        log("Starting camera...")
    time.sleep(1)

    # fix the auto white balance gains at their current values
    g = cam.awb_gains
    cam.awb_mode = "off"
    cam.awb_gains = g

    # fix the shutter speed
    cam.shutter_speed = shutter_speed

    set_analog_gain(cam, 1)
    set_digital_gain(cam, 1)
    """
    if shutter_speed is not None:
        g = cam.awb_gains
        cam.awb_mode = "off"
        cam.awb_gains = g

        cam.shutter_speed = shutter_speed
        cam.exposure_mode = 'off'
    """
    time.sleep(0.5)
    cam.brightness = brightness

    return cam


def save_image(picture_array, k, output_folder, output_filename, compress_step, n_frames_total, quality,
               avg, version=None, skipped=False):
    image = im.fromarray(picture_array)

    try:
        filename = output_filename % k
    except TypeError:
        filename = output_filename

    if compress_step is None:
        save_path = os.path.join(output_folder, filename)
        image.save(save_path, quality=quality)

    else:
        part = k // compress_step
        current_dir = "part%02d" % part

        if k % compress_step == 0:
            try:
                os.mkdir(current_dir)
                #log("\n%s created" % current_dir)
            except FileExistsError:
                # log("\n%s already exists" % current_dir)
                pass

        save_path = os.path.join(current_dir, filename)
        image.save(save_path, quality=quality)

        os.setxattr(save_path, 'user.datetime', (str(datetime.datetime.now())).encode('utf-8'))
        os.setxattr(save_path, 'user.index', ("%06d" % k).encode('utf-8'))
        os.setxattr(save_path, 'user.hostname', (os.uname()[1]).encode('utf-8'))
        os.setxattr(save_path, 'user.jpg_quality', ("%02d" % quality).encode('utf-8'))
        os.setxattr(save_path, 'user.averaged', ("%d" % avg).encode('utf-8'))
        os.setxattr(save_path, 'user.git_version', version.encode('utf-8'))
        os.setxattr(save_path, 'user.skipped', ("%d" % int(skipped)).encode('utf-8'))

        if k % compress_step == compress_step - 1 or k == n_frames_total - 1:
            # log(threading.enumerate())
            #dir_to_compress = "part%02d" % part
            dir_to_compress = current_dir
            log("Dir_to_compress : %s" % dir_to_compress)
            log("Dest path : %s " % output_folder)
            # compress_task = threading.Thread(target=compress, args=(dir_to_compress, output_folder))
            compress_task = multiprocessing.Process(target=compress, args=(dir_to_compress, output_folder))
            compress_task.start()

            # log(threading.enumerate())

    #os.system("ln -sf %s /home/matthieu/tmp/last_frame.jpg" % pathlib.Path(save_path).absolute())
    subprocess.run(['ln', '-sf', '%s' % pathlib.Path(save_path).absolute(), '/home/matthieu/tmp/last_frame.jpg'])

def print_args(args):

    nPicsPerFrames = args.average
    try:
        n_frames_total = args.timeout // args.time_interval
    except ZeroDivisionError:
        n_frames_total = 1

    h = args.timeout // 3600
    mins = (args.timeout - h * 3600) // 60
    s = args.timeout - h * 3600 - mins * 60

    output_str = ""

    output_str += ("Verbosity : %s\n" % args.verbose)
    output_str += ("Time interval between frames [seconds] : %d\n" % args.time_interval)
    output_str += ("Pictures averaged at each frame : %d\n" % nPicsPerFrames)
    output_str += ("Timeout : %ds (%dh%dmin%ds)\n" % (args.timeout, h, mins, s))
    output_str += ("Total number of frames : " + str(n_frames_total) + "\n")
    if args.output is not None:
        output_str += ("Writing file to : %s\n" % args.output[0])
    else:
        output_str += ("Output files NOT saved to disk\n")
    output_str += ("JPG quality : %d\n" % args.quality)
    output_str += ("ISO : %d\n" % args.iso)
    output_str += "Brightness : %s\n" % args.brightness
    if args.shutter_speed is not None:
        output_str += ("Shutter speed : %d\n" % args.shutter_speed)
    else:
        output_str += ("Shutter speed set automatically\n")

    if args.compress is None:
        output_str += ("Without compression\n")
    else:
        output_str += ("Number of images per archive : %d\n" % args.compress)
    output_str += ("Starting frame : %d\n" % args.start_frame)

    output_str += ("\n")

    return output_str


def compress(folder_name, dest_path):
    pid = psutil.Process(os.getpid())

    pid.nice(19)
    log("Starting compression of %s" % folder_name)

    command_string = ("tar --xattrs -czf %s.tgz -C %s ." % (folder_name, folder_name))
    call_args = ['tar', '--xattrs', '-czf', '%s.tgz' % folder_name, '-C', '%s' % folder_name, '.']
    #os.system(command_string)
    subprocess.run(call_args)

    # with tarfile.open(folder_name + ".tgz", "w:gz") as tar:
    #     for file in os.listdir(pathlib.Path(folder_name)):
    #         tar.add(os.path.join(folder_name, file), arcname=file)
    #         time.sleep(0.1)

    log("\n")
    log("Compression of %s done" % folder_name)
    # !!! That is taking much resources !!! -> subprocess ?
    try:
        #shutil.move(folder_name+".tgz", "%s/%s.tgz" % (dest_path, folder_name))
        #shutil.rmtree(folder_name)
        subprocess.run(['mv', '%s.tgz' % folder_name, '%s/%s.tgz' % (dest_path, folder_name)])
        subprocess.run(['rm', '-rf', '%s' % folder_name])
    except OSError as error:
        log("Failed to move and/or delete folder")
        log(error)

    log("%s moved to destination" % folder_name)


def compressor(x, ratio, threshold):
    y1 = np.copy(x)
    y2 = np.copy(x)
    y1[y1>=threshold] = 0
    #y2[y2<threshold] = 0
    y2 = np.array(ratio * y2 + threshold * (1 - ratio), dtype=np.uint8)
    y2[y1<threshold]=0
    return y1+y2

