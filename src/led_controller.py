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

        self.blinking_paused = multiprocessing.Event()  # Event to control pausing of blinking

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
        print(datetime.now(), "LED ON")
        self.logger.log(f'Turning on {self.name} LED', log_level=5)
        GPIO.output(self.gpio_pin, GPIO.HIGH)
        self.is_on = True

    def turn_off(self):
        print(datetime.now(), "LED OFF")
        self.logger.log(f'Turning off {self.name} LED', log_level=5)
        GPIO.output(self.gpio_pin, GPIO.LOW)
        self.is_on = False

    def pause_blinking(self):
        """Pause the blinking process."""
        if self.program and self.program.is_alive():
            self.logger.log(f'Pausing blinking of {self.name} LED', log_level=5)
            self.blinking_paused.set()  # Set the pause flag

    def resume_blinking(self):
        """Resume the blinking process."""
        if self.program and self.program.is_alive():
            self.logger.log(f'Resuming blinking of {self.name} LED', log_level=5)
            self.blinking_paused.clear()  # Clear the pause flag

    def run_led_timer(self, duration, period, timeout, blinking=False):
        # Extend the timeout to ensure that the LED timer process runs until the end of the experiment
        timeout = timeout + (period * 2)

        def led_timer_process():
            # This function defines a separate process for LED control
            end_time = time.time() + timeout
            offset = 0.25

            while time.time() < end_time:
                current_time = time.time()
                time_until_next_activation = (current_time + offset) % period
                remaining_time = period - time_until_next_activation

                # Sleep to get closer to the activation time
                time.sleep(remaining_time)

                if blinking:
                    time.sleep(0.75)
                    start_duration = time.time()
                    while time.time() < start_duration + duration:
                        # Check if blinking is paused
                        if self.blinking_paused.is_set():
                            time.sleep(0.1)  # Wait a little while checking if paused
                            continue

                        # Turn LEDs on and off as part of the blinking pattern
                        print(datetime.now(), "LED ON")
                        self.turn_on()
                        time.sleep(1)  # Keep the LEDs on for 1 second
                        print(datetime.now(), "LED OFF")
                        self.turn_off()
                        if time.time() < start_duration + duration:
                            time.sleep(1)  # Wait for 1 second
                else:
                    # Check if blinking is paused
                    if not self.blinking_paused.is_set():
                        self.turn_on()  # Turn on the LEDs
                        time.sleep(duration)  # Keep the LEDs on for the specified duration

                self.turn_off()  # Turn off the LEDs

        # Create a new multiprocessing process that runs the LED control function
        self.program = multiprocessing.Process(target=led_timer_process)
        self.program.start()

