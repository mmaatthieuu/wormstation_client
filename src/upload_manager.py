import os
import subprocess
import pwd
import time
import pathlib
import psutil

import random

from multiprocessing import Process
from datetime import datetime
from socket import gethostname

from src.analyse import Analyser


class UploadManager:
    def __init__(self, remote_server, remote_dir, recording_name, local_dir=None, logger=None):
        self.username, self.uid, self.gid = self.get_user_info()
        self.remote_server = remote_server
        self.logger = logger
        self.remote_dir = self.get_tree_structure(remote_dir, recording_name)
        self.local_dir = local_dir if local_dir else f"/home/{self.username}/Remote"
        self.full_path = os.path.join(self.local_dir, self.remote_dir)

        self.compress_process = None


    def get_user_info(self):
        username = os.getlogin()
        user_info = pwd.getpwnam(username)
        return username, user_info.pw_uid, user_info.pw_gid

    def create_working_dir(self):
        # Ensure working directory exists
        self.logger.log(f"Creating working directory {self.full_path}", log_level=5)
        os.makedirs(self.full_path, exist_ok=True)

    def file_exists(self, filename):
        # Check if a file exists in the local mount point
        file_path = os.path.join(self.full_path, filename)
        return os.path.exists(file_path)

    def upload(self, file_to_upload, filename_at_destination="", async_upload=True):
        if async_upload:
            self.async_upload(file_to_upload, filename_at_destination)
        else:
            return self.sync_upload(file_to_upload, filename_at_destination)

    def async_upload(self, file_to_upload, filename_at_destination=""):
        upload_proc = Process(target=self.sync_upload, args=(file_to_upload, filename_at_destination))
        upload_proc.start()

    def sync_upload(self, file_to_upload, filename_at_destination=""):
        # Check if the remote directory is accessible
        if not self.is_mounted() or not self.is_accessible():
            self.logger.log(f"Remote directory is not accessible, trying to mount it", log_level=2)
            if not self.mount() or not self.is_accessible():
                self.logger.log("Failed to mount or remote directory is not accessible, skipping upload", log_level=1)
                return False

        if file_to_upload is not None:
            # Check if the file to upload exists
            if not os.path.exists(file_to_upload):
                self.logger.log(f"File {file_to_upload} does not exist", log_level=1)
                return False


            # Get file size
            file_size = os.path.getsize(file_to_upload)

            # If file is bigger than 10MB, add some random delay to avoid all devices to upload simultaneously
            if file_size > 10 * 1024 * 1024:
                self.wait_random_delay()

            # Get path to the mounted remote directory
            remote_dir = self.get_mounted_path()

            # Copy the file in the mounted remote directory
            command = f'cp {file_to_upload} {remote_dir}/{filename_at_destination}'

            self.logger.log(f'Uploading {file_to_upload} to {remote_dir}/{filename_at_destination}', log_level=5)

            # Run the command
            result = subprocess.run(command, shell=True, capture_output=True)

            # Check if the command was successful
            if result.returncode != 0:
                # Log an error message if the command failed
                self.logger.log(f'Error occurred during upload: {result.stderr.decode()}', log_level=1)
                return False

        return True


    def wait_random_delay(self):
        delay = random.randint(0, 60)
        self.logger.log(f"Delay upload for {delay} seconds", log_level=5)
        time.sleep(delay)

    def upload_check(self, file):
        upload_check = self.file_exists(file)
        if upload_check:
            self.logger.log(f"File {file} uploaded successfully", log_level=5)
            return True
        else:
            self.logger.log(f"Failed to upload {file}", log_level=1)
            return False

    def start_async_compression_and_upload(self, dir_to_compress, format):
        self.logger.log(f'Compressing and uploading {dir_to_compress}, with format {format}', log_level=5)
        # log("Dest path : %s " % output_folder)
        # self.save_process.join()
        self.compress_process = Process(target=self.compress_analyze_and_upload,
                                        args=(dir_to_compress, format,))
        self.compress_process.start()

    def is_compressing(self):
        return self.compress_process.is_alive()

    def wait_for_compression(self):
        self.compress_process.join()
    def compress_analyze_and_upload(self, folder_name, format, analyze=False):
        # self.logger.log("start compression")
        compressed_file = self.compress(folder_name=folder_name, format=format)

        # Check if the file has been created
        if self.check_compression(compressed_file):
            # The compression was successful
            # Remove the original folder

            # The data are now saved as a movie, it is better to delete the pictures to avoid saturating the disk
            # in case of failed upload
            subprocess.run(['rm', '-rf', '%s' % folder_name])

        # TODO: need to disentangle this mess (compression, analysis, upload)


        output_files = []

        if analyze:
            analyser = Analyser(logger=self.logger)
            output_files = analyser.run(video_path=compressed_file)

        else:
            self.logger.log("Skipping Analysis", log_level=5)
            output_files = [compressed_file]

        self.logger.log(f"Output files : {output_files}", log_level=5)

        for output_file in output_files:
            # Upload the compressed file
            self.upload(output_file, async_upload=False)

            # Check if the file has been uploaded
            if self.upload_check(output_file):
                # The upload was successful
                # Remove the compressed file
                self.logger.log(f"Removing {output_file}", log_level=5)
                subprocess.run(['rm', '-f', '%s' % output_file])


    def check_compression(self, compressed_file):
        # Check if the file has been created
        if not os.path.exists(compressed_file):
            # The compression failed
            self.logger.log("Compression failed (file not created)", log_level=1)
            return False
        # Check if the file is empty
        elif os.path.getsize(compressed_file) == 0:
            # The compression failed
            self.logger.log("Compression failed (file empty)", log_level=1)
            return False
        return True

    def compress(self, folder_name, format="tgz"):

        self.logger.log(f'Compressing {folder_name} to {format}', log_level=5)

        pid = psutil.Process(os.getpid())
        pid.nice(19)

        if format == "tgz":
            output_file = '%s.tgz' % folder_name
            call_args = ['tar', '--xattrs', '-czf', output_file, '-C', '%s' % folder_name, '.']
        else:
            input_files = str(pathlib.Path(folder_name).absolute()) + '/*.jpg'
            output_file = '%s.mkv' % folder_name
            call_args = ['ffmpeg', '-r', '25', '-pattern_type', 'glob', '-i',
                         input_files, '-vcodec', 'libx264',
                         '-crf', '22', '-y',
                         '-refs', '2', '-preset', 'veryfast', '-profile:v',
                         'main', '-threads', '4', '-hide_banner',
                         '-loglevel', 'warning', output_file]

        args_string = ' '.join(call_args)
        self.logger.log(f'Running command : {args_string}', log_level=5)


        subprocess.run(call_args, stdout=subprocess.DEVNULL)

        self.logger.log("Compression of %s done" % folder_name, begin="\n")

        return output_file


    def upload_remaining_files(self, rec_folder):
        self.logger.log("Checking if all files are uploaded", log_level=3)

        # Check if there are some not uploaded files

        # Get list of files in the current directory
        files = os.listdir(rec_folder)

        # Log files that are not uploaded
        self.logger.log(f"Files not uploaded : {files}", log_level=3)

        # Check if there are any files in the directory
        if len(files) > 0:
            for file in files:
                # Upload the file to the NAS
                upload_ok = self.upload(file_to_upload=file, async_upload=False)
                # When upload is done, and successful, remove the file
                if upload_ok:
                    self.logger.log(f"File {file} uploaded successfully, deleting locally", log_level=3)
                    os.remove(file)

                else:
                    self.logger.log(f"File {file} not uploaded, keeping it locally", log_level=1)
                    # Create a folder in the parent folder named after recodring name
                    local_folder_save = os.path.join('../', self.remote_dir)
                    os.makedirs(local_folder_save, exist_ok=True)
                    # Move the file to the folder
                    self.logger.log(f"Moving {file} to {local_folder_save}", log_level=3)
                    os.rename(file, os.path.join(local_folder_save, file))


        else:
            self.logger.log("No files to upload", log_level=3)


    def start(self):
        self.mount()
        self.create_working_dir()

    def mount(self):
        raise NotImplementedError("Mount method should be implemented in subclass")

    def unmount(self):
        raise NotImplementedError("Unmount method should be implemented in subclass")

    def is_mounted(self):
        raise NotImplementedError("is_mounted method should be implemented in subclass")

    def is_accessible(self):
        raise NotImplementedError("is_accessible method should be implemented in subclass")

    def get_tree_structure(self, remote_dir, recording_name):
        raise NotImplementedError("get_tree_structure method should be implemented in subclass")

    def get_mounted_path(self):
        return self.full_path

    def test(self):
        try:
            if not self.mount():
                print("Failed to mount, skipping upload")
                return

            # Ensure working directory exists
            self.create_working_dir()

            print(self.file_exists("test.txt"))

            # Check if the remote directory is mounted and accessible
            if self.is_mounted() and self.is_accessible():
                print("Remote directory is mounted and accessible")
            else:
                print("Remote directory is not accessible")

            time.sleep(3)

        except subprocess.CalledProcessError as e:
            print(f"An error occurred: {e}")

        finally:
            self.unmount()



