# SPDX-FileCopyrightText: 2020 Foundation Devices, Inc.  <hello@foundationdevices.com>
# SPDX-License-Identifier: GPL-3.0-or-later
#
# SPDX-FileCopyrightText: 2018 Coinkite, Inc.  <coldcardwallet.com>
# SPDX-License-Identifier: GPL-3.0-only
#
# (c) Copyright 2018 by Coinkite Inc. This file is part of Coldcard <coldcardwallet.com>
# and is covered by GPLv3 license found in COPYING.
#
# settings.py - manage a few key values that aren't super secrets
#
# Goals:
# - Single wallet settings
# - Wear leveling of the flash
# - If no settings are readable, erase flash and start over
#
# Result:
# - up to 4k of values supported (after json encoding)
# - encrypted and stored in SPI flash, in last 128k area
# - AES encryption key is derived from actual wallet secret
# - if logged out, then use fixed key instead (ie. it's public)
# - to support multiple wallets and plausible deniablity, we
#   will preserve any noise already there, and only replace our own stuff
# - you cannot move data between slots because AES-CTR with CTR seed based on slot #
# - SHA check on decrypted data
#
import os
import ujson
import ustruct
import uctypes
import gc
import trezorcrypto
from uio import BytesIO
from uasyncio import sleep_ms
from ubinascii import hexlify as b2a_hex

# Base address for internal memory-mapped flash used for settings: 0x81E0000
SETTINGS_FLASH_START = const(0x81E0000)
SETTINGS_FLASH_LENGTH = const(0x20000)  # 128K
SETTINGS_FLASH_END = SETTINGS_FLASH_START + SETTINGS_FLASH_LENGTH - 1
DATA_SIZE = const(4096 - 32)
BLOCK_SIZE = const(4096)

# Setting values:
#   xfp = master xpub's fingerprint (32 bit unsigned)
#   xpub = master xpub in base58
#   chain = 3-letter codename for chain we are working on (BTC)
#   words = (bool) BIP39 seed words exist (else XPRV or master secret based)
#   b39skip = (bool) skip discussion about use of BIP39 passphrase
#   idle_to = idle timeout period (seconds)
#   _version = internal version number for data - incremented every time the data is saved
#   terms_ok = customer has signed-off on the terms of sale
#   tested = selftest has been completed successfully
#   multisig = list of defined multisig wallets (complex)
#   pms = trust/import/distrust xpubs found in PSBT files
#   axi = index of last selected address in explorer
#   lgto = (minutes) how long to wait for Login Countdown feature
#   usr = (dict) map from username to their secret, as base32
# Stored w/ key=00 for access before login
#   _skip_pin = hard code a PIN value (dangerous, only for debug)
#   nick = optional nickname for this coldcard (personalization)
#   rngk = randomize keypad for PIN entry


# These are the data slots available to use.  We have 32 slots
# for flash wear leveling.
SLOT_ADDRS = range(SETTINGS_FLASH_START, SETTINGS_FLASH_END - BLOCK_SIZE, BLOCK_SIZE)


