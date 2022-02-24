

class CrashTimeOutException(TimeoutError):
    def __init__(self, frame_number_):
        super(CrashTimeOutException, self).__init__()
        self.frame_number = frame_number_