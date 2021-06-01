# SPDX-FileCopyrightText: 2020 Foundation Devices, Inc. <hello@foundationdevices.com>
# SPDX-License-Identifier: GPL-3.0-or-later
#
# SPDX-FileCopyrightText: 2018 Coinkite, Inc. <coldcardwallet.com>
# SPDX-License-Identifier: GPL-3.0-only
#
# (c) Copyright 2018 by Coinkite Inc. This file is part of Coldcard <coldcardwallet.com>
# and is covered by GPLv3 license found in COPYING.
#
# actions.py
#
# Every function here is called directly by a menu item. They should all be async.
#

import pyb
import version
from files import CardMissingError, CardSlot
# import main
from uasyncio import sleep_ms
import common
from common import settings, system, noise, dis
from utils import (UXStateMachine, imported, pretty_short_delay, xfp2str, to_str,
                   truncate_string_to_width, set_next_addr, scan_for_address, get_accounts, run_chooser,
                   make_account_name_num, is_valid_address, save_next_addr, needs_microsd)
from wallets.utils import get_export_mode, get_addr_type_from_address, get_deriv_path_from_addr_type_and_acct
from ux import (the_ux, ux_confirm, ux_enter_pin,
                ux_enter_text, ux_scan_qr_code, ux_shutdown,
                ux_show_story, ux_show_story_sequence, ux_show_text_as_ur, ux_show_word_list)
from se_commands import *
from data_codecs.qr_type import QRType
import trezorcrypto
from seed_check_ux import SeedCheckUX

async def about_info(*a):
    from common import system
    from display import FontTiny
    from utils import swab32

    while True:
        serial = system.get_serial_number()
        my_xfp = settings.get('xfp', 0)
        xpub = settings.get('xpub', None)

        msg = '''
Master Fingerprint:
{xfp}

Reversed Fingerprint:
{rev_xfp}

Master XPUB:
{xpub}

Serial Number:
{serial}'''.format(xfp=xfp2str(my_xfp) if my_xfp else '<No Seed Yet>',
                 rev_xfp=xfp2str(swab32(my_xfp)) if my_xfp else '<No Seed Yet>',
                 xpub=xpub if xpub != None else '<No Seed Yet>',
                 serial=serial)

        result = await ux_show_story(msg, center=True, center_vertically=True, font=FontTiny, right_btn='REGULATORY')
        if result == 'y':
            await regulatory_info()
        else:
            return

async def regulatory_info():
    from display import FontTiny

    msg = """\

Passport

Foundation Devices
6 Liberty Square #6018
Boston, MA 02109 USA"""

    await ux_show_story(msg, title='Regulatory', center=True, font=FontTiny, overlay=(None, 303 - 34 - 72, 'fcc_ce_logos'))

# async def account_info(*a):
#     # show the XPUB, and other useful information
#     import common
#     import stash
#     from display import FontTiny
#
#     xfp = settings.get('xfp', 0)
#     if xfp == None:
#         xfp = '<Unknown>'
#     else:
#         xfp = xfp2str(xfp)
#
#     # Can only get these values if the derivation path is known
#     xpub = '<Unknown>'
#     path = '<Unknown>'
#     if common.active_account.deriv_path:
#         with stash.SensitiveValues() as sv:
#             path = common.active_account.deriv_path
#             node = sv.derive_path(path)
#             xpub = sv.chain.serialize_public(node, common.active_account.addr_type)
#             print('account_info(): xpub={}'.format(xpub))
#
#     msg = '''
# Account Number:
# {acct_num}
#
# Derivation Path:
# {path}
#
# Account Fingerprint:
# {xfp}
#
# Account XPUB:
# {xpub}'''.format(acct_num=common.active_account.acct_num,
#                  path=path,
#                  xfp=xfp,
#                  xpub=xpub)
#
#     await ux_show_story(
#             msg,
#             title=common.active_account.name,
#             center=True,
#             font=FontTiny)

async def rename_account(menu, label, item):
    from export import auto_backup
    from utils import account_exists, do_rename_account
    from constants import MAX_ACCOUNT_NAME_LEN

    account = common.active_account

    while True:
        new_name = await ux_enter_text('Rename', label="Enter account name", initial_text=account.get('name'),
            right_btn='RENAME', max_length=MAX_ACCOUNT_NAME_LEN)

        if new_name == None:
            # User selected BACK
            return

        # See if an account with this name already exists
        if account_exists(new_name):
            result = await ux_show_story('An account with the name "{}" already exists. Please choose a different name.'.format(new_name),
                title='Duplicate', center=True, center_vertically=True, right_btn='RENAME')
            if result == 'x':
                self.goto_prev()
            else:
                continue

        # Get the accounts and replace the name and save it
        await do_rename_account(account.get('acct_num'), new_name)
        # Pop so we skip over the sub-menu for the account
        the_ux.pop()
        return

async def delete_account(menu, label, item):
    from utils import do_delete_account, make_account_name_num
    from ux import the_ux

    account = common.active_account

    # Confirm the deletion
    name_num = make_account_name_num(account.get('name'), account.get('acct_num'))

    if not await ux_confirm('Are you sure you want to delete this account?\n\n{}'.format(name_num)):
        return

    await do_delete_account(account.get('acct_num'))
    # Pop so we skip over the sub-menu for the account we just deleted
    the_ux.pop()


class VerifyAddressUX(UXStateMachine):

    def __init__(self):
        # States
        self.SELECT_ACCOUNT = 1
        self.SELECT_SIG_TYPE = 2
        self.VERIFY_ADDRESS = 3

        # print('VerifyAddressUX init')
        super().__init__(self.SELECT_ACCOUNT)

        self.acct_num = None
        self.sig_type = None
        self.multisig_wallet = None

    # Account chooser
    def account_chooser(self):
        choices = []
        values = []

        accounts = get_accounts()
        accounts.sort(key=lambda a: a.get('acct_num', 0))

        for acct in accounts:
            acct_num = acct.get('acct_num')
            account_name_num = make_account_name_num(acct.get('name'), acct_num)
            choices.append(account_name_num)
            values.append(acct_num)

        def select_account(index, text):
            self.acct_num = values[index]

        return 0, choices, select_account

    # Select the sig type and if multisig, the specific multisig wallet
    def sig_type_chooser(self):
        from multisig import MultisigWallet
        choices = ['Single-sig']
        values = ['single-sig']

        num_multisigs = MultisigWallet.get_count()
        for ms_idx in range(num_multisigs):
            ms = MultisigWallet.get_by_idx(ms_idx)
            choices.append('%d/%d: %s' % (ms.M ,ms.N, ms.name))
            values.append(ms)

        def select_sig_type(index, text):
            if index == 0:
                self.sig_type = 'single-sig'
                self.multisig_wallet = None
            else:
                self.sig_type = 'multisig'
                self.multisig_wallet = values[index]

        return 0, choices, select_sig_type

    async def show(self):
        while True:
            # print('show: state={}'.format(self.state))
            if self.state == self.SELECT_ACCOUNT:
                self.acct_num = None
                accounts = get_accounts()
                if len(accounts) == 1:
                    self.acct_num = 0
                    self.goto(self.SELECT_SIG_TYPE, save_curr=False)  # Don't save this since we're skipping this state
                    continue

                await run_chooser(self.account_chooser, 'Account', show_checks=False)
                if self.acct_num == None:
                    return

                self.goto(self.SELECT_SIG_TYPE)

            elif self.state == self.SELECT_SIG_TYPE:
                # Multisig only possible for account 0, so skip this if not account 0
                if self.acct_num > 0:
                    self.sig_type = 'single-sig'
                    self.goto(self.VERIFY_ADDRESS, save_curr=False)  # Don't save this since we're skipping this state
                    continue

                # Choose a wallet from the available list
                multisigs = settings.get('multisig', [])
                if len(multisigs) == 0:
                    self.sig_type = 'single-sig'
                else:
                    await run_chooser(self.sig_type_chooser, 'Type', show_checks=False)
                    if self.sig_type == None:
                        if not self.goto_prev():
                            # Nothing to return back to, so we must have skipped one or more steps...were' done
                            return
                        continue

                # print('self.sig_type={}'.format(self.sig_type))

                self.goto(self.VERIFY_ADDRESS)

            elif self.state == self.VERIFY_ADDRESS:
                # Scan the address to be verified - should be a normal QR code
                system.turbo(True);
                address = await ux_scan_qr_code('Verify Address')
                if address == None:
                    return

                # Ensure lowercase
                address = address.lower()

                # Strip prefix if present
                if address.startswith('bitcoin:'):
                    address = address[8:]

                if not is_valid_address(address):
                    result = await ux_show_story('That is not a valid Bitcoin address.', title='Error', left_btn='BACK',
                                                 right_btn='SCAN', center=True, center_vertically=True)
                    if result == 'x':
                        if not self.goto_prev():
                            # Nothing to return back to, so we must have skipped one or more steps...were' done
                            return
                    continue

                # Get the address type from the address
                is_multisig = self.sig_type == 'multisig'
                # print('address={} acct_num={} is_multisig={}'.format(address, self.acct_num, is_multisig))
                addr_type = get_addr_type_from_address(address, is_multisig)
                deriv_path = get_deriv_path_from_addr_type_and_acct(addr_type, self.acct_num, is_multisig)

                # Scan addresses to see if it's valid
                addr_idx = await scan_for_address(self.acct_num, address, addr_type, deriv_path, self.multisig_wallet)
                if addr_idx >= 0:
                    # Remember where to start from next time
                    save_next_addr(self.acct_num, addr_type, addr_idx)

                    dis.fullscreen('Address Verified')
                    await sleep_ms(1000)
                    return
                else:
                    # User asked to stop searching
                    return


async def verify_address(*a):
    verify_address_ux = VerifyAddressUX()
    await verify_address_ux.show()


async def update_firmware(*a):
    # Upgrade via microSD card
    # - search for a particular file
    # - verify it lightly
    # - erase serial flash
    # - copy it over (slow)
    # - reboot into bootloader, which finishes install
    from common import sf, dis
    from constants import FW_HEADER_SIZE, FW_ACTUAL_HEADER_SIZE, FW_MAX_SIZE
    import trezorcrypto

    # Don't show any files that are pubkeys
    def no_pubkeys(filename):
        return not filename.endswith('-pub.bin')

    fn = await file_picker('On the next screen, select the firmware file you want to install.', suffix='.bin', title='Select File', taster=no_pubkeys)
    # print('\nselected fn = {}\n'.format(fn))
    if not fn:
        return

    failed = None

    system.turbo(True)

    with CardSlot() as card:
        with open(fn, 'rb') as fp:
            import os

            offset = 0
            s = os.stat(fn)
            size = s[6]

            if size < FW_HEADER_SIZE:
                await ux_show_story('Firmware file is too small.', title='Error', left_btn='BACK', right_btn='OK', center=True, center_vertically=True)
                return

            if size > FW_MAX_SIZE:
                await ux_show_story('Firmware file is too large.', title='Error', left_btn='BACK', right_btn='OK', center=True, center_vertically=True)
                return

            # Read the header
            header = fp.read(FW_HEADER_SIZE)
            if len(header) != FW_HEADER_SIZE:
                system.turbo(False)
                await ux_show_story('Firmware file is too small, and the system misreported its size.', title='Error', left_btn='BACK', right_btn='OK', center=True, center_vertically=True)
                return

            # Validate the header
            is_valid, version, error_msg = system.validate_firmware_header(header)
            if not is_valid:
                system.turbo(False)
                await ux_show_story('Firmware header is invalid.\n\n{}'.format(error_msg), title='Error', left_btn='BACK', right_btn='OK', center=True, center_vertically=True)
                return

            system.turbo(False)

            # Give the user a chance to confirm/back out
            if not await ux_confirm('Please make sure your Passport is backed up before proceeding.\n\n' +
                                    'Are you sure you want to update the firmware?\n\nNew Version:\n{}'.format(version),
                                    title='Update', scroll_label='MORE'):
                return

            if not await ux_confirm('Do not remove the batteries or shutdown Passport during the firmware update.\n\nWe recommend using fresh batteries.',
                                    title='Reminder', negative_btn='CANCEL', positive_btn='OK'):
                return

            # Start the update
            system.turbo(True)

            # copy binary into serial flash
            fp.seek(offset)

            # Calculate the update request hash so that the booloader knows this was requested by the user, not
            # injected into SPI flash by some external attacker.
            # Hash the firmware header
            header_hash = bytearray(32)

            # Only hash the bytes that contain the passport_firmware_header_t to match what's hashed in the bootloader
            firmware_header = header[0:FW_ACTUAL_HEADER_SIZE]
            system.sha256(firmware_header, header_hash)
            system.sha256(header_hash, header_hash) # Double sha

            # Get the device hash
            device_hash = bytearray(32)
            system.get_device_hash(device_hash)

            # Combine them
            s = trezorcrypto.sha256()
            s.update(header_hash)
            s.update(device_hash)

            # Result
            update_hash = s.digest()

            # Erase first page
            sf.sector_erase(0)
            while sf.is_busy():
                await sleep_ms(10)

            buf = bytearray(256)        # must be flash page size
            buf[0:32] = update_hash  # Copy into the buf we'll use to write to SPI flash

            sf.write(0, buf)  # Need to write the entire page of 256 bytes

            # Start one page in so that we can use the first page for storing a hash.
            # The hash combines the firmware hash with the device hash.
            pos = 256
            update_display = 0
            while pos <= size + 256:
                # print('pos = {}'.format(pos))
                # Update progress bar every 50 flash pages
                if update_display % 50 == 0:
                    dis.splash(message='Preparing Update...', progress=(pos-256)/size)
                update_display += 1

                here = fp.readinto(buf)
                if not here:
                    break

                if pos % 4096 == 0:
                    # erase here
                    sf.sector_erase(pos)
                    while sf.is_busy():
                        await sleep_ms(10)

                sf.write(pos, buf)

                # full page write: 0.6 to 3ms
                while sf.is_busy():
                    await sleep_ms(1)

                pos += here

    if failed:
        system.turbo(False)
        await ux_show_story(failed, title='Sorry!')
        return

    # Save an entry to the settings indicating that we are doing an update
    (curr_version, _, _, _) = system.get_software_info()
    settings.set('update', '{}->{}'.format(curr_version, version))  # old_version->new_version
    await settings.save()

    # NOTE: We intentionally stay in turbo mode here as we reboot to keep the final splash display fast.
    #       Bootloader will go back to top speed anyway.

    # continue process...
    # print("RESTARTING!")

    # Show final progress bar at 100% and change message
    dis.splash(message='Restarting...', progress=1)  # TODO: Make 0-100 to be consistent with progress bar

    system.turbo(False)

    await sleep_ms(1000)

    import machine
    machine.reset()

