# SPDX-FileCopyrightText: 2021 Foundation Devices, Inc. <hello@foundationdevices.com>
# SPDX-License-Identifier: GPL-3.0-or-later
#
# self_test_ux.py - Self test UX
#

from common import system
from utils import UXStateMachine, needs_microsd
from ux import ux_show_text_as_ur, ux_keypad_test, ux_scan_qr_code, ux_show_story, ux_draw_alignment_grid
from data_codecs.qr_type import QRType

async def microsd_test():
    import uos
    import os
    from files import CardSlot, CardMissingError
    from utils import file_exists

    msg = 'The Times 03/Jan/2009 Chancellor on brink of second bailout for banks'

    while True:
        try:
            with CardSlot() as card:
                filename = '{}/microsd-test.txt'.format(card.get_sd_root())

                if file_exists(filename):
                    os.remove(filename)

                with open(filename, 'wt') as fd:
                    fd.write(msg)

                with open(filename, 'rt') as fd:
                    read_msg = fd.read()

                    if read_msg != msg:
                        await ux_show_story('The text read back from the microSD card did not match that written. Read:\n\n {}'.format(read_msg), title='Error')
                        return False

                    os.remove(filename)
                    await ux_show_story('microSD card is working properly!', title='microSD Test', center=True, center_vertically=True)
                    return True

        except CardMissingError:
            result = await needs_microsd()
            if result == 'x':
                return False

        except Exception as e:
            await ux_show_story('{}'.format(e), title='Exception')
            return False


class SelfTestUX(UXStateMachine):

    def __init__(self):
        # States
        self.KEYPAD_TEST = 1
        self.CAMERA_TEST = 2
        self.CAMERA_TEST_RESULT = 3
        self.SCREEN_ALIGNMENT = 4
        self.MICROSD_TEST = 5
        self.TESTS_COMPLETE = 6
        self.qr_data = None

        # print('SelfTestUX init')
        super().__init__(self.KEYPAD_TEST)

    async def show(self):
        while True:
            if self.state == self.KEYPAD_TEST:
                # print('Keypad Test!')
                result = await ux_keypad_test()
                if result == 'x':
                    self.goto_prev()
                else:
                    self.goto(self.SCREEN_ALIGNMENT)

            elif self.state == self.SCREEN_ALIGNMENT:
                result = await ux_draw_alignment_grid(title='Align Screen')
                if result == 'x':
                    self.goto_prev()
                else:
                    self.goto(self.CAMERA_TEST)

            elif self.state == self.CAMERA_TEST:
                # print('Camera Test!')
                system.turbo(True)
                self.qr_data = await ux_scan_qr_code('Camera Test')
                # print('qr_data=|{}|'.format(self.qr_data))
                system.turbo(False)
                self.goto(self.CAMERA_TEST_RESULT, save_curr=False)

            elif self.state == self.CAMERA_TEST_RESULT:
                if self.qr_data == None:
                    result = await ux_show_story('No QR code scanned.', right_btn='RETRY')
                    if result == 'x':
                        self.goto_prev()
                    else:
                        self.goto(self.CAMERA_TEST)
                else:
                    # Show the data - The QR code used in the factory starts with "Camera Test Passed!"
                    result = await ux_show_story(self.qr_data, right_btn='DONE')
                    if result == 'x':
                        self.goto_prev()
                    else:
                        self.goto(self.MICROSD_TEST)

            elif self.state == self.MICROSD_TEST:
                    # Describe the microSD test
                    result = await ux_show_story('This test will exercise the read/write features of the microSD card.', title='microSD Test', right_btn='START', center=True, center_vertically=True)
                    if result == 'x':
                        self.goto_prev()
                        continue

                    if await microsd_test():
                        self.goto(self.TESTS_COMPLETE)

            elif self.state == self.TESTS_COMPLETE:
                    result = await ux_show_story('All tests complete!', title='Complete', right_btn='SHUTDOWN', center=True, center_vertically=True)
                    if result == 'x':
                        self.goto_prev()
                    else:
                        system.shutdown()
