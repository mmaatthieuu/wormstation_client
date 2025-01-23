import time

from pyftdi.spi import SpiController
from pyftdi.ftdi import FtdiError
from pyftdi.usbtools import UsbToolsError

from src.led_control.pulser import Pulser
from src.led_control.usb_handler import USBHandler


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