async def reset_self(*a):
    import machine
    machine.soft_reset()
    # NOT REACHED

async def initial_pin_setup(*a):
    from common import pa, dis, loop


    # TODO: Move the messaging into EnterInitialPinUX state machine
    # First time they select a PIN
    while 1:
        #         ch = await ux_show_story('''\
        # Passport uses a PIN from 6 to 12 digits long.
        #
        # There is an additional security feature that you can use. After entering 2 or more digits of your PIN, press and hold the VALIDATE \
        # button and Passport will show you two Security Words unique to your device and PIN prefix.
        #
        # Remember these two words, and remember how many digits you entered before checking them. When logging in, you can \
        # repeat this process and you should see the same words.
        #
        # If you see different words, then either:
        #
        # 1. You entered a different number of digits
        #
        # 2. You entered the wrong first digits of your PIN
        #
        # 3. Your Passport has been tampered with''', title='PIN Info', scroll_label='MORE')
        #         if ch == 'y':
            while 1:
                ch = await ux_show_story('''\
Now it's time to set your 6-12 digit PIN.

There is no way to recover a lost PIN or reset Passport.

Please record your PIN somewhere safe.''', title='Set PIN', scroll_label='MORE')

                if ch != 'y':
                    break

                # Enter the PIN
                from login_ux import EnterInitialPinUX
                new_pin_ux = EnterInitialPinUX()
                await new_pin_ux.show()
                pin = new_pin_ux.pin
                # print('pin = {}'.format(pin))

                if pin is None:
                    continue

                # New pin is being saved
                dis.fullscreen("Saving PIN...")

                system.show_busy_bar()

                try:
                    assert pa.is_blank()

                    pa.change(new_pin=pin)

                    # check it? kinda, but also get object into normal "logged in" state
                    pa.setup(pin)
                    ok = pa.login()
                    assert ok

                except Exception as e:
                    print("Exception: {}".format(e))
                finally:
                    system.hide_busy_bar()

                return


async def login_countdown(minutes):
    # show a countdown, which may need to
    # run for multiple **days**
    from common import dis
    from display import FontSmall

    sec = minutes * 60
    while sec:
        dis.clear()
        y = 0
        dis.text(None, y, 'Login countdown in', font=FontSmall)
        y += 14
        dis.text(None, y, 'effect. Must wait:', font=FontSmall)
        y += 14
        y += 5

        dis.text(None, y, pretty_short_delay(sec), font=FontSmall)

        dis.show()
        dis.busy_bar(1)
        await sleep_ms(1000)

        sec -= 1

    dis.busy_bar(0)


async def block_until_login(*a):
    #
    # Force user to enter a valid PIN.
    #
    from login_ux import LoginUX
    from common import pa, loop, dis

    # print('pa.is_successful() = {}'.format(pa.is_successful()))
    while not pa.is_successful():
        login_ux = LoginUX()

        # try:
        await login_ux.show()
        # except Exception as e:
        #     print('ERROR when logging in: {}'.format(e))
        #     # not allowed!
        #     pass

    # print('!!!!LOGGED IN!!!!')
    system.turbo(False)

async def create_new_seed(*a):
    from ubinascii import hexlify as b2a_hex
    import seed

    system.show_busy_bar()

    wallet_seed_bytes = await seed.create_new_wallet_seed()
    # print('wallet_seed_bytes = {}'.format(b2a_hex(wallet_seed_bytes)))

    mnemonic_str = trezorcrypto.bip39.from_data(wallet_seed_bytes)
    # print('mnemonic = {}'.format(mnemonic_str))
    mnemonic_words = mnemonic_str.split(' ')

    # Save the wallet so we can work with it (needs to be saved for backup to work)
    await seed.save_wallet_seed(wallet_seed_bytes)

    # Update xpub/xfp in settings after creating new wallet
    import stash
    with stash.SensitiveValues() as sv:
        sv.capture_xpub()

    system.hide_busy_bar()

    while True:
        ch = await ux_show_story('''Now let's create a backup of your seed. We recommend backing up Passport to the two included microSD cards.

Experienced users can always view and record the 24-word seed in the Advanced settings menu.''', title='Backup')
        if ch == 'x':
            if await ux_confirm("Are you sure you want to cancel the backup?\n\nWithout a microSD backup or the seed phrase, you won't be able to recover your funds."):
                # Go back to the outer loop and show the selection again
                break

        # Ensure microSD card is inserted before continuing
        try:
            with CardSlot() as card:
                # TODO: Call the export.make_complete_backup() directly and have it return True/False to indicate if the backup completed
                await make_microsd_backup()
                break
        except CardMissingError:
            ch = await needs_microsd()
            if ch == 'x':
                continue

    await goto_top_menu()

async def restore_wallet_from_seed(menu, label, item):
    result = await ux_show_story('''On the next screen you'll be able to restore your seed using predictive text input.

If you'd like to enter "car" for example, type 2-2-7 and select "car" from the dropdown.''', title='Restore Seed')
    if result == 'x':
        return

    fake_it = True
    if fake_it:
        mnemonic = 'fabric humor guess asset day palace wealth spare trend seek focus empower hair advance myself defy grain inhale market noodle right need joke scatter'
    else:
        from seed_entry_ux import SeedEntryUX
        seed_phrase_entry = SeedEntryUX(seed_len=item.arg)
        await seed_phrase_entry.show()
        if not seed_phrase_entry.is_seed_valid:
            return

        # Seed is valid, so go ahead and convert the mnemonic to seed bits and save it
        mnemonic = ' '.join(seed_phrase_entry.words)

    # print('mnemonic = {}'.format(mnemonic))
    await handle_seed_data_format(mnemonic)

async def handle_seed_data_format(mnemonic):
    import seed
    from foundation import bip39
    from common import dis, pa
    from ubinascii import hexlify as b2a_hex

    entropy = bytearray(33)  # Includes and extra byte for the checksum bits

    # Don't let them import seed if there is already a wallet.
    if not pa.is_secret_blank():
        await ux_show_story('''Unable to import seed phrase because this Passport is alread configured with a seed.

First use Advanced > Erase Passport to remove the current seed.''', right_btn='OK')
        return False

    bip = bip39()
    len = bip.mnemonic_to_entropy(mnemonic, entropy)

    if len == 264: # 24 words x 11 bits each
        trim_pos = 32
    elif len == 198: # 18 words x 11 bits each
        trim_pos = 24
    elif len == 132: # 12 words x 11 bits each
        trim_pos = 16
    entropy = entropy[:trim_pos]  # Trim off the excess (including checksum bits)
    # print('entropy = {}'.format(b2a_hex(entropy)))

    # Entropy is now the right length - SecretStash.encode() adds a marker byte to indicate length of the secret
    # so we can decode it correctly.
    await seed.save_wallet_seed(entropy)
    # print('Seed was imported successfully!')

    # Update xpub/xfp in settings after creating new wallet
    import stash
    with stash.SensitiveValues() as sv:
        sv.capture_xpub()

    # Show post-creation message
    dis.fullscreen('Successfully Imported!')
    await sleep_ms(1000)

    await goto_top_menu()
    return True

async def erase_wallet(menu, label, item):
    # Erase the seed words, and private key from this wallet!
    # This is super dangerous for the customer's money.
    import seed
    from common import pa

    if not await ux_confirm('Are you sure you want to erase this Passport? All funds will be lost if not backed up.'):
        return

    if not await ux_confirm('Without a proper backup, this action will cause you to lose all funds associated with this device.\n\n' +
                             'Please confirm that you understand these risks.', scroll_label='MORE', negative_btn='BACK', positive_btn='CONFIRM'):
        return

    await seed.erase_wallet(item.arg)
    # NOT REACHED -- reset happens


async def view_seed_words(*a):
    import stash
    from common import dis

    if not await ux_confirm(
        'The next screen will show your seed words and, if defined, your passphrase.\n\n' +
        'Anyone who knows these words can control your funds.\n\n' +
        'Do you want to display this sensitive information?', scroll_label='MORE', center=False):
        return

    dis.fullscreen('Retrieving Seed...')
    system.show_busy_bar()

    try:
        with stash.SensitiveValues() as sv:
            assert sv.mode == 'words'       # protected by menu item predicate

            words = trezorcrypto.bip39.from_data(sv.raw).split(' ')

            msg = 'Seed words (%d):\n' % len(words)
            msg += '\n'.join('%2d: %s' % (i+1, w) for i, w in enumerate(words))

            pw = stash.bip39_passphrase
            if pw:
                msg += '\n\nPassphrase:\n%s' % stash.bip39_passphrase

            system.hide_busy_bar()

            ch = await ux_show_story(msg, sensitive=True, right_btn='VERIFY')
            if ch == 'y':
                seed_check = SeedCheckUX(seed_words=words, title='Verify Seed')
                await seed_check.show()
                return

            stash.blank_object(msg)

    except Exception as e:
        print('Exception: {}'.format(e))
        system.hide_busy_bar()
        # Unable to read seed!
        await ux_show_story('Unable to retrieve seed.')


async def start_login_sequence():
    # Boot up login sequence here.
    #
    from common import pa

    while not pa.is_successful():
        # always get a PIN and login first
        await block_until_login()


async def goto_top_menu(*a):
    # Start/restart menu system
    from menu import MenuSystem
    from flow import MainMenu, NoSeedMenu
    from common import pa

    # print('pa.is_secret_blank()={}'.format(pa.is_secret_blank()))
    if pa.is_secret_blank():
        m = MenuSystem(NoSeedMenu)
    else:
        m = MenuSystem(MainMenu)

    the_ux.reset(m)

    return m


SENSITIVE_NOT_SECRET = '''

The file created is sensitive in terms of privacy, but should not \
compromise your funds directly.'''

PICK_ACCOUNT = '''\n\nPress 1 to enter a non-zero account number.'''


async def export_summary(*A):
    # save addresses, and some other public details into a file
    if not await ux_confirm('''\
Saves a text file to microSD with a summary of the *public* details \
of your wallet. For example, this gives the XPUB (extended public key) \
that you will need to import other wallet software to track balance.''' + SENSITIVE_NOT_SECRET,
        title='Export', negative_btn='BACK', positive_btn='CONTINUE'):
        return

    # pick a semi-random file name, save it.
    with imported('export') as exp:
        await exp.make_summary_file()


def electrum_export_story(background=False):
    # saves memory being in a function
    return ('''\
This saves a skeleton Electrum wallet file onto the microSD card. \
You can then open that file in Electrum without ever connecting this Passport to a computer.\n
'''
            + (background or 'Choose an address type for the wallet on the next screen.'+PICK_ACCOUNT)
            + SENSITIVE_NOT_SECRET)


