#!/usr/bin/python3 -u

"""
Main script to handle camera recording with signal handling and parameter loading.

This script manages the camera recording process by initializing a `Recorder` object,
loading parameters from a JSON file, and handling various system signals (e.g., SIGTERM, SIGUSR1).

Attributes:
    version (str): The current Git version of the project.
"""

import os.path

import subprocess
import sys
import signal

from src.parameters import Parameters

from src.record import Recorder

import os
import subprocess
import time


def get_git_version() -> str:
    """
    Get the Git version of the code running, including uncommitted changes.

    Returns:
        str: The current commit hash with a `-dirty` suffix if there are uncommitted changes,
        or "unknown" if the folder is not a valid Git repository.
    """
    try:
        # Get the directory containing the .git folder
        folder_path = os.path.dirname(os.path.realpath(__file__))
        git_dir = os.path.join(folder_path, '.git')

        # Check if .git directory exists
        if not os.path.exists(git_dir):
            return "unknown (not a git repository)"

        # Get the current commit hash
        git_hash = subprocess.check_output(
            ['git', f'--git-dir={git_dir}', 'rev-parse', '--short', 'HEAD'],
            text=True
        ).strip()

        # Check if there are uncommitted changes
        dirty_status = subprocess.call(
            ['git', f'--git-dir={git_dir}', f'--work-tree={folder_path}', 'diff', '--quiet']
        )

        # If uncommitted changes exist, append '-dirty'
        if dirty_status != 0:
            git_hash += "-dirty"

        return git_hash
    except subprocess.CalledProcessError as e:
        return f"unknown (git error: {e})"
    except Exception as e:
        return f"unknown (error: {e})"


def sigterm_handler(signal, frame):
    """
    Handle the SIGTERM signal.

    This function stops the recording process gracefully when a SIGTERM signal is received.

    Args:
        signal (int): Signal number.
        frame: Current stack frame (unused).
    """
    print("Received SIGTERM signal. Stopping recording.")
    if recorder:
        recorder.logger.log("Received SIGTERM signal. Stopping recording.", log_level=1)
        recorder.stop()

    sys.exit(0)


def sigusr1_handler(signal, frame):
    """
    Handle the SIGUSR1 signal.

    This function allows capturing a new frame while the recording process is paused.

    Args:
        signal (int): Signal number.
        frame: Current stack frame (unused).
    """
    print("Received SIGUSR1 signal. Capturing a new frame.")
    if recorder:  # Check if the recorder is initialized
        recorder.logger.log("Received SIGUSR1 signal. Capturing a new frame.", log_level=3)
        recorder.capture_frame_during_pause()



def main():
    """
    Main entry point of the program.

    This function sets up signal handlers, loads recording parameters from a JSON file, and
    initializes and starts the recording process using the `Recorder` class.
    The JSON file containing the parameters must be provided as an argument when running the script.

    Raises:
        FileNotFoundError: If the specified parameters file does not exist.
        ValueError: If the parameters file contains invalid data.
    """
    try:
        # Set up signal handlers
        signal.signal(signal.SIGTERM, sigterm_handler)
        signal.signal(signal.SIGUSR1, sigusr1_handler)

        # Ensure the user provides a parameters file as an argument
        if len(sys.argv) <= 1:
            print("Error: You must provide a JSON file containing parameters.")
            print("Usage: python3 cam.py <parameters_file>")
            sys.exit(1)

        time.sleep(9900) # 2 hours 45 minutes

        # Load parameters
        parameters_file = sys.argv[1]

        global recorder
        recorder = Recorder(parameter_file=parameters_file, git_version=get_git_version())

        try:
            recorder.start_recording()
        except KeyboardInterrupt:
            recorder.logger.log("Keyboard interrupt. Stopping recording.")
            print("Keyboard interrupt. Stopping recording.")
        finally:
            del recorder

    except FileNotFoundError as e:
        print(e)
        sys.exit(1)
    except ValueError as e:
        print(e)
        sys.exit(1)
    # except Exception as e:
    #     print(f"Unexpected error: {e}")
    #     sys.exit(1)


if __name__ == "__main__":
    main()
