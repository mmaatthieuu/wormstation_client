import datetime as dt
import os
import sys
from tqdm import tqdm

class Logger:
    def __init__(self, verbosity_level, save_log=False, recording_name=None):
        self.verbosity_level = verbosity_level

        self.path = self.init_path(save_log, recording_name)

        self.log(f'Logger initialized with verbosity level {verbosity_level}', log_level=3)

        '''
        Verbosity levels:
        0: No log
        1: Only errors
        2: Errors and warnings
        3: Errors, warnings and info
        4: Errors, warnings, info and debug
        5: Errors, warnings, info, debug and trace
        6: Errors, warnings, info, debug, trace and verbose
        7: Errors, warnings, info, debug, trace, verbose and very verbose
        8: Errors, warnings, info, debug, trace, verbose, very verbose and ultra verbose
        '''

    def log(self, log_msg, begin="", end="\n", log_level=None):

        # Define log level prefixes
        log_level_prefixes = {
            0: "",
            1: "[ERROR]",
            2: "[WARNING]",
            3: "[INFO]",
            4: "[DEBUG]",
            5: "[TRACE]",
            6: "[VERBOSE]",
            7: "[VERY VERBOSE]",
            8: "[ULTRA VERBOSE]"
        }

        # Set default log level if not provided
        if log_level is None:
            log_level = self.verbosity_level

        # Check if the log level is valid
        if log_level not in log_level_prefixes:
            raise ValueError(f"Invalid log level: {log_level}")

        # Only log if the message's log level is equal to or greater than the current verbosity level
        if log_level <= self.verbosity_level:
            # Construct the log message with the prefix
            log_prefix = log_level_prefixes[log_level]
            string = f'{begin}[{str(dt.datetime.now())}] {log_prefix} : {log_msg}'

            # Write the log message to the appropriate output
            if self.path is None:
                print(string, end=end)
            else:
                with open(self.path, 'a') as log_file:
                    print(string, end=end, file=log_file)

    def init_path(self, save_log, recording_name):
        # if save_log is True, create a log file in the user's home directory
        if save_log:
            path = f"/home/{os.getlogin()}/log"

            try:
                os.mkdir(path)
            except FileExistsError:
                pass

            # Check if recording_name is None to avoid adding None to the filename
            if recording_name is None:
                path = f'{path}/log_{dt.datetime.now().strftime("%Y%m%d_%H%M")}.out'
            else:
                path = f'{path}/log_{dt.datetime.now().strftime("%Y%m%d_%H%M")}_{recording_name}.out'

            # Create a symbolic link called last_recording.out pointing towards the current log file
            symlink_path = f'/home/{os.getlogin()}/log/last_recording.out'
            try:
                os.symlink(path, symlink_path)
            except FileExistsError:
                os.remove(symlink_path)
                os.symlink(path, symlink_path)
        else:
            path = None

        return path


    def get_log_file_path(self):
        return self.path

    def get_log_filename(self):
        return os.path.basename(self.path)


class FakeLogger:
    def log(self, message, log_level=1):
        print(f"[LOG - Level {log_level}]: {message}")