# async def electrum_skeleton(*a):
#     # save xpub, and some other public details into a file: NOT MULTISIG
#
#     ch = await ux_show_story(electrum_export_story())
#
#     account_num = 0
#     if ch == '1':
#         account_num = await ux_enter_number('Account Number:', 9999)
#     elif ch != 'y':
#         return
#
#     # pick segwit or classic derivation+such
#     from public_constants import AF_CLASSIC, AF_P2WPKH, AF_P2WPKH_P2SH
#     from menu import MenuSystem, MenuItem
#
#     # Ordering and terminology from similar screen in Electrum. I prefer
#     # 'classic' instead of 'legacy' personally.
#     rv = []
#
#     rv.append(MenuItem("Legacy (P2PKH)", f=electrum_skeleton_step2,
#                        arg=(AF_CLASSIC, account_num)))
#     rv.append(MenuItem("P2SH-Segwit", f=electrum_skeleton_step2,
#                        arg=(AF_P2WPKH_P2SH, account_num)))
#     rv.append(MenuItem("Native Segwit", f=electrum_skeleton_step2,
#                        arg=(AF_P2WPKH, account_num)))
#
#     return MenuSystem(rv, title="Electrum")


# async def bitcoin_core_skeleton(*A):
#     # save output descriptors into a file
#     # - user has no choice, it's going to be bech32 with  m/84'/{coin_type}'/0' path
#
#     ch = await ux_show_story('''\
# This saves a command onto the microSD card that includes the public keys. \
# You can then run that command in Bitcoin Core without ever connecting this Passport to a computer.\
# ''' + PICK_ACCOUNT + SENSITIVE_NOT_SECRET)
#
#     account_num = 0
#     if ch == '1':
#         account_num = await ux_enter_number('Account Number:', 9999)
#     elif ch != 'y':
#         return
#
#     # no choices to be made, just do it.
#     with imported('export') as exp:
#         dis.fullscreen('Generating...')
#         body = exp.make_bitcoin_core_wallet(account_num)
#         await write_text_file('bitcoin-core.txt', body, 'Bitcoin Core')

# async def electrum_skeleton_step2(_1, _2, item):
#     # pick a semi-random file name, render and save it.
#     with imported('export') as exp:
#         addr_fmt, account_num = item.arg
#         await exp.make_json_wallet('Electrum wallet', lambda: exp.generate_electrum_wallet(addr_fmt, account_num))

# async def generic_skeleton(*a):
#     # like the Multisig export, make a single JSON file with
#     # basically all useful XPUB's in it.
#
#     if await ux_show_story('''\
# Saves JSON file onto MicroSD card, with XPUB values that are needed to watch typical \
# single-signer UTXO associated with this Coldcard.''' + SENSITIVE_NOT_SECRET) != 'y':
#         return
#
#     account_num = await ux_enter_number('Account Number:', 9999)
#
#     # no choices to be made, just do it.
#     import export
#     await export.make_json_wallet('Generic Export',
#                                     lambda: export.generate_generic_export(account_num),
#                                     'coldcard-export.json')

# async def wasabi_skeleton(*A):
#     # save xpub, and some other public details into a file
#     # - user has no choice, it's going to be bech32 with  m/84'/0'/0' path
#
#     if await ux_show_story('''\
# This saves a skeleton Wasabi wallet file onto the microSD card. \
# You can then open that file in Wasabi without ever connecting this Passport to a computer.\
# ''' + SENSITIVE_NOT_SECRET) != 'y':
#         return
#
#     # no choices to be made, just do it.
#     with imported('export') as exp:
#         await exp.make_json_wallet('Wasabi wallet', lambda: exp.generate_wasabi_wallet(), 'new-wasabi.json')


async def make_microsd_backup(*A):
    # save everything, using a password, into single encrypted file, typically on SD
    with imported('export') as exp:
        await exp.make_complete_backup()


async def verify_microsd_backup(*A):
    # check most recent backup is "good"
    # read 7z header, and measure checksums

    with imported('export') as exp:
        fn = await file_picker('Select the backup to verify.',
            suffix='.7z', max_size=exp.MAX_BACKUP_FILE_SIZE, folder_path='/sd/backups')

        if fn:
            # do a limited CRC-check over encrypted file
            await exp.verify_backup_file(fn)



EMPTY_RESTORE_MSG = '''\
Before restoring from a backup, you must erase this Passport. Make sure your device is backed up.

Navigate to Advanced > Erase Passport.'''

FULL_PARTIAL_MSG = '''A wallet seed already exists.

Do you want to perform a FULL restore or a PARTIAL restore of accounts only?'''

async def restore_microsd_backup(*A):
    from common import pa

    partial_restore = False

    if not pa.is_secret_blank():
        await ux_show_story(EMPTY_RESTORE_MSG)
        return

    # if not pa.is_secret_blank():
    #     result = await ux_show_story(FULL_PARTIAL_MSG, left_btn='FULL', right_btn='PARTIAL')
    #     if result == 'x':
    #         await ux_show_story(EMPTY_RESTORE_MSG)
    #         return
    #     else:
    #         partial_restore = True

    # TODO: Insert step here to pick a backups-* folder when we add the XFP to the folder name

    # Choose a backup file -- must be in 7z format
    fn = await file_picker('Select the backup to restore and then enter the six-word password.',
        suffix='.7z', max_size=10000, folder_path='/sd/backups')

    if fn:
        with imported('export') as exp:
            await exp.restore_complete(fn, partial_restore)


async def format_sd_card(*A):
    if not await ux_confirm('Erase and reformat the microSD card.', negative_btn='BACK', positive_btn='FORMAT'):
        return

    from files import format_microsd_card

    system.turbo(True)
    format_microsd_card()
    system.turbo(False)


async def list_files(*a):
    # list files, don't do anything with them?
    fn = await file_picker('List all files on the microSD card. Select a file to show the SHA256 hash.', min_size=0)
    if not fn:
        return

    from utils import B2A
    chk = trezorcrypto.sha256()

    system.show_busy_bar()
    try:
        with CardSlot() as card:
            with open(fn, 'rb') as fp:
                while 1:
                    data = fp.read(1024)
                    if not data: break
                    chk.update(data)
    except CardMissingError:
        system.hide_busy_bar()
        await needs_microsd()
        return

    basename = fn.rsplit('/', 1)[-1]

    digest = B2A(chk.digest())
    system.hide_busy_bar()

    await ux_show_story('File:\n  %s\n\n%s' % (basename, digest), title='SHA256')


async def file_picker(msg, suffix=None, min_size=None, max_size=None, taster=None, choices=None, none_msg=None, title='Select', folder_path=None):
    # present a menu w/ a list of files... to be read
    # - optionally, enforce a max size, and provide a "tasting" function
    # - if msg==None, don't prompt, just do the search and return list
    # - if choices is provided; skip search process
    # - escape: allow these chars to skip picking process
    from menu import MenuSystem, MenuItem
    import uos
    from utils import get_filesize, folder_exists

    system.turbo(True)

    if choices is None:
        choices = []
        try:
            with CardSlot() as card:
                sofar = set()

                if folder_path == None:
                    folder_path = card.get_paths()
                else:
                    folder_path = [folder_path]

                for path in folder_path:
                    # If the folder doesn't exist, skip it (e.g., if /sd/backups/ doesn't exist)
                    if not folder_exists(path):
                        continue

                    files = uos.ilistdir(path)
                    for fn, ftype, *var in files:
                        # print("fn={} ftype={} var={}  suffix={}".format(fn, ftype, var, suffix))
                        if ftype == 0x4000:
                            # ignore subdirs
                            continue

                        if suffix and not fn.lower().endswith(suffix):
                            # wrong suffix
                            continue

                        if fn[0] == '.':
                            continue

                        full_fname = path + '/' + fn

                        # Consider file size
                        # sigh, OS/filesystem variations
                        file_size = var[1] if len(
                            var) == 2 else get_filesize(full_fname)

                        if min_size is not None and file_size < min_size:
                            continue

                        if max_size is not None and file_size > max_size:
                            continue

                        if taster is not None:
                            try:
                                yummy = taster(full_fname)
                            except IOError:
                                # print("fail: %s" % full_fname)
                                yummy = False

                            if not yummy:
                                continue

                        label = fn
                        while label in sofar:
                            # just the file name isn't unique enough sometimes?
                            # - shouldn't happen anymore now that we dno't support internal FS
                            # - unless we do muliple paths
                            label += path.split('/')[-1] + '/' + fn

                        sofar.add(label)
                        choices.append((label, path, fn))

        except CardMissingError:
            system.turbo(False)
            # don't show anything if we're just gathering data
            if msg is not None:
                await needs_microsd()
            return None

    system.turbo(False)

    if msg is None:
        return choices

    if not choices:
        msg = none_msg or 'Unable to find an applicable file on the microSD card.'

        if not none_msg:
            if suffix:
                msg += '\n\nThe filename must end in "%s".' % suffix

        await ux_show_story(msg, center=True, center_vertically=True, title=title)
        return

    ch = await ux_show_story(msg, center=True, center_vertically=True, title=title)
    if ch == 'x':
        return

    picked = []

    async def clicked(_1, _2, item):
        picked.append('/'.join(item.arg))
        the_ux.pop()

    choices.sort()

    items = [MenuItem(label, f=clicked, arg=(path, fn))
             for label, path, fn in choices]

    menu = MenuSystem(items, title='Select File')
    the_ux.push(menu)

    await menu.interact()

    return picked[0] if picked else None


async def sign_tx_from_sd(*a):
    # Check if any signable in SD card, if so do it
    from public_constants import MAX_TXN_LEN

    import stash

    if stash.bip39_passphrase:
        title = '[%s]' % xfp2str(settings.get('xfp'))
    else:
        title = 'Select PSBT'

    def is_psbt(filename):
        if '-signed' in filename.lower():
            return False

        with open(filename, 'rb') as fd:
            taste = fd.read(10)
            if taste[0:5] == b'psbt\xff':
                return True
            if taste[0:10] == b'70736274ff':        # hex-encoded
                return True
            if taste[0:6] == b'cHNidP':             # base64-encoded
                return True
            return False

    choices = await file_picker(None, suffix='psbt', min_size=50,
                                max_size=MAX_TXN_LEN, taster=is_psbt)

    if not choices:
        await ux_show_story("""\
Copy an unsigned PSBT transaction onto the microSD card and insert it into Passport.
""", title=title)
        return

    if len(choices) == 1:
        # skip the menu
        label, path, fn = choices[0]
        input_psbt = path + '/' + fn
    else:
        input_psbt = await file_picker('Choose a PSBT to sign.', choices=choices, title=title)
        if not input_psbt:
            return

    # start the process
    from auth import sign_psbt_file

    await sign_psbt_file(input_psbt)


async def sign_message_on_sd(*a):
    # Menu item: choose a file to be signed (as a short text message)
    #
    def is_signable(filename):
        if '-signed' in filename.lower():
            return False
        with open(filename, 'rt') as fd:
            lines = fd.readlines()
            return (1 <= len(lines) <= 5)

    fn = await file_picker('Choose text file to sign.',
                           suffix='txt', min_size=2,
                           max_size=500, taster=is_signable,
                           none_msg='No suitable files found. Must be one line of text, in a .TXT file, optionally followed by a subkey derivation path on a second line.')

    if not fn:
        return

    # start the process
    from auth import sign_txt_file
    await sign_txt_file(fn)


async def change_pin(*a):
    # Help user change pins with appropriate warnings.
    from login_ux import ChangePinUX

    change_pin_ux = ChangePinUX()
    await change_pin_ux.show()

# Reset pin to blank (all zeroes)
# async def set_blank_pin(*a):
#     from common import pa
#
#     args = {}
#     old_pin = await ux_enter_pin(title='Enter Old PIN', heading='Old PIN')
#     args['old_pin'] = old_pin.encode()
#     blank_pin = [32] * 0
#     args['new_pin'] = bytearray(blank_pin)
#     try:
#         pa.change(**args)
#     except Exception as e:
#         print('Exception: {}'.format(e))

async def show_version(*a):
    # show firmware, bootloader versions
    from utils import get_month_str
    from utime import localtime

    system.turbo(True)
    (fw_version, fw_timestamp, boot_counter, user_signed) = system.get_software_info()

    time = localtime(fw_timestamp)
    fw_date = '{} {}, {}'.format(get_month_str(time[1]), time[2], time[0]-30)

    msg = '''\
Current Firmware:
v{fw_version}
{fw_date}'''.format(fw_version=fw_version,
           fw_date=fw_date)

    if user_signed:
        msg += '\nSigned by User'

    msg += '''

Boot Counter:
{boot_counter}\
'''.format(boot_counter=boot_counter)
    system.turbo(False)

    await ux_show_story(msg, center=True, center_vertically=True)


