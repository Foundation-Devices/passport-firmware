# SPDX-FileCopyrightText: 2020 Foundation Devices, Inc. <hello@foundationdevices.com>
# SPDX-License-Identifier: GPL-3.0-or-later
#
# login_ux.py - UX related to PIN code entry/login.
#
# NOTE: Mark3 hardware does not support secondary wallet concept.
#

import version
from display import Display, FontSmall, FontTiny
from common import dis, pa, system, settings
from uasyncio import sleep_ms
from utils import UXStateMachine
from ux import KeyInputHandler, ux_show_story, ux_show_word_list, ux_enter_pin, ux_shutdown, ux_confirm, ux_enter_text
from pincodes import BootloaderError
import utime
from constants import SECURITY_WORDS_ENABLED_DEFAULT

# Separate PIN state machines to keep the logic cleaner in each and make it easier to change messaging in each

class LoginUX(UXStateMachine):

    def __init__(self, passphrase_entry_enabled=True):
        # States
        self.ENTER_PIN = 1
        self.CHECK_PIN = 2
        self.PIN_ATTEMPT_FAILED = 3
        self.SHOW_BRICK_MESSAGE = 4
        self.ENTER_PASSPHRASE = 5

        # Different initial state if we are a brick
        if pa.attempts_left == 0:
            initial_state = self.SHOW_BRICK_MESSAGE
        else:
            initial_state = self.ENTER_PIN

        # print('LoginUX init: pa={}'.format(pa))
        super().__init__(initial_state)

        self.pin = None
        self.security_words_enabled = settings.get('security_words_enabled', SECURITY_WORDS_ENABLED_DEFAULT)
        self.show_passphrase_entry = passphrase_entry_enabled

    async def show(self):
        while True:
            # print('show: state={}'.format(self.state))
            if self.state == self.ENTER_PIN:
                success, self.pin = await ux_enter_pin( title='Login',
                                                        heading='Enter PIN',
                                                        left_btn='SHUTDOWN',
                                                        security_words_enabled=self.security_words_enabled,
                                                        saved_pin=self.pin)
                if self.pin != None and success == True:
                    self.goto(self.CHECK_PIN)
                else:
                    await ux_shutdown()

            elif self.state == self.CHECK_PIN:
                try:
                    from common import dis
                    dis.fullscreen('Verifying PIN...')
                    system.show_busy_bar()
                    pa.setup(self.pin)
                    if pa.login():
                        # PIN is correct!
                        if self.show_passphrase_entry:
                            # NOTE: We never return from this function unless the PIN is correct.
                            enable_passphrase = settings.get('enable_passphrase', False)
                            if enable_passphrase:
                                self.goto(self.ENTER_PASSPHRASE)
                            else:
                                return
                        else:
                            return
                    else:
                        self.goto(self.PIN_ATTEMPT_FAILED)

                except RuntimeError as err:
                    system.hide_busy_bar()
                    self.goto(self.PIN_ATTEMPT_FAILED)
                except BootloaderError as err:
                    system.hide_busy_bar()
                    self.goto(self.PIN_ATTEMPT_FAILED)
                except Exception as err:
                    # print('Exception err={}'.format(err))
                    self.goto(self.PIN_ATTEMPT_FAILED)
                finally:
                    system.hide_busy_bar()

            elif self.state == self.PIN_ATTEMPT_FAILED:
                # Switch to bricked view if no more attempts
                if pa.attempts_left == 0:
                    self.goto(self.SHOW_BRICK_MESSAGE)
                    continue

                result = await ux_show_story(
                    'You have {} attempts remaining.'.format(pa.attempts_left),
                    title="Wrong PIN",
                    left_btn='SHUTDOWN',
                    right_btn='RETRY',
                    center_vertically=True,
                    center=True)

                if result == 'y':
                    self.pin = None
                    self.goto(self.ENTER_PIN)
                elif result == 'x':
                    await ux_shutdown()

            elif self.state == self.SHOW_BRICK_MESSAGE:
                msg = '''After %d failed PIN attempts, this Passport is now permanently disabled.

Restore a microSD backup or seed phrase onto a new Passport to recover your funds.''' % pa.num_fails

                result = await ux_show_story(msg, title='Error', left_btn='SHUTDOWN', right_btn='RESTART')
                if result == 'x':
                    await ux_shutdown()
                else:
                    import machine
                    machine.reset()

            elif self.state == self.ENTER_PASSPHRASE:
                    import sys
                    from seed import set_bip39_passphrase

                    passphrase = await ux_enter_text('Passphrase', label='Enter Passphrase', left_btn='NONE', right_btn='APPLY')
                    # print("Entered passphrase = {}".format(passphrase))

                    # if not await ux_confirm('Are you sure you want to apply the passphrase:\n\n{}'.format(passphrase)):
                    #     return

                    if passphrase != None and len(passphrase) > 0:
                        # Applying the passphrase takes a bit of time so show message
                        from common import dis
                        dis.fullscreen("Applying Passphrase...")

                        system.show_busy_bar()

                        try:
                            err = set_bip39_passphrase(passphrase)

                            if err:
                                await ux_show_story('Unable to apply passphrase.')
                                return

                        except BaseException as exc:
                            sys.print_exception(exc)

                        system.hide_busy_bar()
                    return


