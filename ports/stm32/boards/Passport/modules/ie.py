# SPDX-FileCopyrightText: 2021 Foundation Devices, Inc. <hello@foundationdevices.com>
# SPDX-License-Identifier: GPL-3.0-or-later
#
# ie.py - Web browser
#

from uasyncio import sleep_ms

async def show_browser(*a):
    from common import dis, system
    from display import Display, FontSmall

    system.turbo(True)

    # Show the logo and the loading screen
    dis.clear()
    dis.draw_header('IE9')
    logo_w, logo_h = dis.icon_size('ie_logo')
    dis.icon(None, Display.HALF_HEIGHT - logo_h//2 - 5, 'ie_logo')

    y = Display.HEIGHT - 68
    dis.text(None,  y, 'Loading browser...', font=FontSmall)

    dis.show()

    for i in range(100):
        system.progress_bar(i)
        await sleep_ms(30)

    # Just kidding!
    dis.clear()
    dis.draw_header('IE9')
    dis.icon(None, Display.HALF_HEIGHT - logo_h//2 - 5, 'ie_logo')
    dis.text(None,  y, 'Just kidding!', font=FontSmall)
    dis.show()
    await sleep_ms(2000)

    system.turbo(False)

# This doesn't do anything obviously since Passport is airgapped!
async def handle_http(url):
    await show_browser()