async def import_multisig_from_sd(*a):
    # pick text file from SD card, import as multisig setup file

    def possible(filename):
        with open(filename, 'rt') as fd:
            for ln in fd:
                if 'pub' in ln:
                    return True

    fn = await file_picker('Select multisig wallet file to import (.txt)', suffix='.txt',
                           min_size=100, max_size=20*200, taster=possible)

    if not fn:
        return

    system.turbo(True);
    try:
        with CardSlot() as card:
            with open(fn, 'rt') as fp:
                data = fp.read()
    except CardMissingError:
        system.turbo(False);
        await needs_microsd()
        return

    # print('data={}'.format(data))

    from auth import maybe_enroll_xpub
    from utils import problem_file_line, show_top_menu
    from export import offer_backup
    try:
        possible_name = (fn.split('/')[-1].split('.'))[0]
        maybe_enroll_xpub(config=data, name=possible_name)
        await show_top_menu()  # wait for interaction with the enroll

        system.turbo(False);
        await offer_backup()
    except Exception as e:
        system.turbo(False);
        await ux_show_story('Unable to import multisig configuration.\n\n{}\n{}'.format(e, problem_file_line(e)), title='Error')


async def import_multisig_from_qr(*a):
    system.turbo(True);
    data = await ux_scan_qr_code('Import Multisig')
    system.turbo(False);

    if data != None:
        # TOnly need to decode this for QR codes...from SD card it's already in bytes
        data = data.decode('utf-8')
        await handle_import_multisig_config(data)

async def handle_import_multisig_config(data):
    from auth import maybe_enroll_xpub
    from export import offer_backup
    from utils import show_top_menu

    try:
        possible_name = "ms"
        maybe_enroll_xpub(config=data, name=possible_name)
        await show_top_menu()  # wait for interaction with the enroll

        await offer_backup()
    except Exception as e:
        await ux_show_story('Unable to import multisig configuration.\n\n'+str(e), title='Error')


# Scan QR code and magically determine what to do
async def magic_scan(menu, label, item):
    from common import dis
    from data_codecs.data_format import get_flow_for_data

    title = item.arg

    while True:
        system.turbo(True)
        data = await ux_scan_qr_code(title)
        system.turbo(False)

        # Run the samplers to figure out what type of data was scanned and run the corresponding flow, if any
        if data == None:
            return

        flow = get_flow_for_data(data)
        if flow == None:
            # Show error to user
            result = await ux_show_story('Unrecognized data format.', title='Error', right_btn='RETRY', center=True, center_vertically=True)
            if result == 'y':
                continue
            return
        else:
            # Run the flow
            retry = await flow(data)
            if retry:
                continue
            return

# Handler for psbt
async def handle_psbt_data_format(data):
    from common import dis

    if data != None:
        try:
            from auth import sign_psbt_buf

            # The data can be a string or may already be a bytes object
            if isinstance(data, bytes):
                data_buf = data
            else:
                data_buf = bytes(data, 'utf-8')
            # print("data_buf={}".format(data_buf))
            system.show_busy_bar()
            dis.fullscreen('Analyzing...')
            await sign_psbt_buf(data_buf)
        except Exception as e:
            # print('Signing exception:{}'.format(e))
            result = await ux_show_story('Error signing transaction:\n\n{}'.format(e), title='Error', right_btn='RETRY')
            return result == 'y'
        finally:
            system.hide_busy_bar()

    return False

async def import_user_firmware_pubkey(*a):
    from common import system, dis
    from ubinascii import hexlify

    result = await ux_show_story('''Passport allows you to compile your own firmware version and sign it \
with your private key.

To enable this, you must first import your corresponding public key.

On the next screen, you can select your public key and import it into Passport.''', title='Import PubKey')
    if result == 'x':
        return

    fn = await file_picker('Select public key file (*-pub.bin)', suffix='-pub.bin')
    if fn == None:
        return

    system.turbo(True)
    with CardSlot() as card:
        with open(fn, 'rb') as fd:
            fd.seek(24)  # Skip the header
            pubkey = fd.read(64)  # Read the pubkey

            # print('pubkey = {}'.format(hexlify(pubkey)))

            result = system.set_user_firmware_pubkey(pubkey)
            if result:
                dis.fullscreen('Successfully Imported!')
            else:
                dis.fullscreen('Unable to Import')
            await sleep_ms(1000)
            # print('system.set_user_firmware_pubkey() = {}'.format(result))
    system.turbo(False)


async def read_user_firmware_pubkey(*a):
    from common import system
    from ubinascii import hexlify

    pubkey = bytearray(64)

    system.turbo(True)
    result = system.get_user_firmware_pubkey(pubkey)
    # print('system.get_user_firmware_pubkey() = {}'.format(result))
    # print('  len={} pubkey = {}'.format(len(pubkey), hexlify(pubkey)))
    system.turbo(False)


async def enter_passphrase(menu, label, item):
    import sys
    from seed import set_bip39_passphrase
    from constants import MAX_PASSPHRASE_LENGTH

    title = item.arg
    passphrase = await ux_enter_text(title, label="Enter a Passphrase", max_length=MAX_PASSPHRASE_LENGTH)

    # print("Chosen passphrase = {}".format(passphrase))

    if not await ux_confirm('Are you sure you want to apply the passphrase:\n\n{}'.format(passphrase)):
        return

    # Applying the passphrase takes a bit of time so show message
    from common import dis
    dis.fullscreen("Applying Passphrase...")

    system.show_busy_bar()

    result = None
    try:
        err = set_bip39_passphrase(passphrase)

        if err:
            await ux_show_story('Unable to apply passphrase: {}'.format(err))
        else:
            result = settings.get('xpub')

    except BaseException as exc:
        sys.print_exception(exc)

    system.hide_busy_bar()

async def enter_seed_phrase(menu, label, item):
    from seed_entry_ux import SeedEntryUX
    seed_phrase_entry = SeedEntryUX(seed_len=item.arg)
    await seed_phrase_entry.show()
    # print('seed words = {}'.format(seed_phrase_entry.words))

async def sample_stories(menu, label, item):
    result = await ux_show_story_sequence(
        [
            {'msg': 'Testing 1\nTesting 1\nTesting 1\nTesting 1\nTesting 1\nTesting 1\nTesting 1\nTesting 1\nTesting 1\nTesting 1\n', 'title': 'Story 1'},
            {'msg': 'Testing 2', 'title': 'Story 2'},
            {'msg': 'Testing 3', 'title': 'Story 3', 'right_btn': 'ACTION'}
        ]
    )
    if result == 'y':
        # Do some action at the end
        pass

# TODO: Go back and reimplement this as a state machine like LoginUX
async def validate_passport_hw(*a):
    from pincodes import PinAttempt
    from ubinascii import unhexlify as a2b_hex
    from common import system

    if settings.get('validated_ok'):
        return

    while True:

        # Explain what validation is
        result = await ux_show_story('''\
Next, let's make sure your Passport has not been tampered with during shipping.

The setup guide will direct you to a page containing a QR code.

On the next screen, scan that QR code. Your Passport will show you 4 Security Words in response.

Enter those 4 words in the same order into the validation page.''',
            title='Validation', left_btn='SHUTDOWN', scroll_label='MORE')
        if result == 'y':

            while True:
                # Scan a QR code
                system.turbo(True)
                qr_data = await ux_scan_qr_code('Validation')
                # qr_data = 'af7e2098fd626650b342398905b82a73c835213dc1b4b1ca10f783d4e4593c95'
                system.turbo(False)

                # Generate the 4 validation words
                # 4 words gives 2048 choose 4 possibilties = 730,862,190,080
                if qr_data == None:

                    while True:
                        result = await ux_show_story('''No QR code was scanned. Do you want to try again, or skip validation?\n\nIMPORTANT: If you skip validation now, there will be no way to do so in the future.''', left_btn='SKIP', right_btn='RETRY')
                        if result == 'x':
                            # Confirm?
                            confirmed = await ux_confirm('Are you sure you want to permanently skip supply chain validation?')
                            if confirmed:
                                # 2 means validation was skipped, but we won't show it again
                                settings.set('validated_ok', 2)
                                return
                        else:
                            # Break out of the inner loop and back out the the QR validation scan loop
                            break

                else:

                    # Split the data up into the challenge and the signature
                    parts = qr_data.split(' ')
                    # print('parts={}'.format(parts))

                    if len(parts) != 2:
                        # print('ERROR: len={}'.format(len(parts)))
                        result = await ux_show_story('The QR code is not formatted correctly. Are you sure you are ' +
                            'on the correct website?',
                            left_btn='SHUTDOWN',
                            right_btn='RETRY')
                        if result == 'x':
                            await ux_shutdown()
                        else:
                            # Retry in the outer loop - scan the QR code again
                            break

                    system.turbo(True)
                    challenge = parts[0]
                    challenge_hash = bytearray(32)
                    system.sha256(challenge, challenge_hash)
                    # print('challenge: {}'.format(challenge))
                    # print('challenge_hash: {}'.format(challenge_hash))

                    signature_str = parts[1]
                    signature = a2b_hex(signature_str)
                    # print('signature_str: {}'.format(signature_str))
                    # print('signature: {}'.format(signature))
                    system.turbo(False)

                    # Let's make sure that this challenge was actually signed by the Foundation server
                    if system.verify_supply_chain_server_signature(challenge_hash, signature) == False:
                        result = await ux_show_story('The QR code you scanned does not appear to be from the ' +
                            'Foundation Devices validation server.\n\nPlease ensure that you navigated to the correct website.',
                            left_btn='SHUTDOWN',
                            right_btn='RETRY')
                        if result == 'x':
                            await ux_shutdown()
                        else:
                            # Retry in the outer loop - scan the QR code again
                            break

                        await ux_show_story('The QR code you scanned does not appear to be from the ' +
                                            'Foundation Devices validation server!\n\nPlease ensure ' +
                                            'that you navigated to the correct website.', 'Error', right_btn='OK')
                        return

                    # print('CHALLENGE SIGNATURE IS VALID!!!!!')

                    # The challenge was properly signed by the Foundation server, so now generate the response
                    words = PinAttempt.supply_chain_validation_words(a2b_hex(challenge))
                    # print('Validation words={}'.format(words))
                    numbered_words = []
                    for i in range(len(words)):
                        numbered_words.append('{}. {}'.format(i+1, words[i]))

                    result = await ux_show_word_list(
                        'Validate',
                        numbered_words,
                        heading1='Enter these words on',
                        heading2='the validation page.',
                        left_aligned_center=True,
                        left_btn='INVALID',
                        right_btn='VALID'
                    )
                    if result == 'x':
                        while True:
                            result = await ux_show_story('''\
                                If the words did not match, your Passport may have been modified after it was manufactured. Please contact us at support@foundationdevices.com.''', left_btn='SHUTDOWN', right_btn='RETRY')
                            if result == 'x':
                                await ux_shutdown()
                            else:
                                # Retry in the outer loop - scan the QR code again
                                break
                    elif result == 'y':
                        # Note that they confirmed the validation words were correct
                        settings.set('validated_ok', 1)
                        return
        elif result == 'x':
            await ux_shutdown()


async def test_ur(*a):
    from test import TestUR

    test = TestUR()
    test.run_tests()


async def test_ur_encoder(_1, _2, item):
    await ux_show_text_as_ur(title='Test UR Encoding', msg='Animated UR Code', qr_text=b'Y\x01\x00\x91n\xc6\\\xf7|\xad\xf5\\\xd7\xf9\xcd\xa1\xa1\x03\x00&\xdd\xd4.\x90[w\xad\xc3nO-<\xcb\xa4O\x7f\x04\xf2\xdeD\xf4-\x84\xc3t\xa0\xe1I\x13o%\xb0\x18RTYa\xd5_\x7fz\x8c\xdem\x0e.\xc4?;-\xcbdJ"\t\xe8\xc9\xe3J\xf5\xc4ty\x84\xa5\xe8s\xc9\xcf_\x96^%\xee)\x03\x9f\xdf\x8c\xa7O\x1cv\x9f\xc0~\xb7\xeb\xae\xc4n\x06\x95\xae\xa6\xcb\xd6\x0b>\xc4\xbb\xff\x1b\x9f\xfe\x8a\x9er@\x12\x93w\xb9\xd3q\x1e\xd3\x8dA/\xbbDB%o\x1eoY^\x0f\xc5\x7f\xedE\x1f\xb0\xa0\x10\x1f\xb7k\x1f\xb1\xe1\xb8\x8c\xfd\xfd\xaa\x94b\x94\xa4}\xe8\xff\xf1s\xf0!\xc0\xe6\xf6[\x05\xc0\xa4\x94\xe5\x07\x91\'\n\x00P\xa7:\xe6\x9bg%PZ.\xc8\xa5y\x14W\xc9\x87m\xd3J\xad\xd1\x92\xa5:\xa0\xdcf\xb5V\xc0\xc2\x15\xc7\xce\xb8$\x8bq|"\x95\x1ee0[V\xa3pn>\x86\xeb\x01\xc8\x03\xbb\xf9\x15\xd8\x0e\xdc\xd6MM',
                             qr_type=QRType.UR1, qr_args=None)

