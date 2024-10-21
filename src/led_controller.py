import time
import multiprocessing
import atexit
from pyftdi.spi import SpiController


class LightController:
    """Class to control the LEDs using the FT232H chip."""

    def __init__(self, logger=None, empty=False):
        """Constructor for the LightController class."""
        """
        Possible channels: 0, 1, 2, 3
        Channel 0: IR LED
        Channel 1: Orange LED
        Channel 2: Blue LED

        Possible current values [mA]: 7.5, 12.5, 25, 37.5, 50, 75, 100
        """

        self.logger = logger
        self.spi_controller = FT232H(logger=self.logger)

        # Initialize an empty dictionary if 'empty' is True
        if empty:
            self.leds = {}
        else:
            # Default LEDs
            self.leds = {
                "IR": LED(spi_controller=self.spi_controller, channel=0, current='37.5mA', name='IR', logger=self.logger),
                "Orange": LED(spi_controller=self.spi_controller, channel=1, current='50mA', name='Orange', logger=self.logger),
                "Blue": LED(spi_controller=self.spi_controller, channel=2, current='37.5mA', name='Blue', logger=self.logger)
            }

    def __getitem__(self, name):
        """Allow accessing the LEDs via dictionary-like access."""
        return self.leds.get(name)

    def add_LED(self, name, channel, current='7.5mA'):
        """Add a new LED to the LightController."""
        if name in self.leds:
            self.logger.log(f"LED with name '{name}' already exists.", log_level=2)
            return

        self.leds[name] = LED(spi_controller=self.spi_controller, channel=channel, current=current, name=name, logger=self.logger)
        self.logger.log(f"Added new LED: {name} on channel {channel} with current {current}.", log_level=5)

    def turn_on_all_leds(self):
        """Turn on all the LEDs."""
        for led in self.leds.values():
            led.turn_on()

    def turn_off_all_leds(self):
        """Turn off all the LEDs."""
        for led in self.leds.values():
            led.turn_off()

    def pause_all_leds(self):
        """Pause all the blinking processes."""
        for led in self.leds.values():
            led.pause_process()

    def resume_all_leds(self):
        """Resume all the blinking processes."""
        for led in self.leds.values():
            led.resume_process()


class FT232H:
    """Class to control the FT232H chip using the PyFtdi library."""

    def __init__(self, logger=None):
        self.logger = logger
        self.spi = SpiController()
        self.spi.configure('ftdi://ftdi:232h/1', cs_count=3, frequency=12E6)  # Reserve chip selects

        self.vsync_pin = 0x40  # ADBUS6
        self.test_led_pin = 0x80  # ADBUS7

        pins = [self.vsync_pin, self.test_led_pin]

        self.vsync_gpio_port = self.spi.get_gpio()
        self.vsync_gpio_port.set_direction(sum(pins), sum(pins))  # Set all pins as output

    def __del__(self):
        self.spi.close()

    def get_port(self, cs, freq=12E6, mode=0):
        return self.spi.get_port(cs=cs, freq=freq, mode=mode)


