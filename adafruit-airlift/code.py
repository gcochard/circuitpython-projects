# SPDX-FileCopyrightText: Brent Rubell for Adafruit Industries
# SPDX-License-Identifier: MIT

import time
import rtc
from microcontroller import cpu
import board
import busio
from digitalio import DigitalInOut, Pull
from adafruit_esp32spi import adafruit_esp32spi
from adafruit_esp32spi import adafruit_esp32spi_wifimanager
import adafruit_esp32spi.adafruit_esp32spi_socket as socket
import adafruit_minimqtt.adafruit_minimqtt as MQTT
from adafruit_minimqtt.adafruit_minimqtt import MMQTTException
from adafruit_io.adafruit_io import IO_MQTT, IO_HTTP
import adafruit_requests
from battery import measure_voltage, on_batt, calculate_percentage
import neopixel
from random import randint

uart = busio.UART(board.GP0, board.GP1)
clock = rtc.RTC()

def print_u(data, *rest):
    print(data, *rest)
    uart.write(data.encode('utf8'))
    for r in rest:
        if hasattr(r, 'encode'):
            uart.write(r.encode('utf8'))
        else:
            uart.write(r)
    uart.write(b'\n')

def strftime(fspec, tt):
    fspec = fspec.replace('%Y', str(tt[0]))
    fspec = fspec.replace('%m', '{0:0>2}'.format(tt[1]))
    fspec = fspec.replace('%d', '{0:0>2}'.format(tt[2]))
    fspec = fspec.replace('%H', '{0:0>2}'.format(tt[3]))
    fspec = fspec.replace('%M', '{0:0>2}'.format(tt[4]))
    fspec = fspec.replace('%S', '{0:0>2}'.format(tt[5]))
    return fspec
class UartLogger:
    def __init__(self, name, level, time=True):
        self.name = name
        self.level = level
        self.time = time
    def print(self, *args):
        now = strftime('%Y-%m-%d %H:%M:%S', clock.datetime)
        level = args[0]
        args = args[1:]
        if len(args) > 1:
            fmt = args[0]
            print_u(f'{now} [{self.name}] {level}', fmt % args[1:])
        else:
            print_u(f'{now} [{self.name}] {level}', *args)
    def error(self, *args):
        if self.level <= 40:
            return self.print('ERROR: ', *args)
    def warning(self, *args):
        if self.level <= 30:
            return self.print('WARNING: ', *args)
    def info(self, *args):
        if self.level <= 20:
            return self.print('INFO: ', *args)
    def debug(self, *args):
        if self.level <= 10:
            return self.print('DEBUG: ', *args)
    def setLevel(self, level):
        self.level = level
    @classmethod
    def getLogger(cls, name, level=10):
        return cls(name, level)

logger = UartLogger.getLogger('code')
logger.setLevel(20)
logger.debug('test %s', 'a')
### WiFi ###

# Get wifi details and more from a secrets.py file
try:
    from secrets import secrets
except ImportError:
    logger.warning("WiFi secrets are kept in secrets.py, please add them there!")
    raise

# Raspberry Pi RP2040
esp32_cs = DigitalInOut(board.GP13)
esp32_ready = DigitalInOut(board.GP14)
esp32_reset = DigitalInOut(board.GP15)

spi = busio.SPI(board.GP10, board.GP11, board.GP12)
esp = adafruit_esp32spi.ESP_SPIcontrol(spi, esp32_cs, esp32_ready, esp32_reset)

wifi = adafruit_esp32spi_wifimanager.ESPSPI_WiFiManager(esp, secrets)

# Configure the RP2040 Pico LED Pin as an output
led_pin = DigitalInOut(board.LED)
led_pin.switch_to_output()

NUM_PIXELS = 3
neokey = neopixel.NeoPixel(board.GP16, NUM_PIXELS, brightness=0.1, auto_write=False)

switch = DigitalInOut(board.GP17)
# when switch is False, it's pressed
switch.switch_to_input(pull=Pull.DOWN)

http_client = IO_HTTP(
    secrets['aio_username'],
    secrets['aio_key'],
    adafruit_requests
)

# Define callback functions which will be called when certain events happen.
# pylint: disable=unused-argument
def connected(client):
    # Connected function will be called when the client is connected to Adafruit IO.
    logger.info("Connected to Adafruit IO! ")
    io.publish("connect", 1)


# pylint: disable=unused-argument
def disconnected(client):
    # Disconnected function will be called when the client disconnects.
    logger.info("Disconnected from Adafruit IO!")

