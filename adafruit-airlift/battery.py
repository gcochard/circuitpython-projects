import board
import alarm
import digitalio
import analogio
import time
from math import pow

vbus = digitalio.DigitalInOut(board.GP24)
vbus.direction = digitalio.Direction.INPUT
vsys = analogio.AnalogIn(board.A3)

FULL_BATTERY = 4.2
NOMINAL_BATTERY = 3.7
EMPTY_BATTERY = 3.2

def get_voltage(raw):
    # conversion factor provided by:
    # https://github.com/pimoroni/pimoroni-pico/blob/main/micropython/examples/pimoroni_pico_lipo/battery.py#L22
    volts = (raw * 3 * 3.3) / 65535
    print("raw = {:5d} volts = {:5.2f}".format(raw, volts))
    return volts

def measure_voltage():
    raw = vsys.value
    return get_voltage(raw)

def on_batt():
    print("on battery", not vbus.value)
    return not vbus.value

def calculate_percentage(v):
    return 123 - (123/pow(1+pow(v/NOMINAL_BATTERY,80),0.165))

def lowsleep(s):
    time_alarm = alarm.time.TimeAlarm(monotonic_time=time.monotonic() + s)
    alarm.light_sleep_until_alarms(time_alarm)

if __name__ == "__main__":
    while True:
        ontime = 0.1_0
        offtime = 1
        v = get_voltage(vsys.value)
        if not on_batt():
            ontime  = 0.5
            offtime = 1
        else:
            #led.value = True
            #time.sleep(0.05)
            #led.value = False
            """
            if v >= 3.5:
                ontime  = 0.5
                offtime = 0.1
            elif v >= 3.4 and v < 3.5:
                ontime  = 0.4
                offtime = 0.2
            elif v >= 3.3 and v < 3.4:
                ontime  = 0.3
                offtime = 0.3
            elif v >= 3.2 and v < 3.3:
                ontime  = 0.2
                offtime = 0.4
            elif v >= 3.1 and v < 3.2:
                ontime  = 0.1
                offtime = 0.5
            """

            for v in range(0, int(v)):
                led.value = True
                time.sleep(0.5)
                led.value = False
                time.sleep(0.1)
            for v in range(0, v * 10 - (int(v) * 10)):
                led.value = True
                time.sleep(0.25)
                led.value = False
                time.sleep(0.1)
        lowsleep(offtime)
        led.value = True
        time.sleep(ontime)
        led.value = False
        lowsleep(offtime)
