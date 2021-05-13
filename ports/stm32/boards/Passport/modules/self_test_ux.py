# SPDX-FileCopyrightText: 2021 Foundation Devices, Inc. <hello@foundationdevices.com>
# SPDX-License-Identifier: GPL-3.0-or-later
#
# self_test_ux.py - Self test UX
#

from common import system
from utils import UXStateMachine
from ux import ux_show_text_as_ur, ux_keypad_test, ux_scan_qr_code, ux_show_story, ux_draw_alignment_grid
from data_codecs.qr_type import QRType

class SelfTestUX(UXStateMachine):

    def __init__(self):
        # States
        self.SHOW_SERIAL_NUMBER = 1
        self.KEYPAD_TEST = 2
        self.CAMERA_TEST = 3
        self.CAMERA_TEST_RESULT = 4
        self.SCREEN_ALIGNMENT = 5
        self.qr_data = None

        # print('SelfTestUX init')
        super().__init__(self.SHOW_SERIAL_NUMBER)

    async def show(self):
        while True:
            # print('show: state={}'.format(self.state))
            if self.state == self.SHOW_SERIAL_NUMBER:
                serial = system.get_serial_number()
                result = await ux_show_text_as_ur(title='Serial Num.', qr_text=serial, qr_type=QRType.QR, msg=serial,
                    right_btn='NEXT') # If right_btn is specified, then RESIZE doesn't appear/work, which is fine here
                if result == 'x':
                    return
                else:
                    self.goto(self.KEYPAD_TEST)

            elif self.state == self.KEYPAD_TEST:
                # print('Keypad Test!')
                result = await ux_keypad_test()
                if result == 'x':
                    self.goto(self.SHOW_SERIAL_NUMBER)
                else:
                    self.goto(self.SCREEN_ALIGNMENT)

            elif self.state == self.SCREEN_ALIGNMENT:
                result = await ux_draw_alignment_grid(title='Align Screen')
                if result == 'x':
                    self.goto(self.KEYPAD_TEST)
                else:
                    self.goto(self.CAMERA_TEST)

            elif self.state == self.CAMERA_TEST:
                # print('Camera Test!')
                system.turbo(True)
                self.qr_data = await ux_scan_qr_code('Camera Test')
                # print('qr_data=|{}|'.format(self.qr_data))
                system.turbo(False)
                self.goto(self.CAMERA_TEST_RESULT)

            elif self.state == self.CAMERA_TEST_RESULT:
                if self.qr_data == None:
                    result = await ux_show_story('No QR code scanned.', right_btn='RETRY')
                    if result == 'x':
                        self.goto(self.SCREEN_ALIGNMENT)
                    else:
                        self.goto(self.CAMERA_TEST)
                else:
                    # Show the data - The QR code used in the factory starts with "Camera Test Passed!"
                    result = await ux_show_story(self.qr_data, right_btn='DONE')
                    if result == 'x':
                        self.goto(self.SCREEN_ALIGNMENT)
                    else:
                        return