class Color:
    def __init__(self, n):
        self.cur = 0
        self.colors = [(255,0,0),(0,255,0),(0,0,255),(255,255,0),(255,0,255),(0,255,255),(255,255,255)]
        self.random = False
        self.p = n
    def next(self):
        if self.random:
            val = self.rand()
        else:
            self.cur += 1
            self.cur %= len(self.colors)
            val = self.colors[self.cur]
        logger.debug("before: {}".format(self.p))
        for i in range(len(self.p), 0, -1):
            #logger.debug(self.p[i-2], self.p[i-1])
            self.p[i-1] = self.p[i-2]
        self.p[0] = val
        logger.debug("after: {}".format(self.p))
        self.p.show()
    def rand(self):
        return (randint(0, 255), randint(0, 255), randint(0, 255))
    def toggle_rand(self):
        self.random = not self.random

color = Color(neokey)

def on_led_msg(client, topic, message):
    # Method called whenever user/feeds/led has a new value
    logger.debug("New message on topic {0}: {1} ".format(topic, message))
    color.toggle_rand()
    if message == "ON":
        led_pin.value = True
    elif message == "OFF":
        led_pin.value = False
    else:
        logger.warning("Unexpected message on LED feed.")

# print the firmware version and mac address first
logger.debug('Firmware version: {}'.format(esp.firmware_version))
logger.debug('MAC address: {}'.format([hex(i) for i in esp.MAC_address]))

# Connect to WiFi
logger.info("Connecting to WiFi...")
wifi.connect()
logger.info("Connected!")

# Initialize MQTT interface with the esp interface
MQTT.set_socket(socket, esp)
#adafruit_requests.set_socket(socket)

#default to 60 second socket timeout
#socket.settimeout(60)

# Initialize a new MQTT Client object
mqtt_client = MQTT.MQTT(
    broker="io.adafruit.com",
    port=1883,
    username=secrets["aio_username"],
    password=secrets["aio_key"],
)
mqtt_client.enable_logger(UartLogger, log_level=10)
# Initialize an Adafruit IO MQTT Client
io = IO_MQTT(mqtt_client)

def subscribe(client, userdata, topic, granted_qos):
    # This method is called when the client subscribes to a new feed.
    logger.debug("Subscribed to {0} with QOS level {1}".format(topic, granted_qos))
    led_pin.value = False
    time.sleep(0.1)
    led_pin.value = True
    time.sleep(0.1)
    # now get the latest value of the feed...
    logger.debug('Requesting current value of LED')
    io.publish("led/get", 1)
    #value = http_client.receive_data(topic.split('/')[-1]).get('value')
    #logger.info("Got current value: {}".format(value))
    #on_led_msg(None, topic, value)

# Connect the callback methods defined above to Adafruit IO
io.on_connect = connected
io.on_disconnect = disconnected
io.on_subscribe = subscribe

# Set up a callback for the led feed
io.add_feed_callback("led", on_led_msg)

# Connect to Adafruit IO
logger.info("Connecting to Adafruit IO...")
io.connect()

# Subscribe to all messages on the led feed
io.subscribe("led")
current_time = 0

SECONDS_PER_HOUR = 60 * 60
def init_clock(tries=0,tz=-7):
    try:
        current_time = esp.get_time()[0]
        current_time += (tz * SECONDS_PER_HOUR)
        clock.datetime = time.localtime(current_time)
    except ValueError:
        logger.error("Error getting current time")
        if tries < 3:
            time.sleep(2**tries)
            init_clock(tries+1)
    if tries == 0:
        logger.info("Current time: {}".format(clock.datetime))
init_clock()
prv_refresh_time = 0.0
prv_blink_time = 0.0

while True:
    # Poll for incoming messages
    try:
        #logger.debug('Running io loop')
        io.loop()
        if switch.value:
            color.toggle_rand()
            #print('Switch pressed!')
        color.next()

        # pulse the LED every minute
        if (time.monotonic() - prv_blink_time) > 60:
            prv_blink_time = time.monotonic()
            logger.info('.')
            led_pin.value = not led_pin.value
            time.sleep(0.5)
            led_pin.value = not led_pin.value
        # Send a new temperature reading to IO every 30 seconds
        if (time.monotonic() - prv_refresh_time) > 30:
            # take the cpu's temperature
            cpu_temp = cpu.temperature
            # truncate to two decimal points
            cpu_temp = str(cpu_temp)[:5]
            logger.debug("CPU temperature is %s degrees C", cpu_temp)
            # publish it to io
            logger.debug("Publishing %s to temperature feed...", cpu_temp)
            io.publish("temperature", cpu_temp)
            volts = measure_voltage()
            logger.debug("Publishing %s to voltage feed...", volts)
            io.publish("voltage", volts)
            if on_batt():
                pct = calculate_percentage(volts)
            else:
                pct = 100
            logger.debug("Publishing %s to battery feed...", pct)
            io.publish("battery", pct)
            logger.debug("Published!")
            prv_refresh_time = time.monotonic()
    except (ValueError, RuntimeError, MMQTTException) as e:
        logger.warning("Failed to get data, retrying\n{}".format(e))
        wifi.reset()
        wifi.connect()
        io.reconnect()
        continue