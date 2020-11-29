# SPDX-FileCopyrightText: 2020 Foundation Devices, Inc.  <hello@foundationdevices.com>
# SPDX-License-Identifier: GPL-3.0-or-later
#
# SPDX-FileCopyrightText: 2018 Coinkite, Inc.  <coldcardwallet.com>
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
from common import settings, system, noise
from utils import imported, pretty_short_delay, xfp2str,swab32
from ux import (the_ux, ux_confirm, ux_dramatic_pause, ux_enter_pin,
                ux_enter_number, ux_enter_text, ux_scan_qr_code, ux_shutdown,
                ux_show_story, ux_show_story_sequence, ux_show_text_as_ur, ux_show_word_list)
from se_commands import *
import trezorcrypto

async def test_normal_menu():
    goto_top_menu()


async def start_selftest(*args):

    if len(args) and not version.is_factory_mode():
        # called from inside menu, not directly
        if not await ux_confirm('''Selftest destroys settings on other profiles (not seeds). Requires microSD card and might have other consequences. Recommended only for factory.'''):
            return

    with imported('selftest') as st:
        await st.start_selftest()

    settings.save()


async def needs_microsd():
    # Standard msg shown if no SD card detected when we need one.
    await ux_show_story("Please insert a microSD card before attempting this operation.")


async def needs_primary():
    # Standard msg shown if action can't be done w/o main PIN
    await ux_show_story("Only the holder of the main PIN (not the secondary) can perform this function. Please start over with the main PIN.")


async def accept_terms(*a):
    # do nothing if they have accepted the terms once (ever), otherwise
    # force them to read message...

    if settings.get('terms_ok'):
        return

    while 1:
        ch = await ux_show_story("""\
Welcome to Passport! Congratulations for taking the first step towards sovereignty and ownership of your Bitcoin.

Please accept our Terms of Use. You can read the full terms at:

foundationdevices.com/passport-terms""", left_btn='SHUTDOWN', right_btn='CONTINUE', scroll_label='MORE')

        print('accept_terms() ch={}'.format(ch))
        if ch == 'y':
            accepted_terms = await ux_confirm('I confirm that I have read and accept the Terms of Use.', negative_btn='BACK', positive_btn='I ACCEPT')
            if accepted_terms:
                # Note fact they accepted the terms. Annoying to ask user more than once.
                settings.set('terms_ok', 1)
                settings.save()
                break

        elif ch == 'x':
            # We only return from here if the user chose to not shutdown
            await ux_shutdown()


async def view_ident(*a):
    # show the XPUB, and other ident on screen
    from common import settings
    import stash

    tpl = '''\
Master Key Fingerprint:

{xfp}

Fingerprint as LE32:

{xfp_le}

Extended Master Key:

{xpub}
'''
    my_xfp = settings.get('xfp', 0)
    my_xfp_le = swab32(my_xfp)
    msg = tpl.format(xpub=settings.get('xpub', '(none yet)'),
                     xfp=xfp2str(my_xfp), xfp_le=xfp2str(my_xfp_le),
                     serial=version.serial_number())

    if stash.bip39_passphrase:
        msg += '\nBIP39 passphrase is in effect.\n'

    await ux_show_story(msg, center=True)


async def maybe_dev_menu(*a):
    from common import is_devmode

    if not is_devmode:
        ok = await ux_confirm('Developer features could be used to weaken security or release key material.\n\nDo not proceed unless you know what you are doing and why.')

        if not ok:
            return None

    from flow import DevelopersMenu
    return DevelopersMenu


async def microsd_upgrade(*a):
    # Upgrade vis microSD card
    # - search for a particular file
    # - verify it lightly
    # - erase serial flash
    # - copy it over (slow)
    # - reboot into bootloader, which finishes install

    fn = await file_picker('Pick firmware image to use (.BIN)')

    if not fn:
        return

    failed = None

    with CardSlot() as card:
        with open(fn, 'rb') as fp:
            from common import sf, dis
            import os

            offset = 0
            s = os.stat(fn)
            size = s[6]

            # we also put a copy of special signed header at the end of the flash
            # from sigheader import FW_HEADER_OFFSET, FW_HEADER_SIZE

            # # read just the signature header
            # hdr = bytearray(FW_HEADER_SIZE)
            # fp.seek(offset + FW_HEADER_OFFSET)
            # rv = fp.readinto(hdr)
            # assert rv == FW_HEADER_SIZE

            # check header values

            # copy binary into serial flash
            fp.seek(offset)

            buf = bytearray(256)        # must be flash page size
            pos = 0
            update_display = 0
            while pos <= size:
                # print('pos = {}'.format(pos))
                # Update progress bar every 50 flash pages
                if update_display % 50 == 0:
                    dis.fullscreen("Preparing Update...", percent=pos/size)
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
        await ux_show_story(failed, title='Sorry!')
        return

    # continue process...
    print("RESTARTING!")

    # Show final progress bar at 100% and change message
    dis.fullscreen("Restarting...", percent=1)
    await sleep_ms(1000)

    import machine
    machine.reset()

async def reset_self(*a):
    import machine
    machine.soft_reset()
    # NOT REACHED


