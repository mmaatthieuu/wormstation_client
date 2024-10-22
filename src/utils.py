from datetime import datetime, timedelta
import time
import psutil
import os


def wait_until_next_even_second():
    period = 2
    while True:
        current_time = time.time()
        if current_time % period < 0.005:
            break

        remaining_time = period - (current_time % period)
        time.sleep(remaining_time)


def get_most_available_core(exclude_cores=None):
    """
    Get the most available CPU core, optionally excluding specific cores.

    :param exclude_cores: List of cores to exclude from selection. If None, no cores are excluded.
    :return: The core number of the most available CPU core.
    """
    # Get CPU usage for all cores
    cpu_usage = psutil.cpu_percent(percpu=True)

    # If exclude_cores is not provided or is an empty list, consider all cores
    if exclude_cores:
        for core in exclude_cores:
            # Set the usage of excluded cores to infinity to avoid selecting them
            cpu_usage[core] = float('inf')

    # Return the index (core number) of the core with the lowest usage
    return cpu_usage.index(min(cpu_usage))


def set_affinity(pid, core, logger=None):
    """
    Set CPU affinity for a process.

    :param pid: Process ID (use os.getpid() for the current process)
    :param core: The core number to assign
    """
    os.sched_setaffinity(pid, {core})
    if logger is not None:
        logger.log(f"Process {pid} assigned to core {core}.", log_level=5)

    else:
        print(f"Process {pid} assigned to core {core}.")  # Replace with logger if needed