# SPDX-FileCopyrightText: 2020 Foundation Devices, Inc. <hello@foundationdevices.com>
# SPDX-License-Identifier: GPL-3.0-or-later
#
# SPDX-FileCopyrightText: 2018 Coinkite, Inc. <coldcardwallet.com>
# SPDX-License-Identifier: GPL-3.0-only
#
# (c) Copyright 2018 by Coinkite Inc. This file is part of Coldcard <coldcardwallet.com>
# and is covered by GPLv3 license found in COPYING.
#
# export.py - Save and restore backup data.
#
import gc
import sys
import os

import chains
import compat7z
import seed
import stash
import trezorcrypto
import ujson
import version
from ubinascii import hexlify as b2a_hex
from ubinascii import unhexlify as a2b_hex
from uio import StringIO
from utils import (imported, xfp2str, get_bytewords_for_buf, to_str, run_chooser, ensure_folder_exists, file_exists,
    is_dir, get_accounts, get_backups_folder_path)
from ux import ux_confirm, ux_show_story
from common import noise

# we make passwords with this number of words
NUM_PW_WORDS = const(6)

# max size we expect for a backup data file (encrypted or cleartext)
MAX_BACKUP_FILE_SIZE = const(10000)     # bytes


def ms_has_master_xfp(xpubs):
    from common import settings
    master_xfp = settings.get('xfp', None)

    for xpub in xpubs:
        (xfp, _) = xpub
        # print('ms_has_master_xfp: xfp={} master_xfp={}'.format(xfp, master_xfp))
        if xfp == master_xfp:
            # print('Including this one')
            return True

    # print('EXCLUDING this one')
    return False

def render_backup_contents():
    # simple text format:
    #   key = value
    # or #comments
    # but value is JSON
    from common import settings, pa, system
    from utils import get_month_str
    from utime import localtime

    rv = StringIO()

    def COMMENT(val=None):
        if val:
            rv.write('\n# %s\n' % val)
        else:
            rv.write('\n')

    def ADD(key, val):
        rv.write('%s = %s\n' % (key, ujson.dumps(val)))

    rv.write('# Passport backup file! DO NOT CHANGE.\n')

    chain = chains.current_chain()

    COMMENT('Private Key Details: ' + chain.name)

    with stash.SensitiveValues(for_backup=True) as sv:

        if sv.mode == 'words':
            ADD('mnemonic', trezorcrypto.bip39.from_data(sv.raw))

        if sv.mode == 'master':
            ADD('bip32_master_key', b2a_hex(sv.raw))

        ADD('chain', chain.ctype)
        ADD('xfp', xfp2str(sv.get_xfp()))
        ADD('xprv', chain.serialize_private(sv.node))
        ADD('xpub', chain.serialize_public(sv.node))

        # BTW: everything is really a duplicate of this value
        ADD('raw_secret', b2a_hex(sv.secret).rstrip(b'0'))

    COMMENT('Firmware Version (informational):')
    (fw_version, fw_timestamp, _, _) = system.get_software_info()
    time = localtime(fw_timestamp)
    fw_date = '{} {}, {}'.format(get_month_str(time[1]), time[2], time[0]-30)

    ADD('fw_version', fw_version)
    ADD('fw_date', fw_date)

    COMMENT('User Preferences:')

    # user preferences - sort so that accounts is processed before multisig
    multisig_ids = []
    for k, v in sorted(settings.curr_dict.items()):
        # print('render handling key "{}"'.format(k))
        if k[0] == '_':
            continue        # debug stuff in simulator
        if k == 'xpub':
            continue        # redundant, and wrong if bip39pw
        if k == 'xfp':
            continue         # redundant, and wrong if bip39pw

        # if k == 'accounts':
        #     # Filter out accounts that have a passphrase
        #     print('Filtering out accounts that have a bip39_hash')
        #     v = list(filter(lambda acct: acct.get('bip39_hash', '') == '', v))
        #     multisig_ids = [acct.get('multisig_id', None) for acct in v]
        #     multisig_ids = list(filter(lambda ms: ms != None, multisig_ids))  # Don't include None entries
        #     print('multisig_ids={}'.format(multisig_ids))
        #
        if k == 'multisig':
            # Only backup multisig entries that have the master XFP - plausible deniability in your backups
            # "Passphrase wallets? I don't have any passphrase wallets!"
            # print('ms={}'.format(v))
            v = list(filter(lambda ms: ms_has_master_xfp(ms[2]), v))

        ADD('setting.' + k, v)

    rv.write('\n# EOF\n')

    return rv.getvalue()


