import numpy as np

class NPImage(object):
    y_data = np.empty((2464, 3296), dtype=np.uint8)

    def write(self, buf):
        # write will be called once for each frame of output. buf is a bytes
        # object containing the frame data in YUV420 format; we can construct a
        # numpy array on top of the Y plane of this data quite easily:
        self.y_data = np.frombuffer(
            buf, dtype=np.uint8, count=3296 * 2464).reshape((2464, 3296))



    def flush(self):
        # this will be called at the end of the recording; do whatever you want
        # here
        pass

    def get_data(self):
        return self.y_data