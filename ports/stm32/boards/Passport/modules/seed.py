# SPDX-FileCopyrightText: 2020 Foundation Devices, Inc.  <hello@foundationdevices.com>
# SPDX-License-Identifier: GPL-3.0-or-later
#
# SPDX-FileCopyrightText: 2018 Coinkite, Inc.  <coldcardwallet.com>
# SPDX-License-Identifier: GPL-3.0-only
#
# (c) Copyright 2018 by Coinkite Inc. This file is part of Coldcard <coldcardwallet.com>
# and is covered by GPLv3 license found in COPYING.
#
# seed.py - bip39 seeds and words
#
# references:
# - <https://github.com/bitcoin/bips/blob/master/bip-0039.mediawiki>
# - <https://iancoleman.io/bip39/#english>
# - zero values:
#    - 'abandon' * 23 + 'art'
#    - 'abandon' * 17 + 'agent'
#    - 'abandon' * 11 + 'about'
#

from common import noise

import trezorcrypto
import uctypes
from pincodes import AE_LONG_SECRET_LEN, AE_SECRET_LEN
from stash import SecretStash, SensitiveValues
from ubinascii import hexlify as b2a_hex
from utils import pop_count, xfp2str
from ux import ux_show_story

# seed words lengths we support: 24=>256 bits, and recommended
VALID_LENGTHS = (24, 18, 12)


def create_new_wallet_seed():
    # Pick a new random seed, and

    # await ux_dramatic_pause('Generating...', 4)
    # TODO: Show screen to indicate delay?

    # always full 24-word (256 bit) entropy
    seed = bytearray(32)
    noise.random_bytes(seed)

    # hash to mitigate any potential bias in Avalanche RNG
    seed = trezorcrypto.sha256(seed).digest()
    print('create_new_wallet(): New seed = {}'.format(b2a_hex(seed)))

    return seed

def save_wallet_seed(seed_bits):
    from common import dis, pa, settings

    print('save_wallet_seed 1')
    # encode it for our limited secret space
    nv = SecretStash.encode(seed_bits=seed_bits)
    print('save_wallet_seed 2: nv={}'.format(b2a_hex(nv)))

    dis.fullscreen('Saving Wallet...')
    pa.change(new_secret=nv)
    print('save_wallet_seed 3')

    # re-read settings since key is now different
    # - also captures xfp, xpub at this point
    pa.new_main_secret(nv)
    print('save_wallet_seed 4')

    # check and reload secret
    pa.reset()
    print('save_wallet_seed 5')
    pa.login()
    print('save_wallet_seed 6')

# TODO: PASSPHRASE
def set_bip39_passphrase(pw):
    # apply bip39 passphrase for now (volatile)
    # - return None or error msg
    import stash

    stash.bip39_passphrase = pw

    # takes a bit, so show something
    from common import dis
    dis.fullscreen("Working...")

    with stash.SensitiveValues() as sv:
        if sv.mode != 'words':
            # can't do it without original seed woods
            return 'No BIP39 seed words'

        sv.capture_xpub()


async def remember_bip39_passphrase():
    # Compute current xprv and switch to using that as root secret.
    import stash
    from common import dis, pa

    dis.fullscreen('Check...')

    with stash.SensitiveValues() as sv:
        if sv.mode != 'words':
            # not a BIP39 derived secret, so cannot work.
            await ux_show_story('''The wallet secret was not based on a seed phrase, so we cannot add a BIP39 passphrase at this time.''', title='Failed')
            return

        nv = SecretStash.encode(xprv=sv.node)

    # Important: won't write new XFP to nvram if pw still set
    stash.bip39_passphrase = ''

    dis.fullscreen('Saving...')
    pa.change(new_secret=nv)

    # re-read settings since key is now different
    # - also captures xfp, xpub at this point
    pa.new_main_secret(nv)

    # check and reload secret
    pa.reset()
    pa.login()


def clear_seed(restart=True):
    from common import dis, pa, settings
    import utime
    import version

    dis.fullscreen('Erasing Seed...')

    # clear settings associated with this key, since it will be no more
    settings.reset()

    # save a blank secret (all zeros is a special case, detected by bootloader)
    nv = bytes(AE_SECRET_LEN)
    pa.change(new_secret=nv)

    # wipe the long secret too
    nv = bytes(AE_LONG_SECRET_LEN)
    pa.ls_change(nv)

    if restart:
        dis.fullscreen('Restarting...')
        utime.sleep(1)

        # security: need to reboot to really be sure to clear the secrets from main memory.
        from machine import reset
        reset()



# EOF