async def restore_from_dict(vals):
    # Restore from a dict of values. Already JSON decoded.
    # Reboot on success, return stringg on failure
    from common import pa, dis, settings, system
    from pincodes import SE_SECRET_LEN

    # print("Restoring from: %r" % vals)

    # Step 1: the private key
    # - prefer raw_secret over other values
    try:
        system.turbo(True)
        chain = chains.get_chain(vals.get('chain', 'BTC'))

        assert 'raw_secret' in vals
        raw = bytearray(SE_SECRET_LEN)
        rs = vals.pop('raw_secret')
        if len(rs) % 2:
            rs += '0'
        x = a2b_hex(rs)
        raw[0:len(x)] = x

        # check we can decode this right (might be different firweare)
        opmode, bits, node = stash.SecretStash.decode(raw)
        assert node

        # verify against xprv value (if we have it)
        if 'xprv' in vals:
            check_xprv = chain.serialize_private(node)
            if check_xprv != vals['xprv']:
                system.turbo(False)
                return 'The xprv in the backup file does not match the xprv derived from the raw secret.'

    except Exception as e:
        system.turbo(False)
        return ('Unable to restore the seed value from the backup.\n\n\n' + str(e))

    dis.fullscreen("Saving Wallet...")
    system.progress_bar(0)

    # clear (in-memory) settings and change also nvram key
    # - also captures xfp, xpub at this point
    pa.change(new_secret=raw)

    # force the right chain
    await pa.new_main_secret(raw, chain)         # updates xfp/xpub

    # NOTE: don't fail after this point... they can muddle thru w/ just right seed

    # restore settings from backup file
    for idx, k in enumerate(vals):
        system.progress_bar(int(idx * 100 / len(vals)))
        if not k.startswith('setting.'):
            continue

        if k == 'xfp' or k == 'xpub':
            continue

        # TODO: If we implement partial restore, merge in accounts and multisigs if some already exist

        settings.set(k[8:], vals[k])

    system.turbo(False)

    # write out
    # await settings.save()

    await ux_show_story('Everything has been successfully restored. '
                        'Passport will now reboot to finalize the '
                        'updated settings and seed.', title='Success', left_btn='RESTART', right_btn='OK', center=True, center_vertically=True)

    from machine import reset
    reset()

def get_ms_wallet_by_id(id):
    matches = list(filter(lambda ms: ms['id'] == multisig_id, multisig))
    return matches[0] if len(matches) == 1 else None

def find_acct(deriv_path, bip39_hash):
    from common import settings
    accounts = get_accounts()
    # print('find_acct: deriv_path={}  bip39_hash={}'.format(deriv_path, bip39_hash))
    matches = list(filter(lambda acct: (acct.get('deriv_path') == deriv_path and acct.get('bip39_hash') == bip39_hash), accounts))
    # print('matches={}'.format(matches))
    return matches[0] if len(matches) == 1 else None

def get_restorable_accounts(vals):
    # Make a list of accounts and their corresponding multisigs, if any
    restorable = []
    # print('get_restorable_accounts: vals={}'.format(to_str(vals)))
    accounts = vals.get('setting.accounts', [])
    multisig = vals.get('setting.multisig', [])

    # print('get_restorable_accounts: accounts={}'.format(accounts))
    # print('get_restorable_accounts: multisig={}'.format(multisig))
    for account in accounts:
        multisig_id = account.get('multisig_id')
        # print('multisig_id={}'.format(multisig_id))
        ms_wallet = None
        if multisig_id:
            # Find matching multisig entry
            ms_wallet = get_ms_wallet_by_id(multisig_id)
            # print('ms_wallet={}'.format(ms_wallet))

        # See if this account exists already (based on derivation path and bip39_hash
        existing_acct = find_acct(account.get('deriv_path'), account.get('bip39_hash', ''))
        # Only allow restoration of non-active accounts
        if existing_acct != None and existing_acct.get('status') != 'a':
            restorable.append((account, ms_wallet))

    return restorable

