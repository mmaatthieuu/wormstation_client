import threading
import time

import RPi.GPIO as GPIO

from src.led_control.led_driver import LEDDriver


class LED:
    """
    Class to control a LED array using the FT232H chip and LED driver. High-level control of the LED.
    Wrapper class for the LEDDriver to control the LED array and do specific LED operations.
    """

    def __init__(self, usb_handler, channel, current='7.5mA', logger=None, name=None, final_state=False):
        self.channel = channel  # SPI channel for this LED
        self.led_driver = LEDDriver(usb_handler=usb_handler, channel=self.channel, current=current, logger=logger)

        self.logger = logger
        self.name = name
        self.is_on = None
        self.program = None
        self.running = threading.Event()
        self.pause_event = threading.Event()
        self.pause_event.set()  # Initially set to allow execution
        self.final_state = final_state # Keep the LED in the final state after cleanup

    def set_current(self, current):
        """Set the current for the LED."""
        self.led_driver.set_max_current(self.led_driver.read_current_input(current))

    def turn_on(self):
        self.logger.log(f'Turning on {self.name} LED', log_level=5)
        self.is_on = self.led_driver.turn_on_leds()

    def turn_off(self):
        self.logger.log(f'Turning off {self.name} LED', log_level=5)
        self.is_on = self.led_driver.turn_off_leds()

    def cleanup(self):
        """Cleanup the LED processes and turn it off."""
        if self.program and self.program.is_alive():
            self.logger.log(f"Terminating LED program for {self.name}", log_level=5)
            self.running.clear()
            self.pause_event.set()  # Ensure it doesn't hang on pause
            self.program.join(timeout=20)  # Ensure the thread has terminated
            if self.program.is_alive():
                self.logger.log(f"Failed to terminate LED program for {self.name}", log_level=3)
            else:
                self.logger.log(f"LED program for {self.name} terminated", log_level=5)

        # By default, turn off the LED, but if final_state is True, keep it in the final state
        if self.final_state:
            pass  # Keep the LED in the final state
        else:
            self.turn_off()

    def pause_process(self):
        """Pause the blinking process."""
        if self.program and self.program.is_alive():
            self.logger.log(f'Pausing blinking of {self.name} LED', log_level=5)
            self.pause_event.clear()

    def resume_process(self):
        """Resume the blinking process."""
        if self.program and self.program.is_alive():
            self.logger.log(f'Resuming blinking of {self.name} LED', log_level=5)
            self.pause_event.set()

    def turn_on_for_n_sec(self, duration):
        self.turn_on()
        time.sleep(duration)
        self.turn_off()

    def blink(self, total_duration, blink_on_duration, blink_period):
        """Blink the LED for a total duration."""
        self.logger.log(f"[{self.name} LED] Blinking for {total_duration:.2f} seconds with {blink_on_duration:.2f},"
                        f" period {blink_period:.2f}",
                        log_level=6)
        end_time = time.time() + total_duration
        off_time = blink_period - blink_on_duration

        while time.time() < end_time and self.running.is_set():
            self.turn_on()
            time.sleep(blink_on_duration)

            # Check if thread should terminate before turning off
            if not self.running.is_set():
                break

            self.turn_off()
            time.sleep(off_time)

            # Check again before the next cycle
            if not self.running.is_set():
                break

    def wait_until_next_activation(self, period, offset, increment_step=10):
        """Wait until the next activation of the LED based on the period and offset."""
        current_time = time.time()
        time_until_next_activation = (current_time - offset) % period
        remaining_time = period - time_until_next_activation
        self.logger.log(f'[{self.name} LED] Waiting for {remaining_time:.2f} seconds until next activation',
                        log_level=6)

        end_time = time.time() + remaining_time
        while time.time() < end_time:
            # Check if the pause_event is cleared, if so, break the loop
            if not self.pause_event.is_set():
                self.logger.log(f'[{self.name} LED] Paused during waiting. Interrupting wait.', log_level=6)
                break
            # Sleep in small increments to allow periodic checking of pause_event
            waiting_time = min(increment_step, end_time - time.time())
            self.logger.log(f'[{self.name} LED] Waiting for another {waiting_time:.2f} seconds',
                            log_level=6)
            time.sleep(waiting_time)

        # If end_time is reached, log a message
        if time.time() >= end_time:
            self.logger.log(f'[{self.name} LED] Resuming after waiting for {remaining_time:.2f} seconds',
                            log_level=6)
            return True

        return False


    def run_led_timer(self, duration, period, timeout, blinking=False, blinking_period=None):
        """
        Run a timer to control the LED.
        Parameters:
        - duration: The duration for which the LED should be on, in seconds.
        - period: The time interval between each activation of the LED.
        - timeout: The total time for which the LED should run, in seconds.
        - blinking: A flag to indicate whether the LED should blink or stay on.
        """
        timeout += period  # Ensure some extra time buffer

        def led_timer_thread():
            end_time = time.time() + timeout

            while time.time() < end_time and self.running.is_set():
                self.pause_event.wait()  # Wait for the pause event to be set
                if blinking:
                    wait_done = self.wait_until_next_activation(period, 0.5)
                    if not self.running.is_set() or not wait_done:
                        break  # Exit early if requested
                    self.blink(duration, 1, blinking_period)
                else:
                    wait_done = self.wait_until_next_activation(period, -0.25)
                    if not self.running.is_set() or not wait_done:
                        break  # Exit early if requested
                    self.turn_on_for_n_sec(duration)

        if self.program and self.program.is_alive():
            self.cleanup()

        try:
            self.running.set()  # Signal to start the timer
            self.program = threading.Thread(target=led_timer_thread)
            self.program.start()
            self.logger.log(f'Started LED timer thread for {self.name}', log_level=5)
        except AttributeError:
            self.logger.log("Illumination PCB not connected", log_level=3)

    def wait_end_of_led_timer(self):
        """Wait for the LED timer to end."""
        if self.program and self.program.is_alive():
            self.program.join(timeout=20)


class LEDLegacy(LED):
    """Class to control a LED using the GPIO pins directly."""
    def __init__(self, _control_gpio_pin, logger=None, name=None, keep_state=False):
        super().__init__(None, None, None, logger, name, keep_state)
        GPIO.setwarnings(False)

        self.gpio_pin = _control_gpio_pin

        GPIO.setmode(GPIO.BCM)
        GPIO.setup(self.gpio_pin, GPIO.OUT)




    def turn_on(self):
        self.logger.log(f'Turning on {self.name} LED (GPIO {self.gpio_pin})', log_level=5)
        GPIO.output(self.gpio_pin, GPIO.HIGH)

    def turn_off(self):
        self.logger.log(f'Turning off {self.name} LED (GPIO {self.gpio_pin})', log_level=5)
        GPIO.output(self.gpio_pin, GPIO.LOW)