# TODO: Convert this to a state machine
async def initial_pin_setup(*a):
    from common import pa, dis, settings, loop

    # First time they select a PIN of any type.
    title = 'Choose PIN'

    while 1:
        ch = await ux_show_story('''\
Passport uses two PINs. Each PIN must be 2 to 6 digits long.

The first is your Security Code. This PIN is used to verify your Passport has not been swapped or tampered with.

The second is your Login PIN. This PIN allows you to unlock and use Passport.
''', title=title, scroll_label='MORE')
        if ch == 'y':

            while 1:
                ch = await ux_show_story('''\
There is no way to recover a lost PIN or factory reset your Passport.

Please write down your PINs somewhere safe or store them in a password manager.''', title='WARNING', scroll_label='MORE')

                if ch != 'y':
                    break

                # do the actual picking
                from login_ux import EnterNewPinUX
                new_pin_ux = EnterNewPinUX()
                await new_pin_ux.show()
                pin = new_pin_ux.pin
                print('pin = {}'.format(pin))

                if pin is None:
                    return

                # New pin is being saved
                dis.fullscreen("Saving...")

                try:
                    assert pa.is_blank()

                    pa.change(new_pin=pin)

                    # check it? kinda, but also get object into normal "logged in" state
                    pa.setup(pin)
                    ok = pa.login()
                    assert ok

                    # must re-read settings after login, because they are encrypted
                    # with a key derived from the main secret.
                    settings.set_key()
                    settings.load()
                except Exception as e:
                    print("Exception: {}".format(e))

                from menu import MenuSystem
                from flow import NoWalletMenu
                return MenuSystem(NoWalletMenu)


async def login_countdown(minutes):
    # show a countdown, which may need to
    # run for multiple **days**
    from common import dis
    from display import FontSmall, FontLarge

    sec = minutes * 60
    while sec:
        dis.clear()
        y = 0
        dis.text(None, y, 'Login countdown in', font=FontSmall)
        y += 14
        dis.text(None, y, 'effect. Must wait:', font=FontSmall)
        y += 14
        y += 5

        dis.text(None, y, pretty_short_delay(sec), font=FontLarge)

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
    from common import pa, loop, settings, dis

    print('pa.is_successful() = {}'.format(pa.is_successful()))
    while not pa.is_successful():
        login_ux = LoginUX()

        try:
            await login_ux.show()
        except Exception as e:
            print('ERROR when logging in: {}'.format(e))
            # not allowed!
            pass

    settings.set_key()
    settings.load()

    # Apply screen brightness
    dis.set_brightness(settings.get('screen_brightness', 100))

    print('!!!!LOGGED IN!!!!')


async def logout_now(*a):
    # wipe memory and lock up
    from utils import clean_shutdown
    clean_shutdown()


async def login_now(*a):
    # wipe memory and reboot
    from utils import clean_shutdown
    clean_shutdown(2)

async def start_seed_import(menu, label, item):
    import seed
    return seed.WordNestMenu(item.arg)


async def start_b39_pw(menu, label, item):
    if not settings.get('b39skip', False):
        ch = await ux_show_story('''\
You may add a passphrase to your BIP39 seed words. \
This creates an entirely new wallet, for every possible passphrase.

By default, Passport uses an empty string as the passphrase.

On the next menu, you can enter a passphrase by selecting \
individual letters, choosing from the word list (recommended), \
or by typing numbers.

Please write down the fingerprint of all your wallets, so you can \
confirm when you've got the right passphrase. (If you are writing down \
the passphrase as well, it's okay to put them together.) There is no way for \
Passport to know if your password is correct, and if you have it wrong, \
you will be looking at an empty wallet.

Limitations: 100 characters max length, ASCII \
characters 32-126 (0x20-0x7e) only.

OK to start.
X to go back. Or press 2 to hide this message forever.
''')
        if ch == '2':
            settings.set('b39skip', True)
        if ch == 'x':
            return

    import seed
    return seed.PassphraseMenu()


async def create_new_wallet(*a):
    from ubinascii import hexlify as b2a_hex
    import seed
    wallet_seed_bytes = seed.create_new_wallet_seed()
    print('wallet_seed_bytes = {}'.format(b2a_hex(wallet_seed_bytes)))

    mnemonic_str = trezorcrypto.bip39.from_data(wallet_seed_bytes)
    print('mnemonic = {}'.format(mnemonic_str))
    mnemonic_words = mnemonic_str.split(' ')

    # Show new wallet seed words to user
    msg = 'Seed words (%d):\n' % len(mnemonic_words)
    msg += '\n'.join('%2d: %s' % (i+1, w) for i, w in enumerate(mnemonic_words))

    trezor_seed = trezorcrypto.bip39.seed(mnemonic_str, '')
    print('trezor_seed = {}'.format(b2a_hex(trezor_seed)))

    result = await ux_show_story(msg, sensitive=True, title="New Seed", right_btn='DONE')
    if result == 'y':
        # TODO: Quiz user on all words in random order to ensure they remember them all

        # Set the seed into the SE
        seed.save_wallet_seed(wallet_seed_bytes)

    goto_top_menu()