async def restore_from_dict_partial(vals):
    from common import pa, dis, settings, system
    from uasyncio import sleep_ms

    restorable = get_restorable_accounts(vals)
    if len(restorable) == 0:
        await ux_show_story('All accounts in this backup already exist on this Passport.', title='Info',
                         center=True, center_vertically=True)
        return

    acct_to_restore = None

    def account_chooser():
        choices = ['Restore All']
        values = ['all']
        for entry in restorable:
            (account, _) = entry
            choices.append(account.get('name'))
            values.append(entry)

        def select_account(index, text):
            nonlocal acct_to_restore
            acct_to_restore = values[index]

        return 0, choices, select_account

    # Ask user to select account to restore
    await run_chooser(account_chooser, 'Select Acct.', show_checks=False)
    # print('acct_to_restore={}'.format(to_str(acct_to_restore)))
    if acct_to_restore == None:
        # print('No account selected!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!')
        # User wants to go back without selecting an account
        return

    # Actually restore the account(s) now
    entries = restorable if acct_to_restore == 'all' else [acct_to_restore]
    curr_accounts = get_accounts()
    curr_multisig = settings.get('multisig', [])

    for entry in entries:
        (account, multisig) = entry
        # print('Handling account.name={}'.format(account.get('name')))

        existing_acct = find_acct(account.get('deriv_path'), account.get('bip39_hash', ''))
        if existing_acct:
            if existing_acct['status'] == 'r':
                result = await ux_confirm('''An archived account with the following details already exists \
on this Passport:

Archived Name:
{}

Backup Name:
{}

Derivation Path:
{}

Do you want to replace it?

If you select NO, this account will not be restored and you can use the Advanced > Archived Accts. \
feature to recover it later.'''.format(existing_acct.get('name'), account.get('name'), account.get('deriv_path')),
                title='Duplicate Acct.')
                if result == 'x':
                    continue
                else:
                    # Remove the old entry and append the new one
                    curr_accounts.remove(existing_acct)
            elif existing_acct['status'] == 'd':
                # Remove the old entry since deleted entries are missing many account details and can't be recovered
                curr_accounts.remove(existing_acct)

        # Restore the account
        curr_accounts.append(account)

        # Add in the multisig entry, if any
        if multisig:
            curr_multisig.append(multisig)

    # Save all the accounts that were restored
    settings.set('accounts', curr_accounts)
    settings.set('multisig', curr_multisig)

    await settings.save()

    dis.fullscreen('Restore Successful')
    await sleep_ms(1000)


# Pick password based on the device hash  and secret (entropy) so that it's always the same -- let's you make repeated backups
# without having to write down a new password each time.
def make_backup_password():
    from common import system, pa
    from utils import bytes_to_hex_str

    device_hash = bytearray(32)
    system.get_device_hash(device_hash)
    secret = pa.fetch()
    # print('secret: {}'.format(bytes_to_hex_str(secret)))

    pw = trezorcrypto.sha256()
    pw.update(device_hash)
    pw.update(secret)
    password_hash = pw.digest()

    # print('password_hash: {}'.format(bytes_to_hex_str(password_hash)))

    words = get_bytewords_for_buf(password_hash[:NUM_PW_WORDS])
    # print('words: {}'.format(words))
    return words

