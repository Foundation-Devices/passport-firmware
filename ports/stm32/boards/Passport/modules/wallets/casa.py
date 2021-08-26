# SPDX-FileCopyrightText: 2021 Foundation Devices, Inc. <hello@foundationdevices.com>
# SPDX-License-Identifier: GPL-3.0-or-later
#
# casa.py - Casa support (preliminary)
#

from .multisig_json import create_multisig_json_wallet
from .multisig_import import read_multisig_config_from_qr, read_multisig_config_from_microsd
import chains
import stash
from utils import xfp2str

def create_casa_export(sw_wallet=None, addr_type=None, acct_num=0, multisig=False, legacy=False):
    # Get public details about wallet.
    #
    # simple text format:
    #   key = value
    # or #comments
    # but value is JSON
    from common import settings
    from public_constants import AF_CLASSIC

    chain = chains.current_chain()

    with stash.SensitiveValues() as sv:
        s = '''\
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
'''.format(nb=chain.name, xpub=chain.serialize_public(sv.node),
           sym=chain.ctype, ct=chain.b44_cointype, xfp=xfp2str(settings.get('xfp')))

        # print('create_casa_export() returning:\n{}'.format(s))
        return (s, None) # No 'acct_info'


CasaWallet = {
    'label': 'Casa',
    'sig_types': [
        {'id':'multisig', 'label':'Multisig', 'addr_type': None, 'create_wallet': create_casa_export,
         'import_microsd': read_multisig_config_from_microsd}
    ],
    'export_modes': [
        {'id': 'microsd', 'label': 'microSD', 'filename_pattern': '{sd}/{xfp}-casa.txt', 'ext': '.txt',
         'filename_pattern_multisig': '{sd}/{xfp}-casa-multisig.txt', 'ext_multisig': '.txt'}
    ]
}