async def test_num_entry(*a):
    num = await ux_enter_text('Enter Number', label='Enter an integer', num_only=True)
    dis.fullscreen('Number = {}'.format(num))
    await sleep_ms(2000)

async def play_snake(*a):
    from snake import snake_game
    await snake_game()


async def play_stacking_sats(*a):
    from stacking_sats import stacking_sats_game
    await stacking_sats_game()


# Secure Element Test Actions
async def se_get_config(*a):
    config = bytearray(128)
    system.dispatch(CMD_GET_SE_CONFIG, config, 0)

    import ubinascii
    s = ubinascii.hexlify(config).decode('utf8')
    lines = [s[i:i+16] for i in range(0, len(s), 16)]
    data = '\n'.join(lines)
    await ux_show_story("SE Config\n\n" + data)

async def gen_random(_1, _2, item):
    from ubinascii import hexlify
    seed = bytearray(32)
    valid = noise.random_bytes(seed, item.arg)
    # print('Random bytes = {}'.format(hexlify(seed)))

async def show_power_monitor(*a):
    from foundation import Powermon
    powermon = Powermon()

    for i in range(10):
        (current, voltage) = powermon.read()
        # print('current={} voltage={}'.format(current, voltage))
        await sleep_ms(1000)

async def show_board_rev(*a):
    from foundation import Boardrev
    boardrev = Boardrev()

    rev = boardrev.read()
    # print('Board rev={}'.format(rev))

async def erase_user_settings(*a):
    confirm = await ux_confirm('Are you sure you want to erase the User Settings?\n\nWhen restarting, you will be prompted to accept terms again and go through Supply Chain Authentication again.')
    if confirm:
        settings.erase_settings_flash()

async def update_xpub(*a):
    import stash
    with stash.SensitiveValues() as sv:
        sv.capture_xpub()

async def coming_soon(*a):
    await ux_show_story('This feature is under development. Stay tuned!', title='Coming Soon')

async def dump_settings(*a):
    print('Current Settings:\n{}'.format(to_str(settings.curr_dict)))

async def dump_flash_cache(*a):
    from common import flash_cache
    print('Current Flash Cache:\n{}'.format(to_str(flash_cache.current)))

async def test_ur1_old(*a):
    from ur1.decode_ur import decode_ur
    from ur1.encode_ur import encode_ur

    # Encoding
    data = '7e4a61385e2550981b4b5633ab178eb077a30505fbd53f107ec1081e7cf0ca3c0dc0bfea5b8bfb5e6ffc91afd104c3aa756210b5dbc5118fd12c87ee04269815ba6a9968a0d0d3b7a9b631382a36bc70ab626d5670b4b48ff843f4d9a15631aa67c7aaf0ac6ce7e3bff03b2c9643e3375e47493c4e0f8635329d66fdec41b10ce74dcbf25fc15d829e7830c325643a98561f441b40a02e8353493e6afc16192fe99d90d8ca65539af77ddeaccc8943a37563a9ba83675bd5d4da7c60c9a172cf6940cbf0ec8fe04175a629932e3512c5d2aaea3cca3246f40a21ffdc33c3987dc7b880351230eb3759fe3c7dc7b2d3a20a95996ff0b7a0dba834f96beb64c14e3426fb051a936ba41569ab99c0066a6d9c0777a49e49e6cbad24d722a4c7da112432679264b9adc0a8cff9dd1fe0ee9ee2747f6a68537c389a7303a1af23c534ee6392bc17b04cf0fbce7689e66b673a440c04a9454005b0c76664639113458eb7d0902eff04d11138ce2a8ee16a9cd7c8926514efa9bd83ae7a4c139835f0fe0f68c628e0645c8524c30dfc314e825a7aa13224d98e2f7a9d12183a999bb1f28549c99a9072d99c05c24e0c84848c4fc147a094ab7b69e9cbea86952fccf15500fbb234ffe6ee6e6ded515c8016cb017ba36fb931ef276cec4ed22c1aed1495d2df3b3ce66c03f5b9ffa8434bf0e8fb149de94e050b3da178df1f76c00a366cb2801fabdf1a1e90cd3cd45ecb7a930a40b151455f76b726d552f31c21324992da257ff8bde2923dfd5d0d6b87233fae215ffacbecd96249099e7e3427d533db56cdb09c7475b4ce3314e33f43953a7370866cc11d85f00b71b15510b46c4b4fa490c660ddfeda0ceb1b8265995f7071c155ad1b57465fdc0fa81a73f9f19ac4872029d5844c1838f732e803043673e26cbc5b51297a324ff00a2d2d4222bad556b93d27c8e376e3ff8f9d37b3073410708ebb3d4dd7473d27212310b71a3c33a5c8f87f44824640e7f8970f4eda9364195c87a91172b8f085f1773641dde1ce21938746234055bc971ce2325f814e3eec60f781dd4faf52afd5be4a6b38656f7e9739f724cb7ccd4e4d01e802add3dc7b83191f894b3ee0ed752ee514d5ec55'

    result = encode_ur(data)
    if result == [
        'ur:bytes/1of7/0jsmw5retzcecxhpgz2e6pnzw9qy98m0frafzjuwn324w4yf8xdq0h0cmw/typjqlj2vyu9uf2snqd5k43n4vtcavrh5vzst7748ug8asggre70pj3uphqtl6jm30a4umlujxhazpxr4f6kyy94m0z3rr739jr7uppxnq2m565edzsdp5ah4xmrzwp2x678p2mzd4t8pd953luy8axe59trr2n8c740ptrvul3mlupm9jty8cehter5j0zwp7rr2v5a',
        'ur:bytes/2of7/0jsmw5retzcecxhpgz2e6pnzw9qy98m0frafzjuwn324w4yf8xdq0h0cmw/vm77csd3pnn5mjljtlq4mq570qcvxfty82v9v86yrdq2qt5r2dynu6huzcvjl6vajrvv5e2nntmhmh4vejy58gm4vw5m4qm8t02afknuvry6zuk0d9qvhu8v3lsyzadx9xfjudgjchf2463uegeydaq2y8lacv7rnp7u0wyqx5frp6eht8lrclw8ktf6yz54n9hlpdaq',
        'ur:bytes/3of7/0jsmw5retzcecxhpgz2e6pnzw9qy98m0frafzjuwn324w4yf8xdq0h0cmw/mw5rf7ttadjvzn35ymas2x5ndwjp26dtn8qqv6ndnsrh0fy7f8nvhtfy6u32f376zyjryeujvju6ms9gelua68lqa60wyarldf59xlpcnfes8gd0y0znfmnrj27p0vzv7rauua5fue4kwwjypsz2j32qqkcvwenyvwg3x3vwklgfqthlqng3zwxw928wz65u6lyfyeg5',
        'ur:bytes/4of7/0jsmw5retzcecxhpgz2e6pnzw9qy98m0frafzjuwn324w4yf8xdq0h0cmw/a75mmqaw0fxp8xp47rlq76xx9rsxghy9ynpsmlp3f6p9574pxgjdnr3002w3yxp6nxdmru59f8ye4yrjmxwqtsjwpjzgfrz0c9r6p99t0d57njl2s62jln8325q0hv35llnwumnda4g4eqqkevqhhgm0hyc77fmva38dytq6a52ft5kl8v7wvmqr7kull2zrf0cw37c5',
        'ur:bytes/5of7/0jsmw5retzcecxhpgz2e6pnzw9qy98m0frafzjuwn324w4yf8xdq0h0cmw/nh55upgt8ksh3hclwmqq5dnvk2qpl27lrg0fpnfu630vk75npfqtz529tamtwfk42te3cgfjfxfd5ftllz779y3al4ws66u8yvl6ug2llt97ektzfyyeul35yl2n8k6kekcfcar4kn8rx98r8ape2wnnwzrxesgashcqkud325gtgmztf7jfp3nqmhld5r8trwpxtx2l',
        'ur:bytes/6of7/0jsmw5retzcecxhpgz2e6pnzw9qy98m0frafzjuwn324w4yf8xdq0h0cmw/wpcuz4ddrdt5vh7up75p5ule7xdvfpeq982cgnqc8rmn96qrqsm88cnvh3d4z2t6xf8lqz3d94pz9wk426un6f7gudmw8lu0n5mmxpe5zpcgaweafht5w0f8yy33pdc68se6tj8c0azgy3jqulufwr6wm2fkgx2us753zu4c7zzlzaekg8w7rn3pjwr5vg6q2k7fw88z',
        'ur:bytes/7of7/0jsmw5retzcecxhpgz2e6pnzw9qy98m0frafzjuwn324w4yf8xdq0h0cmw/xf0czn37a3s00qwaf7h49t74he9xkwr9dalfww0hyn9hen2wf5q7sq4d60w8hqcer7y5k0hqa46jaeg56hk92xd0vz4',
    ]:
        print('encode_ur() worked!')
    else:
        print('encode_ur() failed!')

    # Decoding
    workloads = [
            'ur:bytes/7of7/0jsmw5retzcecxhpgz2e6pnzw9qy98m0frafzjuwn324w4yf8xdq0h0cmw/xf0czn37a3s00qwaf7h49t74he9xkwr9dalfww0hyn9hen2wf5q7sq4d60w8hqcer7y5k0hqa46jaeg56hk92xd0vz4',
            'ur:bytes/4of7/0jsmw5retzcecxhpgz2e6pnzw9qy98m0frafzjuwn324w4yf8xdq0h0cmw/a75mmqaw0fxp8xp47rlq76xx9rsxghy9ynpsmlp3f6p9574pxgjdnr3002w3yxp6nxdmru59f8ye4yrjmxwqtsjwpjzgfrz0c9r6p99t0d57njl2s62jln8325q0hv35llnwumnda4g4eqqkevqhhgm0hyc77fmva38dytq6a52ft5kl8v7wvmqr7kull2zrf0cw37c5',
            'ur:bytes/2of7/0jsmw5retzcecxhpgz2e6pnzw9qy98m0frafzjuwn324w4yf8xdq0h0cmw/vm77csd3pnn5mjljtlq4mq570qcvxfty82v9v86yrdq2qt5r2dynu6huzcvjl6vajrvv5e2nntmhmh4vejy58gm4vw5m4qm8t02afknuvry6zuk0d9qvhu8v3lsyzadx9xfjudgjchf2463uegeydaq2y8lacv7rnp7u0wyqx5frp6eht8lrclw8ktf6yz54n9hlpdaq',
            'ur:bytes/5of7/0jsmw5retzcecxhpgz2e6pnzw9qy98m0frafzjuwn324w4yf8xdq0h0cmw/nh55upgt8ksh3hclwmqq5dnvk2qpl27lrg0fpnfu630vk75npfqtz529tamtwfk42te3cgfjfxfd5ftllz779y3al4ws66u8yvl6ug2llt97ektzfyyeul35yl2n8k6kekcfcar4kn8rx98r8ape2wnnwzrxesgashcqkud325gtgmztf7jfp3nqmhld5r8trwpxtx2l',
            'ur:bytes/3of7/0jsmw5retzcecxhpgz2e6pnzw9qy98m0frafzjuwn324w4yf8xdq0h0cmw/mw5rf7ttadjvzn35ymas2x5ndwjp26dtn8qqv6ndnsrh0fy7f8nvhtfy6u32f376zyjryeujvju6ms9gelua68lqa60wyarldf59xlpcnfes8gd0y0znfmnrj27p0vzv7rauua5fue4kwwjypsz2j32qqkcvwenyvwg3x3vwklgfqthlqng3zwxw928wz65u6lyfyeg5',
            'ur:bytes/6of7/0jsmw5retzcecxhpgz2e6pnzw9qy98m0frafzjuwn324w4yf8xdq0h0cmw/wpcuz4ddrdt5vh7up75p5ule7xdvfpeq982cgnqc8rmn96qrqsm88cnvh3d4z2t6xf8lqz3d94pz9wk426un6f7gudmw8lu0n5mmxpe5zpcgaweafht5w0f8yy33pdc68se6tj8c0azgy3jqulufwr6wm2fkgx2us753zu4c7zzlzaekg8w7rn3pjwr5vg6q2k7fw88z',
            'ur:bytes/1of7/0jsmw5retzcecxhpgz2e6pnzw9qy98m0frafzjuwn324w4yf8xdq0h0cmw/typjqlj2vyu9uf2snqd5k43n4vtcavrh5vzst7748ug8asggre70pj3uphqtl6jm30a4umlujxhazpxr4f6kyy94m0z3rr739jr7uppxnq2m565edzsdp5ah4xmrzwp2x678p2mzd4t8pd953luy8axe59trr2n8c740ptrvul3mlupm9jty8cehter5j0zwp7rr2v5a',
    ]
    result = decode_ur(workloads)
    # print('test_random_part_order: result = '.format(result))
    if result == '7e4a61385e2550981b4b5633ab178eb077a30505fbd53f107ec1081e7cf0ca3c0dc0bfea5b8bfb5e6ffc91afd104c3aa756210b5dbc5118fd12c87ee04269815ba6a9968a0d0d3b7a9b631382a36bc70ab626d5670b4b48ff843f4d9a15631aa67c7aaf0ac6ce7e3bff03b2c9643e3375e47493c4e0f8635329d66fdec41b10ce74dcbf25fc15d829e7830c325643a98561f441b40a02e8353493e6afc16192fe99d90d8ca65539af77ddeaccc8943a37563a9ba83675bd5d4da7c60c9a172cf6940cbf0ec8fe04175a629932e3512c5d2aaea3cca3246f40a21ffdc33c3987dc7b880351230eb3759fe3c7dc7b2d3a20a95996ff0b7a0dba834f96beb64c14e3426fb051a936ba41569ab99c0066a6d9c0777a49e49e6cbad24d722a4c7da112432679264b9adc0a8cff9dd1fe0ee9ee2747f6a68537c389a7303a1af23c534ee6392bc17b04cf0fbce7689e66b673a440c04a9454005b0c76664639113458eb7d0902eff04d11138ce2a8ee16a9cd7c8926514efa9bd83ae7a4c139835f0fe0f68c628e0645c8524c30dfc314e825a7aa13224d98e2f7a9d12183a999bb1f28549c99a9072d99c05c24e0c84848c4fc147a094ab7b69e9cbea86952fccf15500fbb234ffe6ee6e6ded515c8016cb017ba36fb931ef276cec4ed22c1aed1495d2df3b3ce66c03f5b9ffa8434bf0e8fb149de94e050b3da178df1f76c00a366cb2801fabdf1a1e90cd3cd45ecb7a930a40b151455f76b726d552f31c21324992da257ff8bde2923dfd5d0d6b87233fae215ffacbecd96249099e7e3427d533db56cdb09c7475b4ce3314e33f43953a7370866cc11d85f00b71b15510b46c4b4fa490c660ddfeda0ceb1b8265995f7071c155ad1b57465fdc0fa81a73f9f19ac4872029d5844c1838f732e803043673e26cbc5b51297a324ff00a2d2d4222bad556b93d27c8e376e3ff8f9d37b3073410708ebb3d4dd7473d27212310b71a3c33a5c8f87f44824640e7f8970f4eda9364195c87a91172b8f085f1773641dde1ce21938746234055bc971ce2325f814e3eec60f781dd4faf52afd5be4a6b38656f7e9739f724cb7ccd4e4d01e802add3dc7b83191f894b3ee0ed752ee514d5ec55':
        print('decode_ur() worked!')
    else:
        print('decode_ur() failed!')


