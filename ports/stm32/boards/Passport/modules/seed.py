# SPDX-FileCopyrightText: 2020 Foundation Devices, Inc. <hello@foundationdevices.com>
# SPDX-License-Identifier: GPL-3.0-or-later
#
# SPDX-FileCopyrightText: 2018 Coinkite, Inc. <coldcardwallet.com>
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
from pincodes import SE_SECRET_LEN
from stash import SecretStash, SensitiveValues
from ubinascii import hexlify as b2a_hex
from utils import pop_count, xfp2str
from ux import ux_show_story

# seed words lengths we support: 24=>256 bits, and recommended
VALID_LENGTHS = (24, 18, 12)


async def create_new_wallet_seed():
    from noise_source import NoiseSource
    from common import dis, system
    from uasyncio import sleep_ms

    # Pick a new random seed
    dis.fullscreen('Generating Seed...')
    await sleep_ms(1000)

    # always full 24-word (256 bit) entropy
    seed = bytearray(32)
    noise.random_bytes(seed, NoiseSource.ALL)

    # hash to mitigate any potential bias in Avalanche RNG
    seed = trezorcrypto.sha256(seed).digest()
    # print('create_new_wallet_seed(): New seed = {}'.format(b2a_hex(seed)))

    return seed

async def save_wallet_seed(seed_bits):
    from common import dis, pa, settings, system

    dis.fullscreen('Saving Seed...')

    system.show_busy_bar()

    # encode it for our limited secret space
    nv = SecretStash.encode(seed_bits=seed_bits)

    pa.change(new_secret=nv)

    # re-read settings since key is now different
    # - also captures xfp, xpub at this point
    await pa.new_main_secret(nv)

    # check and reload secret
    pa.reset()
    pa.login()

    system.hide_busy_bar()

def set_bip39_passphrase(pw):
    # apply bip39 passphrase for now (volatile)
    # - return None or error msg
    import stash
    from common import system
    from utils import bytes_to_hex_str

    stash.bip39_passphrase = pw

    # Create a hash from the passphrase
    if len(stash.bip39_passphrase) > 0:
        digest = bytearray(32)
        system.sha256(stash.bip39_passphrase, digest)
        digest_hex = bytes_to_hex_str(digest)
        stash.bip39_hash = digest_hex[:8]  # Take first 8 characters (32-bits)
        # print('stash.bip39_hash={}'.format(stash.bip39_hash))
    else:
        stash.bip39_hash = ''

    with stash.SensitiveValues() as sv:
        if sv.mode != 'words':
            # can't do it without original seed words
            return 'No BIP39 seed words'

        sv.capture_xpub()


async def remember_bip39_passphrase():
    # Compute current xprv and switch to using that as root secret.
    import stash
    from common import dis, pa, system

    dis.fullscreen('Check...')

    with stash.SensitiveValues() as sv:
        # GIT: https://github.com/Coldcard/firmware/commit/7e97d93153aee1a6878702145410ff9a6106119a
        # If this message is deemed unnecessary, we could consider if the above commit fixes it
        if sv.mode != 'words':
            # not a BIP39 derived secret, so cannot work.
            await ux_show_story('''The wallet secret was not based on a seed phrase, so we cannot add a BIP39 passphrase at this time.''', title='Failed')
            return

        nv = SecretStash.encode(xprv=sv.node)

    # Important: won't write new XFP to nvram if pw still set
    stash.bip39_passphrase = ''

    system.show_busy_bar()

    dis.fullscreen('Saving...')
    pa.change(new_secret=nv)

    # re-read settings since key is now different
    # - also captures xfp, xpub at this point
    await pa.new_main_secret(nv)

    system.hide_busy_bar()

    # check and reload secret
    pa.reset()
    pa.login()


async def erase_wallet(restart=True):
    from common import dis, pa, settings,system
    import utime
    import version

    dis.fullscreen('Erasing Wallet...')

    system.show_busy_bar();

    # Remove wallet-related settings, but leave other settings alone like terms_ok, validated_ok
    settings.remove('xfp')
    settings.remove('xpub')
    settings.remove('words')
    settings.remove('multisig')
    settings.remove('accounts')
    settings.remove('backup_quiz')
    settings.remove('enable_passphrase')

    # save a blank secret (all zeros is a special case)
    nv = bytes(SE_SECRET_LEN)
    pa.change(new_secret=nv)

    await settings.save()
    system.hide_busy_bar();

    if restart:
        dis.fullscreen('Restarting...')
        utime.sleep(1)

        # security: need to reboot to really be sure to clear the secrets from main memory.
        from machine import reset
        reset()


# EOF
