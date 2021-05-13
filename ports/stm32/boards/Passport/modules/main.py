# SPDX-FileCopyrightText: 2020 Foundation Devices, Inc. <hello@foundationdevices.com>
# SPDX-License-Identifier: GPL-3.0-or-later
#
# SPDX-FileCopyrightText: 2018 Coinkite, Inc. <coldcardwallet.com>
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
from periodic import update_ambient_screen_brightness, update_battery_level, check_auto_shutdown, demo_loop
from schema_evolution import handle_schema_evolutions

#
# Show REPL welcome message
print("Entered main.py")
import gc
print('Available RAM = {}'.format(gc.mem_free()))

SETTINGS_FLASH_START = 0x81E0000
SETTINGS_FLASH_SIZE  = 0x20000

# We run main in a separate task so that the startup loop's variables can be released
async def main():

    from ux import the_ux

    while 1:
        await sleep_ms(10)
        await the_ux.interact()


async def startup():
    import common
    from common import pa, loop
    from actions import goto_top_menu, validate_passport_hw, initial_pin_setup, start_login_sequence

    print("startup()")
    common.system.hide_busy_bar()

    import uctypes
    buf = uctypes.bytearray_at(0x38000000, 1)

    # Check for self-test
    if buf[0] == 1:
        from self_test_ux import SelfTestUX
        self_test = SelfTestUX()
        await self_test.show()

    from accept_terms_ux import AcceptTermsUX
    accept_terms = AcceptTermsUX()
    await accept_terms.show()

    await validate_passport_hw()

    # Setup initial PIN if it's blank
    if pa.is_blank():
        await initial_pin_setup()

    # Prompt for PIN and then pick appropriate top-level menu
    await start_login_sequence()

    # Set the key for the flash cache (cache is inaccessible prior to user logging in)
    common.system.show_busy_bar()
    common.flash_cache.set_key()
    common.flash_cache.load()

    # Trigger a get here so that the XFP & XPUB are captured
    common.settings.get('xfp')

    # See if an update was just performed -- we may need to run a schema evolution script
    update_from_to = common.settings.get('update')
    # print('update_from_to={}'.format(update_from_to))
    if update_from_to:
        await handle_schema_evolutions(update_from_to)

    common.system.hide_busy_bar()

    await goto_top_menu()

    loop.create_task(main())


def go():
    import common
    from sram4 import viewfinder_buf

    # Initialize the common objects

    # Avalanche noise source
    from foundation import Noise
    common.noise = Noise()

    # Initialize the seed of the PRNG in MicroPython with a real random number
    # We only use the PRNG for non-critical randomness that just needs to be fast
    import random
    from utils import randint
    random.seed(randint(0, 2147483647))

    # Power monitor
    from foundation import Powermon
    common.powermon = Powermon()

    # Get the async event loop to pass in where needed
    common.loop = asyncio.get_event_loop()

    # System
    from foundation import System
    common.system = System()
    common.system.show_busy_bar()

    # Initialize the keypad
    from keypad import Keypad
    common.keypad = Keypad()

    # Initialize SD card
    from files import CardSlot
    CardSlot.setup()

    # External SPI Flash
    from sflash import SPIFlash
    common.sf = SPIFlash()

    # Initialize internal flash settings
    from settings import Settings
    common.settings = Settings(common.loop)

    # Initialize the external flash cache
    from flash_cache import FlashCache
    common.flash_cache = FlashCache(common.loop)

    # Initialize the display and show the splash screen
    from display import Display
    common.dis = Display()
    common.dis.set_brightness(common.settings.get('screen_brightness', 100))
    common.dis.splash()

    # Allocate buffers for camera
    from constants import VIEWFINDER_WIDTH, VIEWFINDER_HEIGHT, CAMERA_WIDTH, CAMERA_HEIGHT

    # QR buf is 1 byte per pixel grayscale
    import uctypes
    common.qr_buf = uctypes.bytearray_at(0x20000000, CAMERA_WIDTH * CAMERA_HEIGHT)
    # common.qr_buf = bytearray(CAMERA_WIDTH * CAMERA_HEIGHT)

    # Viewfinder buf 1s 1 bit per pixel and we round the screen width up to 240
    # so it's a multiple of 8 bits. The screen height of 303 minus 31 for the
    # header and 31 for the footer gives 241 pixels, which we round down to 240
    # to give one blank (white) line before the footer.
    common.viewfinder_buf = bytearray((VIEWFINDER_WIDTH * VIEWFINDER_HEIGHT) // 8)

    # Show REPL welcome message
    print("Passport by Foundation Devices Inc. (C) 2020.\n")

    from foundation import SettingsFlash
    f = SettingsFlash()

    try:
        from pincodes import PinAttempt

        common.pa = PinAttempt()
        common.pa.setup(b'')
    except RuntimeError as e:
        print("Secure Element Problem: %r" % e)


    # Setup the startup task
    common.loop.create_task(startup())

    # Setup check for automatic screen brightness control
    # Not used at this time
    # common.loop.create_task(update_ambient_screen_brightness())

    # Setup check to read battery level and put it in common.battery_level
    common.loop.create_task(update_battery_level())

    # Setup check for auto shutdown
    common.loop.create_task(check_auto_shutdown())

    # Setup check to read battery level and put it in common.battery_level
    common.loop.create_task(demo_loop())

    gc.collect()

    print('Available RAM after init = {}'.format(gc.mem_free()))

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


go()