async def test_ur1(*a):
    from ur1.decode_ur import decode_ur
    from ur1.encode_ur import encode_ur
    from ubinascii import unhexlify, hexlify

    # Encoding
    data = '70736274ff01005e0200000001ec609ee4ba6cd94f9fc5aac5ec6a07cf15fa57079501ec866c77885ab8b1d44c0100000000ffffffff015802000000000000220020e62c3bf1cf1e7a78133c4ef8fb21a68b2f0a5519da30d742c4ae321180f5970200000000000100fd88010200000000010153a921bb59af10165684d1dbbb42bff6fedf1867517605319cd46d0a8e1490030000000000ffffffff029c0b000000000000220020e5f40bdb0b4938b97a940912062537bc9b717491c96a5fe949323328e8ae2cf3f1430000000000002200202e691b3a2c57d0b77d4979101dfd3bbd7737dfdf7702f3d4ce9e9d547a04be550400483045022100eacf00d9c626257a3267d4ef69fad45e4f4cefdafeee7825fa09833f39acc8ac02203628f2659b68fd4570b8c835c30225a9ef16d4f65ab7a81e26e61af50ed61e5a01473044022071ce9d40247ce983771e4db332795d92607c34a75e86427ecd936495ff5f32dd022033b162bb1204c72dfe700b965ab56ca1a5137907e2bddf06f7fa8149991849b801695221025c5d8a75673f9810802a54d387f73bcecab2ce327d2c7cb3d01e9423b81f7144210309296fc7ca56609d0bab5623bff5d315a9aaa0646a900598cc384b8f8b3f09ca210328adad6ad3627bdf5fa7562754c3ca8bf01ed742e086654848e595f43b2f14e053ae0000000001012bf1430000000000002200202e691b3a2c57d0b77d4979101dfd3bbd7737dfdf7702f3d4ce9e9d547a04be552202020696b21057f70b9476a75229c93428d0cddceaaac9488e4b2a1f37d24918fe384830450221009fb917bf041cb7e00ace7b57e40d0265ed32d09862b90a13be20db0bb6f65d22022023707aa2f23bde856b1954e7189d9695b6f983e11b0b18fedfe893eaaf76a1f901220203d9277a7c106434329ba12cb7e6a7e3059cd1d3ce675e49a6b998d8497940fc424730440220076e268c09acadf5b22872450463d40c41cb4a231b86c8375aca591a8b2eac23022050e497440a3fd3f6dded6c4b72d54dde1bd62bc3c456111c0696e6458c5236620101030401000000220603d9277a7c106434329ba12cb7e6a7e3059cd1d3ce675e49a6b998d8497940fc421c317184b630000080000000800000008002000080010000000000000022060234745d1d85a741aa0921cfd89fea4a3540c818d7599af30afb637c1960a4e9031c83bd41063000008000000080000000800200008001000000000000002206020696b21057f70b9476a75229c93428d0cddceaaac9488e4b2a1f37d24918fe381c1799c1ce3000008000000080000000800200008001000000000000000105695221020696b21057f70b9476a75229c93428d0cddceaaac9488e4b2a1f37d24918fe38210234745d1d85a741aa0921cfd89fea4a3540c818d7599af30afb637c1960a4e9032103d9277a7c106434329ba12cb7e6a7e3059cd1d3ce675e49a6b998d8497940fc4253ae0000'
    data = hexlify(data)

    # self.qr_sizes = [500, 200, 60]
    result = encode_ur(data, fragment_capacity=200)
    if result == [
        'ur:bytes/1of18/0p90t76gsdfeachgyjsh8plf6g34lepg2r6mk2ehc0ekvwtrtphq3w3c32/tyy9cdesxuenvv3hx3nxvvp3xqcr2efsxgcrqvpsxqcrqvt9vvmrqwt9v56xycfkvdjrjdrx89nxxdtpv93n2etrxesnqdmrvccn2enpx5mnqdeex5crzetr8qmrvcehxuursdtpvguxyvtyxs6xxvp3xqcrqvpsxqcrqenxvenxvenxvccrzdfcxqerqvpsxqcrqvps',
        'ur:bytes/2of18/0p90t76gsdfeachgyjsh8plf6g34lepg2r6mk2ehc0ekvwtrtphq3w3c32/xqcrqvpjxgcrqv3sv5mrycenvfnrzcmxx9jnwcfh8qcnxvmrx3jkvwrxvgerzcfk8p3rye3svy6n2vfev3snxvryxu6ryce5v9jnxv33xyurqe348ymnqv3sxqcrqvpsxqcrqvpsxycrqeny8qurqvfsxgcrqvpsxqcrqvpsxycrzdfnvyunyvtzvg6njctxxycrzd34',
        'ur:bytes/3of18/0p90t76gsdfeachgyjsh8plf6g34lepg2r6mk2ehc0ekvwtrtphq3w3c32/xcurgep3v33xyc35xf3xve3kvejkge338qmrwdf3xumrqdfnxyukxep5xejrqcfcv5cngwfsxqenqvpsxqcrqvpsxqcxvenxvenxvenxxqerjcesvgcrqvpsxqcrqvpsxqcrqv3jxqcryvr9x4nrgvrzv33rqc358yensc3exasnjdps8ycnyvpkxg6nxdmzvvukyde3',
        'ur:bytes/4of18/0p90t76gsdfeachgyjsh8plf6g34lepg2r6mk2ehc0ekvwtrtphq3w3c32/xu6rjvtr8ymxzdtxv5ungwfnxgenxv3cv5uxzefjvdnrxe33xsenqvpsxqcrqvpsxqcrqvpjxgcrqv3sxfjnvwf3vgekzvnrx5mkgvrzxumkgdpexuunzvp3v3nxgvmzvfjrwdenxajxverxxumnqvnxxdjrgcm989jnjep4xsmkzvp5vfjn2dfsxscrqdpcxvcrgdfs',
        'ur:bytes/5of18/0p90t76gsdfeachgyjsh8plf6g34lepg2r6mk2ehc0ekvwtrtphq3w3c32/xgerzvpsv4skxe3sxpjrjcekxgmrydfhvyenyd3hvs6x2e3k89nxzep5x4jnge35vdjkverpvejk2efh8qer2enpxqunsvenvcenjctrvvuxzcesxgerqvekxguxvv3kx5ukyd3cvejrgdfhxp3rscecxv6kxvesxger2cfev4nrzdnyx3nrvdtpvgmkzwp3v5ervefk',
        'ur:bytes/6of18/0p90t76gsdfeachgyjsh8plf6g34lepg2r6mk2ehc0ekvwtrtphq3w3c32/x9skvdfsv4jrvvt9x4snqvf5xuenqdp5xqeryvphx93k2wtyxscrydphvdjnjwpnxumnzef5v33rxvejxuun2epexgmrqdmrxv6xzde4v5urvdpjxajkxepexvmrgwf4venr2e3nxfjxgvpjxgcrxvmzxymrycnzxyerqdrrxuexgen9xucrqc3exc6kzc34xe3kzvtp',
        'ur:bytes/7of18/0p90t76gsdfeachgyjsh8plf6g34lepg2r6mk2ehc0ekvwtrtphq3w3c32/x5cnxdeexqmk2vnzv3jxvvpkvcmkvcfcxy6rjwfexyurgwtz8qcrzd3ex5eryvfsxg6kxdty8psnwdfkxuekvwfcxycrsvpjvy6ngepn8qmkvdenvf3k2cmpvgexxefnxgmkgvnrxa3kyvmyxqck2wf5xgekywp3vcmnzdp5xgcnqves8yerjdnxvvmkxcf4xcmrqwty',
        'ur:bytes/8of18/0p90t76gsdfeachgyjsh8plf6g34lepg2r6mk2ehc0ekvwtrtphq3w3c32/xp3xzc34xcerxcnxvc6kgve3x4snjctpvycrvdpkvyunqvp48yuxxcen8q6xywrx8p3rxe3s893kzv33xqenywrpv3skgdnpvsenvv3hvfjxvdtxvymn2d3jxu6ngcenvdsnscnxxqck2ephxsex2vpcxcmr2dpcxsux2dfex4nrgvmzxfnrzdr9xq6nxct9xqcrqvps',
        'ur:bytes/9of18/0p90t76gsdfeachgyjsh8plf6g34lepg2r6mk2ehc0ekvwtrtphq3w3c32/xqcrqvp3xqcnycnxxy6rxvpsxqcrqvpsxqcrqvpsxgerqvpjxqex2d3ex93rxcfjvv6nwepsvgmnwep58ymnjvfsx9jxvepnvf3xgdehxvmkgenyvcmnwvpjvcekgdrrv5uk2wtyx56rwcfsx33x2df4xgerqv3sxgcrvwfkvgerzvp4xanrwvrz8y6rwdnpxu6nyv3e',
        'ur:bytes/10of18/0p90t76gsdfeachgyjsh8plf6g34lepg2r6mk2ehc0ekvwtrtphq3w3c32/vvunxdpj8pjrqcmyv33k2ctpv93njdpc8pjngc3jvyckvvehvsergwf38pnx2vecxsurxvp5x5cryv33xqcrjenz8ycnwcnxxq6rzcmzxajnqvrpvdjnwc34xajngvryxqervdt9vsenyeps8yurvvnz8ycxzvfnvfjnyvryvgcxyc3kvcmr2epjxgcryv3sxgenwvph',
        'ur:bytes/11of18/0p90t76gsdfeachgyjsh8plf6g34lepg2r6mk2ehc0ekvwtrtphq3w3c32/v9snye3jxd3xgefcx5mxyvfex56x2de38qukgwfk8y6kydnx8yurxef3x93rqc338pnx2erxv5urjvm9v9skvdekvyckvwfsxyeryvpjxqekgwfjxumkzdmrxycrvdpnxsenywtzvycnycmzxajnvcfhv5enqdfevdjrzepnvdjnvde4v56rjcfkvgunjwry8q6rjdee',
        'ur:bytes/12of18/0p90t76gsdfeachgyjsh8plf6g34lepg2r6mk2ehc0ekvwtrtphq3w3c32/xscxvce5xg6rwvesxs6rqv3jxqcrwdn9xgmrsces89skxctyvc6kyv3j8qmnydp4xq6rvvmyxscxxdp3vd3rgcfjxvckywpkvvurxde4v93kzdfex9snsc3jv4skxv3nxqeryvp4xpjngwfhxs6rqcfnvejrxe3kv3jx2epkvv6xydejvs6ngeryv5ckyepkxf3xxvmr',
        'ur:bytes/13of18/0p90t76gsdfeachgyjsh8plf6g34lepg2r6mk2ehc0ekvwtrtphq3w3c32/xs6nvvf3x93nqd3exejnvdp48p3n2v3nxcmryvp3xqcnqvesxscrzvpsxqcrqvpjxgcrvvpnvsunydehvymkxvfsxc6rxdpnxgukycf3xf3kydm9xesnwefnxq6njcmyx9jrxcm9xcmn2ef589snvc3e8yuxgwp58ymnjdpsve3ngv33vvenzde38q6xyd3nxqcrqvps',
        'ur:bytes/14of18/0p90t76gsdfeachgyjsh8plf6g34lepg2r6mk2ehc0ekvwtrtphq3w3c32/8qcrqvpsxqcrqwpsxqcrqvpsxqurqvpjxqcrqvpcxqcrzvpsxqcrqvpsxqcrqvpsxqcryv3sxccryve5xu6r2ep3vsur2cfhxsckzcfs8yerzcmxvsurjen9vy6xzve4xscxxwp38pjrwdfe89skvvesv9nxyd3nxa3nzwfkxpsngefexqenzcecxd3xgdp3xqmrxvps',
        'ur:bytes/15of18/0p90t76gsdfeachgyjsh8plf6g34lepg2r6mk2ehc0ekvwtrtphq3w3c32/xqcrqwpsxqcrqvpsxqurqvpsxqcrqvpcxqcryvpsxqcrsvpsxycrqvpsxqcrqvpsxqcrqvpsxgerqd3sxgcrvwfkvgerzvp4xanrwvrz8y6rwdnpxu6nyv3evvunxdpj8pjrqcmyv33k2ctpv93njdpc8pjngc3jvyckvvehvsergwf38pnx2vecx93nzdee893nzcm9',
        'ur:bytes/16of18/0p90t76gsdfeachgyjsh8plf6g34lepg2r6mk2ehc0ekvwtrtphq3w3c32/xvcrqvpsxqurqvpsxqcrqvpcxqcrqvpsxqcrsvpsxgcrqvps8qcrqvfsxqcrqvpsxqcrqvpsxqcrqvp3xq6nvwf4xgerzvpjxqmrjdnzxgcnqdfhvcmnqc3exsmnvcfhx5erywtr8yengv3cvscxxeryvdjkzctpvvungwpcv56xyvnpx9nrxdmyxg6rjvfcvejnxwpj',
        'ur:bytes/17of18/0p90t76gsdfeachgyjsh8plf6g34lepg2r6mk2ehc0ekvwtrtphq3w3c32/xycryve5xu6r2ep3vsur2cfhxsckzcfs8yerzcmxvsurjen9vy6xzve4xscxxwp38pjrwdfe89skvvesv9nxyd3nxa3nzwfkxpsngefexqenyvfsxdjrjv3hxasnwce3xqmrgve5xverjcnpxyexxc3hv5mxzdm9xvcr2wtrvsckgvmrv5mrwdt9xsukzdnz8yunsepc',
        'ur:bytes/18of18/0p90t76gsdfeachgyjsh8plf6g34lepg2r6mk2ehc0ekvwtrtphq3w3c32/xsunwwf5xpnxxdpjx5ekzefsxqcrqyyqyag'
    ]:
        print('encode_ur() worked!')
    else:
        print('encode_ur() failed!')
        print('result={}'.format(result))


    # Decoding
    workloads = [
        'ur:bytes/1of18/0p90t76gsdfeachgyjsh8plf6g34lepg2r6mk2ehc0ekvwtrtphq3w3c32/tyy9cdesxuenvv3hx3nxvvp3xqcr2efsxgcrqvpsxqcrqvt9vvmrqwt9v56xycfkvdjrjdrx89nxxdtpv93n2etrxesnqdmrvccn2enpx5mnqdeex5crzetr8qmrvcehxuursdtpvguxyvtyxs6xxvp3xqcrqvpsxqcrqenxvenxvenxvccrzdfcxqerqvpsxqcrqvps',
        'ur:bytes/2of18/0p90t76gsdfeachgyjsh8plf6g34lepg2r6mk2ehc0ekvwtrtphq3w3c32/xqcrqvpjxgcrqv3sv5mrycenvfnrzcmxx9jnwcfh8qcnxvmrx3jkvwrxvgerzcfk8p3rye3svy6n2vfev3snxvryxu6ryce5v9jnxv33xyurqe348ymnqv3sxqcrqvpsxqcrqvpsxycrqeny8qurqvfsxgcrqvpsxqcrqvpsxycrzdfnvyunyvtzvg6njctxxycrzd34',
        'ur:bytes/3of18/0p90t76gsdfeachgyjsh8plf6g34lepg2r6mk2ehc0ekvwtrtphq3w3c32/xcurgep3v33xyc35xf3xve3kvejkge338qmrwdf3xumrqdfnxyukxep5xejrqcfcv5cngwfsxqenqvpsxqcrqvpsxqcxvenxvenxvenxxqerjcesvgcrqvpsxqcrqvpsxqcrqv3jxqcryvr9x4nrgvrzv33rqc358yensc3exasnjdps8ycnyvpkxg6nxdmzvvukyde3',
        'ur:bytes/4of18/0p90t76gsdfeachgyjsh8plf6g34lepg2r6mk2ehc0ekvwtrtphq3w3c32/xu6rjvtr8ymxzdtxv5ungwfnxgenxv3cv5uxzefjvdnrxe33xsenqvpsxqcrqvpsxqcrqvpjxgcrqv3sxfjnvwf3vgekzvnrx5mkgvrzxumkgdpexuunzvp3v3nxgvmzvfjrwdenxajxverxxumnqvnxxdjrgcm989jnjep4xsmkzvp5vfjn2dfsxscrqdpcxvcrgdfs',
        'ur:bytes/5of18/0p90t76gsdfeachgyjsh8plf6g34lepg2r6mk2ehc0ekvwtrtphq3w3c32/xgerzvpsv4skxe3sxpjrjcekxgmrydfhvyenyd3hvs6x2e3k89nxzep5x4jnge35vdjkverpvejk2efh8qer2enpxqunsvenvcenjctrvvuxzcesxgerqvekxguxvv3kx5ukyd3cvejrgdfhxp3rscecxv6kxvesxger2cfev4nrzdnyx3nrvdtpvgmkzwp3v5ervefk',
        'ur:bytes/6of18/0p90t76gsdfeachgyjsh8plf6g34lepg2r6mk2ehc0ekvwtrtphq3w3c32/x9skvdfsv4jrvvt9x4snqvf5xuenqdp5xqeryvphx93k2wtyxscrydphvdjnjwpnxumnzef5v33rxvejxuun2epexgmrqdmrxv6xzde4v5urvdpjxajkxepexvmrgwf4venr2e3nxfjxgvpjxgcrxvmzxymrycnzxyerqdrrxuexgen9xucrqc3exc6kzc34xe3kzvtp',
        'ur:bytes/7of18/0p90t76gsdfeachgyjsh8plf6g34lepg2r6mk2ehc0ekvwtrtphq3w3c32/x5cnxdeexqmk2vnzv3jxvvpkvcmkvcfcxy6rjwfexyurgwtz8qcrzd3ex5eryvfsxg6kxdty8psnwdfkxuekvwfcxycrsvpjvy6ngepn8qmkvdenvf3k2cmpvgexxefnxgmkgvnrxa3kyvmyxqck2wf5xgekywp3vcmnzdp5xgcnqves8yerjdnxvvmkxcf4xcmrqwty',
        'ur:bytes/8of18/0p90t76gsdfeachgyjsh8plf6g34lepg2r6mk2ehc0ekvwtrtphq3w3c32/xp3xzc34xcerxcnxvc6kgve3x4snjctpvycrvdpkvyunqvp48yuxxcen8q6xywrx8p3rxe3s893kzv33xqenywrpv3skgdnpvsenvv3hvfjxvdtxvymn2d3jxu6ngcenvdsnscnxxqck2ephxsex2vpcxcmr2dpcxsux2dfex4nrgvmzxfnrzdr9xq6nxct9xqcrqvps',
        'ur:bytes/9of18/0p90t76gsdfeachgyjsh8plf6g34lepg2r6mk2ehc0ekvwtrtphq3w3c32/xqcrqvp3xqcnycnxxy6rxvpsxqcrqvpsxqcrqvpsxgerqvpjxqex2d3ex93rxcfjvv6nwepsvgmnwep58ymnjvfsx9jxvepnvf3xgdehxvmkgenyvcmnwvpjvcekgdrrv5uk2wtyx56rwcfsx33x2df4xgerqv3sxgcrvwfkvgerzvp4xanrwvrz8y6rwdnpxu6nyv3e',
        'ur:bytes/10of18/0p90t76gsdfeachgyjsh8plf6g34lepg2r6mk2ehc0ekvwtrtphq3w3c32/vvunxdpj8pjrqcmyv33k2ctpv93njdpc8pjngc3jvyckvvehvsergwf38pnx2vecxsurxvp5x5cryv33xqcrjenz8ycnwcnxxq6rzcmzxajnqvrpvdjnwc34xajngvryxqervdt9vsenyeps8yurvvnz8ycxzvfnvfjnyvryvgcxyc3kvcmr2epjxgcryv3sxgenwvph',
        'ur:bytes/11of18/0p90t76gsdfeachgyjsh8plf6g34lepg2r6mk2ehc0ekvwtrtphq3w3c32/v9snye3jxd3xgefcx5mxyvfex56x2de38qukgwfk8y6kydnx8yurxef3x93rqc338pnx2erxv5urjvm9v9skvdekvyckvwfsxyeryvpjxqekgwfjxumkzdmrxycrvdpnxsenywtzvycnycmzxajnvcfhv5enqdfevdjrzepnvdjnvde4v56rjcfkvgunjwry8q6rjdee',
        'ur:bytes/12of18/0p90t76gsdfeachgyjsh8plf6g34lepg2r6mk2ehc0ekvwtrtphq3w3c32/xscxvce5xg6rwvesxs6rqv3jxqcrwdn9xgmrsces89skxctyvc6kyv3j8qmnydp4xq6rvvmyxscxxdp3vd3rgcfjxvckywpkvvurxde4v93kzdfex9snsc3jv4skxv3nxqeryvp4xpjngwfhxs6rqcfnvejrxe3kv3jx2epkvv6xydejvs6ngeryv5ckyepkxf3xxvmr',
        'ur:bytes/13of18/0p90t76gsdfeachgyjsh8plf6g34lepg2r6mk2ehc0ekvwtrtphq3w3c32/xs6nvvf3x93nqd3exejnvdp48p3n2v3nxcmryvp3xqcnqvesxscrzvpsxqcrqvpjxgcrvvpnvsunydehvymkxvfsxc6rxdpnxgukycf3xf3kydm9xesnwefnxq6njcmyx9jrxcm9xcmn2ef589snvc3e8yuxgwp58ymnjdpsve3ngv33vvenzde38q6xyd3nxqcrqvps',
        'ur:bytes/14of18/0p90t76gsdfeachgyjsh8plf6g34lepg2r6mk2ehc0ekvwtrtphq3w3c32/8qcrqvpsxqcrqwpsxqcrqvpsxqurqvpjxqcrqvpcxqcrzvpsxqcrqvpsxqcrqvpsxqcryv3sxccryve5xu6r2ep3vsur2cfhxsckzcfs8yerzcmxvsurjen9vy6xzve4xscxxwp38pjrwdfe89skvvesv9nxyd3nxa3nzwfkxpsngefexqenzcecxd3xgdp3xqmrxvps',
        'ur:bytes/15of18/0p90t76gsdfeachgyjsh8plf6g34lepg2r6mk2ehc0ekvwtrtphq3w3c32/xqcrqwpsxqcrqvpsxqurqvpsxqcrqvpcxqcryvpsxqcrsvpsxycrqvpsxqcrqvpsxqcrqvpsxgerqd3sxgcrvwfkvgerzvp4xanrwvrz8y6rwdnpxu6nyv3evvunxdpj8pjrqcmyv33k2ctpv93njdpc8pjngc3jvyckvvehvsergwf38pnx2vecx93nzdee893nzcm9',
        'ur:bytes/16of18/0p90t76gsdfeachgyjsh8plf6g34lepg2r6mk2ehc0ekvwtrtphq3w3c32/xvcrqvpsxqurqvpsxqcrqvpcxqcrqvpsxqcrsvpsxgcrqvps8qcrqvfsxqcrqvpsxqcrqvpsxqcrqvp3xq6nvwf4xgerzvpjxqmrjdnzxgcnqdfhvcmnqc3exsmnvcfhx5erywtr8yengv3cvscxxeryvdjkzctpvvungwpcv56xyvnpx9nrxdmyxg6rjvfcvejnxwpj',
        'ur:bytes/17of18/0p90t76gsdfeachgyjsh8plf6g34lepg2r6mk2ehc0ekvwtrtphq3w3c32/xycryve5xu6r2ep3vsur2cfhxsckzcfs8yerzcmxvsurjen9vy6xzve4xscxxwp38pjrwdfe89skvvesv9nxyd3nxa3nzwfkxpsngefexqenyvfsxdjrjv3hxasnwce3xqmrgve5xverjcnpxyexxc3hv5mxzdm9xvcr2wtrvsckgvmrv5mrwdt9xsukzdnz8yunsepc',
        'ur:bytes/18of18/0p90t76gsdfeachgyjsh8plf6g34lepg2r6mk2ehc0ekvwtrtphq3w3c32/xsunwwf5xpnxxdpjx5ekzefsxqcrqyyqyag'
    ]
    encoded_data = decode_ur(workloads)
    result = unhexlify(encoded_data).decode('utf-8')

    # print('test_random_part_order: result = '.format(result))
    if result == '70736274ff01005e0200000001ec609ee4ba6cd94f9fc5aac5ec6a07cf15fa57079501ec866c77885ab8b1d44c0100000000ffffffff015802000000000000220020e62c3bf1cf1e7a78133c4ef8fb21a68b2f0a5519da30d742c4ae321180f5970200000000000100fd88010200000000010153a921bb59af10165684d1dbbb42bff6fedf1867517605319cd46d0a8e1490030000000000ffffffff029c0b000000000000220020e5f40bdb0b4938b97a940912062537bc9b717491c96a5fe949323328e8ae2cf3f1430000000000002200202e691b3a2c57d0b77d4979101dfd3bbd7737dfdf7702f3d4ce9e9d547a04be550400483045022100eacf00d9c626257a3267d4ef69fad45e4f4cefdafeee7825fa09833f39acc8ac02203628f2659b68fd4570b8c835c30225a9ef16d4f65ab7a81e26e61af50ed61e5a01473044022071ce9d40247ce983771e4db332795d92607c34a75e86427ecd936495ff5f32dd022033b162bb1204c72dfe700b965ab56ca1a5137907e2bddf06f7fa8149991849b801695221025c5d8a75673f9810802a54d387f73bcecab2ce327d2c7cb3d01e9423b81f7144210309296fc7ca56609d0bab5623bff5d315a9aaa0646a900598cc384b8f8b3f09ca210328adad6ad3627bdf5fa7562754c3ca8bf01ed742e086654848e595f43b2f14e053ae0000000001012bf1430000000000002200202e691b3a2c57d0b77d4979101dfd3bbd7737dfdf7702f3d4ce9e9d547a04be552202020696b21057f70b9476a75229c93428d0cddceaaac9488e4b2a1f37d24918fe384830450221009fb917bf041cb7e00ace7b57e40d0265ed32d09862b90a13be20db0bb6f65d22022023707aa2f23bde856b1954e7189d9695b6f983e11b0b18fedfe893eaaf76a1f901220203d9277a7c106434329ba12cb7e6a7e3059cd1d3ce675e49a6b998d8497940fc424730440220076e268c09acadf5b22872450463d40c41cb4a231b86c8375aca591a8b2eac23022050e497440a3fd3f6dded6c4b72d54dde1bd62bc3c456111c0696e6458c5236620101030401000000220603d9277a7c106434329ba12cb7e6a7e3059cd1d3ce675e49a6b998d8497940fc421c317184b630000080000000800000008002000080010000000000000022060234745d1d85a741aa0921cfd89fea4a3540c818d7599af30afb637c1960a4e9031c83bd41063000008000000080000000800200008001000000000000002206020696b21057f70b9476a75229c93428d0cddceaaac9488e4b2a1f37d24918fe381c1799c1ce3000008000000080000000800200008001000000000000000105695221020696b21057f70b9476a75229c93428d0cddceaaac9488e4b2a1f37d24918fe38210234745d1d85a741aa0921cfd89fea4a3540c818d7599af30afb637c1960a4e9032103d9277a7c106434329ba12cb7e6a7e3059cd1d3ce675e49a6b998d8497940fc4253ae0000':
        print('decode_ur() worked!')
    else:
        print('decode_ur() failed!')
        print('result={}'.format(result))

