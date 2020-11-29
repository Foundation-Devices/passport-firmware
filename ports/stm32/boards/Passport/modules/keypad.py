# SPDX-FileCopyrightText: 2020 Foundation Devices, Inc.  <hello@foundationdevices.com>
# SPDX-License-Identifier: GPL-3.0-or-later
#
# keypad.py
#
# Get keycodes from the keypad device driver (they are in a queue)
# and translate them into the required format for KeyInputHandler.
#

from foundation import Keypad as _Keypad
import utime

class Keypad:
    def __init__(self):
        self.keypad = _Keypad()
        self.key_id_dict = {
            112: '1',
            103: '2',
            111: '3',
            114: '4',
            109: '5',
            110: '6',
            107: '7',
            108: '8',
            106: '9',
            97: '0',
            104: 'u',
            101: 'd',
            102: 'l',
            100: 'r',
            113: 'x',
            99: 'y',
            98: '*',
            105: '#',
        }
        self.last_event_time = utime.ticks_ms()

    def get_event(self):
        keycode = self.keypad.get_keycode()
        if keycode == None:
            return None, None
        event = self.keycode_to_event(keycode)
        self.last_event_time = utime.ticks_ms()
        return event

    def keycode_to_event(self, keycode):
        key_id = keycode & 0x7F
        key = self.key_id_dict.get(key_id, None)
        # print('keycode={} key={}'.format(keycode, key))
        is_down = keycode & 0x80 == 0x80
        return (key, is_down)

    def get_last_event_time(self):
        return self.last_event_time
