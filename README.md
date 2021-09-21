# piworm

usage: cam.py [-h] [-v] [-vv] [-p] [-t [TIMEOUT]] [-ti [TIME_INTERVAL]]
              [-avg [AVERAGE]] [-o OUTPUT] [-q [QUALITY]] [-iso [ISO]]
              [-ss [SHUTTER_SPEED]] [-x [COMPRESS]]

optional arguments:
  -h, --help            show this help message and exit
  -v, --verbose         increase output verbosity
  -vv, --vverbose       increase more output verbosity
  -p, --preview         display camera preview
  -t [TIMEOUT], --timeout [TIMEOUT]
                        time (in s) before takes picture and shuts down
  -ti [TIME_INTERVAL], --time-interval [TIME_INTERVAL]
                        time interval between frames in seconds
  -avg [AVERAGE], --average [AVERAGE]
                        number of pictures to average at each frame
  -o OUTPUT, --output OUTPUT
                        output filename
  -q [QUALITY], --quality [QUALITY]
                        set jpeg quality <0 to 100>
  -iso [ISO], --iso [ISO]
                        sets the apparent ISO setting of the camera
  -ss [SHUTTER_SPEED], --shutter-speed [SHUTTER_SPEED]
                        sets the shutter speed of the camera in microseconds
  -x [COMPRESS], --compress [COMPRESS]
