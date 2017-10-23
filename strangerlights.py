#!/usr/bin/env python3

from colorsys import hsv_to_rgb
from itertools import cycle
from time import sleep
import atexit
import random
import logging
import asyncio

from rpi_ws281x import Color, PixelStrip
import _rpi_ws281x as ws

from hbmqtt.client import MQTTClient, ClientException
from hbmqtt.mqtt.constants import QOS_0

log = logging.getLogger("strangerlights")

# LED strip configuration:
LED_COUNT = 50
LED_PIN = 18
LED_TYPE = ws.WS2811_STRIP_RGB

#Predefined Colors and Masks
OFF = Color(0, 0, 0)
WHITE = Color(255, 255, 255)
RED = Color(255, 0, 0)
GREEN = Color(0, 255, 0)
BLUE = Color(0, 0, 255)
PURPLE = Color(128, 0, 128)
YELLOW = Color(255, 255, 0)
ORANGE = Color(255, 50, 0)
TURQUOISE = Color(64, 224, 208)

#bitmasks used in scaling RGB values
REDMASK = 0xff0000
GREENMASK = 0x00ff00
BLUEMASK = 0x0000ff

#list of colors, tried to match the show as close as possible
COLOURS = [YELLOW, GREEN, RED, BLUE, ORANGE, TURQUOISE, GREEN, YELLOW, PURPLE,
           RED, GREEN, BLUE, YELLOW, RED, TURQUOISE, GREEN, RED, BLUE, GREEN,
           ORANGE, YELLOW, GREEN, RED, BLUE, ORANGE, TURQUOISE, RED, BLUE,
           ORANGE, RED, YELLOW, GREEN, PURPLE, BLUE, YELLOW, ORANGE, TURQUOISE,
           RED, GREEN, YELLOW, PURPLE, YELLOW, GREEN, RED, BLUE, ORANGE,
           TURQUOISE, GREEN, BLUE, ORANGE]

LETTERS = "----------a-b-cd-ef-g--hijklm--nopqrstuvwxyz"
BLINK_ON = 1
BLINK_OFF = 0.5

MQTT_BROKER = "mqtt://10.0.1.216/"
MQTT_TOPIC = "control/strangerlights"

MODES = []

strip = None

showing_message = False


def rainbow():
    """ A simple colour wheel fade across the LEDs """
    for i in range(LED_COUNT):
        r, g, b = hsv_to_rgb(i/LED_COUNT, 1, 1)
        r, g, b = [int(v * 255) for v in (r, g, b)]
        strip.setPixelColorRGB(i, r, g, b)
    strip.show()
MODES.append(rainbow)


async def fairy_lights(fade_in=False):
    """ Standard fairy light colours along the strip """
    leds = list(zip(range(LED_COUNT), cycle(COLOURS)))
    random.shuffle(leds)
    for i, colour in leds:
        strip.setPixelColor(i, colour)
        if fade_in:
            strip.show()
            await asyncio.sleep(random.randint(10,80)/1000.0)
    strip.show()
MODES.append(fairy_lights)


async def fade_out():
    leds = list(range(LED_COUNT))
    random.shuffle(leds)
    for i in leds:
        strip.setPixelColor(i, OFF)
        strip.show()
        await asyncio.sleep(random.randint(10,80)/1000.0)


async def show_message(message):
    """ Display a message on the fairy lights, one letter at a time """
    global showing_message
    showing_message = True
    await fade_out()
    off()
    await asyncio.sleep(1)
    for char in message:
        i = LETTERS.find(char.lower())
        if i > -1:
            await blink_led(i, random.choice(COLOURS))
    await asyncio.sleep(1)
    await fairy_lights(fade_in=True)
    showing_message = False


async def blink_led(i, colour):
    strip.setPixelColor(i, colour)
    strip.show()
    await asyncio.sleep(BLINK_ON)
    strip.setPixelColor(i, OFF)
    strip.show()
    await asyncio.sleep(BLINK_OFF)


def colour_of_led(i):
    colour = strip.getPixelColor(i)
    red = (colour & REDMASK) >> 16
    green = (colour & GREENMASK) >> 8
    blue = (colour & BLUEMASK)
    return red, green, blue


async def flicker_led(i):
    r, g, b = colour_of_led(i)

    def reset_colour():
        strip.setPixelColorRGB(i, r, g, b)
        strip.show()

    await asyncio.sleep(random.randint(1, 4))
    for _ in range(random.randint(1, 12)):
        if showing_message:
            reset_colour()
            return
        strip.setPixelColor(i, OFF)
        strip.show()
        await asyncio.sleep(random.randint(10,50)/1000.0)
        fade_factor = random.random()
        nr, ng, nb = int(r*fade_factor), int(g*fade_factor), int(b*fade_factor)
        strip.setPixelColorRGB(i, nr, ng, nb)
        strip.show()
        await asyncio.sleep(random.randint(10,80)/1000.0)
    reset_colour()


async def flickering():
    leds = random.sample(list(range(LED_COUNT)), LED_COUNT//8)
    await asyncio.gather(*[flicker_led(i) for i in leds])


def off():
    """ Switch everything off """
    for i in range(LED_COUNT):
        strip.setPixelColor(i, 0)
    strip.show()


def lights_setup():
    global strip
    strip = PixelStrip(LED_COUNT, LED_PIN)
    ws.ws2811_channel_t_strip_type_set(strip._channel, LED_TYPE)
    strip.begin()
    atexit.register(off)

    # fairy_lights(strip)
    # fade_out(strip)
    # fairy_lights()


def lights_loop():
    flickering()

    while True:
        try:
            pass
        except KeyboardInterrupt:
            break


async def mqtt_loop():
    client = MQTTClient()
    await client.connect(MQTT_BROKER)
    log.info("Connected")
    await client.subscribe([(MQTT_TOPIC, QOS_0)])
    log.info("Subscribed")
    await fairy_lights()
    try:
        while True:
            message = await client.deliver_message()
            packet = message.publish_packet
            topic = packet.variable_header.topic_name
            payload = bytes(packet.payload.data)
            log.debug("{}: {}".format(topic, payload))
            await show_message(payload.decode())
        await client.unsubscribe([(MQTT_TOPIC, QOS_0)])
        await client.disconnect()
        log.info("Disconnected")
    except ClientException:
        log.exception("A client exception occurred.")

async def effects_loop():
    while True:
        if not showing_message:
            await flickering()
        await asyncio.sleep(random.randint(1, 4))

def main():
    formatter = "[%(asctime)s] %(name)s {%(filename)s:%(lineno)d} " \
            "%(levelname)s - %(message)s"
    logging.basicConfig(level=logging.DEBUG, format=formatter)
    lights_setup()
    asyncio.ensure_future(mqtt_loop())
    asyncio.ensure_future(effects_loop())
    asyncio.get_event_loop().run_forever()


if __name__ == '__main__':
    main()
