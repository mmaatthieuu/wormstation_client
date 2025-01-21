import time
import threading
from pyftdi.spi import SpiController
from pyftdi.ftdi import FtdiError
from pyftdi.usbtools import UsbToolsError
# from utils import get_most_available_core, set_affinity

import RPi.GPIO as GPIO
import multiprocessing
import atexit
import psutil
from datetime import datetime

from src.usb_handler import USBHandler


class LightController:
    """Class to control the LEDs using the FT232H chip."""


    def __init__(self, logger=None, empty=False, keep_final_state=False, enable_legacy_gpio_mode=False):
        """
        :param logger: The logger instance to use for logging messages.
        :param empty: A flag to initialize the LightController without any LEDs.
        :param keep_final_state: A flag to keep the LEDs in their final state after cleanup.
        :param enable_legacy_gpio_mode: A flag to enable the legacy GPIO mode for controlling the LEDs

        """
        self.logger = logger
        self.device_connected = False
        self.leds = {}
        self.initialized = threading.Event()  # Use an event to signal initialization completion
        self.spi_controller = None
        self.leds_lock = threading.Lock()
        self.legacy_gpio_mode = False

        # Start asynchronous initialization in a separate thread
        init_thread = threading.Thread(target=self.initialize, args=(empty,keep_final_state,enable_legacy_gpio_mode,))
        init_thread.start()

    def initialize(self, empty, keep_final_state=False, enable_legacy_gpio_mode=False):
        try:
            self.spi_controller = FT232H(logger=self.logger)
            self.spi_controller.start_vsync()
            self.device_connected = True

            if not empty:
                # Initialize LEDs
                self.leds = {
                    "IR": LED(usb_handler=self.spi_controller.usb_handler,
                              channel=0,
                              current='100mA',
                              name='IR',
                              logger=self.logger,
                              final_state=keep_final_state),
                    "Orange": LED(usb_handler=self.spi_controller.usb_handler,
                                  channel=1, current='max',
                                  name='Orange',
                                  logger=self.logger,
                                  final_state=keep_final_state),
                    "Blue": LED(usb_handler=self.spi_controller.usb_handler,
                                channel=2,
                                current='max',
                                name='Blue',
                                logger=self.logger,
                                final_state=keep_final_state)
                }
        except (FtdiError, UsbToolsError) as e:
            if self.logger:
                self.logger.log(f"Initialization error: {e}", log_level=3)

            if self.spi_controller:
                self.spi_controller.close()
                self.device_connected = False

            if enable_legacy_gpio_mode:
                """
                Note: This is a fallback mechanism to use the legacy GPIO mode for controlling the LEDs.
                This implementation can be improved as to will be used for the 3 over 4 devices not connected to USB
                  PCB, even if the setup uses USB PCB (with the FT232H chip).
                """
                # Fallback to legacy GPIO mode
                self.logger.log("Falling back to legacy GPIO mode.", log_level=3)
                self.leds = {
                    "IR": LEDLegacy(17, logger=self.logger, name='IR', keep_state=keep_final_state),
                    "Orange": LEDLegacy(18, logger=self.logger, name='Orange', keep_state=keep_final_state),
                }
                self.device_connected = True
                self.legacy_gpio_mode = True

        finally:
            self.initialized.set()  # Signal that initialization is complete

    def wait_until_ready(self):
        """Block until initialization is complete."""
        self.initialized.wait()

    def legacy_mode(self):
        """Check if the LightController is in legacy GPIO mode."""
        return self.legacy_gpio_mode

    def __getitem__(self, name):
        """Allow accessing the LEDs via dictionary-like access."""
        return self.leds.get(name)

    def close_func(self):
        """Explicitly clean up resources."""
        if not self.device_connected:
            self.logger.log("No USB device to clean up.", log_level=3)
            return
        self.logger.log("Starting LightController cleanup.", log_level=5)
        for led in self.leds.values():
            led.cleanup()
        time.sleep(0.1)
        if self.spi_controller:
            self.spi_controller.close()
        self.logger.log("LightController resources cleaned up.", log_level=5)

    def close(self):
        close_thread = threading.Thread(target=self.close_func)
        close_thread.start()
        close_thread.join()

    def add_LED(self, name, channel, current='7.5mA', final_state=False):
        """Add a new LED to the LightController."""
        with self.leds_lock:
            if name in self.leds:
                self.logger.log(f"LED with name '{name}' already exists.", log_level=2)
                return
            if not self.device_connected:
                self.logger.log("No device connected. Cannot add new LED.", log_level=3)
                return

            if self.legacy_gpio_mode:
                # Not very efficient, but this is a fallback mechanism for legacy PCB
                gpio_pin = {"IR": 17, "Orange": 18, "Blue" : 18}.get(name)
                self.leds[name] = LEDLegacy(_control_gpio_pin=gpio_pin, logger=self.logger, name=name, keep_state=final_state)
                self.logger.log(f"Added new legacy LED: {name} on GPIO pin {gpio_pin}.", log_level=5)
            else:
                self.leds[name] = LED(usb_handler=self.spi_controller.usb_handler, channel=channel, current=current, name=name,
                                      logger=self.logger, final_state=final_state)
                self.logger.log(f"Added new LED: {name} on channel {channel} with current {current}.", log_level=5)

    def test(self):
        """Test the LEDs by turning them on for 2 seconds each."""
        if self.device_connected:
            for led in self.leds.values():
                led.turn_on_for_n_sec(2)

    def turn_on_all_leds(self):
        """Turn on all the LEDs."""
        if self.device_connected:
            for led in self.leds.values():
                led.turn_on()

    def turn_off_all_leds(self):
        """Turn off all the LEDs."""
        if self.device_connected:
            for led in self.leds.values():
                led.turn_off()

    def pause_all_leds(self):
        """Pause all the blinking processes."""
        if self.device_connected:
            for led in self.leds.values():
                led.pause_process()

    def resume_all_leds(self):
        """Resume all the blinking processes."""
        if self.device_connected:
            for led in self.leds.values():
                led.resume_process()

    # Terminate all LED programs
    def terminate_leds(self):
        """Terminate all LED programs."""
        if self.device_connected:
            for led in self.leds.values():
                led.cleanup()

    def switch_led(self, name: str, state: bool):
        """Switch an LED on or off based on its name and state."""
        if name in self.leds:
            if not self.device_connected:
                self.logger.log(f"No USB device found. Cannot switch {name} LED.", log_level=2)
                return
            led = self.leds[name]
            if state:
                self.logger.log(f"Switching ON {name} LED", log_level=5)
                led.turn_on()
            else:
                self.logger.log(f"Switching OFF {name} LED", log_level=5)
                led.turn_off()
        else:
            self.logger.log(f"LED '{name}' does not exist.", log_level=2)