async def import_wallet(menu, label, item):
    from foundation import bip39
    from ubinascii import hexlify as b2a_hex
    import seed

    entropy = bytearray(33)  # Includes and extra byte for the checksum bits

    result = ux_show_story('''On the next screen you'll be able to restore your seed using predictive text input. If you'd like to enter "car" for example, please type 2-2-7 and select "car" from the dropdown.''')
    if result ==  'x':
        return

    fake_it = False
    if fake_it:
        # mnemonic = 'circle ecology lazy world fuel plate column priority crouch midnight scorpion cute defense enforce mention display dove review churn term canvas donate square broken'
        mnemonic = 'park minute parrot ketchup river vital gravity wagon peanut inform craft amount erosion regular rent attack rubber then auto visa upon either fresh other'
        # mnemonic = 'fabric humor guess asset day palace wealth spare trend seek focus empower hair advance myself defy grain inhale market noodle right need joke scatter'
    else:
        from seed_phrase_ux import SeedEntryUX
        seed_phrase_entry = SeedEntryUX(seed_len=item.arg)
        await seed_phrase_entry.show()
        if not seed_phrase_entry.is_seed_valid:
            return

        # Seed is valid, so go ahead and convert the mnemonic to seed bits and save it
        mnemonic = ' '.join(seed_phrase_entry.words)

    print('mnemonic = {}'.format(mnemonic))
    bip = bip39()  # TODO: Can't we have static methods?
    bip.mnemonic_to_entropy(mnemonic, entropy)
    entropy = entropy[:32]  # Trim off the checksum byte
    print('entropy = {}'.format(b2a_hex(entropy)))

    seed.save_wallet_seed(entropy)
    print('Wallet was imported successfully!')

    # TODO: Show post-creation story

    goto_top_menu()


async def convert_bip39_to_bip32(*a):
    import seed
    import stash

    if not await ux_confirm('''This operation computes the extended master private key using your BIP39 seed words and passphrase, and then saves the resulting value (xprv) as the wallet secret.

The seed words themselves are erased forever, but effectively there is no other change. If a BIP39 passphrase is currently in effect, its value is captured during this process and will be 'in effect' going forward, but the passphrase itself is erased and unrecoverable. The resulting wallet cannot be used with any other passphrase.

A reboot is part of this process. PIN code, and funds are not affected.
''', negative_btn='BACK', positive_btn='LOCK DOWN'):
        return

    print('bip={}'.format(stash.bip39_passphrase))
    if not stash.bip39_passphrase:
        if not await ux_confirm('''You do not have a BIP39 passphrase set right now, so this command does little except forget the seed words. It does not enhance security.'''):
            return

    await seed.remember_bip39_passphrase()

    settings.save()

    await login_now()


async def clear_seed(*a):
    # Erase the seed words, and private key from this wallet!
    # This is super dangerous for the customer's money.
    import seed
    from common import pa

    if not await ux_confirm('''Are you sure you want to erase the current wallet? All funds will be lost if not backed up.'''):
        return

    confirmed = await ux_confirm('''Without a proper backup, this action will cause you to lose all funds associated with this wallet.\n
Are you sure you read this message and understand the risks?''')
    if not confirmed:
        return

    seed.clear_seed()
    # NOT REACHED -- reset happens

async def clear_seed_no_reset(*a):
    # Erase the seed words, and private key from this wallet!
    # This is super dangerous for the customer's money.
    import seed
    from common import pa

    if not await ux_confirm('''Are you sure you want to erase the current wallet? All funds will be lost if not backed up.'''):
        return

    confirmed = await ux_confirm('''Without a proper backup, this action will cause you to lose all funds associated with this wallet.\n
Are you sure you read this message and understand the risks?''')
    if not confirmed:
        return

    seed.clear_seed(False)
    # NOT REACHED -- reset happens


async def view_seed_words(*a):
    import stash

    if not await ux_confirm(
        'The next screen will show the seed words (and if defined, your BIP39 passphrase).\n\n' +
        'Anyone who knows these words can control all funds in this wallet.\n\n' +
        'Do you want to display this sensitive information?'):
        return

    try:
        with stash.SensitiveValues() as sv:
            assert sv.mode == 'words'       # protected by menu item predicate

            words = trezorcrypto.bip39.from_data(sv.raw).split(' ')

            msg = 'Seed words (%d):\n' % len(words)
            msg += '\n'.join('%2d: %s' % (i+1, w) for i, w in enumerate(words))

            pw = stash.bip39_passphrase
            if pw:
                msg += '\n\nBIP39 Passphrase:\n%s' % stash.bip39_passphrase

            await ux_show_story(msg, sensitive=True, right_btn='DONE')

            stash.blank_object(msg)
    except:
        # Unable to read seed!
        await ux_show_story('Unable to retrieve seed.')

