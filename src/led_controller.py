import RPi.GPIO as GPIO
import time
from datetime import datetime
import multiprocessing



class LED():

    def __init__(self, _control_gpio_pin):

        GPIO.cleanup()
        self.gpio_pin = _control_gpio_pin

        GPIO.setmode(GPIO.BCM)  # set pin numbering mode to BCM
        GPIO.setup(self.gpio_pin, GPIO.OUT)  # set GPIO pin control_gpio_pin as an output

        self.turn_off()

    def turn_on(self):
        GPIO.output(self.gpio_pin, GPIO.HIGH)

    def turn_off(self):
        GPIO.output(self.gpio_pin, GPIO.LOW)


    def __del__(self):
        GPIO.cleanup()
