import json
import re
import os
from datetime import datetime, timedelta
import sys
import time

from dotenv import load_dotenv
from email_manager import EmailClient, IgnoredFoldersManager

# Add the root directory of the project to the Python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))

from src.upload_manager import SMBManager


# # Constants for configuration
# RECORDING_PATH = "/path/to/folder"
# TIME_WINDOW_TO_CHECK_IN_DAYS = 3
# LOG_FILE_EXTENSION = ".out"
# VIDEO_FILE_EXTENSIONS = (".mkv", ".mp4")
#
# IGNORED_FOLDERS_FILE = "ignored_folders.txt"

# Load configuration from JSON file
def load_config(config_path):
    with open(config_path, "r") as file:
        return json.load(file)


class WormstationMonitor:
    """
    Class to monitor and validate recordings of wormstations.
    """

    def __init__(self, config, email_client, ignored_manager):
        self.recording_path = config["recording_path"]
        self.time_window_days = config["time_window_to_check_in_days"]
        self.log_file_extension = config["log_file_extension"]
        self.video_file_extensions = tuple(config["video_file_extensions"])
        self.email_client = email_client
        self.ignored_manager = ignored_manager

        self.recordings_to_recheck_later = []
        self.skipped_folders = []
        self.terminated_recordings = []
        self.recordings_ok = []
        self.recordings_not_ok = []
        self.recordings_potentially_not_ok = []

    @staticmethod
    def extract_json_from_log(file_path):
        """
        Extracts and parses JSON from a log file.

        :param file_path: Path to the log file.
        :return: Parsed JSON data as a dictionary, or None if parsing fails.
        """
        json_lines = []  # To collect JSON lines
        inside_json = False  # Flag to indicate if we're inside a JSON block

        try:
            with open(file_path, "r") as file:
                for line in file:
                    line = line.strip()  # Remove leading and trailing whitespace

                    # Detect the start of a JSON block
                    if "{" in line and not inside_json:
                        inside_json = True
                        json_lines.append(line[line.index("{"):])  # Capture JSON starting from '{'

                    # Collect lines if inside a JSON block
                    elif inside_json:
                        json_lines.append(line)

                    # Detect the end of a JSON block
                    if "}" in line and inside_json:
                        inside_json = False
                        json_string = " ".join(json_lines)  # Combine lines into a single JSON string
                        return json.loads(json_string)  # Parse the JSON

        except (FileNotFoundError, json.JSONDecodeError) as e:
            # Handle errors gracefully
            print(f"Error reading or parsing JSON in {file_path}: {e}")

        return None

    @staticmethod
    def get_start_time_from_name(name):
        """
        Extracts the start time of a recording from its folder or log file name.

        The naming format should be: "YYYYMMDD_HHMM_*" or "log_YYYYMMDD_HHMM.out".

        :param name: Name of the folder or log file.
        :return: Start time as a datetime object, or None if the format is incorrect.
        """
        match = re.search(r"(\d{8})_(\d{4})", name)  # Match date and time
        if match:
            date_str, time_str = match.groups()
            return datetime.strptime(f"{date_str} {time_str}", "%Y%m%d %H%M")  # Convert to datetime
        return None

    @staticmethod
    def how_many_video_files_to_expect(parameters, elapsed_time):
        """
        Calculates the expected number of video files based on recording parameters.

        :param parameters: Dictionary of recording parameters from the log file.
        :param elapsed_time: Time elapsed since the start of the recording, in seconds.
        :return: Expected number of video files.
        """
        # Extract the time interval (in seconds between frames)
        time_interval = parameters.get("time_interval")
        fps = 1 / time_interval  # Frames per second

        # Check for continuous recording mode
        if parameters.get("record_for_s") == 0 or parameters.get("record_every_h") == 0:
            expected_frames = elapsed_time / time_interval  # Total expected frames
            return int(expected_frames // parameters.get("compress"))  # Divide frames into video files

        # For non-continuous recordings, calculate sessions and videos per session
        sessions = elapsed_time // (parameters.get("record_every_h") * 3600) + 1
        videos_per_session = parameters.get("record_for_s") / parameters.get("compress") / time_interval
        return int(sessions * videos_per_session)

    def get_excluded_folders(self):
        """
        Reads a file containing paths to be ignored.

        :return: Set of normalized absolute folder paths.
        """

        file_path = self.ignored_manager.ignored_folders_file

        if not os.path.exists(file_path):
            return set()
        with open(file_path, "r") as f:
            # Normalize each path to ensure consistent comparison
            return {os.path.abspath(line.strip()) for line in f if line.strip()}

    def check_recordings(self, recheck_delay=900):
        """
        Main function to check all recordings in the specified path.

        It validates:
        - Whether the recording is within the time window.
        - The number of video files against the expected count.
        """
        # Get all recording folders in the path
        recordings = [
            os.path.join(self.recording_path, f) for f in os.listdir(self.recording_path)
            if os.path.isdir(os.path.join(self.recording_path, f))
        ]

        # Sort the recordings by name
        recordings.sort()

        # Get the list of folders to ignore
        excluded_folders = self.get_excluded_folders()

        for recording_path in recordings:
            recording_path = os.path.abspath(recording_path)  # Normalize the path

            # Skip excluded folders
            if recording_path in excluded_folders:
                # print(f"Skipping ignored folder: {recording_path}")
                self.skipped_folders.append(recording_path)
                continue

            # Extract the start time from the folder name
            start_time = self.get_start_time_from_name(recording_path)

            # Skip recordings if the start time is invalid or outside the time window
            if not start_time or start_time < datetime.now() - timedelta(days=self.time_window_days):
                continue

            # Check all devices in this recording
            self.check_devices_in_recording(recording_path, start_time)

        self.print_results()

        # Recheck flagged recordings
        if self.recordings_to_recheck_later:
            print(f"\nWaiting for {recheck_delay} minutes before rechecking...")
            time.sleep(recheck_delay)  # Wait 15 minutes
            print("\nRechecking flagged recordings:")
            self.clear_results()
            for device_path, start_time in list(self.recordings_to_recheck_later):
                self.check_device_logs_and_videos(device_path, start_time, force_alert=True)
                self.recordings_to_recheck_later.remove((device_path, start_time))  # Remove after rechecking

            self.print_results()

    def clear_results(self):
        """
        Clears the results lists.
        """
        self.skipped_folders.clear()
        self.terminated_recordings.clear()
        self.recordings_ok.clear()
        self.recordings_not_ok.clear()
        self.recordings_potentially_not_ok.clear()

    def print_results(self):
        # Print summary of results
        print("\nSummary:")
        print(f"  Skipped folders: {len(self.skipped_folders)}")
        print(f"  Terminated recordings: {len(self.terminated_recordings)}")
        print(f"  Recordings OK: {len(self.recordings_ok)}")
        print(f"  Recordings not OK: {len(self.recordings_not_ok)}")
        print(f"  Recordings potentially not OK: {len(self.recordings_potentially_not_ok)}")

        print("\n\nDetails:")
        print(f"  Skipped folders:")
        for folder in self.skipped_folders:
            print(f"    {folder}")
        print(f"  Terminated recordings:")
        for folder, start_time in self.terminated_recordings:
            print(f"    {folder} (started at {start_time})")
        print(f"  Recordings not OK:")
        for folder, actual, expected in self.recordings_not_ok:
            print(f"    {folder} has {actual} video files but {expected} were expected.")
        print(f"  Recordings potentially not OK:")
        for folder, actual, expected in self.recordings_potentially_not_ok:
            print(
                f"    {folder} has {actual} video files but {expected} were expected. Video compression may be ongoing.")
        print(f"  Recordings OK:")
        for folder, actual, expected in self.recordings_ok:
            print(f"    {folder} has the expected number of video files.")

        print("\n\n")


    def check_devices_in_recording(self, recording_path, start_time):
        """
        Checks all devices within a specific recording folder.

        :param recording_path: Path to the recording folder.
        :param start_time: Start time of the recording as a datetime object.
        """
        # Get subfolders for each device in the recording
        devices = [
            os.path.join(recording_path, d) for d in os.listdir(recording_path)
            if os.path.isdir(os.path.join(recording_path, d))
        ]

        excluded_folders = self.get_excluded_folders()

        for device_path in devices:
            # Check logs and videos for each device

            if device_path in excluded_folders:
                # print(f"Skipping ignored folder: {device_path}")
                self.skipped_folders.append(device_path)
                continue

            self.check_device_logs_and_videos(device_path, start_time)

    def check_device_logs_and_videos(self, device_path, start_time, force_alert=False):
        """
        Validates log files and video files for a specific device.

        :param device_path: Path to the device folder.
        :param start_time: Start time of the recording as a datetime object.
        """

        # Find all log files in the device folder
        log_files = [
            os.path.join(device_path, f) for f in os.listdir(device_path) if f.endswith(self.log_file_extension)
        ]

        for log_file in log_files:
            # Parse parameters from the log file
            parameters = self.extract_json_from_log(log_file)
            if not parameters:
                continue

            # Check for timeout conditions
            timeout = parameters.get("timeout")
            elapsed_time = (datetime.now() - start_time).total_seconds()  # Total elapsed time in seconds
            if elapsed_time > timeout:
                # print(f"  {log_file} has timed out")
                self.terminated_recordings.append((device_path, start_time))
                continue

            # Get video files in the folder
            video_files = [
                f for f in os.listdir(device_path) if f.endswith(self.video_file_extensions)
            ]

            # Calculate the expected number of video files
            expected_videos = self.how_many_video_files_to_expect(parameters, elapsed_time)

            if not self.compare_video_count(device_path, len(video_files), expected_videos, force_alert):
                if not force_alert:
                    self.recordings_to_recheck_later.append((device_path, start_time))


    def compare_video_count(self, device_path, actual, expected, force_alert=False):
        """
        Compares the actual and expected number of video files and prints a status message.
        """
        if actual < expected - 1 or force_alert:
            # print(f"  {device_path} has {actual} video files but {expected} were expected.")
            self.email_client.send_email_to_all(
                subject="Wormstation Recording Alert",
                body=f"Discrepancy detected in {device_path}.\n"
                     f"Expected: {expected}, Actual: {actual}.\n"
                     f"Please check the recording folder.\n\n"
                     f"If you want to ignore future warnings for this folder, reply to this email with the text:\n"
                     f"IGNORE:{device_path}"
            )
            self.recordings_not_ok.append((device_path, actual, expected))
            return True
        elif actual < expected:
            # print(
                # f"  {device_path} has {actual} video files but {expected} were expected. Video compression may be ongoing.")
            self.recordings_potentially_not_ok.append((device_path, actual, expected))
            return False
        else:
            # print(f"  {device_path} has the expected number of video files.")
            self.recordings_ok.append((device_path, actual, expected))
            return True


if __name__ == "__main__":

    # Load configuration
    try:
        config = load_config("monitor_config.json")
    except FileNotFoundError:
        config = load_config(sys.argv[1])


    # Load environment variables
    load_dotenv()
    EMAIL_USER = os.getenv("EMAIL_USER")
    EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")
    if not EMAIL_USER or not EMAIL_PASSWORD:
        raise ValueError("Email credentials are missing. Please set them in environment variables or a .env file.")

    # Initialize components
    email_client = EmailClient(EMAIL_USER, EMAIL_PASSWORD, recipient_list=config["recipient_list"])
    ignored_manager = IgnoredFoldersManager(config["ignored_folders_file"])
    monitor = WormstationMonitor(config, email_client, ignored_manager)

    uploader = SMBManager(nas_server=config["nas_server"],
                          share_name=config["share_name"],
                          credentials_file=config["credentials_file"],
                          working_dir=config["smb_dir"])

    # Check if NAS is already mounted, if not mount it
    if not uploader.is_mounted():
        uploader.mount()

    # Run the monitor
    try:
        email_client.connect_imap()
        ignored_manager.update(email_client)
        monitor.check_recordings()
    except Exception as e:
        print(f"Error: {e}")
    finally:
        email_client.disconnect_imap()