class FT232H:
    """Class to control the FT232H chip using the PyFtdi library."""

    # spi_lock = threading.Lock()

    def __init__(self, logger=None):
        self.logger = logger
        self.spi = SpiController()
        self.usb_handler = None

        try:
            # Attempt to configure the SPI controller
            self.spi.configure('ftdi://ftdi:232h/1', cs_count=3, frequency=12E6)
        except FtdiError as e:
            self.logger.log(f"FT232H initialization failed: {e}", log_level=3)
            raise e
        except UsbToolsError as e:
            self.logger.log(f"USB error occurred: {e}", log_level=3)
            raise e

        self.vsync_pin = 1 << 6  # ADBUS6
        self.test_led_pin = 1 << 7   # ADBUS7

        pins = [self.vsync_pin, self.test_led_pin]

        self.gpio = self.spi.get_gpio()
        self.gpio.set_direction(sum(pins), sum(pins))  # Set all pins as output

        # Create a USBHandler thread and start it
        self.usb_handler = USBHandler(self.spi, self.gpio, logger=self.logger)
        self.usb_handler.start()

        # Initialize the Pulser for VSYNC
        self.logger.log("Initializing VSYNC pulser...", log_level=5)
        self.pulser = Pulser(self.usb_handler, self.vsync_pin, frequency=25)
        self.logger.log("VSYNC pulser initialized.", log_level=5)
        time.sleep(0.1) # Short delay for stability [Required otherwise there is a segmentation fault]
        self.logger.log("FT232H initialized.", log_level=5)

    def close(self):
        """Explicitly clean up resources with additional checks."""
        self.logger.log("Starting FT232H cleanup.", log_level=5)

        # Stop VSYNC signal if running
        if hasattr(self, 'pulser') and self.pulser.vsync_running.is_set():
            self.pulser.stop_vsync()

        # Stop the USBHandler thread if it exists
        if hasattr(self, 'usb_handler'):
            self.usb_handler.stop()

        # Close the SPI connection if initialized
        if hasattr(self, 'spi'):
            self.spi.close()

        self.logger.log("FT232H resources cleaned up.", log_level=5)


    def get_port(self, cs, freq=12E6, mode=0):
        return self.spi.get_port(cs=cs, freq=freq, mode=mode)

    def start_vsync(self):
        """Start the VSYNC signal using the pulser."""
        self.pulser.start_vsync()

    def stop_vsync(self):
        """Stop the VSYNC signal."""
        self.pulser.stop_vsync()

    # def access_spi(self, func, *args, **kwargs):
    #     """A helper function to safely access SPI with locking."""
    #     with FT232H.spi_lock:
    #         return func(*args, **kwargs)


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



