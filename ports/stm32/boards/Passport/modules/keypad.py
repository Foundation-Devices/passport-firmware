# SPDX-FileCopyrightText: 2020 Foundation Devices, Inc. <hello@foundationdevices.com>
# SPDX-License-Identifier: GPL-3.0-or-later
#
# keypad.py
#
# Get keycodes from the keypad device driver (they are in a queue)
# and translate them into the required format for KeyInputHandler.
#

from foundation import Keypad as _Keypad
import utime
import common
from utils import save_qr_code_image


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
        self.injected_keys = []

    def get_event(self):
        if len(self.injected_keys) > 0:
            keycode = self.injected_keys.pop(0)
        else:
            keycode = self.keypad.get_keycode()

        if keycode == None:
            return None, None

        # Update activity time to defer idle timeout
        common.last_activity_time = utime.ticks_ms()

        event = self.keycode_to_event(keycode)

        # Handle screenshots and snapshots
        if common.screenshot_mode_enabled:
            (key, is_down) = event
            if key == '#' and is_down:
                # print('SCREENSHOT!')
                common.dis.screenshot()
        elif common.snapshot_mode_enabled:
            (key, is_down) = event
            if key == '#' and is_down:
                # print('SNAPSHOT! SAY CHEESE!')
                common.dis.snapshot()
                save_qr_code_image(common.qr_buf)


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

    def inject(self, key, is_down=None):
        for code,val in self.key_id_dict.items():
            if key == val:
                if is_down == None:
                    # Inject both down and up events
                    self.injected_keys.append(code | 0x80)  # down
                    self.injected_keys.append(code)         # up
                elif is_down == True:
                    self.injected_keys.append(code | 0x80)  # down
                else:
                    self.injected_keys.append(code)         # up
                return

        # If not found, just do nothing

    def clear_keys(self):
        # Clear out any injected keys
        self.injected_keys = []

        # Read keys until nothing left
        while True:
            keycode = self.keypad.get_keycode()
            if keycode == None:
                return
