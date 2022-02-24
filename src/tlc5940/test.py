from tlc import tlc5940
import time

leds = tlc5940(blankpin = 27,
               progpin = 22,
               latchpin = 17,
               gsclkpin = 18,
               serialpin = 23,
               clkpin = 24)

try:
    leds.initialise()

    leds.blank(0)

    for led in range(0, 16):
        #leds.set_dot(led, 1)
        leds.set_grey(led, 1)



    while 1:
        #leds.write_dot_values()
        leds.write_grey_values()
        leds.pulse_clk()

except KeyboardInterrupt:
    pass

leds.blank(1)
leds.cleanup() # may cause odd flickering due to default Rpi pin settings.
               # Comment out if necessary