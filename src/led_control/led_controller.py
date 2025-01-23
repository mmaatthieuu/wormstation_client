import time
import threading
from pyftdi.spi import SpiController
from pyftdi.ftdi import FtdiError
from pyftdi.usbtools import UsbToolsError
# from utils import get_most_available_core, set_affinity

import multiprocessing

from src.led_control.ft232h import FT232H
from src.led_control.led import LED, LEDLegacy
from src.led_control.led_driver import LEDDriver
from src.led_control.pulser import Pulser
from src.led_control.usb_handler import USBHandler


class LightController:
    """Class to control the LEDs using the FT232H chip."""


    def __init__(self, parameters, logger=None, empty=False, keep_final_state=False, enable_legacy_gpio_mode=False):
        """
        :param logger: The logger instance to use for logging messages.
        :param empty: A flag to initialize the LightController without any LEDs.
        :param keep_final_state: A flag to keep the LEDs in their final state after cleanup.
        :param enable_legacy_gpio_mode: A flag to enable the legacy GPIO mode for controlling the LEDs

        """
        self.parameters = parameters
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

    def start(self):

        self["IR"].run_led_timer(duration=self.parameters["illumination_pulse"] / 1000,
                                        period=self.parameters["time_interval"],
                                        timeout=self.parameters["timeout"])


        if self.parameters["optogenetic"]:
            try:
                color = self.parameters["optogenetic_color"]

                self[color].run_led_timer(duration=self.parameters["pulse_duration"],
                                             period=self.parameters["pulse_interval"],
                                             timeout=self.parameters["timeout"],
                                             blinking=True,
                                             blinking_period=self.parameters["time_interval"])

            except KeyError:
                self.logger.log("Optogenetic parameters not correctly set", log_level=2)
                self.logger.log("Using Orange LEDs", log_level=2)
                self["Orange"].run_led_timer(duration=self.parameters["pulse_duration"],
                                                 period=self.parameters["pulse_interval"],
                                                 timeout=self.parameters["timeout"],
                                                 blinking=True,
                                                 blinking_period=self.parameters["time_interval"])



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

