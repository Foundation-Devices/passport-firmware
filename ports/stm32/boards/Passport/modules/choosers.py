# SPDX-FileCopyrightText: 2020 Foundation Devices, Inc. <hello@foundationdevices.com>
# SPDX-License-Identifier: GPL-3.0-or-later
#
# SPDX-FileCopyrightText: 2018 Coinkite, Inc. <coldcardwallet.com>
# SPDX-License-Identifier: GPL-3.0-only
#
# (c) Copyright 2018 by Coinkite Inc. This file is part of Coldcard <coldcardwallet.com>
# and is covered by GPLv3 license found in COPYING.
#
# choosers.py - various interactive menus for setting config values.
#
from common import settings


def shutdown_timeout_chooser():
    DEFAULT_SHUTDOWN_TIMEOUT = (2*60) # 2 minutes

    timeout = settings.get('shutdown_timeout', DEFAULT_SHUTDOWN_TIMEOUT)        # in seconds

    ch = [' 1 minute',
          ' 2 minutes',
          ' 5 minutes',
          '15 minutes',
          '30 minutes',
          '60 minutes',
          'Never']
    va = [1*60, 2*60, 5*60, 15*60, 30*60, 60*60, 0]

    try:
        which = va.index(timeout)
    except ValueError:
        which = 1

    def set_shutdown_timeout(idx, text):
        settings.set('shutdown_timeout', va[idx])

    return which, ch, set_shutdown_timeout


def brightness_chooser():
    screen_brightness = settings.get('screen_brightness', 100)

    ch = ['Off', '25%', '50%', '75%', '100%'] # , 'Automatic']
    va = [0, 25, 50, 75, 100] # , 999]

    try:
        which = va.index(screen_brightness)
    except ValueError:
        which = 4

    def set(idx, text):
        from common import dis
        dis.set_brightness(va[idx])
        settings.set('screen_brightness', va[idx])

    return which, ch, set


def enable_passphrase_chooser():
    # Should the Passphrase menu be enabled in the main menu?
    ch = ['Disabled', 'Enabled']
    va = [False, True]
    assert len(ch) == len(va)

    enable_passphrase = settings.get('enable_passphrase', False)
    try:
        which = va.index(enable_passphrase)
    except ValueError:
        which = 0

    def set_enable_passphrase(idx, text):
        settings.set('enable_passphrase', va[idx])

    return which, ch, set_enable_passphrase

def chain_chooser():
    from chains import AllChains

    chain = settings.get('chain', 'BTC')

    ch = [(i.ctype, i.menu_name or i.name) for i in AllChains ]

    # find index of current choice
    try:
        which = [n for n, (k,v) in enumerate(ch) if k == chain][0]
    except IndexError:
        which = 0

    def set_chain(idx, text):
        val = ch[idx][0]
        assert ch[idx][1] == text
        settings.set('chain', val)

        try:
            # update xpub stored in settings
            import stash
            with stash.SensitiveValues() as sv:
                sv.capture_xpub()
        except ValueError:
            # no secrets yet, not an error
            pass

    return which, [t for _,t in ch], set_chain
    
def units_chooser():
    DEFAULT_UNITS = "BTC"

    units = settings.get('units', DEFAULT_UNITS)

    ch = ['BTC',
          'sats']
    val = ['BTC',
          'sats']

    try:
        which = val.index(units)
    except ValueError:
        which = 1

    def set_units(idx, text):
        settings.set('units', val[idx])

    return which, ch, set_units

# EOF
