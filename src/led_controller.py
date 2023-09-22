import RPi.GPIO as GPIO
import time
import multiprocessing
import atexit
import psutil

class LED():
    def __init__(self, _control_gpio_pin):
        GPIO.setwarnings(False)
        self.gpio_pin = _control_gpio_pin
        self.is_on = None

        GPIO.setmode(GPIO.BCM)
        GPIO.setup(self.gpio_pin, GPIO.OUT)

        self.program = None

        #self.turn_off()

        # Register a cleanup function to stop the LED timer process on exit
        atexit.register(self.cleanup)

    def __del__(self):
        self.cleanup()

    def cleanup(self):
        if self.program and self.program.is_alive():
            self.program.terminate()
            self.program.join()

    def turn_on(self):
        GPIO.output(self.gpio_pin, GPIO.HIGH)
        self.is_on = True

    def turn_off(self):
        GPIO.output(self.gpio_pin, GPIO.LOW)
        self.is_on = False

    def run_led_timer(self, duration, period, timeout):
        timeout = timeout + (period * 2)
        def led_timer_process():

            # Set the process's CPU priority to a high value
            #psutil.Process().nice(20)  # Adjust the nice value as needed

            # led_control = LED(self.gpio_pin)
            end_time = time.time() + timeout

            # LEDs are turned on <offset> seconds before pictures are taken
            offset = 0.25

            while time.time() < end_time:
                current_time = time.time()
                if (current_time + offset) % period < 0.01:
                    self.turn_on()
                    time.sleep(duration)
                    self.turn_off()

                remaining_time = period - ((time.time() + offset) % period)
                time.sleep(remaining_time)

        self.program = multiprocessing.Process(target=led_timer_process)
        self.program.start()
