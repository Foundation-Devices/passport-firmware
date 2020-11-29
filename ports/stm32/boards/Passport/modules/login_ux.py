# SPDX-FileCopyrightText: 2020 Foundation Devices, Inc.  <hello@foundationdevices.com>
# SPDX-License-Identifier: GPL-3.0-or-later
#
# SPDX-FileCopyrightText: 2018 Coinkite, Inc.  <coldcardwallet.com>
# SPDX-License-Identifier: GPL-3.0-only
#
# (c) Copyright 2018 by Coinkite Inc. This file is part of Coldcard <coldcardwallet.com>
# and is covered by GPLv3 license found in COPYING.
#
# login.py - UX related to PIN code entry/login.
#
# NOTE: Mark3 hardware does not support secondary wallet concept.
#
import pincodes
import version
from callgate import show_logout
from display import Display, FontLarge, FontSmall, FontTiny
from common import dis, pa
from uasyncio import sleep_ms
from utils import pretty_delay, UXStateMachine
from ux import (KeyInputHandler, ux_show_story, ux_show_word_list, ux_enter_pin, ux_shutdown)
import utime

MAX_PIN_PART_LEN = 6
MIN_PIN_PART_LEN = 2


# Separate state machines to keep
class LoginUX(UXStateMachine):

    def __init__(self):
        # States
        self.ENTER_PIN1 = 1
        self.VERIFY_ANTI_PHISHING_WORDS = 2
        self.VERIFY_ANTI_PHISHING_WORDS_FAILED = 3
        self.ENTER_PIN2 = 4
        self.CHECK_PIN = 5
        self.PIN_ATTEMPT_FAILED = 6
        self.SHOW_BRICK_MESSAGE = 7

        print('LoginUX init: pa={}'.format(pa))
        super().__init__(self.ENTER_PIN1)

        # Different initial state if we are a brick
        # TODO: Why does this say no attempts left?
        # if not pa.attempts_left:
        #     self.state = self.SHOW_BRICK_MESSAGE

        self.pin1 = None
        self.pin2 = None
        self.pin = None


    async def show(self):
        while True:
            print('show: state={}'.format(self.state))
            if self.state == self.ENTER_PIN1:
                self.pin1 = await ux_enter_pin(title='Security Code', heading='Enter Security Code')
                if self.pin1 != None and len(self.pin1) >= MIN_PIN_PART_LEN:
                    self.goto(self.VERIFY_ANTI_PHISHING_WORDS)

            elif self.state == self.VERIFY_ANTI_PHISHING_WORDS:
                # TODO: Wrap this function with foundation.busy_bar.show() .hide() sinve this takes a while
                words = pincodes.PinAttempt.anti_phishing_words(self.pin1.encode())

                result = await ux_show_word_list('Security Words', words, heading1='Do you recognize', heading2='these words?')
                if result == 'y':
                    self.goto(self.ENTER_PIN2)
                else:
                    self.goto(self.VERIFY_ANTI_PHISHING_WORDS_FAILED)

            elif self.state == self.VERIFY_ANTI_PHISHING_WORDS_FAILED:
                result = await ux_show_story('''\
                        If the Security Words do not match, then you either entered the incorrect PIN or your Passport may have been tampered with.''', left_btn='SHUTDOWN', right_btn='RETRY')
                if result == 'x':
                    await ux_shutdown()
                elif result == 'y':
                    self.pin1 = None
                    self.goto(self.ENTER_PIN1)

            elif self.state == self.ENTER_PIN2:
                self.pin2 = await ux_enter_pin(title='Login PIN', heading='Enter Login PIN')
                if self.pin2 != None and len(self.pin2) >= MIN_PIN_PART_LEN:
                    self.pin = self.pin1 + self.pin2
                    self.goto(self.CHECK_PIN)

            elif self.state == self.CHECK_PIN:
                pa.setup(self.pin)
                try:
                    # TODO: Wrap this function with foundation.busy_bar.show() .hide() sinve this takes a while
                    #       Put the hide() in a finally block
                    if pa.login():
                        # PIN is correct!
                        # NOTE: We never return from this function unless the PIN is correct.
                        return
                except RuntimeError as err:
                    # TODO: This means the device is bricked - add appropriate handling
                    self.goto(self.PIN_ATTEMPT_FAILED)
                except BootloaderError as err:
                    self.goto(self.PIN_ATTEMPT_FAILED)

            elif self.state == self.PIN_ATTEMPT_FAILED:
                if pa.attempts_left <= 10:
                    # TODO: Should we display the PIN here like coldcard did?  Seems sketch.
                    result = await ux_show_story(
                        'You have {} attempts remaining before this Passport IS BRICKED FOREVER.\n\nCheck and double-check your entry:\n\n  {}'.format(pa.attempts_left, self.pin),
                        title="WARNING",
                        left_btn='SHUTDOWN',
                        right_btn='RETRY',
                        center_vertically=True,
                        center=True)
                else:
                    result = await ux_show_story(
                        'You have {} attempts remaining.'.format(pa.attempts_left),
                        title="INCORRECT PIN",
                        left_btn='SHUTDOWN',
                        right_btn='RETRY',
                        center_vertically=True,
                        center=True)
                if result == 'y':
                    self.pin1 = None
                    self.pin2 = None
                    self.pin = None
                    self.goto(self.ENTER_PIN1)
                elif result == 'x':
                    self.goto(self.CONFIRM_SHUTDOWN)

                pass

            elif self.state == self.SHOW_BRICK_MESSAGE:
                msg = '''After %d failed PIN attempts this Passport is locked forever. \
By design, there is no way to recover the device, and its contents \
are now forever inaccessible.

Restore your seed words onto a new Passport.''' % pa.num_fails

                result = await ux_show_story(msg, title='I Am Brick!', left_btn='SHUTDOWN', right_btn='-')
                if result == 'x':
                    self.goto(self.CONFIRM_SHUTDOWN)
            else:
                while True:
                    print('ERROR: Should never hit this else case!')
                    from uasyncio import sleep_ms
                    await sleep_ms(1000)