async def start_login_sequence():
    # Boot up login sequence here.
    #
    from common import pa, settings, dis, loop


    # if pa.is_blank():
    #     # Blank devices, with no PIN set all, can continue w/o login

    #     # Do green-light set immediately after firmware upgrade
    #     if version.is_fresh_version():
    #         pa.greenlight_firmware()
    #         dis.show()

    #     goto_top_menu()
    #     return

    # # Allow impatient devs and crazy people to skip the PIN
    # guess = settings.get('_skip_pin', None)
    # if guess is not None:
    #     try:
    #         dis.fullscreen("(Skip PIN)")
    #         pa.setup(guess)
    #         pa.login()
    #     except:
    #         pass

    # if that didn't work, or no skip defined, force
    # them to login successfully.
    print('start_login_sequence 1')
    while not pa.is_successful():
        print('start_login_sequence 2')
        # always get a PIN and login first
        await block_until_login()

    # print('start_login_sequence 3')

    # # Must re-read settings after login
    # settings.set_key()
    # print('start_login_sequence 4')
    # settings.load()
    # print('start_login_sequence 5')

    # # implement "login countdown" feature
    # delay = settings.get('lgto', 0)
    # if delay:
    #     pa.reset()
    #     await login_countdown(delay)
    #     await block_until_login()

    # # Do green-light set immediately after firmware upgrade
    # if version.is_fresh_version():
    #     pa.greenlight_firmware()
    #     dis.show()

    # # Populate xfp/xpub values, if missing.
    # # - can happen for first-time login of d-u-r-e-s-s wallet
    # # - may indicate lost settings, which we can easily recover from
    # # - these values are important to USB protocol
    # if not (settings.get('xfp', 0) and settings.get('xpub', 0)) and not pa.is_secret_blank():
    #     try:
    #         import stash

    #         # Recalculate xfp/xpub values (depends both on secret and chain)
    #         with stash.SensitiveValues() as sv:
    #             sv.capture_xpub()
    #     except Exception as exc:
    #         # just in case, keep going; we're not useless and this
    #         # is early in boot process
    #         print("XFP save failed: %s" % exc)

    # # Allow USB protocol, now that we are auth'ed
    # # from usb import enable_usb
    # # enable_usb(loop, False)



def goto_top_menu():
    # Start/restart menu system
    from menu import MenuSystem
    from flow import NoPINMenu, MainMenu, NoWalletMenu
    from common import pa


    # if version.is_factory_mode():
    #     m = MenuSystem(???, title='Factory')
    # elif pa.is_blank():
    #     # let them play a little before picking a PIN first time
    #     m = MenuSystem(
    #         NoPINMenu, should_cont=lambda: pa.is_blank(), title='Setup')
    # else:
    #     assert pa.is_successful(), "nonblank but wrong pin"


    m = MenuSystem(NoWalletMenu if pa.is_secret_blank() else MainMenu)

    the_ux.reset(m)

    return m


SENSITIVE_NOT_SECRET = '''

The file created is sensitive--in terms of privacy--but should not \
compromise your funds directly.'''

PICK_ACCOUNT = '''\n\nPress 1 to enter a non-zero account number.'''


async def dump_summary(*A):
    # save addresses, and some other public details into a file
    if not await ux_confirm('''\
Saves a text file to microSD with a summary of the *public* details \
of your wallet. For example, this gives the XPUB (extended public key) \
that you will need to import other wallet software to track balance.''' + SENSITIVE_NOT_SECRET):
        return

    # pick a semi-random file name, save it.
    with imported('backups') as bk:
        await bk.make_summary_file()


def electrum_export_story(background=False):
    # saves memory being in a function
    return ('''\
This saves a skeleton Electrum wallet file onto the microSD card. \
You can then open that file in Electrum without ever connecting this Passport to a computer.\n
'''
            + (background or 'Choose an address type for the wallet on the next screen.'+PICK_ACCOUNT)
            + SENSITIVE_NOT_SECRET)


async def electrum_skeleton(*a):
    # save xpub, and some other public details into a file: NOT MULTISIG

    ch = await ux_show_story(electrum_export_story())

    account_num = 0
    if ch == '1':
        account_num = await ux_enter_number('Account Number:', 9999)
    elif ch != 'y':
        return

    # pick segwit or classic derivation+such
    from public_constants import AF_CLASSIC, AF_P2WPKH, AF_P2WPKH_P2SH
    from menu import MenuSystem, MenuItem

    # Ordering and terminology from similar screen in Electrum. I prefer
    # 'classic' instead of 'legacy' personally.
    rv = []

    rv.append(MenuItem("Legacy (P2PKH)", f=electrum_skeleton_step2,
                       arg=(AF_CLASSIC, account_num)))
    rv.append(MenuItem("P2SH-Segwit", f=electrum_skeleton_step2,
                       arg=(AF_P2WPKH_P2SH, account_num)))
    rv.append(MenuItem("Native Segwit", f=electrum_skeleton_step2,
                       arg=(AF_P2WPKH, account_num)))

    return MenuSystem(rv, title="Electrum")


async def xpub_qr(*a):
    # Create and show a QR code that BlueWallet can import

    # pick segwit or classic derivation+such
    from public_constants import AF_CLASSIC, AF_P2WPKH, AF_P2WPKH_P2SH
    from menu import MenuSystem, MenuItem

    # TODO: Insert a step to choose a different account_num
    account_num = 0

    # Ordering and terminology from similar screen in Electrum. I prefer
    # 'classic' instead of 'legacy' personally.
    rv = []

    rv.append(MenuItem("Native Segwit (zpub)", f=xpub_qr_step2,
                       arg=(AF_P2WPKH, account_num)))

    return MenuSystem(rv, title="BlueWallet")