class EnterInitialPinUX(UXStateMachine):

    def __init__(self):
        # States
        self.ENTER_PIN = 1

        # print('EnterInitialPinUX init: pa={}'.format(pa))
        super().__init__(self.ENTER_PIN)
        self.pins = [None, None]  # PIN is entered twice for confirmation
        self.round = 0
        self.security_words_enabled = settings.get('security_words_enabled', SECURITY_WORDS_ENABLED_DEFAULT)

    def is_confirming(self):
        return self.round == 1

    def pins_match(self):
        return self.pins[0] == self.pins[1]

    def is_pin_valid(self, pin):
        return pin != None

    async def show(self):
        while True:
            if self.state == self.ENTER_PIN:
                heading = '{} PIN'.format('Confirm' if self.is_confirming() else 'Enter')
                success, self.pins[self.round] = await ux_enter_pin(title='Set PIN',
                                                            heading=heading,
                                                            left_btn='SHUTDOWN',
                                                            hide_attempt_counter=True,
                                                            is_new_pin=True,
                                                            security_words_enabled=self.security_words_enabled,
                                                            saved_pin=self.pins[self.round])
                if self.pins[self.round] == None or success == False:
                    await ux_shutdown()
                    continue

                if self.is_confirming():
                    if self.pins_match():
                        self.pin = self.pins[0]
                        # print('Entered and confirmed PIN is {}'.format(self.pin))
                        return
                    else:
                        result = await ux_show_story('PINs do not match. Please try again.', title="PIN Mismatch", left_btn="SHUTDOWN", right_btn="RETRY", center=True, center_vertically=True)
                        if result == 'y':
                            # Reset to initial state so PIN needs to be entered and confirmed again
                            # since we don't know if they messed up the first entry or the second one.
                            self.round = 0
                            self.pins[0] = None
                            self.pins[1] = None
                            continue
                        elif result == 'x':
                            await ux_shutdown()
                else:
                    # Have the user re-enter the PIN to confirm
                    self.round = 1


class ChangePinUX(UXStateMachine):

    def __init__(self):
        # States
        self.ENTER_OLD_PIN = 1
        self.ENTER_NEW_PIN = 2
        self.CHANGE_PIN = 3
        self.CHANGE_FAILED = 4
        self.CHANGE_SUCCESS = 5

        # print('ChangePinUX init: pa={}'.format(pa))
        super().__init__(self.ENTER_OLD_PIN)

        self.reset()
        self.security_words_enabled = settings.get('security_words_enabled', SECURITY_WORDS_ENABLED_DEFAULT)

    def reset(self):
        self.pins = [None, None]
        self.old_pin = None
        self.round = 0  # Ask for old PIN first, then new

    def is_confirming(self):
        return self.round == 1

    def pins_match(self):
        return self.pins[0] == self.pins[1]

    def is_pin_valid(self, pin):
        return pin != None

    async def show(self):
        from common import system

        pin = None
        while True:
            # print('show: state={}'.format(self.state))
            if self.state == self.ENTER_OLD_PIN:
                success, pin = await ux_enter_pin(  title='Change PIN',
                                                    heading='Enter Current PIN',
                                                    security_words_enabled=self.security_words_enabled,
                                                    saved_pin=pin)
                if not self.is_pin_valid(pin) or success == False:
                    return

                self.old_pin = pin
                self.goto(self.ENTER_NEW_PIN)

            elif self.state == self.ENTER_NEW_PIN:
                success, pin = await ux_enter_pin(
                    title='Change PIN',
                    heading='{} New PIN'.format('Enter' if self.round == 0 else 'Confirm'),
                    left_btn='BACK',
                    is_new_pin=not self.is_confirming(),
                    security_words_enabled=self.security_words_enabled)
                if not self.is_pin_valid(pin) or success == False:
                    self.goto_prev()

                self.pins[self.round] = pin
                if self.is_confirming():
                    if self.pins_match():
                        self.goto(self.CHANGE_PIN)
                    else:
                        result = await ux_show_story('PINs do not match. Please try again.', title="PIN Mismatch", left_btn="SHUTDOWN", right_btn="RETRY", center=True, center_vertically=True)
                        if result == 'y':
                            # Reset to initial state so PIN needs to be entered and confirmed again
                            # since we don't know if they messed up the first entry or the second one.
                            self.round = 0
                            self.pins[0] = None
                            self.pins[1] = None
                            self.goto(self.ENTER_OLD_PIN)
                        elif result == 'x':
                            await ux_shutdown()
                else:
                    self.round = 1
                    continue

            elif self.state == self.CHANGE_PIN:
                try:
                    # print('Change PIN: old pin={}, new pin={}'.format(self.old_pin, self.pins[0]))
                    args = {}
                    args['old_pin'] = (self.old_pin).encode()
                    args['new_pin'] = (self.pins[0]).encode()
                    # print('pa.change: args={}'.format(args))
                    system.show_busy_bar()
                    pa.change(**args)
                    self.goto(self.CHANGE_SUCCESS)
                except Exception as err:
                    # print('err={}'.format(err))
                    self.goto(self.CHANGE_FAILED)
                finally:
                    system.hide_busy_bar()

            elif self.state == self.CHANGE_FAILED:
                result = await ux_show_story('Unable to change PIN. The current PIN is incorrect.',
                    center=True, center_vertically=True, title='PIN Error', right_btn='RETRY')
                if result == 'y':
                    self.reset()
                    self.goto(self.ENTER_OLD_PIN)
                else:
                    return

            elif self.state == self.CHANGE_SUCCESS:
                dis.fullscreen('PIN changed', line2='Restarting...')
                utime.sleep(2)
                system.reset()
                return