class EnterNewPinUX(UXStateMachine):

    def __init__(self):
        # States
        self.ENTER_PIN1 = 1
        self.SHOW_ANTI_PHISHING_WORDS = 2
        self.ENTER_PIN2 = 3

        super().__init__(self.ENTER_PIN1)
        self.pin1 = [None, None]
        self.pin2 = [None, None]
        self.round = 0

    def is_verifying(self):
        return self.round == 1

    def pin1_matches(self):
        return self.pin1[0] == self.pin1[1]

    def pin2_matches(self):
        return self.pin2[0] == self.pin2[1]

    def is_pin_valid(self, pin):
        return pin and len(pin) >= MIN_PIN_PART_LEN

    async def show(self):
        while True:
            if self.state == self.ENTER_PIN1:
                heading = '{} Security Code'.format('Reenter' if self.is_verifying() else 'Enter')
                self.pin1[self.round] = await ux_enter_pin(title='Security Code', heading=heading)
                if self.is_pin_valid(self.pin1[self.round]):
                    if self.is_verifying():
                        if self.pin1_matches():
                            self.goto(self.ENTER_PIN2)
                            #self.goto(self.SHOW_ANTI_PHISHING_WORDS)
                        else:
                            result = await ux_show_story('Security Code did not match.  Please try again', title="PIN Mismatch", left_btn="SHUTDOWN", right_btn="RETRY")
                            if result == 'y':
                                self.pin1[self.round] = None
                            elif result == 'x':
                                await ux_shutdown()

                    else:
                        self.goto(self.SHOW_ANTI_PHISHING_WORDS)
                else:
                    # TODO: Error message that PIN is too short - Can we disable the right button until it's long enough?
                    pass

            elif self.state == self.SHOW_ANTI_PHISHING_WORDS:
                words = pincodes.PinAttempt.anti_phishing_words(self.pin1[self.round].encode())
                result = await ux_show_word_list('Security Words', words, heading1='Remember these', heading2='Security Words:', left_btn='BACK', right_btn='OK')
                if result == 'x':
                    self.pin1[self.round] = None
                    self.goto(self.ENTER_PIN1)
                else:
                    self.goto(self.ENTER_PIN2)

            elif self.state == self.ENTER_PIN2:
                heading = '{} Login PIN'.format('Reenter' if self.is_verifying() else 'Enter')
                self.pin2[self.round] = await ux_enter_pin(title='Login PIN', heading=heading)
                if self.pin2[self.round] == None:
                    self.goto(self.ENTER_PIN1)
                    continue

                if self.is_pin_valid(self.pin2[self.round]):
                    if self.is_verifying():
                        if self.pin2_matches():
                            self.pin = self.pin1[0] + self.pin2[0]
                            print('Entered and verified PIN is {}'.format(self.pin))
                            return
                        else:
                            result = await ux_show_story('Login PIN did not match.  Please try again', title="PIN Mismatch", left_btn="SHUTDOWN", right_btn="RETRY")
                            if result == 'y':
                                self.pin2[self.round] = None
                            elif result == 'x':
                                await ux_shutdown()
                    else:
                        # Go back to have the user reenter both PINs and verify that they match
                        self.round = 1
                        self.goto(self.ENTER_PIN1)
                else:
                    # TODO: Error message that PIN is too short - Can we disable the right button until it's long enough?
                    pass

            else:
                while True:
                    print('ERROR: Should never hit this else case!')
                    from uasyncio import sleep_ms
                    await sleep_ms(1000)