async def xpub_qr_step2(_1, _2, item):
    from ubinascii import hexlify
    import ujson

    addr_fmt, account_num = item.arg

    with imported('backups') as bk:
        wallet = bk.generate_electrum_wallet(addr_fmt, account_num)
        print('wallet={}'.format(wallet))
        # xpub = wallet['keystore']['xpub']

        # msg = '''{"keystore": {"ckcc_xpub": "xpub661MyMwAqRbcEd36dwxWycMGRYR9kioqmtd5XScTXxXWcDBNWf9svbcTSJw1nFLQRUFnbvFuEiB4QqygXakhZ3Jx3hh1pnV5uWCCwAk3kAK", "xpub": "zpub6qUao2NtyxySY7tDdSS13Chc3TqMrTF7jxCGExBUD9daszd5ibBME2t359in7m8TiToTSeHGTgCaVMNwKqrRdydyp68jyQ2owZy2UvVCh76", "label": "Coldcard Import 6FCC570C", "ckcc_xfp": 207080559, "type": "hardware", "hw_type": "coldcard", "derivation": "m/84'/0'/0'"}, "wallet_type": "standard", "use_encryption": false, "seed_version": 17}'''

        encoded_msg = ujson.dumps(wallet).encode('ascii')
        print('encoded_msg={}'.format(encoded_msg))
        hex_msg = hexlify(encoded_msg)
        str_msg = hex_msg.decode('ascii')

        await ux_show_text_as_ur(title='BlueWallet', qr_text=str_msg)


async def bitcoin_core_skeleton(*A):
    # save output descriptors into a file
    # - user has no choice, it's going to be bech32 with  m/84'/{coin_type}'/0' path

    ch = await ux_show_story('''\
This saves a command onto the microSD card that includes the public keys. \
You can then run that command in Bitcoin Core without ever connecting this Passport to a computer.\
''' + PICK_ACCOUNT + SENSITIVE_NOT_SECRET)

    account_num = 0
    if ch == '1':
        account_num = await ux_enter_number('Account Number:', 9999)
    elif ch != 'y':
        return

    # no choices to be made, just do it.
    with imported('backups') as bk:
        await bk.make_bitcoin_core_wallet(account_num)


async def electrum_skeleton_step2(_1, _2, item):
    # pick a semi-random file name, render and save it.
    with imported('backups') as bk:
        addr_fmt, account_num = item.arg
        await bk.make_json_wallet('Electrum wallet', lambda: bk.generate_electrum_wallet(addr_fmt, account_num))


async def wasabi_skeleton(*A):
    # save xpub, and some other public details into a file
    # - user has no choice, it's going to be bech32 with  m/84'/0'/0' path

    if await ux_show_story('''\
This saves a skeleton Wasabi wallet file onto the microSD card. \
You can then open that file in Wasabi without ever connecting this Passport to a computer.\
''' + SENSITIVE_NOT_SECRET) != 'y':
        return

    # no choices to be made, just do it.
    with imported('backups') as bk:
        await bk.make_json_wallet('Wasabi wallet', lambda: bk.generate_wasabi_wallet(), 'new-wasabi.json')


async def backup_everything(*A):
    # save everything, using a password, into single encrypted file, typically on SD
    with imported('backups') as bk:
        await bk.make_complete_backup()


async def verify_backup(*A):
    # check most recent backup is "good"
    # read 7z header, and measure checksums

    with imported('backups') as bk:

        fn = await file_picker('Select file containing the backup to be verified. No password will be required.', suffix='.7z', max_size=bk.MAX_BACKUP_FILE_SIZE)

        if fn:
            # do a limited CRC-check over encrypted file
            await bk.verify_backup_file(fn)


def import_from_dice(*a):
    import seed
    return seed.import_from_dice()


async def import_xprv(*A):
    # read an XPRV from a text file and use it.
    import chains
    import ure
    from common import pa
    from stash import SecretStash
    from ubinascii import hexlify as b2a_hex
    from backups import restore_from_dict

    assert pa.is_secret_blank()  # "must not have secret"

    def contains_xprv(fname):
        # just check if likely to be valid; not full check
        try:
            with open(fname, 'rt') as fd:
                for ln in fd:
                    # match tprv and xprv, plus y/zprv etc
                    if 'prv' in ln:
                        return True
                return False
        except OSError:
            # directories?
            return False

    # pick a likely-looking file.
    fn = await file_picker('Select file containing the XPRV to be imported.',
                           min_size=50, max_size=2000, taster=contains_xprv)

    if not fn:
        return

    node, chain, addr_fmt = None, None, None

    # open file and do it
    pat = ure.compile(r'.prv[A-Za-z0-9]+')
    with CardSlot() as card:
        with open(fn, 'rt') as fd:
            for ln in fd.readlines():
                if 'prv' not in ln:
                    continue

                found = pat.search(ln)
                if not found:
                    continue

                found = found.group(0)

                for ch in chains.AllChains:
                    for kk in ch.slip132:
                        if found[0] == ch.slip132[kk].hint:
                            try:
                                node = trezorcrypto.bip32.deserialize(found,
                                                             ch.slip132[kk].pub, ch.slip132[kk].priv)
                                chain = ch
                                addr_fmt = kk
                                break
                            except ValueError:
                                pass
                if node:
                    break

    if not node:
        # unable
        await ux_show_story('''\
Sorry, wasn't able to find an extended private key to import. It should be at \
the start of a line, and probably starts with "xprv".''', title="FAILED")
        return

    # encode it in our style
    d = dict(chain=chain.ctype, raw_secret=b2a_hex(
        SecretStash.encode(xprv=node)))

    # This function was added by coinkite
    # TODO: Important enough to add blank() back into trezor?
    # node.blank()

    # TODO: capture the address format implied by SLIP32 version bytes
    # addr_fmt =

    # restore as if it was a backup (code reuse)
    await restore_from_dict(d)

    # not reached; will do reset.

