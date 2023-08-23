from datetime import datetime, timedelta
import time
def wait_until_next_even_second():
    period = 2
    while True:
        current_time = time.time()
        if current_time % period < 0.005:
            break

        remaining_time = period - (current_time % period)
        time.sleep(remaining_time)
