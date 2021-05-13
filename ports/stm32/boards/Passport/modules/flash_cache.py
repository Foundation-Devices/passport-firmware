# SPDX-FileCopyrightText: 2021 Foundation Devices, Inc. <hello@foundationdevices.com>
# SPDX-License-Identifier: GPL-3.0-or-later
#
# SPDX-FileCopyrightText: 2018 Coinkite, Inc. <coldcardwallet.com>
# SPDX-License-Identifier: GPL-3.0-only
#
# (c) Copyright 2018 by Coinkite Inc. This file is part of Coldcard <coldcardwallet.com>
# and is covered by GPLv3 license found in COPYING.
#
# flash_cache.py - Manage a cache of values in flash - similar to settings, but in external flash and much larger
#
# Notes:
# - Working memory is a 256K block of flash at the end of the 2MB extermal flash block
# - Cache size is 16K of JSON-encoded data
# - There are 16 cache blocks available which we rotate through randomly for flash wear leveling
# - All data is encrypted with an AES encryption key is derived from actual wallet secret
# - A 32-byte SHA is appended to the end of the cache as a checksum
#
import os, ujson, trezorcrypto, ustruct, gc
from uasyncio import sleep_ms
from uio import BytesIO
from sffile import SFFile
from utils import bytes_to_hex_str, to_str
from constants import (
    SPI_FLASH_SECTOR_SIZE,
    FLASH_CACHE_START,
    FLASH_CACHE_END,
    FLASH_CACHE_TOTAL_SIZE,
    FLASH_CACHE_BLOCK_SIZE,
    FLASH_CACHE_CHECKSUM_SIZE,
    FLASH_CACHE_MAX_JSON_LEN)

# Setup address offsets for the cache slotsk of the slots in external flash
# 256K total cache size at the end of the SPI flash split into 16 blocks of 16K each
SLOTS = range(FLASH_CACHE_START, FLASH_CACHE_END, FLASH_CACHE_BLOCK_SIZE)

# Working buffer from SRAM4
from sram4 import flash_cache_buf

