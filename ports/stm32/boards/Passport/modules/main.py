# SPDX-FileCopyrightText: 2020 Foundation Devices, Inc.  <hello@foundationdevices.com>
# SPDX-License-Identifier: GPL-3.0-or-later
#
# SPDX-FileCopyrightText: 2018 Coinkite, Inc.  <coldcardwallet.com>
# SPDX-License-Identifier: GPL-3.0-only
#
# (c) Copyright 2018 by Coinkite Inc. This file is part of Coldcard <coldcardwallet.com>
# and is covered by GPLv3 license found in COPYING.
#
# main.py - Main initialization code
#

import utime
import uasyncio.core as asyncio
from uasyncio import sleep_ms

# Show REPL welcome message
print("Entered main.py")
import gc
print('1: Available RAM = {}'.format(gc.mem_free()))

# camera = Camera()
# start = utime.ticks_ms()
# camera.copy_capture(bytearray(10), bytearray(10))
# camera.copy_capture(bytearray(10), bytearray(10))
# camera.copy_capture(bytearray(10), bytearray(10))
# end = utime.ticks_ms()
# print('Camera copy and conversion took {}ms'.format(end - start))

SETTINGS_FLASH_START = 0x81E0000
SETTINGS_FLASH_SIZE  = 0x20000

# We run main in a separate task so that the startup loop's variable can be released
async def main():

    from ux import the_ux

    while 1:
        await sleep_ms(10)
        await the_ux.interact()

# Setup a new task for the main execution


async def startup():
    print("startup()")

    from actions import accept_terms, validate_passport_hw
    await accept_terms()

    # We will come here again if the device is shutdown, but the validation
    # words have not been confirmed (assuming the terms were accepted).
    await validate_passport_hw()

    # Setup first PIN if it's blank
    from common import pa
    from actions import initial_pin_setup
    if pa.is_blank():
        await initial_pin_setup()

    # Prompt for PIN and then pick appropriate top-level menu,
    # based on contents of secure chip (ie. is there
    # a wallet defined)
    from actions import start_login_sequence
    await start_login_sequence()

    # from actions import test_normal_menu
    # await test_normal_menu()
    from actions import goto_top_menu
    goto_top_menu()

    from common import loop
    loop.create_task(main())


def go(operation='', field='chain', value='BTC'):
    import common
    from sram4 import viewfinder_buf
    print('2: Available RAM = {}'.format(gc.mem_free()))

    # Avalanche noise source
    from foundation import Noise
    common.noise = Noise()

    # Get the async event loop to pass in where needed
    common.loop = asyncio.get_event_loop()

    # System
    from foundation import System
    common.system = System()

    print('2.75: Available RAM = {}'.format(gc.mem_free()))
    # Initialize the keypad
    from keypad import Keypad
    common.keypad = Keypad()
    print('3: Available RAM = {}'.format(gc.mem_free()))

    # Initialize SD card
    from files import CardSlot
    CardSlot.setup()
    print('3.5: Available RAM = {}'.format(gc.mem_free()))

    # External SPI Flash
    from sflash import SPIFlash
    common.sf = SPIFlash()

    # Initialize NV settings
    from settings import Settings
    common.settings = Settings(common.loop)
    print('4: Available RAM = {}'.format(gc.mem_free()))


    # Initialize the display and show the splash screen
    from display import Display
    print("disp 1")
    common.dis = Display()
    print("disp 2")
    common.dis.set_brightness(common.settings.get('screen_brightness', 100))
    print("disp 3")
    common.dis.splash()
    print('5: Available RAM = {}'.format(gc.mem_free()))

    # Allocate buffers for camera
    from constants import VIEWFINDER_WIDTH, VIEWFINDER_HEIGHT, CAMERA_WIDTH, CAMERA_HEIGHT

    # QR buf is 1 byte per pixel grayscale
    import uctypes
    common.qr_buf = uctypes.bytearray_at(0x20000000, CAMERA_WIDTH * CAMERA_HEIGHT)
    # common.qr_buf = bytearray(CAMERA_WIDTH * CAMERA_HEIGHT)
    print('6: Available RAM = {}'.format(gc.mem_free()))

    # Viewfinder buf 1s 1 bit per pixel and we round the screen width up to 240
    # so it's a multiple of 8 bits.  The screen height of 303 minus 31 for the
    # header and 31 for the footer gives 241 pixels, which we round down to 240
    # to give one blank (white) line before the footer.
    common.viewfinder_buf = bytearray((VIEWFINDER_WIDTH * VIEWFINDER_HEIGHT) // 8)
    print('7: Available RAM = {}'.format(gc.mem_free()))


    # Show REPL welcome message
    print("Passport by Foundation Devices Inc. (C) 2020.\n")

    print('8: Available RAM = {}'.format(gc.mem_free()))

    from foundation import SettingsFlash
    f = SettingsFlash()

    if operation == 'dump':
        print('Settings = {}'.format(common.settings.curr_dict))
        print('addr = {}'.format(common.settings.addr))
    elif operation == 'erase':
        f.erase()
    elif operation == 'set':
        common.settings.set(field, value)
    elif operation == 'stress':
        for f in range(35):
            print("Round {}:".format(f))
            print('  Settings = {}'.format(common.settings.curr_dict))            
            common.settings.set('field_{}'.format(f), f)
            common.settings.save()

        print('\nFinal Settings = {}'.format(common.settings.curr_dict))            

    # This "pa" object holds some state shared w/ bootloader about the PIN
    try:
        from pincodes import PinAttempt

        common.pa = PinAttempt()
        common.pa.setup(b'')
    except RuntimeError as e:
        print("Secure Element Problem: %r" % e)
    print('9: Available RAM = {}'.format(gc.mem_free()))


    # Setup the startup task
    common.loop.create_task(startup())

    run_loop()


def run_loop():
    # Wrapper for better error handling/recovery at top level.
    try:
        # This keeps all async tasks alive, including the main task created above
        from common import loop
        loop.run_forever()
    except BaseException as exc:
        import sys
        sys.print_exception(exc)
        # if isinstance(exc, KeyboardInterrupt):
        #     # preserve GUI state, but want to see where we are
        #     print("KeyboardInterrupt")
        #     raise
        if isinstance(exc, SystemExit):
            # Ctrl-D and warm reboot cause this, not bugs
            raise
        else:
            print("Exception:")
            # show stacktrace for debug photos
            try:
                import uio
                import ux
                tmp = uio.StringIO()
                sys.print_exception(exc, tmp)
                msg = tmp.getvalue()
                del tmp
                print(msg)
                ux.show_fatal_error(msg)
            except Exception as exc2:
                sys.print_exception(exc2)

            # securely die (wipe memory)
            # TODO: Add this back in!
            # try:
            #     import callgate
            #     callgate.show_logout(1)
            # except: pass


# Initialization
# - NV storage / options
# - PinAttempt class
# -

# Required to port
# - pincodes.py - need to simplify
#


go()
