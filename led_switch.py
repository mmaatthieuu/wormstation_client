import argparse
import time
from src.led_controller import LightController  # Adjust the path based on your actual file structure
from src.log import FakeLogger  # Assuming you have the FakeLogger or another logger implementation


def parse_args():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Control LEDs using FT232H. Available colors: IR, Orange, Blue."
    )
    parser.add_argument(
        '--color', '-c', type=str, required=True,
        help='LED color to control. Available options: IR, Orange, Blue'
    )
    parser.add_argument(
        '--state', '-s', type=int, choices=[0, 1], required=True,
        help='State of the LED: 0 for OFF, 1 for ON'
    )
    parser.add_argument(
        '--current', '-a', type=str, default='37.5mA',
        help='Current for the LED. Available values: 7.5mA, 12.5mA, 25mA, 37.5mA, 50mA, 75mA, 100mA (default: 37.5mA)'
    )
    return parser.parse_args()


def switch_led(color, state, current):
    """Switch the specified LED on or off with the specified current."""
    logger = FakeLogger()  # Replace with your actual logger if needed
    light_controller = LightController(logger=logger)  # Replace with your actual LightController

    # Add the LED with the specified current if not already added
    if color not in light_controller.leds:
        light_controller.add_LED(name=color, channel=light_controller.leds[color].channel, current=current)
    else:
        light_controller[color].set_current(current)

    # Turn LED on or off based on user input
    try:
        if state:
            light_controller[color].turn_on()
            # Do not close light_controller if the LED is turned on, to keep it on
            print(f"{color} LED is turned on with {current}.")
        else:
            light_controller[color].turn_off()
            print(f"{color} LED is turned off.")
            # Close the light controller to clean up if the LED is turned off
            light_controller.close()

    except KeyError:
        print(f"Error: '{color}' is not a valid LED color. Available options: IR, Orange, Blue.")
    except Exception as e:
        print(f"An error occurred: {e}")
        # Always close the light_controller in case of error
        light_controller.close()



def main():
    """Main function to handle the command-line interface."""
    args = parse_args()

    # Validate the color argument
    valid_colors = ['IR', 'Orange', 'Blue']
    color = args.color.capitalize()  # Capitalize to match dictionary keys

    if color not in valid_colors:
        print(f"Error: Invalid color '{args.color}'. Available colors are: {', '.join(valid_colors)}")
        return

    # Validate the current argument
    valid_currents = ['7.5mA', '12.5mA', '25mA', '37.5mA', '50mA', '75mA', '100mA']
    if args.current not in valid_currents:
        print(f"Error: Invalid current '{args.current}'. Available values are: {', '.join(valid_currents)}")
        return

    # Switch the LED based on the state (0 = off, 1 = on)
    switch_led(color, args.state, args.current)


if __name__ == "__main__":
    main()
