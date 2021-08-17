# SPDX-FileCopyrightText: 2020 Foundation Devices, Inc. <hello@foundationdevices.com>
# SPDX-License-Identifier: GPL-3.0-or-later
#
# SPDX-FileCopyrightText: 2018 Coinkite, Inc. <coldcardwallet.com>
# SPDX-License-Identifier: GPL-3.0-only
#
# (c) Copyright 2018 by Coinkite Inc. This file is part of Coldcard <coldcardwallet.com>
# and is covered by GPLv3 license found in COPYING.
#
# sram2.py - Jam some larger, long-lived objects into the SRAM2 area, which isn't used enough.
#
# Cautions/Notes:
# - Total size of SRAM4 bank is 64K
# - mpy heap does not include SRAM4, so doing manual memory alloc here.
# - top 8k reserved for bootloader, which will wipe it on each entry
# - 2k at bottom reserved for code in `flashbdev.c` to use as cache data for flash writing
# - keep this file in sync with simulated version
#
import uctypes
from constants import VIEWFINDER_WIDTH, VIEWFINDER_HEIGHT

# see stm32/Passport/passport.ld where this is effectively defined
SRAM4_START = const(0x38000800)
SRAM4_LENGTH = const(0x10000)
SRAM4_END = SRAM4_START + SRAM4_LENGTH

_start = SRAM4_START

def _alloc(ln):
    global _start
    rv = uctypes.bytearray_at(_start, ln)
    _start += ln
    return rv

flash_cache_buf = _alloc(16 * 1024)
tmp_buf = _alloc(1024)
psbt_tmp256 = _alloc(256)
viewfinder_buf = _alloc((VIEWFINDER_WIDTH*VIEWFINDER_HEIGHT) // 8)
framebuffer_addr = _alloc(4) # Address of the frmebuffer memory so we can read it from OCD


assert _start <= SRAM4_END