class Settings:

    def __init__(self, loop=None):
        from foundation import SettingsFlash
        self.loop = loop
        self.is_dirty = 0

        self.aes_key = b'\0' * 32
        self.curr_dict = self.default_values()
        self.overrides = {}     # volatile overide values
 
        self.flash = SettingsFlash()

        self.load()

    def get_aes(self, flash_offset):
        # Build AES key for en/decrypt of specific block.
        # Include the slot number as part of the initial counter (CTR)
        return trezorcrypto.aes(trezorcrypto.aes.CTR, self.aes_key, ustruct.pack('<4I', 4, 3, 2, flash_offset))

    def set_key(self, new_secret=None):
        # System settings (not secrets) are stored in internal flash, encrypted with this
        # key that is derived from main wallet secret. Call this method when the secret
        # is first loaded, or changes for some reason.
        from common import pa
        from stash import blank_object

        key = None
        mine = False

        if not new_secret:
            if not pa.is_successful() or pa.is_secret_blank():
                # simple fixed key allows us to store a few things when logged out
                key = b'\0'*32
            else:
                # read secret and use it.
                new_secret = pa.fetch()
                mine = True

        if new_secret:
            # hash up the secret... without decoding it or similar
            assert len(new_secret) >= 32

            s = trezorcrypto.sha256(new_secret)

            for round in range(5):
                s.update('pad')

                s = trezorcrypto.sha256(s.digest())

            key = s.digest()

            if mine:
                blank_object(new_secret)

        # for restore from backup case, or when changing (created) the seed
        self.aes_key = key

    def load(self):
        # Search all slots for any we can read, decrypt that,
        # and pick the newest one (in unlikely case of dups)

        try:
            # reset
            self.curr_dict.clear()
            self.overrides.clear()
            self.addr = 0
            self.is_dirty = 0

            for addr in SLOT_ADDRS:
                buf = uctypes.bytearray_at(addr, 4)
                if buf[0] == buf[1] == buf[2] == buf[3] == 0xff:
                    # Save this so we can start at an empty slot when no decodable data
                    # is found (we can't just start at the beginning since it might
                    # not be erased).
                    # print('  Slot is ERASED')
                    # erased (probably)
                    continue

                # check if first 2 bytes makes sense for JSON
                flash_offset = (addr - SETTINGS_FLASH_START) // BLOCK_SIZE
                aes = self.get_aes(flash_offset)
                chk = aes.decrypt(b'{"')

                if chk != buf[0:2]:
                    # doesn't look like JSON, so skip it
                    # print(' Slot does not contain JSON')
                    continue

                # probably good, so prepare to read it
                aes = self.get_aes(flash_offset)
                chk = trezorcrypto.sha256()
                expect = None

                # Copy the data - our flash is memory mapped, so we read directly by address
                buf = uctypes.bytearray_at(addr, DATA_SIZE)

                # Get a bytearray for the SHA256 at the end
                expected_sha = uctypes.bytearray_at(addr + DATA_SIZE, 32)

                # Decrypt and check hash 
                b = aes.decrypt(buf)

                # Add the decrypted result to the SHA
                chk.update(b)

                try:
                    # verify hash in last 32 bytes
                    assert expected_sha == chk.digest()

                    # FOUNDATION
                    # loads() can't work from a byte array, and converting to
                    # bytes here would copy it; better to use file emulation.
                    # print('json = {}'.format(b))
                    d = ujson.load(BytesIO(b))
                except:
                    # One in 65k or so chance to come here w/ garbage decoded, so
                    # not an error.
                    # print('ERROR?  Unable to decode JSON')
                    continue

                curr_version = d.get('_version', 0)
                if curr_version > self.curr_dict.get('_version', -1):
                    # print('Found candidate JSON: {}'.format(d))
                    # A newer entry was found
                    self.curr_dict = d
                    self.addr = addr

            # If we loaded settings, then we're done
            if self.addr:
                return

            # Add some che
            # if self.

            # If no entries were found, which means this is either the first boot or we have corrupt settings, so raise an exception so we erase and set default
            # raise ValueError('Flash is either blank or corrupt, so me must reset to recover to avoid a crash!')
            self.curr_dict = self.default_values()
            self.overrides.clear()
            self.addr = 0

        except Exception as e:
            print('Exception in settings.load(): e={}'.format(e))
            self.reset()
            self.is_dirty = True
            self.write_out()

    def get(self, kn, default=None):
        if kn in self.overrides:
            return self.overrides.get(kn)
        else:
            return self.curr_dict.get(kn, default)

    def changed(self):
        self.is_dirty += 1
        if self.is_dirty < 2 and self.loop:
            self.loop.call_later_ms(250, self.write_out())

    def set(self, kn, v):
        self.curr_dict[kn] = v
        print('Settings: Set {} to {}'.format(kn, v))
        self.changed()

    def set_volatile(self, kn, v):
        self.overrides[kn] = v

    def reset(self):
        self.erase_settings_flash()
        self.curr_dict = self.default_values()
        self.overrides.clear()
        self.addr = 0
        self.is_dirty = False

    def erase_settings_flash(self):
        self.flash.erase()

    async def write_out(self):
        # delayed write handler
        if not self.is_dirty:
            # someone beat me to it
            return

        # Was sometimes running low on memory in this area: recover
        try:
            gc.collect()
            self.save()
        except MemoryError:
            # TODO: This would be an infinite async loop if it throws an exception every time -- fix this
            self.loop.call_later_ms(250, self.write_out())

    def find_first_erased_addr(self):
        for addr in SLOT_ADDRS:
            buf = uctypes.bytearray_at(addr, 4)
            if buf[0] == buf[1] == buf[2] == buf[3] == 0xff:
                return addr
        return 0

    # We use chunks sequentially since there is no benefit to randomness
    # here.  An attacker needs the PIN to decrypt the AES, and if he has
    # the PIN, first of all, it's game over for the Bitcoin, and even if
    # the attacker cares about these settings, running AES on each of the
    # 32 entries instead of just one is trivial.
    def next_addr(self):
        # If no entries were found on load, addr will be zero
        if self.addr == 0:
            addr = self.find_first_erased_addr()
            if addr == 0:
                # Everything is full, so we must erase and start again
                self.flash.erase()
                return SETTINGS_FLASH_START
            else:
                return addr

        # Go to next address
        if self.addr < SETTINGS_FLASH_END - BLOCK_SIZE:
            return self.addr + BLOCK_SIZE
        
        # We reached the end of the bank -- we need to erase it so
        # the new settings can be written.
        self.flash.erase()
        return SETTINGS_FLASH_START

    def save(self):
        # Render as JSON, encrypt and write it
        self.curr_dict['_version'] = self.curr_dict.get('_version', 0) + 1

        addr = self.next_addr()
        print('===============================================================')
        print('SAVING SETTINGS! _version={} addr={}'.format(self.curr_dict['_version'], hex(addr)))
        print('===============================================================')

        flash_offset = (addr - SETTINGS_FLASH_START) // BLOCK_SIZE
        aes = self.get_aes(flash_offset)

        chk = trezorcrypto.sha256()

        # Create the JSON string as bytes
        json_buf = ujson.dumps(self.curr_dict).encode('utf8')

        # Ensure data is not too big
        # TODO: Check that null byte at the end is handled properly (no overflow)
        if len(json_buf) > DATA_SIZE:
            # TODO: Proper error handling
            assert false, 'JSON data is larger than'.format(DATA_SIZE)

        # Create a zero-filled byte buf
        padded_buf = bytearray(DATA_SIZE)

        # Copy the json data into the padded buffer
        for i in range(len(json_buf)):
            padded_buf[i] = json_buf[i]
        del json_buf

        # Add the data and padding to the AES and SHA
        encrypted_buf = aes.encrypt(padded_buf)
        chk.update(padded_buf)

        # Build the final buf for writing to flash
        save_buf = bytearray(BLOCK_SIZE)
        for i in range(len(encrypted_buf)):
            save_buf[i] = encrypted_buf[i]  # TODO: How to do this with slice notation so it doesn't truncate destination?

        digest = chk.digest()
        for i in range(32):
            save_buf[BLOCK_SIZE - 32 + i] = digest[i]

        # print('addr={}\nbuf={}'.format(hex(addr),b2a_hex(save_buf)))
        self.flash.write(addr, save_buf)

        # We don't overwrite the old entry here, even though it's now useless, as that can
        # cause flash to have ECC errors.

        self.addr = addr
        self.is_dirty = 0
        print("Settings.save(): wrote @ {}".format(hex(addr)))


    def merge(self, prev):
        # take a dict of previous values and merge them into what we have
        self.curr_dict.update(prev)

    @staticmethod
    def default_values():
        # Please try to avoid defaults here. It's better to put into code
        # where value is used, and treat undefined as the default state.
        return dict(_version=0)

# EOF