class ChangePINUX(UXStateMachine):

    def __init__(self):
        # States
        self.ENTER_PIN1 = 1
        self.ENTER_PIN2 = 2
        self.SHOW_ANTI_PHISHING_WORDS = 3
        self.CHANGE_PIN = 4
        self.CHANGE_FAILED = 5
        self.CHANGE_SUCCESS = 6

        print('LoginUX init: pa={}'.format(pa))
        super().__init__(self.ENTER_PIN1)

        # Different initial state if we are a brick
        # TODO: Why does this say no attempts left?
        # if not pa.attempts_left:
        #     self.state = self.SHOW_BRICK_MESSAGE

        self.pin1 = [None, None]
        self.pin2 = [None, None]
        self.round = 0  # Ask for old PIN first, then new


    async def show(self):
        while True:
            print('show: state={}'.format(self.state))
            if self.state == self.ENTER_PIN1:
                self.pin1[self.round] = await ux_enter_pin(title='Security Code', heading='{} Security Code'.format('Old' if self.round == 0 else 'New'))
                if self.pin1[self.round] != None and len(self.pin1[self.round]) >= MIN_PIN_PART_LEN:
                    if self.round == 1:
                        self.goto(self.SHOW_ANTI_PHISHING_WORDS)
                    else:
                        self.goto(self.ENTER_PIN2)

            elif self.state == self.SHOW_ANTI_PHISHING_WORDS:
                start = utime.ticks_us()
                words = pincodes.PinAttempt.anti_phishing_words(self.pin1[self.round].encode())
                end = utime.ticks_us()
                result = await ux_show_word_list('Security Words', words, heading1='Remember these', heading2='Security Words:', left_btn='BACK', right_btn='OK')
                if result == 'x':
                    self.pin1[self.round] = None
                    self.goto(self.ENTER_PIN1)
                else:
                    self.goto(self.ENTER_PIN2)

            elif self.state == self.ENTER_PIN2:
                self.pin2[self.round] = await ux_enter_pin(title='Login PIN', heading='{} Login PIN'.format('Old' if self.round == 0 else 'New'))
                if self.pin2[self.round] != None and len(self.pin2[self.round]) >= MIN_PIN_PART_LEN:
                    if self.round == 0:
                        self.round = 1
                        self.goto(self.ENTER_PIN1)
                    else:
                        self.goto(self.CHANGE_PIN)

            elif self.state == self.CHANGE_PIN:
                try:
                    print('pin1={} pin2={}'.format(self.pin1, self.pin2))
                    args = {}
                    args['old_pin'] = (self.pin1[0] + self.pin2[0]).encode()
                    args['new_pin'] = (self.pin1[1] + self.pin2[1]).encode()
                    print('pa.change: args={}'.format(args))
                    pa.change(**args)
                    self.goto(self.CHANGE_SUCCESS)
                except Exception as err:
                    print('err={}'.format(err))
                    self.goto(self.CHANGE_FAILED)

            elif self.state == self.CHANGE_FAILED:
                result = await ux_show_story('Unable to change PIN.  The old PIN you entered was incorrect.', title='PIN Error', right_btn='RETRY')
                if result == 'y':
                    self.pin1 = [None, None]
                    self.pin2 = [None, None]
                    self.round = 0
                    self.goto(self.ENTER_PIN1)
                else:
                    return

            elif self.state == self.CHANGE_SUCCESS:
                dis.fullscreen('PIN changed')
                utime.sleep(1)
                return

            else:
                while True:
                    print('ERROR: Should never hit this else case!')
                    from uasyncio import sleep_ms
                    await sleep_ms(1000)