async def make_complete_backup():
    from noise_source import NoiseSource
    from common import system, dis, settings
    from uasyncio import sleep_ms
    from seed_check_ux import SeedCheckUX

    backup_quiz_passed = settings.get('backup_quiz', False)

    cancel_msg = "Are you sure you want to cancel the backup?\n\nWithout a microSD backup or the seed phrase, you won't be able to recover your funds."

    while True:
        if backup_quiz_passed:
            ch = await ux_show_story('''Passport is about to create an updated microSD backup.

The password is the same as what you previously recorded.

Please insert a microSD card.''', title='Backup', right_btn='CONTINUE', scroll_label='MORE')
            if ch == 'x':
                # Warn user that the wallet is not backed up (but they HAVE seen the words already)
                if await ux_confirm('Are you sure you want to cancel the backup?'):
                    return
            else:
                break
        else:
            ch = await ux_show_story('''Passport is about to create your first encrypted microSD backup. \
The next screen will show you the password that is REQUIRED to access the backup.

We recommend storing the backup password in cloud storage or a password manager. We consider this safe since physical access \
to the microSD card is required to access the backup.''', title='Backup', right_btn='CONTINUE', scroll_label='MORE')
            if ch == 'x':
                # Warn user that the wallet is not backed up (and they haven't seen seed words yet!)
                if await ux_confirm(cancel_msg):
                    return
            else:
                break

    words = make_backup_password()

    while True:
        if not backup_quiz_passed:
            msg = 'Backup Password (%d):\n' % len(words)
            msg += '\n'.join('%2d: %s' % (i+1, w) for i, w in enumerate(words))
            # print('Backup Password: {}'.format(' '.join(words)))

            ch = await ux_show_story(msg, sensitive=True, right_btn='NEXT')
            stash.blank_object(msg)
            if ch == 'x':
                if await ux_confirm('Are you sure you want to cancel password verification?'):
                    return
                else:
                    continue

            # Quiz
            cancel_msg = '''Are you sure you want to cancel password verification?

The backup will still be saved, but you will be unable to access it without the correct password.'''

            phrase_check = SeedCheckUX(seed_words=words, title="Verify Password", cancel_msg=cancel_msg)
            settings.set('backup_quiz', True)
            if not await phrase_check.show():
                continue  # Show words again

        # Write out the backup, possibly more than once
        await write_complete_backup(words, is_first_backup=not backup_quiz_passed)
        return


async def offer_backup():
    # Try auto-backup first
    if await auto_backup():
        # Success! No need to bother user.
        return

    result = await ux_confirm('The account configuration has been modified. Do you want to make a new microSD backup?',
        title='Backup')
    if result:
        await make_complete_backup()

# Check to see if there is an SD card in the slot with a 'backups' folder and, if so, write a backup.
async def auto_backup():
    from files import CardSlot

    backup_started = False
    # See if the card is there
    try:
        with CardSlot() as card:
            backups_path = get_backups_folder_path(card)
            if not is_dir(backups_path):
                # print('{} is not a directory'.format(backups_path))
                return False

            # microSD is inserted and has a backups folder -- it's AutoBackup time!
            backup_started = True
            words = make_backup_password()
            await write_complete_backup(words, auto_backup=True)
            return True

    except Exception as e:
        from uasyncio import sleep_ms
        # print('auto_backup() e={}'.format(e))

        if backup_started:
            from common import dis
            dis.fullscreen('Unable to Backup')
            await sleep_ms(1000)
        return False

async def view_backup_password(*a):
    from common import system
    words = make_backup_password()

    msg = 'Backup Password (%d):\n' % len(words)
    msg += '\n'.join('%2d: %s' % (i+1, w) for i, w in enumerate(words))

    ch = await ux_show_story(msg, title='Password', sensitive=True, right_btn='OK')
    stash.blank_object(msg)

async def write_complete_backup(words, auto_backup=False, is_first_backup=False):
    # Just do the writing
    from common import dis, pa, settings, system
    from files import CardSlot, CardMissingError
    from uasyncio import sleep_ms

    # Show progress:
    dis.fullscreen('AutoBackup...' if auto_backup else 'Encrypting...' if words else 'Generating...')

    body = render_backup_contents().encode()

    backup_num = 1
    xfp = xfp2str(settings.get('xfp'))
    # print('XFP: {}'.format(xfp))

    gc.collect()

    if words:
        # NOTE: Takes a few seconds to do the key-stretching, but little actual
        # time to do the encryption.

        pw = ' '.join(words)
        #print('pw={}'.format(words))
        zz = compat7z.Builder(password=pw, progress_fcn=system.progress_bar)
        zz.add_data(body)

        hdr, footer = zz.save('passport-backup.txt')

        filesize = len(body) + MAX_BACKUP_FILE_SIZE

        del body

        gc.collect()
    else:
        # cleartext dump
        zz = None
        filesize = len(body)+10

    while True:
        base_filename = ''

        try:
            with CardSlot() as card:
                backups_path = get_backups_folder_path(card)
                ensure_folder_exists(backups_path)

                # Make a unique filename
                while True:
                    base_filename = '{}-backup-{}.7z'.format(xfp, backup_num)
                    fname = '{}/{}'.format(backups_path, base_filename)

                    # Ensure filename doesn't already exist
                    if not file_exists(fname):
                        break

                    # Ooops...that exists, so increment and try again
                    backup_num += 1

                # print('Saving to fname={}'.format(fname))

                # Do actual write
                with open(fname, 'wb') as fd:
                    if zz:
                        fd.write(hdr)
                        fd.write(zz.body)
                        fd.write(footer)
                    else:
                        fd.write(body)

        except Exception as e:
            # includes CardMissingError
            import sys
            # sys.print_exception(e)
            # catch any error
            if not auto_backup:
                ch = await ux_show_story('Unable to write backup. Please insert a formatted microSD card.\n\n' +
                                         str(e), title='Error', center=True, center_vertically=True, right_btn='RETRY')
                if ch == 'x':
                    return
                else:
                    # Retry the write
                    continue
            else:
                return

        if not auto_backup:
            await ux_show_story('Saved backup to\n\n{}\n\nin /backups folder.'.format(base_filename),
                title='Success', left_btn='NEXT', center=True, center_vertically=True)

            if await ux_confirm('Do you want to make an additional backup?\n\nIf so, insert another microSD card.',
                                title='Backup'):
                continue

            if is_first_backup:
                dis.fullscreen('Setup Complete!')
                await sleep_ms(2000)

        return


