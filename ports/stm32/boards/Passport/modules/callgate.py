# SPDX-FileCopyrightText: 2020 Foundation Devices, Inc.  <hello@foundationdevices.com>
# SPDX-License-Identifier: GPL-3.0-or-later
#
# SPDX-FileCopyrightText: 2018 Coinkite, Inc.  <coldcardwallet.com>
# SPDX-License-Identifier: GPL-3.0-only
#
# (c) Copyright 2018 by Coinkite Inc. This file is part of Coldcard <coldcardwallet.com>
# and is covered by GPLv3 license found in COPYING.
#
# callgate.py - Wrapper around system.dispatch() methods

from se_commands import *
from common import system

def get_bootloader_version():
    # version string and related details
    # something like:   ('1.0.0', [('time', '20180220.092345'), ('git', 'master@f8d1758')])
    rv = bytearray(64)
    ln = system.dispatch(0, rv, 0)
    ver, *args = str(rv[0:ln], 'utf8').split(' ')
    return ver, [tuple(i.split('=', 1)) for i in args]


def get_firmware_hash(salt=0):
    # salted hash over code
    rv = bytearray(32)
    system.dispatch(CMD_GET_FIRMWARE_HASH, rv, salt)
    return rv


def enter_dfu(msg=0):
    # enter DFU while showing a message
    #   0 = normal DFU
    #   1 = downgrade attack detected
    #   2 = blankish
    #   3 = i am bricked
    #
    system.dispatch(CMD_UPGRADE_FIRMWARE, msg)


def show_logout(dont_clear=0):
    # wipe memory and die, shows standard message
    # dont_clear=1 => don't clear OLED
    # 2=> restart system after wipe
    system.dispatch(CMD_RESET, dont_clear)


def get_genuine():
    system.dispatch(CMD_LED_CONTROL, None, LED_READ)


def clear_genuine():
    system.dispatch(CMD_LED_CONTROL, None, LED_RED)


def set_genuine():
    # does checksum over firmware, and might set green
    return system.dispatch(CMD_LED_CONTROL, None, LED_ATTEMPT_TO_SET_GREEN)


# Fill buf with random bytes
def fill_random(buf):
    system.dispatch(CMD_GET_RANDOM_BYTES, buf, 0)


def get_is_bricked():
    # see if we are a brick?
    return system.dispatch(CMD_IS_BRICKED, None, 0) != 0


def get_firmware_highwater():
    arg = bytearray(8)
    system.dispatch(CMD_FIRMWARE_CONTROL, arg, GET_MIN_FIRMWARE_VERSION)
    return arg


def set_firmware_highwater(ts):
    arg = bytearray(ts)
    return system.dispatch(CMD_FIRMWARE_CONTROL, arg, UPDATE_HIGH_WATERMARK)


def get_anti_phishing_words(pin_buf):
    return system.dispatch(CMD_GET_ANTI_PHISHING_WORDS, pin_buf, len(pin_buf))


def get_supply_chain_validation_words(buf):
    return system.dispatch(CMD_GET_SUPPLY_CHAIN_VALIDATION_WORDS, buf, len(buf))

# EOF
