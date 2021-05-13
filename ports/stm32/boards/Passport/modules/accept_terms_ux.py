# SPDX-FileCopyrightText: 2020 Foundation Devices, Inc. <hello@foundationdevices.com>
# SPDX-License-Identifier: GPL-3.0-or-later
#
# login_ux.py - UX related to PIN code entry/login.
#
# NOTE: Mark3 hardware does not support secondary wallet concept.
#

from common import settings
from utils import UXStateMachine
from ux import ux_show_story, ux_shutdown, ux_confirm, ux_show_text_as_ur
from data_codecs.qr_type import QRType

# Separate PIN state machines to keep the logic cleaner in each and make it easier to change messaging in each

class AcceptTermsUX(UXStateMachine):

    def __init__(self):
        # States
        self.INTRO = 1
        self.SHOW_URL_QR = 2
        self.TERMS_INFO = 3
        self.CONFIRM_TERMS = 4

        initial_state = self.INTRO

        # print('AcceptTermsUX init')
        super().__init__(initial_state)


    async def show(self):
        while True:
            # print('show: state={}'.format(self.state))
            if self.state == self.INTRO:
                # Already accepted
                if settings.get('terms_ok'):
                    return

                ch = await ux_show_story("""\
Congratulations on taking the first step towards sovereignty and ownership over your Bitcoin!

Open the setup guide by scanning the QR code on the following screen.""",
                    left_btn='SHUTDOWN', right_btn='CONTINUE', scroll_label='MORE')

                if ch == 'x':
                    # We only return from here if the user chose to not shutdown
                    await ux_shutdown()
                elif ch == 'y':
                    self.goto(self.SHOW_URL_QR)

            elif self.state == self.SHOW_URL_QR:
                # Show QR code
                url = 'https://foundationdevices.com/setup'
                result = await ux_show_text_as_ur(title='Setup Guide', qr_text=url, qr_type=QRType.QR, left_btn='BACK', right_btn='NEXT')
                if result == 'x':
                    self.goto_prev()
                else:
                    self.goto(self.TERMS_INFO)

            elif self.state == self.TERMS_INFO:
                ch = await ux_show_story("Please accept our Terms of Use. You can read the full terms in the Passport setup guide.",
                    left_btn='BACK', right_btn='CONTINUE', scroll_label='MORE', center=True, center_vertically=True)
                if ch == 'x':
                    self.goto_prev()
                elif ch == 'y':
                    self.goto(self.CONFIRM_TERMS)

            elif self.state == self.CONFIRM_TERMS:
                accepted_terms = await ux_confirm('I confirm that I have read and accept the Terms of Use.',
                    negative_btn='BACK', positive_btn='I CONFIRM')
                if accepted_terms:
                    # Note fact they accepted the terms. Annoying to ask user more than once.
                    settings.set('terms_ok', 1)
                    return
                else:
                    self.goto_prev()
