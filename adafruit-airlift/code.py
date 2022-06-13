# SPDX-FileCopyrightText: Brent Rubell for Adafruit Industries
# SPDX-License-Identifier: MIT

import time
import rtc
from microcontroller import cpu
import board
import busio
from digitalio import DigitalInOut
from adafruit_esp32spi import adafruit_esp32spi
from adafruit_esp32spi import adafruit_esp32spi_wifimanager
import adafruit_esp32spi.adafruit_esp32spi_socket as socket
import adafruit_minimqtt.adafruit_minimqtt as MQTT
from adafruit_io.adafruit_io import IO_MQTT, IO_HTTP
import adafruit_requests
from battery import measure_voltage, on_batt, calculate_percentage

### WiFi ###

# Get wifi details and more from a secrets.py file
try:
    from secrets import secrets
except ImportError:
    print("WiFi secrets are kept in secrets.py, please add them there!")
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

http_client = IO_HTTP(
    secrets['aio_username'],
    secrets['aio_key'],
    adafruit_requests
)

# Define callback functions which will be called when certain events happen.
# pylint: disable=unused-argument
def connected(client):
    # Connected function will be called when the client is connected to Adafruit IO.
    print("Connected to Adafruit IO! ")
    io.publish("connect", 1)


def subscribe(client, userdata, topic, granted_qos):
    # This method is called when the client subscribes to a new feed.
    print("Subscribed to {0} with QOS level {1}".format(topic, granted_qos))
    led_pin.value = False
    time.sleep(0.1)
    led_pin.value = True
    time.sleep(0.1)
    # now get the latest value of the feed...
    value = http_client.receive_data(topic.split('/')[-1]).get('value')
    on_led_msg(None, topic, value)


# pylint: disable=unused-argument
def disconnected(client):
    # Disconnected function will be called when the client disconnects.
    print("Disconnected from Adafruit IO!")


def on_led_msg(client, topic, message):
    # Method called whenever user/feeds/led has a new value
    print("New message on topic {0}: {1} ".format(topic, message))
    if message == "ON":
        led_pin.value = True
    elif message == "OFF":
        led_pin.value = False
    else:
        print("Unexpected message on LED feed.")

# print the firmware version and mac address first
print('Firmware version:', esp.firmware_version)
print('MAC address:', [hex(i) for i in esp.MAC_address])

# Connect to WiFi
print("Connecting to WiFi...")
wifi.connect()
print("Connected!")

# Initialize MQTT interface with the esp interface
MQTT.set_socket(socket, esp)

# Initialize a new MQTT Client object
mqtt_client = MQTT.MQTT(
    broker="io.adafruit.com",
    port=1883,
    username=secrets["aio_username"],
    password=secrets["aio_key"],
)

# Initialize an Adafruit IO MQTT Client
io = IO_MQTT(mqtt_client)

# Connect the callback methods defined above to Adafruit IO
io.on_connect = connected
io.on_disconnect = disconnected
io.on_subscribe = subscribe

# Set up a callback for the led feed
io.add_feed_callback("led", on_led_msg)

# Connect to Adafruit IO
print("Connecting to Adafruit IO...")
io.connect()

# Subscribe to all messages on the led feed
io.subscribe("led")
current_time = 0
clock = rtc.RTC()
SECONDS_PER_HOUR = 60 * 60
def init_clock(tries=0,tz=-7):
    try:
        current_time = esp.get_time()[0]
        current_time += (tz * SECONDS_PER_HOUR)
        clock.datetime = time.localtime(current_time)
    except ValueError:
        print("Error getting current time")
        if tries < 3:
            time.sleep(2**tries)
            init_clock(tries+1)
    print("Current time:", clock.datetime)
init_clock()
prv_refresh_time = 0.0
while True:
    # Poll for incoming messages
    try:
        io.loop()
    except (ValueError, RuntimeError) as e:
        print("Failed to get data, retrying\n", e)
        wifi.reset()
        wifi.connect()
        io.reconnect()
        continue
    # pulse the LED every minute
    if (time.monotonic() - prv_refresh_time) > 60:
        print('.')
        led_pin.value = not led_pin.value
        time.sleep(0.5)
        led_pin.value = not led_pin.value
    # Send a new temperature reading to IO every 30 seconds
    if (time.monotonic() - prv_refresh_time) > 30:
        # take the cpu's temperature
        cpu_temp = cpu.temperature
        # truncate to two decimal points
        cpu_temp = str(cpu_temp)[:5]
        print("CPU temperature is %s degrees C" % cpu_temp)
        # publish it to io
        print("Publishing %s to temperature feed..." % cpu_temp)
        io.publish("temperature", cpu_temp)
        if on_batt():
            io.publish("battery", calculate_percentage(measure_voltage()))
        else:
            io.publish("battery", 100)
        print("Published!")
        prv_refresh_time = time.monotonic()
