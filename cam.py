#!/usr/bin/python3 -u

#import picamera
import os.path

import subprocess
import sys
import signal

from parameters import Parameters

from src.record import Recorder

from src.camera.CrashTimeOutException import CrashTimeOutException


# TODO make that git check better
git_check = subprocess.run(['git', '--git-dir=/home/matthieu/piworm/.git', 'rev-list',
                            '--all', '--abbrev-commit', '-n', '1'], text=True, capture_output=True)
version = git_check.stdout


def get_git_version():
    # TODO make that git check better
    folder_path = os.path.dirname(os.path.realpath(__file__))
    git_check = subprocess.run(['git', f'--git-dir={folder_path}/.git', 'rev-list',
                                '--all', '--abbrev-commit', '-n', '1'], text=True, capture_output=True)
    version = git_check.stdout
    return version


def sigterm_handler(signal, frame):
    # Handle SIGTERM signal here
    print("Received SIGTERM signal. Stopping recording.")
    if recorder:
        recorder.logger.log("Received SIGTERM signal. Stopping recording.", log_level=1)
        recorder.stop()

    sys.exit(0)


def sigusr1_handler(signal, frame):
    # Handler for custom signal to capture a new frame while recording is in pause
    print("Received SIGUSR1 signal. Capturing a new frame.")
    if recorder:  # Check if the recorder is initialized
        recorder.logger.log("Received SIGUSR1 signal. Capturing a new frame.", log_level=3)
        recorder.capture_frame_during_pause()



def main():
    try:
        # Set up signal handlers
        signal.signal(signal.SIGTERM, sigterm_handler)
        signal.signal(signal.SIGUSR1, sigusr1_handler)

        # Ensure the user provides a parameters file as an argument
        if len(sys.argv) <= 1:
            print("Error: You must provide a JSON file containing parameters.")
            print("Usage: python3 cam.py <parameters_file>")
            sys.exit(1)

        # Load parameters
        parameters_file = sys.argv[1]
        parameters = Parameters(parameters_file)

        global recorder
        recorder = Recorder(parameters=parameters, git_version=get_git_version())

        try:
            recorder.start_recording()
        except KeyboardInterrupt:
            recorder.logger.log("Keyboard interrupt. Stopping recording.")
            print("Keyboard interrupt. Stopping recording.")
        except CrashTimeOutException:
            print("#DEBUG Crash time out exception")
        finally:
            del recorder

    except FileNotFoundError as e:
        print(e)
        sys.exit(1)
    except ValueError as e:
        print(e)
        sys.exit(1)
    except Exception as e:
        print(f"Unexpected error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
