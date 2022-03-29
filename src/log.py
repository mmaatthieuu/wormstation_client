import datetime as dt
import os

class Logger:
    def __init__(self, verbosity_level, save_log=False):
        self.verbosity_level = verbosity_level

        self.path = self.init_path(save_log)


    def log(self, log_msg, begin="", end="\n"):
        string = f'{begin}[{str(dt.datetime.now())}] : {log_msg}'
        if self.path is None:
            print(string, end=end)
        else:
            with open(self.path, 'a') as log_file:
                print(string, end=end, file=log_file)
                #log_file.write(string)

    def init_path(self, save_log):
        if save_log:
            path = f"/home/{os.getlogin()}/log"

            try:
                os.mkdir(path)
            except FileExistsError:
                pass

            path = f'{path}/log_{dt.datetime.now().strftime("%Y%m%d_%H%M")}.out'
        else:
            path = None


        return path


    def get_log_file_path(self):
        return self.path

    def get_log_filename(self):
        return os.path.basename(self.path)




