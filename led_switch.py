import argparse
import time
import threading
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
        help='Current for the LED. Available values: 7.5mA, 12.5mA, 25mA, 37.5mA, 50mA, 75mA, 100mA, max (default: 37.5mA)'
    )
    return parser.parse_args()


def monitor_led(light_controller, color):
    """Monitor the LED and shut it down after 3 seconds if current > 37.5mA."""
    time.sleep(5)  # Wait for 3 seconds
    if light_controller[color].is_on:  # Check if the LED is still on
        light_controller[color].turn_off()
        print(f"Warning: {color} LED automatically turned off after 5 seconds due to high current.")


def switch_led(color, state, current):
    """Switch the specified LED on or off with the specified current."""
    logger = FakeLogger()  # Replace with your actual logger if needed
    light_controller = LightController(logger=logger, empty=True, keep_final_state=True)

    # Wait until the controller is fully initialized
    light_controller.wait_until_ready()

    # Add the LED with the specified current if not already added
    if color not in light_controller.leds:
        # Since `channel` is unknown without the LED, use a default (adjust if needed)
        channel = {"IR": 0, "Orange": 1, "Blue": 2}.get(color, None)
        if channel is not None:
            light_controller.add_LED(name=color, channel=channel, current=current, final_state=True)
        else:
            print(f"Error: '{color}' is not a valid LED color. Available options: IR, Orange, Blue.")
            return

    # Turn LED on or off based on user input
    try:
        if state:
            light_controller[color].turn_on()
            print(f"{color} LED is turned on with {current}.")

            # Start the timer if the LED is Orange or Blue with current > 37.5mA
            try:
                if color in ["Orange", "Blue"] and float(current.replace('mA', '')) > 37.5:
                    timer_thread = threading.Thread(target=monitor_led, args=(light_controller, color), daemon=True)
                    timer_thread.start()
            except ValueError:
                timer_thread = threading.Thread(target=monitor_led, args=(light_controller, color), daemon=True)
                timer_thread.start()
        else:
            light_controller[color].turn_off()
            print(f"{color} LED is turned off.")

    except Exception as e:
        print(f"An error occurred: {e}")

    finally:
        # Wait for timer thread to complete if it was created
        if 'timer_thread' in locals():
            timer_thread.join()

        light_controller.close()


def main():
    """Main function to handle the command-line interface."""
    args = parse_args()

    # Validate the color argument
    valid_colors = ['IR', 'Orange', 'Blue']
    color = args.color.strip()  # Remove extra spaces

    # Match the input with the valid colors
    if color.upper() == "IR":
        color = "IR"
    elif color.lower() == "orange":
        color = "Orange"
    elif color.lower() == "blue":
        color = "Blue"
    else:
        print(f"Error: Invalid color '{args.color}'. Available colors are: {', '.join(valid_colors)}")
        return

    # Validate the current argument
    valid_currents = ['7.5mA', '12.5mA', '25mA', '37.5mA', '50mA', '75mA', '100mA', 'max']
    if args.current not in valid_currents:
        print(f"Error: Invalid current '{args.current}'. Available values are: {', '.join(valid_currents)}")
        return

    # Switch the LED based on the state (0 = off, 1 = on)
    switch_led(color, args.state, args.current)



if __name__ == "__main__":
    main()