async def verify_backup_file(fname_or_fd):
    # read 7z header, and measure checksums
    # - no password is wanted/required
    # - really just checking CRC32, but that's enough against truncated files
    from files import CardSlot, CardMissingError
    from actions import needs_microsd
    prob = None
    fd = None

    # filename already picked, open it.
    try:
        with CardSlot() as card:
            prob = 'Unable to open backup file.'
            with (open(fname_or_fd, 'rb') if isinstance(
                fname_or_fd, str) else fname_or_fd) as fd:

                prob = 'Unable to read backup file headers. Might be truncated.'
                compat7z.check_file_headers(fd)

                prob = 'Unable to verify backup file contents.'
                zz = compat7z.Builder()
                files = zz.verify_file_crc(fd, MAX_BACKUP_FILE_SIZE)

                assert len(files) == 1
                fname, fsize = files[0]

    except CardMissingError:
        await needs_microsd()
        return
    except Exception as e:
        await ux_show_story(prob + '\n\n' + str(e), title='Error', center=True, center_vertically=True)
        return

    await ux_show_story("""Backup file appears to be valid.

Please note this is only a check to ensure the file has not been modified or damaged.""")


async def restore_complete(fname_or_fd, partial_restore):
    from ux import the_ux
    from seed_entry_ux import SeedEntryUX

    fake_it = False
    if fake_it:
        words = ['glow', 'rich', 'veto', 'diet', 'ramp', 'away']
    else:
        seed_entry = SeedEntryUX(title='Encryption Words', seed_len=6, validate_checksum=False, word_list='bytewords')
        await seed_entry.show()
        if not seed_entry.is_seed_valid:
            return
        words = seed_entry.words

    prob = await restore_complete_doit(fname_or_fd, words, partial_restore)

    if prob:
        await ux_show_story(prob, title='Error')


