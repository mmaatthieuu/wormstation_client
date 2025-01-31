import time

class LEDDriver:
    """Class to control the LED driver (LP5860T) using SPI communication. Low-level control of the LP5860T driver."""

    def __init__(self, usb_handler, channel, current, logger=None):
        self.logger = logger
        self.usb_handler = usb_handler

        if self.usb_handler is not None:
            self.channel = channel  # SPI channel
            self.current_level = self.read_current_input(current)

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
            #print(f"Set maximum current to level {current_level}")

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

    def turn_on_leds(self):
        """Turn on all LEDs."""
        self.set_pwm_brightness(0xFF)
        return True

    def turn_off_leds(self):
        """Turn off all LEDs."""
        self.set_pwm_brightness(0x00)
        return False

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
