import time
from pyftdi.spi import SpiController

class LP5860T:
    def __init__(self, spi_port, max_speed_hz=1000000, current_level=2):
        self.spi = spi_port.get_port(cs=0)  # Select the chip select pin (CS=0)
        self.spi.set_frequency(max_speed_hz)  # Set SPI speed
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


def main():
    """Main function to perform continuous SPI read/write operations."""

    # Create an SPI controller and configure the FT232H
    spi_controller = SpiController()
    spi_controller.configure('ftdi://ftdi:232h/1')

    # Create an LP5860T instance using the pyftdi SPI interface
    device = LP5860T(spi_port=spi_controller)

    try:
        while True:
            device.turn_on()
            time.sleep(0.2)
            device.turn_off()
            time.sleep(0.2)

    except KeyboardInterrupt:
        print("Process interrupted by user.")

    finally:
        spi_controller.terminate()

if __name__ == "__main__":
    main()