EMPTY_RESTORE_MSG = '''\
Before restoring from a backup, you must erase the current wallet. \
Please make sure your current wallet is backed up.\n\n\
Visit the advanced settings and choose 'Erase Wallet'.'''


async def restore_everything(*A):
    from common import pa

    if not pa.is_secret_blank():
        await ux_show_story(EMPTY_RESTORE_MSG)
        return

    # restore everything, using a password, from single encrypted 7z file
    fn = await file_picker('Select file containing the backup to be restored, and '
                           'then enter the password.', suffix='.7z', max_size=10000)

    if fn:
        with imported('backups') as bk:
            await bk.restore_complete(fn)


async def restore_everything_cleartext(*A):
    # Asssume no password on backup file; devs and crazy people only
    from common import pa

    if not pa.is_secret_blank():
        await ux_show_story(EMPTY_RESTORE_MSG)
        return

    # restore everything, using NO password, from single text file, like would be wrapped in 7z
    fn = await file_picker('Select the cleartext file containing the backup to be restored.',
                           suffix='.txt', max_size=10000)

    if fn:
        with imported('backups') as bk:
            prob = await bk.restore_complete_doit(fn, [])
            if prob:
                await ux_show_story(prob, title='FAILED')


# async def wipe_filesystem(*A):
#     if not await ux_confirm('''\
# Erase internal filesystem and rebuild it. Resets contents of internal flash area \
# used for code patches. Does not affect funds, settings or seed words. \
# Does not affect SD card, if any.'''):
#         return

#     from files import wipe_flash_filesystem

#     wipe_flash_filesystem()


async def wipe_sd_card(*A):
    if not await ux_confirm('''\
Erases and reformats microSD card. This is not a secure erase but more of a quick format.'''):
        return

    from files import wipe_microsd_card
    wipe_microsd_card()


async def list_files(*A):
    # list files, don't do anything with them?
    fn = await file_picker('List files on microSD')
    return


async def file_picker(msg, suffix=None, min_size=None, max_size=None, taster=None, choices=None, none_msg=None):
    # present a menu w/ a list of files... to be read
    # - optionally, enforce a max size, and provide a "tasting" function
    # - if msg==None, don't prompt, just do the search and return list
    # - if choices is provided; skip search process
    # - escape: allow these chars to skip picking process
    from menu import MenuSystem, MenuItem
    import uos
    from utils import get_filesize

    if choices is None:
        choices = []
        try:
            with CardSlot() as card:
                sofar = set()

                for path in card.get_paths():
                    files = uos.ilistdir(path)
                    for fn, ftype, *var in files:
                        print("fn={} ftype={} var={}".format(fn, ftype, var))
                        if ftype == 0x4000:
                            # ignore subdirs
                            continue

                        if suffix and not fn.lower().endswith(suffix):
                            # wrong suffix
                            continue

                        if fn[0] == '.':
                            continue

                        full_fname = path + '/' + fn

                        # Conside file size
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
            # don't show anything if we're just gathering data
            if msg is not None:
                await needs_microsd()
            return None

    if msg is None:
        return choices

    if not choices:
        msg = none_msg or 'Passport is unable to find the correct file on your microSD card. '

        if not none_msg:
            if suffix:
                msg += 'The filename must end in "%s". ' % suffix

            msg += '\n\nPlease check the files on your microSD card and try again. '

        await ux_show_story(msg)
        return

    # tell them they need to pick; can quit here too, but that's obvious.
    if len(choices) != 1:
        msg += '\n\nThere are %d files to pick from.' % len(choices)
    else:
        msg += '\n\nThere is only one file to pick from.'

    ch = await ux_show_story(msg)
    if ch == 'x':
        return

    picked = []

    async def clicked(_1, _2, item):
        picked.append('/'.join(item.arg))
        the_ux.pop()

    items = [MenuItem(label, f=clicked, arg=(path, fn))
             for label, path, fn in choices]

    if 0:
        # don't like; and now showing count on previous page
        if len(choices) == 1:
            # if only one choice, we could make the choice for them ... except very confusing
            items.append(MenuItem('  (one file)', f=None))
        else:
            items.append(MenuItem('  (%d files)' % len(choices), f=None))

    menu = MenuSystem(items, title='Select a File')
    the_ux.push(menu)

    await menu.interact()

    return picked[0] if picked else None