class LEDDriver:
    """Class to control the LED driver (LP5860T) using SPI communication."""

    def __init__(self, spi_port, current, logger=None):
        self.logger = logger
        self.spi = spi_port

        self.current_level = self.read_current_input(current)
        self.initialize()

    def initialize(self):
        self.write_register(0x000, 0x01)
        self.write_register(0x0A9, 0x00)  # Reset chip to default state

        time.sleep(0.001)

        self.set_max_current(self.current_level)

        self.write_register(0x001, 0x58)  # Set data mode 1
        time.sleep(0.001)
        self.write_register(0x009, 0x7f)  # Set Color Current to 100%
        self.write_register(0x00A, 0x7f)
        self.write_register(0x00B, 0x7f)

    def set_max_current(self, current_level):
        """Set the maximum current in the Dev_config3 register."""
        if current_level < 0 or current_level > 6:
            print("Invalid current level. Please provide a value between 0 and 6.")
            return
        default_value = 0x47
        new_value = (default_value & 0b11110001) | ((current_level << 1) & 0b00001110)
        self.write_register(0x004, new_value)
        print(f"Set maximum current to level {current_level}")

    def write_register(self, register, data):
        """Write data to a specific register on the SPI device."""
        address_byte1 = (register >> 2) & 0xFF
        address_byte2 = ((register & 0x03) << 6) | 0x20
        self.spi.exchange([address_byte1, address_byte2, data])

    def read_register(self, register, print_result=False):
        """Read data from a specific register on the SPI device."""
        address_byte1 = (register >> 2) & 0xFF
        address_byte2 = ((register & 0x03) << 6)
        result = self.spi.exchange([address_byte1, address_byte2, 0x00], duplex=True)
        if print_result:
            print(f"Read result from register {hex(register)}: {hex(result[2])}")
        return result[2]

    def set_pwm_brightness(self, brightness):
        """Set the PWM brightness for all dots."""
        for register in range(0x200, 0x2C5):
            self.write_register(register, brightness)

    def read_current_input(self, current):
        current_levels = {'7.5mA': 0, '12.5mA': 1, '25mA': 2, '37.5mA': 3, '50mA': 4, '75mA': 5, '100mA': 6}

        # Ensure current is a string if it's not already
        current = str(current)

        # Check if the input current is valid (including the 'mA' suffix)
        if current not in current_levels:
            # Try again with a list without the 'mA' suffix
            current_levels_no_suffix = {'7.5': 0, '12.5': 1, '25': 2, '37.5': 3, '50': 4, '75': 5, '100': 6}

            # Check again without the 'mA' suffix
            if current not in current_levels_no_suffix:
                try:
                    # Convert the input current to a float
                    current_value = float(current)
                    # Convert the current levels to a list of floats
                    current_levels_float = {float(k): v for k, v in current_levels_no_suffix.items()}

                    # Get the closest inferior value or the smallest if it's too small
                    closest_value = max([k for k in current_levels_float.keys() if k <= current_value],
                                        default=min(current_levels_float.keys()))

                    # Log the warning
                    self.logger.log(f'Invalid current level. Setting to the closest inferior value: {closest_value} mA',
                                    log_level=3)
                    # Return the corresponding level
                    return current_levels_float[closest_value]

                except ValueError:
                    # Handle invalid input that cannot be converted to float
                    self.logger.log(f"Invalid input '{current}' for current level. Unable to parse.", log_level=1)
                    return None  # Or handle the error as per your needs

            # If a valid string without the 'mA' suffix, return the corresponding level
            return current_levels_no_suffix[current]

        # If valid input with 'mA' suffix, return the corresponding level
        return current_levels[current]


class LED:
    """Class to control an LED using the FT232H chip."""

    def __init__(self, spi_controller, channel, current='7.5mA', logger=None, name=None):
        self.spi_port = spi_controller.get_port(cs=channel)
        self.led_driver = LEDDriver(self.spi_port, current=current, logger=logger)

        self.logger = logger
        self.name = name

        self.is_on = None
        self.program = None
        self.running = multiprocessing.Event()

        atexit.register(self.cleanup)

    def turn_on(self):
        self.logger.log(f'Turning on {self.name} LED', log_level=5)
        self.led_driver.set_pwm_brightness(0xFF)
        self.is_on = True

    def turn_off(self):
        self.logger.log(f'Turning off {self.name} LED', log_level=5)
        self.led_driver.set_pwm_brightness(0x00)
        self.is_on = False

    def cleanup(self):
        self.turn_off()
        if self.program and self.program.is_alive():
            self.program.terminate()
            self.program.join()

    def pause_process(self):
        """Pause the blinking process."""
        if self.program and self.program.is_alive():
            self.logger.log(f'Pausing blinking of {self.name} LED', log_level=5)
            self.running.clear()

    def resume_process(self):
        """Resume the blinking process."""
        if self.program and self.program.is_alive():
            self.logger.log(f'Resuming blinking of {self.name} LED', log_level=5)
            self.running.set()

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
        """Wait until the next activation of the LED based on the period and offset."""
        current_time = time.time()
        time_until_next_activation = (current_time - offset) % period
        remaining_time = period - time_until_next_activation
        time.sleep(remaining_time)

    def run_led_timer(self, duration, period, timeout, blinking=False, blinking_period=None):
        """
        Run a timer to control the LED.

        Parameters:
        - duration: The duration for which the LED should be on, in seconds.
        - period: The time interval between each activation of the LED.
        - timeout: The total time for which the LED should run, in seconds.
        - blinking: A flag to indicate whether the LED should blink or stay on.
        """

        timeout += period * 2

        def led_timer_process():
            end_time = time.time() + timeout

            while time.time() < end_time:
                self.running.wait()

                if blinking:
                    self.wait_until_next_activation(period, 0.5)
                    self.blink(duration, 1, blinking_period)
                else:
                    self.wait_until_next_activation(period, -0.25)
                    self.turn_on_for_n_sec(duration)

        if self.program and self.program.is_alive():
            self.cleanup()

        self.running.set()
        self.program = multiprocessing.Process(target=led_timer_process)
        self.program.start()
        self.logger.log(f'Started LED timer process for {self.name}', log_level=5)
