import os
import subprocess
import pwd
import time
import pathlib
import psutil

import random

from multiprocessing import Process, Pool
from datetime import datetime
from socket import gethostname
from concurrent.futures import ProcessPoolExecutor


class UploadManager:
    def __init__(self, remote_server, remote_dir, recording_name, local_dir=None, logger=None):
        self.username, self.uid, self.gid = self.get_user_info()
        self.remote_server = remote_server
        self.logger = logger
        self.remote_dir = self.get_tree_structure(remote_dir, recording_name)
        self.local_dir = local_dir if local_dir else f"/home/{self.username}/Remote"
        self.full_path = os.path.join(self.local_dir, self.remote_dir)

        # self.compress_process = None
        self.compress_pool = Pool(processes=1)




    def get_user_info(self):
        username = os.getlogin()
        user_info = pwd.getpwnam(username)
        return username, user_info.pw_uid, user_info.pw_gid

    def create_working_dir(self):
        # Ensure working directory exists
        self.logger.log(f"Creating working directory {self.full_path}", log_level=5)
        os.makedirs(self.full_path, exist_ok=True)

    def file_exists(self, filename):
        """
        Check if a file exists in the local mount point.
        Handles potential errors gracefully.
        """
        if not self.is_mounted():
            self.logger.log(f"Cannot check file existence: {self.full_path} is not mounted", log_level=1)
            return False

        if not filename:
            self.logger.log("Filename is invalid or empty", log_level=1)
            return False

        try:
            file_path = os.path.join(self.full_path, filename)
            exists = os.path.exists(file_path)
            self.logger.log(f"File existence check for {file_path}: {exists}", log_level=3)
            return exists
        except Exception as e:
            self.logger.log(f"Error checking file existence for {filename}: {e}", log_level=1)
            return False

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
        """
        Submit a compression task to the pool.
        """
        self.logger.log(f"Queueing compression for {dir_to_compress} with format {format}", log_level=3)
        self.compress_pool.apply_async(self.compress_analyze_and_upload, args=(dir_to_compress, format))


        # if self.compress_process and self.compress_process.is_alive():
        #     self.logger.log("Compression already in progress, waiting for the previous compression to end", log_level=3)
        #     # self.compress_process.join() # Wait for the previous compression to end
        #
        # self.logger.log(f'Compressing and uploading {dir_to_compress}, with format {format}', log_level=3)
        # # log("Dest path : %s " % output_folder)
        # # self.save_process.join()
        # self.compress_process = Process(target=self.compress_analyze_and_upload,
        #                                 args=(dir_to_compress, format,))
        # self.compress_process.start()


    # def is_compressing(self):
    #     return self.compress_process.is_alive()

    def wait_for_compression(self):
        """
        Waits for all tasks in the compression pool to complete.
        """
        self.logger.log("Waiting for all compression tasks to complete...", log_level=3)
        self.compress_pool.close()  # Stop accepting new tasks
        self.compress_pool.join()  # Wait for all submitted tasks to finish
        self.logger.log("All compression tasks completed.", log_level=3)
        # self.compress_process.join()

    def compress_analyze_and_upload(self, folder_name, format, analyze=False):
        compressed_file = self.compress(folder_name=folder_name, format=format)

        # Check if the compressed file is valid
        if not self.check_compression(compressed_file):
            self.logger.log(f"Compression failed for {folder_name}. Original files retained.", log_level=1)
            return False  # Exit early without deleting the original files

        # Perform analysis if required
        output_files = []
        if analyze:
            from src.analyse import Analyser
            analyser = Analyser(logger=self.logger)
            output_files = analyser.run(video_path=compressed_file)
        else:
            self.logger.log("Skipping Analysis", log_level=5)
            output_files = [compressed_file]

        self.logger.log(f"Output files : {output_files}", log_level=5)

        # Upload the compressed file(s) and validate uploads
        for output_file in output_files:

            # Check if NAS is mounted and accessible
            if not self.is_mounted() or not self.is_accessible():
                self.logger.log("Remote directory is not accessible, trying to mount it", log_level=2)
                if not self.mount() or not self.is_accessible():
                    self.logger.log("Failed to mount or remote directory is not accessible, skipping upload", log_level=1)
                    return False

            self.logger.log(f"Remote directory is accessible", log_level=5)
            self.upload(output_file, async_upload=False)

            # Verify upload success before deleting compressed file
            if not self.upload_check(output_file):
                self.logger.log(f"Failed to upload {output_file}. Original files retained.", log_level=1)
                return False  # Exit early without deleting original files or compressed files

            # Remove the compressed file after successful upload
            self.logger.log(f"Removing {output_file}", log_level=5)
            pathlib.Path(output_file).unlink(missing_ok=True)

        # Delete original folder only after all checks pass
        self.logger.log(f"Removing original folder {folder_name}", log_level=5)
        subprocess.run(['rm', '-rf', '%s' % folder_name])

        # Upload remaining files
        self.logger.log(f"Uploading remaining files in {folder_name}", log_level=5)
        # get the parent parent folder name from the path of the compressed file
        abs_path = os.path.abspath(folder_name)
        parent_folder = os.path.dirname(abs_path)
        self.upload_remaining_files(parent_folder)


        return True

    def check_compression(self, compressed_file):
        # Check if the file has been created
        if not os.path.exists(compressed_file):
            self.logger.log(f"Compression failed: {compressed_file} not created.", log_level=1)
            return False

        # Check if the file is empty
        if os.path.getsize(compressed_file) == 0:
            self.logger.log(f"Compression failed: {compressed_file} is empty.", log_level=1)
            return False

        # Verify video integrity with FFmpeg
        check_cmd = ['ffmpeg', '-v', 'error', '-i', compressed_file, '-f', 'null', '-']
        result = subprocess.run(check_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if result.returncode != 0:
            self.logger.log(f"Compression failed: {compressed_file} is not a valid video.", log_level=1)
            return False

        return True

    def compress(self, folder_name, format="tgz", timeout=2700):    # timeout after 45 minutes

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

        try:
            subprocess.run(call_args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=timeout)
            self.logger.log(f"Compression of {folder_name} done", begin="\n")
        except subprocess.TimeoutExpired:
            self.logger.log(f"Compression process for {folder_name} timed out after {timeout} seconds", log_level=1)
            return None  # Return None to indicate failure
        except subprocess.CalledProcessError as e:
            self.logger.log(f"Compression failed for {folder_name}. Error: {e}", log_level=1)
            return None  # Return None to indicate failure

        return output_file


    def upload_remaining_files(self, rec_folder):
        self.logger.log(f"Checking if all files are uploaded in folder {rec_folder}", log_level=3)

        # Check if there are some not uploaded files
        if not rec_folder or not os.path.exists(rec_folder):
            self.logger.log(f"Invalid or non-existent directory: {rec_folder}", log_level=1)
            return

        # Get list of files in the current directory, excluding directories
        files = [f for f in os.listdir(rec_folder) if os.path.isfile(os.path.join(rec_folder, f))]

        # Log files that are not uploaded
        self.logger.log(f"Files not uploaded : {files}", log_level=3)

        # Check if there are any files in the directory
        if len(files) > 0:
            for file in files:
                # Upload the file to the NAS
                upload_ok = self.upload(file_to_upload=file, async_upload=False)
                # When upload is done, and successful, remove the file
                if upload_ok and self.upload_check(file):
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
        """
        Mount the NAS share to the local directory. Adds a timeout to handle long-running commands.
        """
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

        try:
            result = subprocess.run(mount_cmd, capture_output=True, timeout=30)  # Timeout set to 30 seconds
            if result.returncode != 0:
                self.logger.log(f"Failed to mount NAS: {result.stderr.decode()}", log_level=1)
                return False

            self.logger.log(f"Mounted {self.remote_server}/{self.share_name} to {self.local_dir}", log_level=3)
            return True
        except subprocess.TimeoutExpired:
            self.logger.log(f"Mount operation timed out after 30 seconds", log_level=1)
            return False
        except Exception as e:
            self.logger.log(f"Unexpected error during mount operation: {e}", log_level=1)
            return False

    def unmount(self):
        # Unmount the NAS share
        if self.is_mounted():
            unmount_cmd = ["sudo", "umount", self.local_dir]
            subprocess.run(unmount_cmd, check=True)
            print(f"Unmounted {self.local_dir}")

    def is_mounted(self):
        """
        Check if the NAS is mounted by verifying if self.local_dir is a mount point.
        Handles subprocess timeout gracefully.
        """
        try:
            result = subprocess.run(['mountpoint', '-q', self.local_dir], timeout=10, check=False)
            return result.returncode == 0
        except subprocess.TimeoutExpired:
            self.logger.log(f"Timeout expired while checking mount status of {self.local_dir}", log_level=1)
            return False  # Treat it as not mounted if the check times out
        except subprocess.CalledProcessError as e:
            self.logger.log(f"Error checking mount status: {e}", log_level=1)
            return False
        except Exception as e:
            self.logger.log(f"Unexpected error: {e}", log_level=1)
            return False

    def is_accessible(self):
        """
        Check if the NAS server is accessible by pinging it.
        Handles timeout and unexpected errors gracefully.
        """
        nas_host = self.remote_server.lstrip("//").split("/")[0]
        ping_cmd = ["ping", "-c", "1", nas_host]

        try:
            result = subprocess.run(ping_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=5)
            return result.returncode == 0
        except subprocess.TimeoutExpired:
            self.logger.log(f"Ping to {nas_host} timed out after 5 seconds", log_level=1)
            return False
        except Exception as e:
            self.logger.log(f"Error checking accessibility of {nas_host}: {e}", log_level=1)
            return False

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

