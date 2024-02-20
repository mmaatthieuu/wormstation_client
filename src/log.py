import datetime as dt
import os

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

        # TODO: Add prefix to log messages, like [ERROR], [WARNING], [INFO], [DEBUG], [TRACE], [VERBOSE]

        if log_level is None: log_level=self.verbosity_level
        if log_level <= self.verbosity_level:
            string = f'{begin}[{str(dt.datetime.now())}] : {log_msg}'
            if self.path is None:
                print(string, end=end)
            else:
                with open(self.path, 'a') as log_file:
                    print(string, end=end, file=log_file)
                    #log_file.write(string)

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
        else:
            path = None

        return path


    def get_log_file_path(self):
        return self.path

    def get_log_filename(self):
        return os.path.basename(self.path)




