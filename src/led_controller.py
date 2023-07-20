import RPi.GPIO as GPIO
import time
from datetime import datetime
import multiprocessing



class LED():

    def __init__(self, _control_gpio_pin):

        #GPIO.cleanup()
        GPIO.setwarnings(False)
        self.gpio_pin = _control_gpio_pin
        self.is_on = None

        GPIO.setmode(GPIO.BCM)  # set pin numbering mode to BCM
        GPIO.setup(self.gpio_pin, GPIO.OUT)  # set GPIO pin control_gpio_pin as an output

        self.turn_off()

    def __del__(self):
        GPIO.cleanup()

    def turn_on(self):
        GPIO.output(self.gpio_pin, GPIO.HIGH)
        self.is_on = True

    def turn_off(self):
        GPIO.output(self.gpio_pin, GPIO.LOW)
        self.is_on = False

    def turn_on_with_timer_in_ms(self,duration):
        p = multiprocessing.Process(target=self._turn_on_with_timer, args=(duration,))
        p.start()

    def _turn_on_with_timer(self, duration):
        print("ON led")
        self.turn_on()
        time.sleep(duration/1000)
        print("OFF led")
        self.turn_off()

    def get_is_ON(self):
        return self.is_on

    def start_program(self, time_on, period, time_out, offset=0, initial_time=None):
        p = multiprocessing.Process(target=self._program, args=(time_on, period, time_out, offset, initial_time,))
        p.start()

    def _program(self, time_on, period, time_out, offset, initial_time):
        if initial_time is None:
            initial_time = time.time()
        print("initial wait")
        time.sleep(offset)
        while (time.time()-initial_time) <= time_out:
            print(f'turn on for {time_on} s')
            self.turn_on()
            time.sleep(time_on)
            print(f'turn off for {period-time_on} s')
            self.turn_off()
            time.sleep(period-time_on)
        print("exit program")

"""
    def should_be_on(self):
        if self.get_is_ON():
            pass
        else:
            self.turn_on()

    def should_be_off(self):
        if self.get_is_ON():
            self.turn_off()
        else:
            pass

    def get_is_ON(self):
        if GPIO.input(self.gpio_pin) == GPIO.HIGH:
            return True
        else:
            return False

    def get_is_OFF(self):
        return not self.get_is_ON()
"""


