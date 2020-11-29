# SPDX-FileCopyrightText: 2020 Foundation Devices, Inc.  <hello@foundationdevices.com>
# SPDX-License-Identifier: GPL-3.0-or-later
#
from uasyncio import sleep_ms
from common import dis, noise
from display import Display, FontSmall
from settings import Settings
from ux import KeyInputHandler, ux_show_story
from files import CardSlot, CardMissingError
from foundation import Powermon
import utime

UPDATE_RATE = 1000 # in ms

def update(input, now, powermon, fd, prev_time, isRunning):
    font = FontSmall
    if (now - prev_time > UPDATE_RATE):
        prev_time = now

        # Grab PWRMON_V, PWRMON_I
        (current, voltage) = powermon.read()
        voltage = round(voltage * (44.7 + 22.1) / 44.7)
        print('time = {}, current={}, voltage={}'.format(now, current, voltage))
        if voltage < 2550:
            isRunning = False
            return None # make sure to exit before battery dies

        # Write to SD card
        fd.write('{}, {}, {}\n'.format(now, current, voltage))
        # fd.write('{"now":{}, "current":{}, "voltage":{}},'.format(now, current, voltage))

        dis.clear()
        dis.draw_header()
        dis.text(None, Display.HALF_HEIGHT - 3 * font.leading // 4 - 9, 'Time: {}'.format(now))
        dis.text(None, Display.HALF_HEIGHT                         - 9, 'Current: {}'.format(current))
        dis.text(None, Display.HALF_HEIGHT + 3 * font.leading // 4 - 9, 'Voltage: {}'.format(voltage))
        dis.draw_footer('BACK', '', input.is_pressed('x'), input.is_pressed('y'))
        dis.show()

    return None




async def battery_mon():
    isRunning = True
    input = KeyInputHandler(down='udplrxy', up='xy')
    powermon = Powermon()
    prev_time = 0
    (n1, _) = noise.read() 
    FILENAME = 'battery_mon_test_' + str(n1) + '.txt'

    while(True):
        try:
            with CardSlot() as card:
                # fname, nice = card.pick_filename(fname_pattern)
                fname = FILENAME

                # do actual write
                with open(fname, 'wb') as fd:
                    print("writing to SD card...")  
                    fd.write('Time, Current, Voltage\n')             
                    while isRunning:
                        event = await input.get_event()
                        if event != None:
                            key, event_type = event
                            if event_type == 'up':
                                if key == 'x':
                                    isRunning = False

                        update(input, utime.ticks_ms(), powermon, fd, prev_time, isRunning)

                        await sleep_ms(1)

                    fd.close()

                    break

        except Exception as e:
            # includes CardMissingError
            import sys
            sys.print_exception(e)
            # catch any error
            ch = await ux_show_story('Failed to write! Please insert formated microSD card, '
                                     'and press OK to try again.\n\nX to cancel.\n\n\n'+str(e))
            if ch == 'x':
                break
            continue

    return None



    