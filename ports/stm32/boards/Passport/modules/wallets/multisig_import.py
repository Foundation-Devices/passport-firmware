# SPDX-FileCopyrightText: 2021 Foundation Devices, Inc. <hello@foundationdevices.com>
# SPDX-License-Identifier: GPL-3.0-or-later
#
# SPDX-FileCopyrightText: 2018 Coinkite, Inc. <coldcardwallet.com>
# SPDX-License-Identifier: GPL-3.0-only
#
# (c) Copyright 2018 by Coinkite Inc. This file is part of Coldcard <coldcardwallet.com>
# and is covered by GPLv3 license found in COPYING.
#
# multisig_import.py - Multsig config import
#

from ux import ux_scan_qr_code, ux_show_story
import common
from common import system

async def read_multisig_config_from_qr():
    system.turbo(True);
    data = await ux_scan_qr_code('Import Multisig')
    system.turbo(False);

    if isinstance(data, (bytes, bytearray)):
        data = data.decode('utf-8')

    return data


async def read_multisig_config_from_microsd():
    from files import CardSlot, CardMissingError
    from actions import needs_microsd, file_picker

    def possible(filename):
        with open(filename, 'rt') as fd:
            for ln in fd:
                if 'pub' in ln:
                    return True

    fn = await file_picker('Select multisig configuration file to import (.txt)', suffix='.txt',
                           min_size=100, max_size=40*200, taster=possible)

    if not fn:
        return None

    system.turbo(True);
    try:
        with CardSlot() as card:
            with open(fn, 'rt') as fp:
                data = fp.read()
    except CardMissingError:
        system.turbo(False);
        await needs_microsd()
        return None

    system.turbo(False);

    # print('data={}'.format(data))

    return data
