
import RPi.GPIO as GPIO
import sys

def setup_and_output_high(pin=17):
    GPIO.setwarnings(False)
    GPIO.setmode(GPIO.BCM)  # set pin numbering mode to BCM
    GPIO.setup(int(pin), GPIO.OUT)  # set GPIO pin 17 as an output
    GPIO.output(int(pin), GPIO.HIGH)

    return 0


def main():

    pin_number = sys.argv[1] if len(sys.argv) > 1 else 17

    setup_and_output_high(pin_number)
    return 0


if __name__ == "__main__":
    main()




#GPIO.cleanup()