class FlashCache:

    def __init__(self, loop=None):
        self.loop = loop
        self.is_dirty = 0
        self.my_pos = 0

        self.aes_key = b'\0'*32
        self.current = self.default_values()

        # NOTE: We don't load the FlashCache initially since we don't have the AES key until
        #       the user logs in successfully.
        # self.load()

    def get_aes(self, pos):
        # Build AES key for en/decrypt of specific block.
        # Include the slot number as part of the initial counter (CTR)
        return trezorcrypto.aes(trezorcrypto.aes.CTR, self.aes_key, ustruct.pack('<4I', 4, 3, 2, pos))

    def set_key(self, new_secret=None):
        from common import pa
        from stash import blank_object

        key = None
        mine = False

        if not new_secret:
            if pa.is_successful() or pa.is_secret_blank():
                # read secret and use it.
                new_secret = pa.fetch()
                mine = True

        if new_secret:
            # print('====> new_secret={}'.format(new_secret))
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
            # print('====> aes_key={}'.format(self.aes_key))

    def load(self):
        # Search all slots for any we can read, decrypt that,
        # and pick the newest one (in unlikely case of dups)
        from common import sf

        # reset
        self.current.clear()
        self.my_pos = 0
        self.is_dirty = 0

        # 4k, but last 32 bytes are a SHA (itself encrypted)
        global flash_cache_buf

        buf = bytearray(4)
        empty = 0
        for pos in SLOTS:
            # print('pos={}'.format(pos))
            gc.collect()

            sf.read(pos, buf)
            if buf[0] == buf[1] == buf[2] == buf[3] == 0xff:
                # print('probably an empty page')
                # erased (probably)
                empty += 1
                continue

            # check if first 2 bytes makes sense for JSON
            aes = self.get_aes(pos)
            chk = aes.decrypt(b'{"')
            # print('x5')

            if chk != buf[0:2]:
                # print('Doesn\'t look like JSON')
                # doesn't look like JSON meant for me
                continue

            # probably good, read it
            aes = self.get_aes(pos)

            chk = trezorcrypto.sha256()
            expect = None

            with SFFile(pos, length=FLASH_CACHE_BLOCK_SIZE, pre_erased=True) as fd:
                for i in range(FLASH_CACHE_BLOCK_SIZE/32):
                    enc = fd.read(32)
                    b = aes.decrypt(enc)

                    # print('i={}: {}'.format(i, bytes_to_hex_str(b)))
                    if i != (FLASH_CACHE_BLOCK_SIZE/32 - 1):
                        flash_cache_buf[i*32:(i*32)+32] = b
                        chk.update(b)
                    else:
                        expect = b

            try:

                # verify checksum in last 32 bytes
                actual = chk.digest()
                # print('  Expected: {}'.format(expect))
                # print('  Actual:   {}'.format(actual))
                if expect != actual:
                    # print('ERROR: Checksum doesn\'t match!')
                    continue

                # loads() can't work from a byte array, and converting to
                # bytes here would copy it; better to use file emulation.
                fd = BytesIO(flash_cache_buf)
                d = ujson.load(fd)
            except:
                # One in 65k or so chance to come here w/ garbage decoded, so
                # not an error.
                continue

            got_version = d.get('_revision', 0)
            if got_version > self.current.get('_revision', -1):
                # print('Possible winner: _version={}'.format(got_version))
                # likely winner
                self.current = d
                self.my_pos = pos
                # print("flash_cache: data @ %d w/ version=%d" % (pos, got_version))
            else:
                # print('Cleaning up stale data')
                # stale data seen; clean it up.
                assert self.current['_revision'] > 0
                #rint("flash_cache: cleanup @ %d" % pos)
                self.erase_cache_entry(pos)

        # 16k is a large object, sigh, for us right now. cleanup
        gc.collect()

        # done, if we found something
        if self.my_pos:
            # print('Flash cache Load successful!: current={}'.format(to_str(self.current)))
            return

        # print('Nothing found...fall back to defaults')
        # nothing found.
        self.my_pos = 0
        self.current = self.default_values()

        if empty == len(SLOTS):
            # Whole thing is blank. Bad for plausible deniability. Write 3 slots
            # with garbage. They will be wasted space until it fills.
            blks = list(SLOTS)
            trezorcrypto.random.shuffle(blks)

            for pos in blks[0:3]:
                for i in range(0, FLASH_CACHE_BLOCK_SIZE, 256):
                    h = trezorcrypto.random.bytes(256)
                    sf.wait_done()
                    sf.write(pos+i, h)

    def get(self, kn, default=None):
        return self.current.get(kn, default)

    def changed(self):
        self.is_dirty += 1
        if self.is_dirty < 2 and self.loop:
            self.loop.call_later_ms(250, self.write_out())

    def set(self, kn, v):
        self.current[kn] = v
        self.changed()

    def remove(self, kn):
        self.current.pop(kn, None)
        self.changed()

    def clear(self):
        # could be just:
        #       self.current = {}
        # but accomodating the simulator here
        rk = [k for k in self.current if k[0] != '_']
        for k in rk:
            del self.current[k]

        self.changed()

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
            self.loop.call_later_ms(250, self.write_out())

    def find_spot(self, not_here=0):
        # search for a blank sector to use
        # - check randomly and pick first blank one (wear leveling, deniability)
        # - we will write and then erase old slot
        # - if "full", blow away a random one
        from common import sf

        options = [s for s in SLOTS if s != not_here]
        trezorcrypto.random.shuffle(options)

        buf = bytearray(16)
        for pos in options:
            sf.read(pos, buf)
            if set(buf) == {0xff}:
                # blank
                return sf, pos

        victim = options[0]

        # Nowhere to write! (probably a bug because we have lots of slots)
        # ... so pick a random slot and kill what it had
        # print('ERROR: flash_cache full? Picking random slot to blow away...victim={}'.format(victim))

        self.erase_cache_entry(victim)

        return sf, victim

    def erase_cache_entry(self, start_pos):
        from common import sf
        sf.wait_done()
        for i in range(FLASH_CACHE_BLOCK_SIZE // SPI_FLASH_SECTOR_SIZE):
            addr = start_pos + (i*SPI_FLASH_SECTOR_SIZE)
            # print('erasing addr={}'.format(addr))
            sf.sector_erase(addr)
            sf.wait_done()

    def save(self):
        # render as JSON, encrypt and write it.

        self.current['_revision'] = self.current.get('_revision', 1) + 1

        sf, pos = self.find_spot(self.my_pos)
        # print('save(): sf={}, pos={}'.format(sf, pos))

        aes = self.get_aes(pos)

        with SFFile(pos, pre_erased=True, max_size=FLASH_CACHE_BLOCK_SIZE) as fd:
            chk = trezorcrypto.sha256()

            # first the json data
            d = ujson.dumps(self.current)
            # print('data: {}'.format(bytes_to_hex_str(d)))

            # pad w/ zeros
            data_len = len(d)
            pad_len = FLASH_CACHE_MAX_JSON_LEN - data_len
            if pad_len < 0:
                print('ERROR: JSON data is too big!')
                return

            fd.write(aes.encrypt(d))
            chk.update(d)
            del d

            # print('data_len={} pad_len={}'.format(data_len, pad_len))

            while pad_len > 0:
                here = min(32, pad_len)

                pad = bytes(here)
                fd.write(aes.encrypt(pad))
                chk.update(pad)
                # print('pad: {}'.format(bytes_to_hex_str(pad)))

                pad_len -= here

            # print('fd.tell()={}'.format(fd.tell()))

            digest = chk.digest()
            # print('Saving with digest={}'.format(digest))
            enc_digest = aes.encrypt(digest)
            # print('Encrypted digest={}'.format(enc_digest))
            fd.write(enc_digest)
            # print('fd.tell()={}  FLASH_CACHE_BLOCK_SIZE={}'.format(fd.tell(), FLASH_CACHE_BLOCK_SIZE))
            assert fd.tell() == FLASH_CACHE_BLOCK_SIZE

        # erase old copy of data
        if self.my_pos and self.my_pos != pos:
            self.erase_cache_entry(self.my_pos)

        self.my_pos = pos
        self.is_dirty = 0

    def merge(self, prev):
        # take a dict of previous values and merge them into what we have
        self.current.update(prev)

    def blank(self):
        # erase current copy of values in flash cache; older ones may exist still
        # - use when clearing the seed value

        if self.my_pos:
            self.erase_cache_entry(self.my_pos)
            self.my_pos = 0

        # act blank too, just in case.
        self.current.clear()
        self.is_dirty = 0

    @staticmethod
    def default_values():
        # Please try to avoid defaults here... It's better to put into code
        # where value is used, and treat undefined as the default state.
        return dict(_revision=0, _schema=1)

# EOF
