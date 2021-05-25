# SPDX-FileCopyrightText: 2021 Foundation Devices, Inc. <hello@foundationdevices.com>
# SPDX-License-Identifier: GPL-3.0-or-later
#
# SPDX-FileCopyrightText: 2018 Coinkite, Inc. <coldcardwallet.com>
# SPDX-License-Identifier: GPL-3.0-only
#
# (c) Copyright 2018 by Coinkite Inc. This file is part of Coldcard <coldcardwallet.com>
# and is covered by GPLv3 license found in COPYING.
#
# multisig_json.py - Multsig export format
#

import stash
import uio
from utils import xfp2str
from .utils import get_next_account_num
from common import settings
from public_constants import AF_P2SH, AF_P2WSH, AF_P2WSH_P2SH


def create_multisig_json_wallet(sw_wallet=None, addr_type=None, acct_num=0, multisig=False, legacy=False):
    fp = uio.StringIO()

    fp.write('{\n')
    accts = []
    with stash.SensitiveValues() as sv:

        for deriv, name, fmt in [
            ("m/45'", 'p2sh', AF_P2SH),
            ("m/48'/0'/{acct}'/1'", 'p2wsh_p2sh', AF_P2WSH_P2SH),
            ("m/48'/0'/{acct}'/2'", 'p2wsh', AF_P2WSH)
        ]:
            # Fill in the acct number
            dd = deriv.format(acct=acct_num)
            node = sv.derive_path(dd)
            xfp = xfp2str(node.my_fingerprint())
            xpub = sv.chain.serialize_public(node, fmt)
            fp.write('  "%s_deriv": "%s",\n' % (name, dd))
            fp.write('  "%s": "%s",\n' % (name, xpub))

            accts.append( {'fmt': fmt, 'deriv': dd, 'acct': acct_num} ) # e.g., AF_P2WSH_P2SH: {'deriv':m/48'/0'/4'/1', 'acct': 4}

    xfp = xfp2str(settings.get('xfp', 0))
    fp.write('  "xfp": "%s"\n}\n' % xfp)
    result = fp.getvalue()
    # print('xpub json = {}'.format(result))
    return (result, accts)