async def restore_complete_doit(fname_or_fd, words, partial_restore):
    # Open file, read it, maybe decrypt it; return string if any error
    # - some errors will be shown, None return in that case
    # - no return if successful (due to reboot)
    from common import dis, system, pa
    from files import CardSlot, CardMissingError
    from actions import needs_microsd

    # Show progress bar while decrypting
    def progress_fn(p):
        # print('p={}'.format(p))
        system.progress_bar(int(p * 100))

    # build password
    password = ' '.join(words)

    prob = None

    try:
        with CardSlot() as card:
            # filename already picked, taste it and maybe consider using its data.
            try:
                fd = open(fname_or_fd, 'rb') if isinstance(
                    fname_or_fd, str) else fname_or_fd
            except:
                return 'Unable to open backup file.\n\n' + str(fname_or_fd)

            try:
                if not words:
                    contents = fd.read()
                else:
                    try:
                        compat7z.check_file_headers(fd)
                    except Exception as e:
                        return 'Unable to read backup file. The backup may have been modified.\n\nError: ' \
                            + str(e)

                    dis.fullscreen("Decrypting...")
                    try:
                        zz = compat7z.Builder()
                        fname, contents = zz.read_file(fd, password, MAX_BACKUP_FILE_SIZE,
                                                       progress_fcn=progress_fn)

                        # simple quick sanity check
                        assert contents[0:1] == b'#' and contents[-1:] == b'\n'

                    except Exception as e:
                        # assume everything here is "password wrong" errors
                        # print("pw wrong? %s" % e)
                        return ('Unable to decrypt backup file. The password is incorrect.'
                                '\n\nYou entered:\n\n' + password)

            finally:
                fd.close()
    except CardMissingError:
        await needs_microsd()
        return

    vals = {}
    for line in contents.decode().split('\n'):
        if not line:
            continue
        if line[0] == '#':
            continue

        try:
            k, v = line.split(' = ', 1)
            #print("%s = %s" % (k, v))

            vals[k] = ujson.loads(v)
        except:
            # print("Unable to decode line: %r" % line)
            # but keep going!
            pass

    # this leads to reboot if it works, else errors shown, etc.
    # print('vals = {}'.format(to_str(vals)))

    if partial_restore:
        # Check that the seed of this backup is the same as the current one or that the seed is blank
        with stash.SensitiveValues() as sv:
            curr_mnemonic = trezorcrypto.bip39.from_data(sv.raw)

        backup_mnemonic = vals.get('mnemonic')
        # print('pa.is_secret_blank()={}\ncurr_mnemonic={}\backup_mnemonic={}'.format(pa.is_secret_blank(), curr_mnemonic, backup_mnemonic))

        if not pa.is_secret_blank() and curr_mnemonic != backup_mnemonic:
            # ERROR! Can't import between different seeds
            return "Can't restore accounts from a backup that is based on a different seed phrase than the current wallet."

        return await restore_from_dict_partial(vals)
    else:
        return await restore_from_dict(vals)


def generate_public_contents():
    # Generate public details about wallet.
    #
    # simple text format:
    #   key = value
    # or #comments
    # but value is JSON
    from common import settings
    from public_constants import AF_CLASSIC

    num_rx = 5

    chain = chains.current_chain()

    with stash.SensitiveValues() as sv:

        yield ('''\
# Passport Summary File
## For wallet with master key fingerprint: {xfp}

Wallet operates on blockchain: {nb}

For BIP44, this is coin_type '{ct}', and internally we use
symbol {sym} for this blockchain.

## IMPORTANT WARNING

Do **not** deposit to any address in this file unless you have a working
wallet system that is ready to handle the funds at that address!

## Top-level, 'master' extended public key ('m/'):

{xpub}

What follows are derived public keys and payment addresses, as may
be needed for different systems.
'''.format(nb=chain.name, xpub=chain.serialize_public(sv.node),
           sym=chain.ctype, ct=chain.b44_cointype, xfp=xfp2str(sv.node.my_fingerprint())))

        for name, path, addr_fmt in chains.CommonDerivations:

            if '{coin_type}' in path:
                path = path.replace('{coin_type}', str(chain.b44_cointype))

            if '{' in name:
                name = name.format(core_name=chain.core_name)

            show_slip132 = ('Core' not in name)

            yield ('''## For {name}: {path}\n\n'''.format(name=name, path=path))
            yield ('''First %d receive addresses (account=0, change=0):\n\n''' % num_rx)

            submaster = None
            for i in range(num_rx):
                subpath = path.format(account=0, change=0, idx=i)

                # find the prefix of the path that is hardneded
                if "'" in subpath:
                    hard_sub = subpath.rsplit("'", 1)[0] + "'"
                else:
                    hard_sub = 'm'

                if hard_sub != submaster:
                    # dump the xpub needed

                    if submaster:
                        yield "\n"

                    node = sv.derive_path(hard_sub, register=False)
                    yield ("%s => %s\n" % (hard_sub, chain.serialize_public(node)))
                    if show_slip132 and addr_fmt != AF_CLASSIC and (addr_fmt in chain.slip132):
                        yield ("%s => %s   ##SLIP-132##\n" % (
                            hard_sub, chain.serialize_public(node, addr_fmt)))

                    submaster = hard_sub
                    # TODO: Add blank() back into trezor?
                    # node.blank()
                    del node

                # show the payment address
                node = sv.derive_path(subpath, register=False)
                yield ('%s => %s\n' % (subpath, chain.address(node, addr_fmt)))

                # TODO: Do we need to do this? node.blank()
                del node

            yield ('\n\n')

    # from multisig import MultisigWallet
    # if MultisigWallet.exists():
    #     yield '\n# Your Multisig Wallets\n\n'
    #     from uio import StringIO
    #
    #     for ms in MultisigWallet.get_all():
    #         fp = StringIO()
    #
    #         ms.render_export(fp)
    #         print("\n---\n", file=fp)
    #
    #         yield fp.getvalue()
    #         del fp


