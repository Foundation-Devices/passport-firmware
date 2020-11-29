# SPDX-FileCopyrightText: 2020 Foundation Devices, Inc.  <hello@foundationdevices.com>
# SPDX-License-Identifier: GPL-3.0-or-later
#
# SPDX-FileCopyrightText: 2018 Coinkite, Inc.  <coldcardwallet.com>
# SPDX-License-Identifier: GPL-3.0-only
#
# (c) Copyright 2018 by Coinkite Inc. This file is part of Coldcard <coldcardwallet.com>
# and is covered by GPLv3 license found in COPYING.
#
# choosers.py - various interactive menus for setting config values.
#
from common import settings


def max_fee_chooser():
    from psbt import DEFAULT_MAX_FEE_PERCENTAGE
    limit = settings.get('fee_limit', DEFAULT_MAX_FEE_PERCENTAGE)

    ch = ['No Limit', '10%', '25%', '50%']
    va = [-1, 10, 25, 50]

    try:
        which = va.index(limit)
    except ValueError:
        which = 0

    def set(idx, text):
        settings.set('fee_limit', va[idx])

    return which, ch, set


def idle_timeout_chooser():
    from ux import DEFAULT_IDLE_TIMEOUT

    timeout = settings.get('idle_to', DEFAULT_IDLE_TIMEOUT)        # in seconds

    ch = ['  5 minutes',
          ' 15 minutes',
          ' 30 minutes',
          ' 60 minutes']
    va = [5*60, 15*60, 30*60, 60*60]

    try:
        which = va.index(timeout)
    except ValueError:
        which = 0

    def set_idle_timeout(idx, text):
        settings.set('idle_to', va[idx])

    return which, ch, set_idle_timeout


def countdown_chooser():
    # Login countdown length, stored in minutes
    #
    ch = ['Disabled',
          ' 5 minutes',
          '15 minutes',
          '30 minutes',
          ' 1 hour',
          ' 2 hours',
          ' 4 hours',
          ' 8 hours',
          '12 hours',
          '24 hours',
          '48 hours',
          ' 3 days',
          ' 1 week',
          '28 days later',
          ]
    va = [0, 5, 15, 30, 60, 2*60, 4*60, 8*60, 12 *
          60, 24*60, 48*60, 72*60, 7*24*60, 28*24*60]
    assert len(ch) == len(va)

    timeout = settings.get('lgto', 0)        # in minutes
    try:
        which = va.index(timeout)
    except ValueError:
        which = 0

    def set_login_countdown(idx, text):
        settings.set('lgto', va[idx])

    return which, ch, set_login_countdown


def chain_chooser():
    from chains import AllChains

    chain = settings.get('chain', 'BTC')

    ch = [(i.ctype, i.menu_name or i.name) for i in AllChains]

    # find index of current choice
    try:
        which = [n for n, (k, v) in enumerate(ch) if k == chain][0]
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

    return which, [t for _, t in ch], set_chain


def brightness_chooser():
    screen_brightness = settings.get('screen_brightness', 100)

    ch = ['Off', '25%', '50%', '75%', '100%']
    va = [0, 25, 50, 75, 100]

    try:
        which = va.index(screen_brightness)
    except ValueError:
        which = 100

    def set(idx, text):
        from common import dis
        settings.set('screen_brightness', va[idx])
        dis.set_brightness(va[idx])

    return which, ch, set

# EOF
