import threading
import time

class Pulser:
    """Class to handle VSYNC signal using threading instead of multiprocessing."""

    def __init__(self, usb_handler, vsync_pin, frequency=25):
        """
        Initialize the Pulser for VSYNC signal.
        :param usb_handler: The USBHandler instance for managing GPIO operations.
        :param vsync_pin: The GPIO pin for VSYNC.
        :param frequency: The PWM frequency for the VSYNC signal.
        """
        self.usb_handler = usb_handler
        self.vsync_pin = vsync_pin
        self.pwm_frequency = frequency  # PWM frequency (in Hz)
        self.pwm_period = 1.0 / self.pwm_frequency
        self.pwm_duty_cycle = 0.05  # 5% duty cycle
        self.vsync_running = threading.Event()

        # Configure the direction only for the vsync_pin
        self.usb_handler.gpio_set_direction(self.vsync_pin, self.vsync_pin)

    def set_gpio_high(self):
        """Set the VSYNC pin high."""
        current_value = self.usb_handler.gpio_read()
        new_value = current_value | self.vsync_pin
        self.usb_handler.gpio_write(new_value)

    def set_gpio_low(self):
        """Set the VSYNC pin low."""
        current_value = self.usb_handler.gpio_read()
        new_value = current_value & ~self.vsync_pin
        self.usb_handler.gpio_write(new_value)

    def start_vsync(self):
        """Start a thread to generate a 1 ms pulse every 20 ms for VSYNC."""
        self.vsync_running.set()
        self.vsync_thread = threading.Thread(target=self._vsync_pulse)
        self.vsync_thread.start()

    def stop_vsync(self):
        """Stop the VSYNC pulse thread."""
        # Wait for the LED to finish the current cycle
        time.sleep(0.1)

        self.vsync_running.clear()
        self.vsync_thread.join()

    def _vsync_pulse(self):
        """Generate a 1 ms pulse on the VSYNC pin every 20 ms."""
        while self.vsync_running.is_set():
            start_time = time.time()

            # Set VSYNC high for the duty cycle duration
            self.set_gpio_high()
            time.sleep(self.pwm_period * self.pwm_duty_cycle)

            # Set VSYNC low for the remaining period
            self.set_gpio_low()
            elapsed_time = time.time() - start_time
            time.sleep(max(self.pwm_period - elapsed_time, 0))
