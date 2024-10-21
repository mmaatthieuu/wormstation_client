import time
from pyftdi.spi import SpiController
import threading

class LP5860T:
    def __init__(self, spi_port, max_speed_hz=12000000, current_level=2):
        self.spi = spi_port  # The SPI port passed directly
        self.spi.set_frequency(max_speed_hz)  # Set SPI speed
        time.sleep(0.001)  # Short delay for stability

        self.write_register(0x000, 0x00)

        time.sleep(0.001)  # Short delay for stability

        # Set Chip_EN to 1 (activate chip)
        self.write_register(0x000, 0x01)
        self.write_register(0x0A9, 0x00)  # Reset chip to default state
        time.sleep(0.001)  # Short delay for stability
        self.set_max_current(current_level)
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

    def read_register(self, register):
        """Read data from a specific register on the SPI device."""
        address_byte1 = (register >> 2) & 0xFF
        address_byte2 = ((register & 0x03) << 6)
        result = self.spi.exchange([address_byte1, address_byte2, 0x00], duplex=True)
        print(f"Read result from register {hex(register)}: {hex(result[2])}")
        return result[2]

    def set_pwm_brightness(self, brightness):
        """Set the PWM brightness for all dots."""
        for register in range(0x200, 0x2C5):
            self.write_register(register, brightness)

    def turn_on(self):
        self.set_pwm_brightness(0xFF)

    def turn_off(self):
        self.set_pwm_brightness(0x00)


class Pulser:
    def __init__(self, gpio):
        self.vsync_running = False
        self.vsync_pin = 0x40  # ADBUS4, first available GPIO pin (according to the documentation)
        self.gpio = gpio

        # Set ADBUS4 as an output pin (using bitmask)
        self.gpio.set_direction(self.vsync_pin, self.vsync_pin)

    def set_gpio_high(self):
        """Set ADBUS4 high."""
        current_value = self.gpio.read()  # Read current state of GPIO pins
        new_value = current_value | self.vsync_pin  # Set the ADBUS4 bit high
        self.gpio.write(new_value)  # Write back to GPIO

    def set_gpio_low(self):
        """Set ADBUS4 low."""
        current_value = self.gpio.read()  # Read current state of GPIO pins
        new_value = current_value & ~self.vsync_pin  # Set the ADBUS4 bit low
        self.gpio.write(new_value)  # Write back to GPIO

    def start_vsync(self):
        """Start a thread to generate a 1 ms pulse every 20 ms for VSYNC."""
        self.vsync_running = True
        vsync_thread = threading.Thread(target=self._vsync_pulse)
        vsync_thread.start()

    def stop_vsync(self):
        """Stop the VSYNC pulse thread."""
        self.vsync_running = False

    def _vsync_pulse(self):
        """Generate a 1 ms pulse on the VSYNC pin every 20 ms."""
        pulse_duration = 0.01  # 10 ms pulse
        frequency = 10  # 50 Hz
        while self.vsync_running:

            # Set VSYNC high for 1 ms
            self.set_gpio_high()
            time.sleep(pulse_duration)

            # Set VSYNC low for the remaining time
            self.set_gpio_low()
            time.sleep(1 / frequency - pulse_duration)


def main():
    """Main function to perform continuous SPI read/write operations."""

    # Instantiate the SPI controller
    spi_controller = SpiController()

    # Configure the FT232H interface for SPI and GPIO control
    spi_controller.configure('ftdi://ftdi:232h/1', cs_count=3)  # Reserve chip selects and GPIO

    # Get SPI port and GPIO controller
    spi_port = spi_controller.get_port(cs=0, freq=12E6, mode=0)  # SPI with /CS on ADBUS3
    gpio = spi_controller.get_gpio()
    gpio.set_direction(0xc0, 0xc0)  # Set ADBUS4 as an output pin

    # Create an LP5860T instance
    device2 = LP5860T(spi_port=spi_port)  # Device on CS0

    # Create a Pulser instance to generate VSYNC pulses using GPIO
    # pulser = Pulser(gpio)
    # pulser.start_vsync()

    try:
        while True:
            print("Turning on device 2 (CS0)")
            device2.turn_on()
            gpio.write(0x80)
            time.sleep(0.5)
            print("Turning off device 2 (CS0)")
            device2.turn_off()
            gpio.write(0x00)
            time.sleep(0.5)

    except KeyboardInterrupt:
        print("Process interrupted by user.")

    finally:
        # pulser.stop_vsync()
        spi_controller.close()


if __name__ == "__main__":
    main()