async def write_text_file(fname_pattern, body, title, total_parts=72):
    # - total_parts does need not be precise
    from common import dis, pa, settings, system
    from files import CardSlot, CardMissingError
    from actions import needs_microsd

    # choose a filename
    try:
        with CardSlot() as card:
            fname, nice = card.pick_filename(fname_pattern)

            # do actual write
            with open(fname, 'wb') as fd:
                for idx, part in enumerate(body):
                    system.progress_bar((idx * 100) // total_parts)
                    fd.write(part.encode())

    except CardMissingError:
        await needs_microsd()
        return
    except Exception as e:
        await ux_show_story('Unable to write!\n\n\n'+str(e))
        return

    msg = '''%s file written:\n\n%s''' % (title, nice)
    await ux_show_story(msg)


async def make_summary_file(fname_pattern='public.txt'):
    from common import dis

    # record **public** values and helpful data into a text file
    dis.fullscreen('Generating...')

    # generator function:
    body = generate_public_contents()

    await write_text_file(fname_pattern, body, 'Summary')



def make_bitcoin_core_wallet(account_num=0):
    from common import dis, settings
    import ustruct
    xfp = xfp2str(settings.get('xfp'))

    # make the data
    examples = []
    payload = ujson.dumps(
        list(generate_bitcoin_core_wallet(examples, account_num)))

    body = '''\
# Bitcoin Core Wallet Import File
# Exported by Passport

## For wallet with master key fingerprint: {xfp}

Wallet operates on blockchain: {nb}

## Bitcoin Core RPC

The following command can be entered after opening Window -> Console
in Bitcoin Core, or using bitcoin-cli:

importmulti '{payload}'

## Resulting Addresses (first 3)

'''.format(payload=payload, xfp=xfp, nb=chains.current_chain().name)

    body += '\n'.join('%s => %s' % t for t in examples)

    body += '\n'

    return body


def generate_bitcoin_core_wallet(example_addrs, account_num):
    # Generate the data for an RPC command to import keys into Bitcoin Core
    # - yields dicts for json purposes
    from descriptor import append_checksum
    from common import settings
    import ustruct

    from public_constants import AF_P2WPKH

    chain = chains.current_chain()

    derive = "84'/{coin_type}'/{account}'".format(
        account=account_num, coin_type=chain.b44_cointype)

    with stash.SensitiveValues() as sv:
        prefix = sv.derive_path(derive)
        xpub = chain.serialize_public(prefix)

        for i in range(3):
            sp = '0/%d' % i
            node = sv.derive_path(sp, master=prefix)
            a = chain.address(node, AF_P2WPKH)
            example_addrs.append(('m/%s/%s' % (derive, sp), a))

    xfp = settings.get('xfp')
    txt_xfp = xfp2str(xfp).lower()

    chain = chains.current_chain()

    _, vers, _ = version.get_mpy_version()

    for internal in [False, True]:
        desc = "wpkh([{fingerprint}/{derive}]{xpub}/{change}/*)".format(
            derive=derive.replace("'", "h"),
            fingerprint=txt_xfp,
            coin_type=chain.b44_cointype,
            account=0,
            xpub=xpub,
            change=(1 if internal else 0))

        yield {
            'desc': append_checksum(desc),
            'range': [0, 1000],
            'timestamp': 'now',
            'internal': internal,
            'keypool': True,
            'watchonly': True
        }


def generate_wasabi_wallet():
    # Generate the data for a JSON file which Wasabi can open directly as a new wallet.
    from common import settings
    import ustruct
    import version

    # bitcoin (xpub) is used, even for testnet case (ie. no tpub)
    # - altho, doesn't matter; the wallet operates based on it's own settings for test/mainnet
    #   regardless of the contents of the wallet file
    btc = chains.BitcoinMain

    with stash.SensitiveValues() as sv:
        xpub = btc.serialize_public(sv.derive_path("84'/0'/0'"))

    xfp = settings.get('xfp')
    txt_xfp = xfp2str(xfp)

    chain = chains.current_chain()
    assert chain.ctype in {'BTC', 'TBTC'}, "Only Bitcoin supported"

    _, vers, _ = version.get_mpy_version()

    return dict(MasterFingerprint=txt_xfp,
                ColdCardFirmwareVersion=vers,
                ExtPubKey=xpub)

def generate_generic_export(account_num=0):
    # Generate data that other programers will use to import from (single-signer)
    from common import settings
    from public_constants import AF_CLASSIC, AF_P2WPKH, AF_P2WPKH_P2SH

    chain = chains.current_chain()

    rv = dict(chain=chain.ctype,
                xpub = settings.get('xpub'),
                xfp = xfp2str(settings.get('xfp')),
                account = account_num,
            )

    with stash.SensitiveValues() as sv:
        # each of these paths would have /{change}/{idx} in usage (not hardened)
        for name, deriv, fmt, atype in [
            ( 'bip44', "m/44'/{ct}'/{acc}'", AF_CLASSIC, 'p2pkh' ),
            ( 'bip49', "m/49'/{ct}'/{acc}'", AF_P2WPKH_P2SH, 'p2sh-p2wpkh' ),   # was "p2wpkh-p2sh"
            ( 'bip84', "m/84'/{ct}'/{acc}'", AF_P2WPKH, 'p2wpkh' ),
        ]:
            dd = deriv.format(ct=chain.b44_cointype, acc=account_num)
            node = sv.derive_path(dd)
            xfp = xfp2str(node.my_fingerprint())
            xp = chain.serialize_public(node, AF_CLASSIC)
            zp = chain.serialize_public(node, fmt) if fmt != AF_CLASSIC else None

            # bonus/check: first non-change address: 0/0
            node.derive(0)
            node.derive(0)

            rv[name] = dict(deriv=dd, xpub=xp, xfp=xfp, first=chain.address(node, fmt), name=atype)
            if zp:
                rv[name]['_pub'] = zp

    return rv

def generate_electrum_wallet(addr_type, account_num=0):
    # Generate line-by-line JSON details about wallet.
    #
    # Much reverse engineering of Electrum here. It's a complex legacy file format.
    from common import settings
    from public_constants import AF_CLASSIC, AF_P2WPKH, AF_P2WPKH_P2SH

    chain = chains.current_chain()

    xfp = settings.get('xfp')

    # Must get the derivation path, and the SLIP32 version bytes right!
    if addr_type == AF_CLASSIC:
        mode = 44
    elif addr_type == AF_P2WPKH:
        mode = 84
    elif addr_type == AF_P2WPKH_P2SH:
        mode = 49
    else:
        raise ValueError(addr_type)

    derive = "m/{mode}'/{coin_type}'/{account}'".format(mode=mode,
                                                        account=account_num, coin_type=chain.b44_cointype)

    with stash.SensitiveValues() as sv:
        top = chain.serialize_public(sv.derive_path(derive), addr_type)

    # most values are nicely defaulted, and for max forward compat, don't want to set
    # anything more than I need to

    rv = dict(seed_version=17, use_encryption=False, wallet_type='single-sig')

    lab = 'Passport Import %s' % xfp2str(xfp)
    if account_num:
        lab += ' Acct#%d' % account_num

    # the important stuff.
    rv['keystore'] = dict(ckcc_xfp=xfp,
                          ckcc_xpub=settings.get('xpub'),
                          hw_type='passport', type='hardware',
                          label=lab, derivation=derive, xpub=top)

    return rv


async def make_json_wallet(label, generator, fname_pattern='new-wallet.json'):
    # Record **public** values and helpful data into a JSON file

    from common import dis, pa, settings
    from files import CardSlot, CardMissingError
    from actions import needs_microsd

    dis.fullscreen('Generating...')

    body = generator()

    # choose a filename

    try:
        with CardSlot() as card:
            fname, nice = card.pick_filename(fname_pattern)

            # do actual write
            with open(fname, 'wt') as fd:
                ujson.dump(body, fd)

    except CardMissingError:
        await needs_microsd()
        return
    except Exception as e:
        await ux_show_story('Unable to write!\n\n\n'+str(e))
        return

    msg = '''%s file written:\n\n%s''' % (label, nice)
    await ux_show_story(msg)

# EOF
