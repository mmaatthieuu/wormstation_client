

class CrashTimeOutException(TimeoutError):
    def __init__(self, frame_number_):
        self.frame_number = frame_number_