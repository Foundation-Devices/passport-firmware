# SPDX-FileCopyrightText: 2018 Coinkite, Inc.  <coldcardwallet.com>
# SPDX-License-Identifier: GPL-3.0-only
#
# (c) Copyright 2018 by Coinkite Inc. This file is part of Coldcard <coldcardwallet.com>
# and is covered by GPLv3 license found in COPYING.
#
# files.py - microSD and related functions.
#
import pyb
import os
import sys
import utime
from uerrno import ENOENT


def _try_microsd(bad_fs_ok=False):
    # Power up, mount the SD card, return False if we can't for some reason.
    #
    # If we're about to reformat, we don't need a working filesystem

    sd = pyb.SDCard()

    if not sd.present():
        return False

    # if ckcc.is_simulator():
    #     return True

    try:
        # already mounted and ready?
        st = os.statvfs('/sd')
        return True
    except OSError:
        pass

    try:
        sd.power(1)
        os.mount(sd, '/sd', readonly=0, mkfs=0)
        st = os.statvfs('/sd')

        return True

    except OSError as exc:
        # corrupt or unformated SD card (or something)
        if bad_fs_ok:
            return True
        # sys.print_exception(exc)
        return False


def wipe_microsd_card():
    # Erase and re-format SD card. Not secure erase, because that is too slow.
    import callgate
    import pyb
    from common import dis

    try:
        os.umount('/sd')
    except:
        pass

    sd = pyb.SDCard()
    assert sd

    if not sd.present():
        return

    # power cycle so card details (like size) are re-read from current card
    sd.power(0)
    sd.power(1)

    dis.fullscreen('Part Erase...')
    cutoff = 1024       # arbitrary
    blk = bytearray(512)

    for bnum in range(cutoff):
        callgate.fill_random(blk)
        sd.writeblocks(bnum, blk)
        dis.progress_bar_show(bnum/cutoff)

    dis.fullscreen('Formating...')

    # remount, with newfs option
    os.mount(sd, '/sd', readonly=0, mkfs=1)

    # done, cleanup
    os.umount('/sd')

    # important: turn off power
    sd = pyb.SDCard()
    sd.power(0)


class CardMissingError(RuntimeError):
    pass


class CardSlot:
    # Touch interface must be disabled during any SD Card usage!
    last_change = None

    @classmethod
    def setup(cls):
        # Watch the SD card-detect signal line... but very noisy
        # - this is called a few seconds after system startup

        from pyb import Pin, ExtInt

        def card_change(_):
            # Careful: these can come fast and furious!
            cls.last_change = utime.ticks_ms()

        cls.last_change = utime.ticks_ms()

        cls.irq = ExtInt(Pin('SD_SW'), ExtInt.IRQ_RISING_FALLING,
                         Pin.PULL_UP, card_change)

    def __init__(self):
        self.active = False

    def __enter__(self):
        # Get ready!

        # busy wait for card pin to debounce/settle
        while 1:
            since = utime.ticks_diff(utime.ticks_ms(), self.last_change)
            if since > 50:
                break
            utime.sleep_ms(5)

        # attempt to use micro SD
        ok = _try_microsd()

        if not ok:
            self.recover()

            raise CardMissingError

        self.active = True

        return self

    def __exit__(self, *a):
        self.recover()
        return False

    def recover(self):

        self.active = False

        try:
            os.umount('/sd')
        except:
            pass

        # important: turn off power so touch can work again
        sd = pyb.SDCard()
        sd.power(0)

    def get_sd_root(self):
        # get the path to the SD card
        #if False: # ckcc.is_simulator():
        #    return ckcc.get_sim_root_dirs()[1]
        #else:
        return '/sd'

    def get_paths(self):
        # (full) paths to check on the card
        root = self.get_sd_root()

        return [root]

    def pick_filename(self, pattern, path=None):
        # given foo.txt, return a full path to filesystem, AND
        # a nice shortened version of the filename for display to user
        # - assuming we will write to it, so cannot exist
        # - return None,None if no SD card or can't mount, etc.
        # - no UI here please
        import ure

        assert self.active      # used out of context mgr

        # prefer SD card if we can
        path = path or (self.get_sd_root() + '/')

        assert '/' not in pattern
        assert '.' in pattern

        basename, ext = pattern.rsplit('.', 1)
        ext = '.' + ext

        # try w/o any number first
        fname = path + basename + ext
        try:
            os.stat(fname)
        except OSError as e:
            if e.args[0] == ENOENT:
                # file doesn't exist, done
                return fname, basename+ext
            pass

        # look for existing numbered files, even if some are deleted, and pick next
        # highest filename
        highest = 1
        pat = ure.compile(basename + r'-(\d+)' + ext)

        for fn in os.listdir(path):
            m = pat.match(fn)
            if not m:
                continue
            highest = max(highest, int(m.group(1)))

        fname = path + basename + ('-%d' % (highest+1)) + ext

        return fname, fname[len(path):]

    def get_file_path(self, filename, path=None):
        # given foo.txt, return a full path to filesystem, AND
        # a nice shortened version of the filename for display to user

        path = path or (self.get_sd_root() + '/')

        assert '/' not in filename
        assert '.' in filename

        basename, ext = filename.rsplit('.', 1)
        ext = '.' + ext

        fname = path + basename + ext

        return fname, basename+ext

# EOF
