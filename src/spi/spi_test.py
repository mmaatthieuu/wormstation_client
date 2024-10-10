import spidev
import time


class LP5860T:
    def __init__(self, bus=0, device=0, max_speed_hz=1000, current_level=2):
        self.spi = spidev.SpiDev()
        self.bus = bus
        self.device = device
        self.spi.open(self.bus, self.device)
        self.spi.max_speed_hz = max_speed_hz  # Set SPI speed to 1 MHz for initial testing
        time.sleep(0.001)  # Short delay for stability

        # Enable deghosting if needed
        #self.write_register(0x004, 0x45)  # Set max current to 25mA (0x49 for 50mA)

        # Set Chip_EN to 1 (activate chip)
        self.write_register(0x000, 0x01)

        self.write_register(0x0A9, 0x00) # Reset chip to default state

        time.sleep(0.001)  # Short delay for stability

        self.set_max_current(current_level)

        #self.read_register(0x001)

        self.write_register(0x001, 0x58)  # Set data mode 1
        time.sleep(0.001)  # Short delay for stability

        self.read_register(0x001)

        self.write_register(0x001, 0x58)  # Set data mode 1
        self.read_register(0x001)

        # Set Color Current to 100%
        self.write_register(0x009, 0x7f)

        # Enable deghosting if neededcd pi
        #write_register(0x004, 0x45)  # Set max current to 25mA (0x49 for 50mA)
        #write_register(0x001, 0x58)  # Set data mode 1

        # Set Color Current to 100%
        self.write_register(0x009, 0x7f)
        self.write_register(0x00A, 0x7f)
        self.write_register(0x00B, 0x7f)

        self.read_register(0x009)
        self.read_register(0x004)




        # Set Chip_EN to 1 (activate chip)
        #write_register(0x000, 0x01)

        # Set current for Dot L0-CS0
        #write_register(0x100, 0xFF)  # Set maximum current for LED Dot L0-CS0

        # Set current for Dot L0-CS0
        #self.write_register(0x100, 0xFF)  # Set maximum current for LED Dot L0-CS0

    def __del__(self):
        self.write_register(0x000, 0x00)  # Set Chip_EN to 0 (deactivate chip)
        self.spi.close()
        print(f"SPI device {self.device} on bus {self.bus} closed")

    def set_max_current(self, current_level):
        """Set the maximum current in the Dev_config3 register."""
        if current_level < 0 or current_level > 6:
            print("Invalid current level. Please provide a value between 0 and 6.")
            return

        # Read the current value of the Dev_config3 register
        default_value = 0x47

        # Mask out the bits corresponding to Maximum_Current (D3, D2, D1)
        new_value = (default_value & 0b11110001) | ((current_level << 1) & 0b00001110)

        # Write the new value back to the Dev_config3 register
        self.write_register(0x004, new_value)
        print(f"Set maximum current to level {current_level}")

    def write_register(self, register, data):
        """Write data to a specific register on the SPI device."""
        # Prepare the address bytes for the write operation
        address_byte1 = (register >> 2) & 0xFF  # Extract bits 9-2 for Address Byte 1
        address_byte2 = ((register & 0x03) << 6) | 0x20  # Extract bits 1-0, set bit 5 to 1 for write

        # Send the two address bytes followed by the data byte
        #print(f"Writing to register {hex(register)}: {hex(data)}")
        #for i in range(10):
        self.spi.xfer2([address_byte1, address_byte2, data])  # Correct address bytes and data
            # time.sleep(0.00001)  # Short delay for stability
        #time.sleep(1/self.spi.max_speed_hz)  # Short delay for stability

    def read_register(self, register):
        """Read data from a specific register on the SPI device."""
        # print(f"Reading from register {hex(register)}...")

        # Prepare the address bytes for the read operation
        address_byte1 = (register >> 2) & 0xFF  # Extract bits 9-2 for Address Byte 1
        address_byte2 = ((register & 0x03) << 6)  # Extract bits 1-0, set bit 5 to 0 for read

        # Send the register address and a dummy byte in one SPI transaction
        result = self.spi.xfer2([address_byte1, address_byte2, 0x00])  # Combined transaction for address and dummy read

        print(f"Read result from register {hex(register)} on device {self.device}: {hex(result[0])} {hex(result[1])} {hex(result[2])}")

        #print(f"Read result from register {hex(register)}: {hex(result[2])}")
        time.sleep(0.001)  # Short delay for stability
        return result[2]

    def set_DC_current_percentage(self, percentage):
        """Set the Dot Correction current percentage for all dots."""
        # Set the Dot Correction current percentage for all dots
        # 0x00 is 0%, 0xFF is 100%

        for register in range(0x100, 0x1C5):
            self.write_register(register, percentage)

    def set_pwm_brightness(self, brightness):
        """Set the PWM brightness for all dots."""
        # Set the PWM brightness for all dots
        # 0x00 is 0%, 0xFF is 100%

        for register in range(0x200, 0x2C5):
            self.write_register(register, brightness)

    def set_dot_grp_sel(self, value):

        for register in range(0x00C, 0x042):
            self.write_register(register, value)

    def turn_on(self):
        self.set_pwm_brightness(0xFF)

    def turn_off(self):
        self.set_pwm_brightness(0x00)




def main():
    """Main function to perform continuous SPI read/write operations."""

    device0 = LP5860T(current_level=2, device=0, bus=1)  # white
    device1 = LP5860T(current_level=2, device=1, bus=1)  # orange
    device2 = LP5860T(current_level=2, device=2, bus=1)  # orange

    devices = [device1, device0, device2]
    try:


        while True:  # Continuous loop to keep the SPI activity ongoing
            #device0.turn_on()
            #device1.turn_on()
            #device2.turn_on()

            for device in devices:
                # device.turn_on()
                device.write_register(0x200, 0xFF)


                #val1 = device.read_register(0x001)
                #val2 = device1.read_register(0x004)


                # print(f'device: {device.device} val1: {hex(val1)}')

            time.sleep(0.2)

            #device0.turn_off()
            #device1.turn_off()
            #device2.turn_off()

            for device in devices:
                # device.turn_off()
                device.write_register(0x200, 0x00)


            time.sleep(0.2)


            # device0.write_register(0x200, 0xFF)
            # device0.read_register(0x200)
            # time.sleep(0.1)
            # device0.write_register(0x200, 0x00)
            # device0.read_register(0x200)
            # time.sleep(0.1)



    except KeyboardInterrupt:
        print("Process interrupted by user.")
    finally:
        #del device0
        #del device1
        #del device2
        for device in devices:
            del device

if __name__ == "__main__":
    main()