class SMBManager(UploadManager):
    def __init__(self, nas_server, share_name, credentials_file, working_dir, recording_name=None, local_dir=None, logger=None):
        local_dir = local_dir if local_dir else f"/home/{os.getlogin()}/NAS"
        super().__init__(nas_server, working_dir, recording_name, local_dir, logger)
        self.share_name = share_name
        self.credentials_file = credentials_file

    def mount(self):
        # Create local mount point if it does not exist
        if not os.path.exists(self.local_dir):
            os.makedirs(self.local_dir)

        # Check if the NAS is already mounted
        if self.is_mounted():
            self.logger.log(f"{self.remote_server}/{self.share_name} is already mounted", log_level=3)
            return True

        # Mount the NAS share
        mount_cmd = [
            "sudo", "mount", "-t", "cifs",
            "-o", f"credentials={self.credentials_file},uid={self.uid},gid={self.gid},file_mode=0660,dir_mode=0770",
            f"{self.remote_server}/{self.share_name}", self.local_dir
        ]
        result = subprocess.run(mount_cmd, capture_output=True)
        if result.returncode != 0:
            self.logger.log(f"Failed to mount NAS: {result.stderr.decode()}", log_level=1)
            return False

        print(f"Mounted {self.remote_server}/{self.share_name} to {self.local_dir}")
        return True

    def unmount(self):
        # Unmount the NAS share
        if self.is_mounted():
            unmount_cmd = ["sudo", "umount", self.local_dir]
            subprocess.run(unmount_cmd, check=True)
            print(f"Unmounted {self.local_dir}")

    def is_mounted(self):
        # Check if the NAS is mounted
        result = subprocess.run(['mountpoint', '-q', self.local_dir])
        return result.returncode == 0

    def is_accessible(self):
        # Check if the NAS server is accessible by pinging it
        nas_host = self.remote_server.lstrip("//").split("/")[0]
        ping_cmd = ["ping", "-c", "1", nas_host]
        result = subprocess.run(ping_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return result.returncode == 0

    def get_tree_structure(self, remote_dir, recording_name):
        #self.logger.log(f"Creating tree structure with SMB protocol", log_level=5)
        try:
            folder1 = f'{(datetime.now()).strftime("%Y%m%d_%H%M")}_{recording_name}'
        except:
            folder1 = (datetime.now()).strftime("%Y%m%d_%H%M")
        folder2 = gethostname()

        return f'{remote_dir}/{folder1}/{folder2}'



class SSHManager(UploadManager):
    def __init__(self, ssh_server, ssh_user, remote_dir, recording_name, local_dir=None, logger=None):
        super().__init__(ssh_server, remote_dir, recording_name,local_dir, logger)
        self.ssh_user = ssh_user

    def mount(self):
        # Create local mount point if it does not exist
        if not os.path.exists(self.local_dir):
            os.makedirs(self.local_dir)

        # Check if the SSH is already mounted
        if self.is_mounted():
            self.logger.log(f"{self.ssh_user}@{self.remote_server}:{self.remote_dir} is already mounted", log_level=3)
            return True

        # Mount the SSH share
        mount_cmd = [
            "sshfs",
            f"{self.ssh_user}@{self.remote_server}:{self.remote_dir}",
            self.local_dir,
            "-o", f"uid={self.uid},gid={self.gid}"
        ]
        result = subprocess.run(mount_cmd, capture_output=True)
        if result.returncode != 0:
            self.logger.log(f"Failed to mount SSH: {result.stderr.decode()}", log_level=1)
            return False

        print(f"Mounted {self.ssh_user}@{self.remote_server}:{self.remote_dir} to {self.local_dir}")
        return True

    def unmount(self):
        # Unmount the SSH share
        if self.is_mounted():
            unmount_cmd = ["fusermount", "-u", self.local_dir]
            subprocess.run(unmount_cmd, check=True)
            print(f"Unmounted {self.local_dir}")

    def is_mounted(self):
        # Check if the SSH is mounted
        result = subprocess.run(['mountpoint', '-q', self.local_dir])
        return result.returncode == 0

    def is_accessible(self):
        # Check if the SSH server is accessible by pinging it
        ssh_host = self.remote_server
        ping_cmd = ["ping", "-c", "1", ssh_host]
        result = subprocess.run(ping_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return result.returncode == 0


class EmptyUploader:
    def __init__(self):
        pass

    def mount(self):
        return True

    def unmount(self):
        return True

    def is_mounted(self):
        return True

    def is_accessible(self):
        return True

    def get_tree_structure(self, remote_dir, recording_name):
        return remote_dir

    def wait_for_compression(self):
        return True

    def upload(self, file_to_upload, filename_at_destination="", async_upload=True):
        return True

    def upload_remaining_files(self, rec_folder):
        return True

