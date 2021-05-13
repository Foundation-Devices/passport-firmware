# SPDX-FileCopyrightText: 2020 Foundation Devices, Inc. <hello@foundationdevices.com>
# SPDX-License-Identifier: GPL-3.0-or-later
#

from uasyncio import sleep_ms
import random
import utime
import common
from ubinascii import hexlify as b2a_hex

def ambient_to_brightness(ambient):
    return 100 - ambient

async def update_ambient_screen_brightness():
    first_time = True
    while True:
        from common import settings, dis, system
        if not first_time:
            await sleep_ms(5000)
        first_time = False

        # Brightness of 999 means automatic
        if settings.get('screen_brightness', 100) == 999:
            ambient = system.read_ambient()
            brightness = ambient_to_brightness(ambient)
            # print('  ambient = {}  brightness = {}'.format(ambient, brightness))
            dis.set_brightness(brightness)

battery_segments = [
  {'v': 3100, 'p': 100},
  {'v': 3100, 'p': 100},
  {'v': 3025, 'p': 75},
  {'v': 2975, 'p': 50},
  {'v': 2800, 'p': 25},
  {'v': 2400, 'p': 0},
]

def calc_battery_percent(current, voltage):
    # print('calc_battery_percent(): voltage={}'.format(voltage))
    if voltage > 3100:
        voltage = 3100
    elif voltage < 2400:
        voltage = 2400

    # First find the segment we fit in
    for i in range(1, len(battery_segments)):
        curr = battery_segments[i]
        prev = battery_segments[i - 1]
        if voltage >= curr['v']:
            # print('curr[{}]={}'.format(i, curr))

            rise = curr['v'] - prev['v']
            # print('rise={}'.format(rise))

            run = curr['p'] - prev['p']
            # print('run={}'.format(run))

            if run == 0:
                # print('zero run, so return value directly: {}'.format(curr['p']))
                return curr['p']

            # Slope
            m = rise / run
            # print('m={}'.format(m))

            # y = mx + b  =>  x = (y - b) / m  =>  b = y - mx

            # Calculate y intercept for this segment
            b = curr['v'] - (m * curr['p'])
            # print('b={}'.format(b))

            percent = int((voltage - b) / m)
            # print('Returning percent={}'.format(percent))
            return percent

    return 0

NUM_SAMPLES = 2

async def update_battery_level():
    from utils import random_filename
    from files import CardSlot
    header_written = False
    first_time = True
    battery_mon_fname = None

    while True:
        # Take a reading immediately the first time through
        if not first_time:
            await sleep_ms(60000)

        first_time = False

        # Read the current values -- repeat this a number of times and average for better results
        total_current = 0
        total_voltage = 0
        for i in range(NUM_SAMPLES):
            (current, voltage) = common.powermon.read()
            voltage = round(voltage * (44.7 + 22.1) / 44.7)
            total_current += current
            total_voltage += voltage
            await sleep_ms(1) # Wait a bit before next sample
        current = total_current / NUM_SAMPLES
        voltage = total_voltage / NUM_SAMPLES

        # Update the battery_mon file if enabled
        if common.enable_battery_mon:
            try:
                with CardSlot() as card:
                    if battery_mon_fname == None:
                        battery_mon_fname = random_filename(card, 'battery-mon-{}.csv')

                    with open(battery_mon_fname, 'a') as fd:
                        # Write the header
                        if not header_written:
                            # print('Writing battery_mon header')
                            fd.write('Time,Current,Voltage\n')
                            header_written = True

                        # Write the sample values
                        now = utime.ticks_ms()
                        # print('Writing battery_mon sample: current={} voltage={}'.format(current, voltage))
                        fd.write('{},{},{}\n'.format(now, current, voltage))
            except Exception as e:
                # includes CardMissingError
                import sys
                sys.print_exception(e)

        # Update the actual battery level that drives the icon
        level = calc_battery_percent(current, voltage)
        # print(' new battery level = {}'.format(level))
        common.battery_level = level
        common.battery_voltage = voltage


SHUTDOWN_COUNTDOWN_MAX = 6

async def check_auto_shutdown():
    countdown = SHUTDOWN_COUNTDOWN_MAX
    while True:
        from common import settings, dis

        # Never shutdown when doing a battery test!
        if common.enable_battery_mon:
            return

        timeout_ms = settings.get('shutdown_timeout', 5*60) * 1000 # Convert secs to ms

        await sleep_ms(1000)  # Always check again right after waking from sleep
        if timeout_ms == 0:
            continue

        # Give user a chance to abort
        countdown -= 1
        now = utime.ticks_ms()
        idle_so_far = now - common.last_activity_time
        # print('idle_so_far={} timeout_ms={} countdown={}'.format(idle_so_far, timeout_ms, countdown))
        if idle_so_far >= timeout_ms:
            if countdown == -1:
                common.system.shutdown() # Never return from this!
            else:
                dis.fullscreen('Shutting down in {}'.format(countdown), line2='Press key to cancel')
        else:
            # Reset countdown if we haven't hit the timeout yet
            countdown = SHUTDOWN_COUNTDOWN_MAX


ENTER = 'y1'
BACK = 'x1'
BACKSPACE = '*1'
EXIT = -1

main_actions = [
    'd4',
    ENTER,
    2000,
    'd8',
    ENTER,
    2000,
    'd2',
    ENTER,
    2000,
    'd3',
    ENTER,
    2000,
    ENTER,
    5000,
    BACK,
    2000,
    BACK,
    2000,
    BACK,
    2000,
    'u2',
    ENTER,
    2000,
    'd2',
    ENTER,  # 100%
    2000,
    ENTER,
    2000,
    'u2',  # Back to 50%
    ENTER,
    2000,
    BACK,
    'u4',
    5000,
    'd1',
    ENTER,
    15000,  # Camera on for 15 seconds
    BACK,
    'u1',
]

actions = [
    1000,
    'd2',    # Just a wink so you know the script has started
    1000,
    'u2',
    1000,
    {
        'repeat': 1,
        'actions': main_actions
    },
    5000,
    # 7200000, # 2 hour delay before next transaction
]

async def run_actions(actions, repeat):
    import common

    for i in range(repeat):
        for action in actions:
            if common.demo_active:
                await handle_demo_action(action)
                await sleep_ms(100)  # Short delay to keep things from going too fast

async def handle_demo_action(action):
    import common

    if type(action) == int:
        if action == -1:
            # Disable the demo
            common.demo_active = False
            return

        # print('delay {}ms'.format(action))

        # Delay
        await sleep_ms(action)

    elif isinstance(action, dict):
        # Nested script
        print('Starting nested script')
        repeat = action['repeat']
        actions = action['actions']
        await run_actions(actions, repeat)

    else:
        key = action[0]
        count = int(action[1:])

        print('inject "{}" {} times'.format(key, count))
        for i in range(count):
            common.keypad.inject(key)

async def demo_loop():
    import common
    while True:
        if common.demo_active:
            await run_actions(actions, 1)
            common.demo_count += 1
        else:
            common.demo_count = 0
            await sleep_ms(5000)
