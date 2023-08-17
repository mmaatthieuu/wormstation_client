from datetime import datetime, timedelta
import time

"""
def log(log_msg, begin="", end="\n"):
    print("%s[%s] : %s" %  (begin, str(dt.datetime.now()), log_msg), end=end)
"""


def wait_until_next_even_second():
    useconds_until_next_even_second = get_time_until_next_even_second_in_us()
    # Sleep until the next even second
    time.sleep(useconds_until_next_even_second / 1000000)


def get_time_until_next_even_second_in_us():
    # Actually it is not the next even second but the next second multiple of 4.
    # It increases the chances that all the device start simultaneously and are not splitted

    # Get the current time
    current_time = datetime.now()

    # Calculate the number of milliseconds until the next second multiple of 4
    useconds_until_next_even_second = 1000000 - current_time.microsecond + ((current_time.second + 1) % 4) * 1000000

    return useconds_until_next_even_second

def get_time_until_next_second_multiple_of_x(x):
    current_time = datetime.now()

    # Calculate the number of milliseconds until the next second multiple of 4
    useconds_until_next_second_multiple_of_x = 1000000 - current_time.microsecond + ((current_time.second + 1) % x) * 1000000

    return useconds_until_next_second_multiple_of_x

def get_remaining_time_to_next_seconds(time_of_previous_event, n_seconds):
    try:
        previous_second = datetime.fromtimestamp(time_of_previous_event).second
    except:
        previous_second = time_of_previous_event.second

    current_datetime = datetime.now()
    print(f'current time : {current_datetime.strftime("%Y-%m-%d %H:%M:%S.%f")}')

    next_datetime = current_datetime.replace(second=previous_second,microsecond=0) + timedelta(seconds=n_seconds)
    print(f'next time : {next_datetime.strftime("%Y-%m-%d %H:%M:%S.%f")}')

    second_until_next_seconds = (next_datetime - datetime.now()).total_seconds()

    print(f'diff : {second_until_next_seconds}')

    print(f'in function : {second_until_next_seconds}')

    return second_until_next_seconds, next_datetime
