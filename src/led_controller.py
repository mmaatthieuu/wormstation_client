import RPi.GPIO as GPIO
import time
import multiprocessing
import atexit
import psutil
from datetime import datetime

class LED():
    def __init__(self, _control_gpio_pin, logger=None, name=None):
        GPIO.setwarnings(False)
        self.gpio_pin = _control_gpio_pin
        self.is_on = None

        GPIO.setmode(GPIO.BCM)
        GPIO.setup(self.gpio_pin, GPIO.OUT)

        self.program = None

        self.logger = logger
        self.name = name

        #self.turn_off()

        # Register a cleanup function to stop the LED timer process on exit
        atexit.register(self.cleanup)

    def __del__(self):
        self.cleanup()

    def cleanup(self):
        if self.program and self.program.is_alive():
            self.program.terminate()
            self.program.join()

    def turn_on(self):
        self.logger.log(f'Turning on {self.name} LED')
        GPIO.output(self.gpio_pin, GPIO.HIGH)
        self.is_on = True

    def turn_off(self):
        self.logger.log(f'Turning off {self.name} LED')
        GPIO.output(self.gpio_pin, GPIO.LOW)
        self.is_on = False

    def run_led_timer(self, duration, period, timeout):
        # Extend the timeout to ensure that the LED timer process runs until the end of the experiment
        timeout = timeout + (period * 2)

        def led_timer_process():
            # This function defines a separate process for LED control

            # Calculate the end time of the LED timer process
            end_time = time.time() + timeout

            # Define an offset to ensure that the LEDs are turned on just before pictures are taken
            offset = 0.25

            while time.time() < end_time:
                # Check the current time
                current_time = time.time()

                # Calculate the time until the next LED activation
                time_until_next_activation = (current_time + offset) % period

                # Calculate the remaining time until activation
                remaining_time = period - time_until_next_activation

                # Sleep to get closer to the activation time
                time.sleep(remaining_time)

                self.turn_on()  # Turn on the LEDs
                time.sleep(duration)  # Keep the LEDs on for the specified duration
                self.turn_off()  # Turn off the LEDs

        # Create a new multiprocessing process that runs the LED control function
        self.program = multiprocessing.Process(target=led_timer_process)
        self.program.start()