async def battery_mon(*a):
    from battery_mon import battery_mon
    await battery_mon()

async def generate_settings_error(*a):
    from settings import Settings
    s = Settings()
    s.load()
    s.set('sats_highscore', 1234)
    s.save()

async def generate_settings_error2(*a):
    from common import settings

    for i in range(100):
        settings.set('test', i)
        await settings.save()
        await sleep_ms(100)

async def toggle_demo(*a):
    import stash

    import common
    common.demo_active = not common.demo_active

# Repeatedly fetch seed values to try to make it fail (sometimes it does)
async def test_fetch_seeds(*a):
    good = 0
    bad = 0

    for i in range(100):
        try:
            with stash.SensitiveValues() as sv:
                assert sv.mode == 'words'       # protected by menu item predicate

                words = trezorcrypto.bip39.from_data(sv.raw).split(' ')

                msg = 'Seed words (%d):\n' % len(words)
                msg += '\n'.join('%2d: %s' % (i+1, w) for i, w in enumerate(words))

                pw = stash.bip39_passphrase
                if pw:
                    msg += '\n\nBIP39 Passphrase:\n%s' % stash.bip39_passphrase

                # print('msg={}'.format(msg))
                stash.blank_object(msg)
                good += 1

        except Exception as e:
            bad +=1
            # print('Exception: {}'.format(e))
            # print('ERROR fetching words!')


    # print('good={} bad={}'.format(good, bad))