async def sign_tx_from_sd(*a):
    # Top menu choice of top menu! Signing!
    # - check if any signable in SD card, if so do it
    # - if nothing, then talk about USB connection
    from public_constants import MAX_TXN_LEN

    def is_psbt(filename):
        print("filename=" + filename)
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
Please copy an unsigned PSBT transaction onto your microSD card and insert into Passport.
""")
        return

    if len(choices) == 1:
        # skip the menu
        label, path, fn = choices[0]
        input_psbt = path + '/' + fn
    else:
        input_psbt = await file_picker('Choose PSBT file to be signed.', choices=choices)
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

    fn = await file_picker('Choose text file to be signed.',
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
    from login_ux import ChangePINUX

    change_pin_ux = ChangePINUX()
    await change_pin_ux.show()


# Reset pin to blank (all zeroes)
async def set_blank_pin(*a):
    from common import pa

    args = {}
    old_pin_1 = await ux_enter_pin(title='Enter Old PIN', heading='Security Code')
    old_pin_2 = await ux_enter_pin(title='Enter Old PIN', heading='Login PIN')
    old_pin = old_pin_1 + old_pin_2
    args['old_pin'] = old_pin.encode()
    blank_pin = [32] * 0
    args['new_pin'] = bytearray(blank_pin)
    try:
        pa.change(**args)
    except Exception as e:
        print('Exception: {}'.format(e))


async def show_version(*a):
    # show firmware, bootload versions.
    from common import settings
    import callgate
    import version
    from ubinascii import hexlify as b2a_hex

    built, rel, *_ = version.get_mpy_version()
    bl = callgate.get_bootloader_version()[0]
    chk = str(b2a_hex(callgate.get_firmware_hash(0))[-8:], 'ascii')

    msg = '''\
Passport Firmware
  {rel}
  {built}

Bootloader:
  {bl}
  {chk}

Serial:
  {ser}

Hardware:
  {hw}
'''

    await ux_show_story(msg.format(rel=rel, built=built, bl=bl, chk=chk,
                                   ser=version.serial_number(), hw=version.hw_label))


async def set_firmware_highwater(*a):
    # rarely? used command
    import callgate

    have = version.get_mpy_version()[0]
    ts = version.get_header_value('timestamp')

    hw = callgate.get_firmware_highwater()

    if hw == ts:
        await ux_show_story('''Current version (%s) already marked as high-water mark.''' % have)
        return

    ok = await ux_confirm('''Mark current version (%s) as the minimum, and prevent any downgrades below this version.

Rarely needed as critical security updates will set this automatically.''' % have)

    if not ok:
        return

    rv = callgate.set_firmware_highwater(ts)

    # add error display here? meh.

    assert rv == 0, "Failed: %r" % rv


async def import_multisig(*a):
    # pick text file from SD card, import as multisig setup file

    def possible(filename):
        with open(filename, 'rt') as fd:
            for ln in fd:
                if 'pub' in ln:
                    return True

    fn = await file_picker('Pick multisig wallet file to import (.txt)', suffix='.txt',
                           min_size=100, max_size=20*200, taster=possible)

    if not fn:
        return

    try:
        with CardSlot() as card:
            with open(fn, 'rt') as fp:
                data = fp.read()
    except CardMissingError:
        await needs_microsd()
        return

    from auth import maybe_enroll_xpub
    try:
        possible_name = (fn.split('/')[-1].split('.'))[0]
        maybe_enroll_xpub(config=data, name=possible_name)
    except Exception as e:
        await ux_show_story('Failed to import.\n\n\n'+str(e))

async def sign_tx_from_qr(menu, label, item):
    title = item.arg
    data = await ux_scan_qr_code(title)
    # data = '70736274ff010071020000000131d2b534ed8dccf2546323b58a9fc2b0a28475f522fab0b9eb820b3c7bfe43f20000000000ffffffff021027000000000000160014fb141c2c8020a9242da603b6b1a88b981c9bec33c421010000000000160014395b1557687176af8d96fdf26bd4ecf1b44fb406000000000001011fa086010000000000160014f338b1a82c03f057b6b5200d6642492c3c8742d4220602fce63395dc5ff807b501c16fc6d719277c96936b3727667b0f3d19dd23e3905418fa96b9d0540000800000008000000080000000000000000000002202034bf621fed4dfff08f7b8d8e9b5de5bc556ad3885a30807855617d5bcb3e22c2518fa96b9d0540000800000008000000080010000000000000000'

    if data != None:
        from auth import sign_psbt_buf

        # print("data=", data)
        # The data can be a string or may already be a bytes object
        data_buf = data if isinstance(data, bytes) else bytes(data, 'utf8')
        # print("data_buf={}".format(data_buf))
        await sign_psbt_buf(data_buf)

async def enter_passphrase(menu, label, item):
    title = item.arg
    passphrase = await ux_enter_text(title, label="Enter a Passphrase")

    print("Chosen passphrase = {}".format(passphrase))

async def enter_seed_phrase(menu, label, item):
    from seed_phrase_ux import SeedEntryUX
    seed_pharase_entry = SeedEntryUX(seed_len=item.arg)
    await seed_pharase_entry.show()
    print('seed words = {}'.format(seed_pharase_entry.words))

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

    if settings.get('validated_ok'):
        return

    while True:
        # Show a story with explanatory text regarding validation
        result = await ux_show_story('''\
First, let's make sure your Passport has not been tampered with during shipping.

Navigate to:

foundationdevices.com/passport-validation

You will be presented with a validation page containing a QR code.

On the next screen, scan that QR code. Your Passport will show you 4 Security Words in response.

Enter those 4 words in the same order into the web page and click the Validate button.''', title='Validation', left_btn='SHUTDOWN', scroll_label='MORE')

        if result == 'y':

            while True:
                # Scan a QR code
                qr_data = await ux_scan_qr_code('Validation')

                # Generate the 4 validation words
                # 4 words gives 2048^4 possible combinations => 17,592,186,044,416 (~17.5 trillion)
                if qr_data == None:

                    while True:
                        result = await ux_show_story('''No QR code was scanned. Do you want to try again, or skip validation?\n\nIMPORTANT: If you skip validation now, there will be no way to do so in the future.''', left_btn='SKIP', right_btn='RETRY')
                        if result == 'x':
                            # Confirm?
                            confirmed = await ux_confirm('Are you sure you want to permanently skip suoply chain validation?')
                            if confirmed:
                                # 2 means validation was skipped, but we won't show it again
                                settings.set('validated_ok', 2)
                                settings.save()
                                return
                        else:
                            # Break out of the inner loop and back out the the QR validation scan loop
                            break

                else:
                    words = PinAttempt.supply_chain_validation_words(
                        qr_data.encode())
                    print(words)
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
                        settings.save()
                        return
        elif result == 'x':
            await ux_shutdown()


async def test_ur(*a):
    from test import TestUR

    test = TestUR()
    test.run_tests()


async def test_ur_encoder(_1, _2, item):
    await ux_show_text_as_ur(title='Test UR Encoding', msg='Animated UR Code', qr_text=b'Y\x01\x00\x91n\xc6\\\xf7|\xad\xf5\\\xd7\xf9\xcd\xa1\xa1\x03\x00&\xdd\xd4.\x90[w\xad\xc3nO-<\xcb\xa4O\x7f\x04\xf2\xdeD\xf4-\x84\xc3t\xa0\xe1I\x13o%\xb0\x18RTYa\xd5_\x7fz\x8c\xdem\x0e.\xc4?;-\xcbdJ"\t\xe8\xc9\xe3J\xf5\xc4ty\x84\xa5\xe8s\xc9\xcf_\x96^%\xee)\x03\x9f\xdf\x8c\xa7O\x1cv\x9f\xc0~\xb7\xeb\xae\xc4n\x06\x95\xae\xa6\xcb\xd6\x0b>\xc4\xbb\xff\x1b\x9f\xfe\x8a\x9er@\x12\x93w\xb9\xd3q\x1e\xd3\x8dA/\xbbDB%o\x1eoY^\x0f\xc5\x7f\xedE\x1f\xb0\xa0\x10\x1f\xb7k\x1f\xb1\xe1\xb8\x8c\xfd\xfd\xaa\x94b\x94\xa4}\xe8\xff\xf1s\xf0!\xc0\xe6\xf6[\x05\xc0\xa4\x94\xe5\x07\x91\'\n\x00P\xa7:\xe6\x9bg%PZ.\xc8\xa5y\x14W\xc9\x87m\xd3J\xad\xd1\x92\xa5:\xa0\xdcf\xb5V\xc0\xc2\x15\xc7\xce\xb8$\x8bq|"\x95\x1ee0[V\xa3pn>\x86\xeb\x01\xc8\x03\xbb\xf9\x15\xd8\x0e\xdc\xd6MM')


async def play_snake(*a):
    from snake import snake_game
    await snake_game()


async def play_stacksats(*a):
    from stacksats import stacksats_game
    await stacksats_game()


# Secure Element Test Actions
async def se_get_version(*a):
    version = bytearray(64)
    system.dispatch(CMD_GET_BOOTLOADER_VERSION, version, 0)
    print('version={}'.format(version))
    ver_str = version[:16].decode('utf8')
    print('ver_str = {}'.format(ver_str))

    # Hex format for the rest
    import binascii
    s = binascii.hexlify(version[16:]).decode('utf8')
    lines = [s[i:i+16] for i in range(0, len(s), 16)]
    data = '\n'.join(lines)
    await ux_show_story("SE Version\n\n{}\n\n{}".format(ver_str, data))

async def se_get_config(*a):
    config = bytearray(128)
    system.dispatch(CMD_GET_SE_CONFIG, config, 0)

    import binascii
    s = binascii.hexlify(config).decode('utf8')
    lines = [s[i:i+16] for i in range(0, len(s), 16)]
    data = '\n'.join(lines)
    await ux_show_story("SE Config\n\n" + data)

async def gen_random(*a):
    from binascii import hexlify
    seed = bytearray(32)
    valid = noise.random_bytes(seed)
    print('Seed = {}'.format(hexlify(seed)))

async def show_power_monitor(*a):
    from foundation import Powermon
    powermon = Powermon()

    for i in range(10):
        (current, voltage) = powermon.read()
        print('current={} voltage={}'.format(current, voltage))
        await sleep_ms(1000)


async def show_board_rev(*a):
    from foundation import Boardrev
    boardrev = Boardrev()

    rev = boardrev.read()
    print('Board rev={}'.format(rev))

async def factory_setup(*a):
    system.dispatch(CMD_FACTORY_SETUP, None, 0);

async def erase_rom_secrets(*a):
    confirm = await ux_confirm('Are you sure you want to erase the ROM secrets?\n\nThis will UNPAIR your device from the current Secure Element chip!\n\nYou will need to insert a new chip to recover.')
    if confirm:
        system.erase_rom_secrets()

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
    print('Current Settings:\n{}'.format(settings.curr_dict))

async def test_ur1(*a):
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

async def battery_mon(*a):
    from battery_mon import battery_mon
    await battery_mon()