class LEDDriver:
    """Class to control the LED driver (LP5860T) using SPI communication."""

    def __init__(self, usb_handler, channel, current, logger=None):
        self.logger = logger
        self.usb_handler = usb_handler

        if self.usb_handler is not None:
            self.channel = channel  # SPI channel
            self.current_level = self.read_current_input(current)

            print(f'Input current: {current}')
            print(f"Current level read from input: {self.current_level}")

            num_lines = self.get_max_num_lines()

            self.initialize(num_lines)

    def initialize(self, num_lines):
        # Ensure num_lines is valid (1-16 as LP5860T supports up to 16 scan lines)
        if num_lines < 0 or num_lines > 11:
            raise ValueError("num_lines must be between 0 and 11")

        # Use the new function to write multiple registers
        self.write_multiple_registers({
            0x000: 0x01,  # Chip Enable
            0x0A9: 0x00,  # Reset chip to default state
        })
        time.sleep(0.001)
        self.set_max_current(self.current_level)

        # Set the value for byte_reg1
        max_line_num = num_lines << 3  # Shift num_lines - 1 into bits 6 to 3
        byte_reg1 = 0b00000011 | max_line_num  # Preserve bits 0 and 1, set bits 6-3 for max_line_num

        self.write_register(0x001, byte_reg1)

        # Set the value for byte_reg2 to maximize the light output
        byte_reg2 = 0b00001000
        self.write_register(0x002, byte_reg2)

        time.sleep(0.001)


        self.write_multiple_registers({
            0x009: 0x7F,  # Set Color Current to 100%
            0x00A: 0x7F,
            0x00B: 0x7F
        })

    def get_max_num_lines(self):
        """Get the maximum number of scan lines supported by the LP5860T."""
        """This is specific for the current PCB design."""
        if self.channel == 0:
            return 0 # IR LED are not connected to the switch scan so it does not change anything
        if self.channel == 1:
            return 9 # Orange LED are connected 9 switch scan lines
        if self.channel == 2:
            return 10

    def set_max_current(self, current_level):
        """Set the maximum current in the Dev_config3 register."""
        if self.usb_handler is not None:
            if current_level < 0 or current_level > 7:
                print("Invalid current level. Please provide a value between 0 and 6.")
                return
            default_value = 0x47
            new_value = (default_value & 0b11110001) | ((current_level << 1) & 0b00001110)

            self.write_register(0x004, new_value)
            print(f"Set maximum current to level {current_level}")

    def write_register(self, register, data):
        """Write data to a specific register on the SPI device."""
        if self.usb_handler is not None:
            address_byte1 = (register >> 2) & 0xFF
            address_byte2 = ((register & 0x03) << 6) | 0x20
            self.usb_handler.spi_exchange([address_byte1, address_byte2, data], channel=self.channel)
    def write_multiple_registers(self, registers):
        """
        Write multiple registers in one locked operation using auto-increment
        where possible for consecutive addresses.
        """
        if self.usb_handler is not None:
            sorted_registers = sorted(registers.items())  # Sort by register address
            buffer = []
            start_address = None

            for i, (register, data) in enumerate(sorted_registers):
                if start_address is None:
                    # Set the start address for the first register
                    start_address = register
                    buffer.append((start_address >> 2) & 0xFF)  # Address byte 1
                    buffer.append(
                        ((start_address & 0x03) << 6) | 0x20)  # Address byte 2 (Write, auto-increment enabled)

                # Add the data byte
                buffer.append(data)

                # Check if the next register is consecutive
                if i + 1 < len(sorted_registers):
                    next_register = sorted_registers[i + 1][0]
                    if next_register != register + 1:
                        # If the next register is not consecutive, send the current buffer
                        self.usb_handler.spi_exchange(buffer, channel=self.channel)
                        buffer = []  # Reset buffer for the next transaction
                        start_address = None  # Reset start address
                else:
                    # If it's the last register, send the buffer
                    self.usb_handler.spi_exchange(buffer, channel=self.channel)

    def read_register(self, register, print_result=False):
        """Read data from a specific register on the SPI device."""
        """Does not work as expected"""
        if self.usb_handler is not None:
            address_byte1 = (register >> 2) & 0xFF
            address_byte2 = ((register & 0x03) << 6)

            result = self.usb_handler.spi_exchange([address_byte1, address_byte2, 0x00], channel=self.channel,
                                                   duplex=True)

            if print_result:
                print(f"Read result from register {hex(register)}: {hex(result[2])}")
                return result[2]
            else:
                print(f'Result is {result}')
                return result


    def set_pwm_brightness(self, brightness):
        """Set the PWM brightness for all dots."""
        registers = {reg: brightness for reg in range(0x200, 0x2C5)}
        self.write_multiple_registers(registers)

    def read_current_input(self, current):
        current_levels = {'7.5mA': 0, '12.5mA': 1, '25mA': 2, '37.5mA': 3, '50mA': 4, '75mA': 5, '100mA': 6, 'max': 7}

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
                    self.logger.log(
                        f'Invalid current level. Setting to the closest inferior value: {closest_value} mA',
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
        self.led_driver.set_pwm_brightness(0xFF)
        self.is_on = True

    def turn_off(self):
        self.logger.log(f'Turning off {self.name} LED', log_level=5)
        self.led_driver.set_pwm_brightness(0x00)
        self.is_on = False

    def cleanup(self):
        """Cleanup the LED processes and turn it off."""
        if self.program and self.program.is_alive():
            self.logger.log(f"Terminating LED program for {self.name}", log_level=5)
            self.running.clear()
            self.pause_event.set()  # Ensure it doesn't hang on pause
            self.program.join(timeout=2)  # Ensure the thread has terminated
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
        timeout += period * 2  # Ensure some extra time buffer

        def led_timer_thread():
            end_time = time.time() + timeout

            while time.time() < end_time and self.running.is_set():
                self.pause_event.wait()  # Wait for the pause event to be set
                if blinking:
                    self.wait_until_next_activation(period, 0.5)
                    if not self.running.is_set():
                        break  # Exit early if requested
                    self.blink(duration, 1, blinking_period)
                else:
                    self.wait_until_next_activation(period, -0.25)
                    if not self.running.is_set():
                        break  # Exit early if requested
                    self.turn_on_for_n_sec(duration)

        if self.program and self.program.is_alive():
            self.cleanup()

        self.running.set()  # Signal to start the timer
        self.program = threading.Thread(target=led_timer_thread)
        self.program.start()
        self.logger.log(f'Started LED timer thread for {self.name}', log_level=5)




class LEDLegacy(LED):

    def __init__(self, _control_gpio_pin, logger=None, name=None, keep_state=False):
        super().__init__(None, None, None, logger, name, keep_state)
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
        # atexit.register(self.cleanup)

    # def __del__(self):
    #     self.cleanup()

    def turn_on(self):
        #print(datetime.now(), "LED ON")
        self.logger.log(f'Turning on {self.name} LED (GPIO {self.gpio_pin})', log_level=5)
        GPIO.output(self.gpio_pin, GPIO.HIGH)
        # self.is_on = True

    def turn_off(self):
        #print(datetime.now(), "LED OFF")
        self.logger.log(f'Turning off {self.name} LED (GPIO {self.gpio_pin})', log_level=5)
        GPIO.output(self.gpio_pin, GPIO.LOW)
        # self.is_on = False





class FakeLogger:
    def log(self, message, log_level=1):
        print(f"[LOG - Level {log_level}]: {message}")


if __name__ == "__main__":
    # Initialize the logger (You can create a Logger object or set it to None if you do not want logging)
    logger = FakeLogger()  # Replace with an actual Logger object if needed

    # Create an instance of LightController
    light_controller = LightController(logger=logger)

    light_controller.turn_off_all_leds()

    # Flag to control the Blue LED alternation
    blue_led_running = True

    # Turn on each LED for 2 seconds using the turn_on_for_n_sec method
    try:
        # Turn on the IR LED for 2 seconds
        light_controller["IR"].turn_on_for_n_sec(2)

        # Turn on the Orange LED for 2 seconds
        light_controller["Orange"].turn_on_for_n_sec(2)

        # Alternate the Blue LED current between 37.5mA and 50mA every 0.5 seconds
        def alternate_blue_led():
            while blue_led_running:
                # Set Blue LED to 37.5mA
                light_controller.leds["Orange"].led_driver.set_max_current(3)  # 37.5mA
                light_controller["Orange"].turn_on()
                time.sleep(0.5)

                # Check if thread should stop
                if not blue_led_running:
                    break

                # Set Blue LED to 50mA
                light_controller.leds["Orange"].led_driver.set_max_current(4)  # 50mA
                light_controller["Orange"].turn_on()
                time.sleep(0.5)

                # Check if thread should stop
                if not blue_led_running:
                    break

                # Set Blue LED to 50mA
                light_controller.leds["Orange"].led_driver.set_max_current(5)  # 75mA
                light_controller["Orange"].turn_on()
                time.sleep(0.5)

                # Check if thread should stop
                if not blue_led_running:
                    break

                # Set Blue LED to 50mA
                light_controller.leds["Orange"].led_driver.set_max_current(6)  # 100mA
                light_controller["Orange"].turn_on()
                time.sleep(0.5)

        # Start alternating the Blue LED in a separate thread to allow the main program to run
        blue_led_thread = threading.Thread(target=alternate_blue_led)
        blue_led_thread.daemon = True
        blue_led_thread.start()

        # Let it run for a while to observe
        time.sleep(10)  # Run for 10 seconds before stopping the test

        # Stop the Blue LED alternation
        blue_led_running = False
        blue_led_thread.join()  # Wait for the thread to finish

        print("Done.")

    except KeyboardInterrupt:
        print("Process interrupted by user.")

    finally:
        light_controller.close()