async def read_ambient(*a):
    for i in range(10):
        level = system.read_ambient()
        # print('Ambient level = {}'.format(level))


async def test_seed_check(*a):
    seed_words = ['oxygen', 'weapon', 'flee', 'kite', 'bid', 'video', 'coach', 'wish',
                  'invest', 'river', 'vocal', 'sugar', 'help', 'delay', 'outer', 'cruise',
                  'pupil', 'friend', 'disease', 'afraid', 'century', 'actor', 'another', 'impact']
    seed_check = SeedCheckUX(seed_words=seed_words)
    result = await seed_check.show()

    # print('seed_check.is_check_valid = {}'.format(seed_check.is_check_valid))


async def test_derive_addresses(*a):
    import utime
    import stash
    import chains
    from public_constants import AF_P2WPKH
    from common import system

    n = 100
    chain = chains.current_chain()

    addrs = []
    path = "m/84'/0'/{account}'/{change}/{idx}"

    system.turbo(True)
    start_time = utime.ticks_ms()
    with stash.SensitiveValues() as sv:
        for idx in range(n):
            subpath = path.format(account=0, change=0, idx=idx)
            node = sv.derive_path(subpath, register=False)
            addr = chain.address(node, AF_P2WPKH)
            addrs.append(addr)
            # print("{} => {}".format(subpath, addr))

        stash.blank_object(node)
    end_time = utime.ticks_ms()
    system.turbo(False)

    print('Elapsed = {} secs'.format( round(float(end_time - start_time) / 1000, 2) ))

    idx = 0
    for addr in addrs:
        subpath = path.format(account=0, change=0, idx=idx)
        print("{} => {}".format(subpath, addr))
        idx += 1


# Test function only
async def supply_chain_challenge(*a):
    from trezorcrypto import sha256
    from common import noise, system
    from noise_source import NoiseSource
    from ubinascii import hexlify

    # Make a challenge
    challenge = bytearray(32)
    noise.random_bytes(challenge, NoiseSource.ALL)
    # print('challenge:          {}'.format(hexlify(challenge).decode('utf-8')))

    # Hash the challenge with slot 7
    response = bytearray(32)
    if system.supply_chain_challenge(challenge, response) == False:
        pass
        # print('ERROR: Unable to complete supply chain challenge!')
    else:
        # This is the secret in the SE now
        # NOTE: Padded at the end with zeros?
        slot7 = b'\x01\x01\x01\x01\x01\x01\x01\x01\x01\x01\x01\x01\x01\x01\x01\x01\x01\x01\x01\x01\x01\x01\x01\x01\x01\x01\x01\x01\x01\x01\x01\x01'
        # slot7 = b'\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00'
        expected_response = bytearray(32)
        system.hmac_sha256(slot7, challenge, expected_response)

        # print('expected_response:  {}'.format(hexlify(expected_response).decode('utf-8')))
        # print('response:           {}\n'.format(hexlify(response).decode('utf-8')))

async def test_write_flash_cache(*a):
    from common import flash_cache, system

    system.turbo(True)
    flash_cache.set('utxos', {'foo': 1234, 'bar': [1,2,3,4]})
    system.turbo(False)

async def test_read_flash_cache(*a):
    from common import flash_cache, system
    system.turbo(True)
    flash_cache.load()

    utxos = flash_cache.get('utxos', None)
    # print('utxos={}'.format(utxos))
    system.turbo(False)

async def toggle_screenshot_mode(*a):
    import common
    common.screenshot_mode_enabled = not common.screenshot_mode_enabled

    if common.screenshot_mode_enabled:
        await ux_show_story('Press and release the aA1 key in the lower right corner of the keypad to save a screenshot to the microSD card.\n\nIf no microSD is inserted, nothing will happen.',
            title='Screenshots', center=True, center_vertically=True)
    # print('common.screenshot_mode_enabled={}'.format(common.screenshot_mode_enabled))

async def toggle_snapshot_mode(*a):
    import common
    common.snapshot_mode_enabled = not common.snapshot_mode_enabled
    # print('common.snapshot_mode_enabled={}'.format(common.snapshot_mode_enabled))

async def toggle_battery_mon(*a):
    import common
    common.enable_battery_mon = not common.enable_battery_mon
    # print('common.enable_battery_mon={}'.format(common.enable_battery_mon))

# Remove all account info and multisig info - TESTING ONLY
async def clear_accts(*a):
    from common import settings
    settings.remove('multisig')
    settings.remove('accounts')
    settings.remove('wallet_prog')

async def test_folders(*a):
    import uos
    import os
    from files import CardSlot, CardMissingError
    from utils import get_backups_folder_path

    try:
        with CardSlot() as card:
            path = get_backups_folder_path()
            try:
                print('Creating backups')
                uos.mkdir(path)
            except Exception as e:
                print('Backups folder already exists!')
                pass

            fname = '{}/passport-backup-1.bin'.format(path)
            with open(fname, 'wb') as fd:
                fd.write('{ "acb": 123, "def": 456 }')

    except Exception as e:
        print('Exception: {}'.format(e))

async def make_accounts_menu(menu, label, item):
    from accounts import AllAccountsMenu
    # List of all created accounts and ability to create a new account
    rv = AllAccountsMenu.construct()
    return AllAccountsMenu(rv, title=item.arg)

async def reset_device(*a):
    from common import system
    system.reset()

async def test_battery_calcs(*a):
    from periodic import calc_battery_percent

    for voltage in range(2400,3101,10):
        p = calc_battery_percent(0, voltage);  # current is ignored for now
        # print('voltage={} => {}%\n'.format(voltage, p))
        print('{},{}'.format(voltage, p))

async def clear_ovc(*a):
    from history import OutptValueCache
    from common import flash_cache
    OutptValueCache.clear()
