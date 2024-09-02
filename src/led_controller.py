import RPi.GPIO as GPIO
import time
import multiprocessing
import atexit
import psutil
from datetime import datetime

class LED():
    def __init__(self, _control_gpio_pin, logger=None, name=None, keep_state=False):
        GPIO.setwarnings(False)
        self.gpio_pin = _control_gpio_pin
        self.is_on = None
        self.keep_state = keep_state

        GPIO.setmode(GPIO.BCM)
        GPIO.setup(self.gpio_pin, GPIO.OUT)

        self.program = None

        self.logger = logger
        self.name = name

        # Event to control running of the LED process
        self.running = multiprocessing.Event()

        #self.turn_off()

        # Register a cleanup function to stop the LED timer process on exit
        atexit.register(self.cleanup)

    def __del__(self):
        self.cleanup()

    def cleanup(self):
        if not self.keep_state:
            self.turn_off()
        if self.program and self.program.is_alive():
            self.program.terminate()
            self.program.join()

    def turn_on(self):
        #print(datetime.now(), "LED ON")
        self.logger.log(f'Turning on {self.name} LED', log_level=5)
        GPIO.output(self.gpio_pin, GPIO.HIGH)
        self.is_on = True

    def turn_off(self):
        #print(datetime.now(), "LED OFF")
        self.logger.log(f'Turning off {self.name} LED', log_level=5)
        GPIO.output(self.gpio_pin, GPIO.LOW)
        self.is_on = False

    def pause_process(self):
        """Pause the blinking process."""
        if self.program and self.program.is_alive():
            if self.logger:
                self.logger.log(f'Pausing blinking of {self.name} LED', log_level=5)
            self.running.clear()  # Clear the running flag to pause the process

    def resume_process(self):
        """Resume the blinking process."""
        if self.program and self.program.is_alive():
            if self.logger:
                self.logger.log(f'Resuming blinking of {self.name} LED', log_level=5)
            self.running.set()  # Set the running flag to resume the process

    # Patterns
    def turn_on_for_n_sec(self, duration):
        self.turn_on()
        time.sleep(duration)
        self.turn_off()

    def blink(self, total_duration, blink_on_duration, blink_period):
        end_time = time.time() + total_duration

        off_time = blink_period - blink_on_duration

        while time.time() < end_time:
            self.turn_on()
            time.sleep(blink_on_duration)
            self.turn_off()
            time.sleep(off_time)


    def wait_until_next_activation(self, period, offset):
        """"
        Wait until the next activation of the LED based on the period and offset.

        Parameters:
            - period: The time interval between each activation of the LED, in seconds.
                It is based on time so if period is 2, it will activate even seconds. If period
                is one hour, it will activate every hour, at xx:00:00.
            - offset: The time offset from the time of the activation. It is in seconds.
                Ex: if period is 2 and offset is -0.25, it will activate 0.25 seconds before the even seconds.

        """
        current_time = time.time()  # Get the current time
        # Calculate the time until the next activation of the LED
        time_until_next_activation = (current_time - offset) % period
        remaining_time = period - time_until_next_activation

        time.sleep(remaining_time)


    def run_led_timer(self, duration, period, timeout, blinking=False, blinking_period=None):
        """
        Run a timer to control the LED.

        Parameters:
        - duration: The duration for which the LED should be on, in seconds (e.g., 0.5 sec).
        - period: The time interval between each activation of the LED, in seconds (e.g., 2 sec).
        - timeout: The total time for which the LED should run, in seconds.
        - blinking: A flag to indicate whether the LED should blink or stay on. It is only for optogenetics.
            It creates a blinking pattern with a 1-second on and 1-second off cycle, within the specified duration.
        """

        # Extend the timeout to ensure that the LED timer process runs until the end of the experiment
        timeout = timeout + (period * 2)

        def led_timer_process():
            """
            This function defines a separate process for LED control.
            It manages the LED state (on/off) based on the timing parameters.
            """
            end_time = time.time() + timeout  # Calculate the end time for the LED process

            # Small offset to ensure alignment with the frame acquisition process.
            # The LEDs turn on <offset> seconds before the frames are captured. 0.25 sec is a good value.
            #offset = 0.25

            while time.time() < end_time:  # Main loop runs until the timeout is reached

                # Wait until the process is set to run
                self.running.wait()  # This will block the loop if the running flag is not set

                if blinking:  # If the LED should blink, i.e. be disynchronized with the frame acquisition.
                        self.wait_until_next_activation(period, 0.5)
                        self.blink(duration, 1, blinking_period)

                else:  # If blinking is not enabled (steady state)
                    self.wait_until_next_activation(period, -0.25)
                    self.turn_on_for_n_sec(duration)

        # Ensure any existing process is properly cleaned up before starting a new one
        if self.program and self.program.is_alive():
            self.cleanup()

        # Initialize the running flag as True to start the process
        self.running.set()

        # Create a new multiprocessing process that runs the LED control function
        self.program = multiprocessing.Process(target=led_timer_process)
        self.program.start()
        self.logger.log(f'Started LED timer process for {self.name}', log_level=5)




