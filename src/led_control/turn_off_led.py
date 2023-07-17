
import RPi.GPIO as GPIO

GPIO.setwarnings(False)

GPIO.setmode(GPIO.BCM) # set pin numbering mode to BCM
GPIO.setup(17, GPIO.OUT) # set GPIO pin 17 as an output

GPIO.output(17, GPIO.LOW)

#GPIO.cleanup()