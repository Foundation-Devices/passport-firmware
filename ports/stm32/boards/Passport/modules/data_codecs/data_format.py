# SPDX-FileCopyrightText: 2020 Foundation Devices, Inc. <hello@foundationdevices.com>
# SPDX-License-Identifier: GPL-3.0-or-later
#
# data_format.py
#
# Simple types to act as an enums for all data formats that we read from file or QR code
#

from .multisig_config_sampler import MultisigConfigSampler
from .psbt_txn_sampler import PsbtTxnSampler
from .seed_sampler import SeedSampler
from .address_sampler import AddressSampler
from .http_sampler import HttpSampler
from .sign_message_sampler import SignMessageSampler

from actions import handle_psbt_data_format, handle_import_multisig_config, handle_seed_data_format, handle_sign_message_format #, handle_validate_address
from ie import handle_http

class QRType:
    QR = 0      # Standard QR code with no additional encoding
    UR1 = 1     # UR 1.0 pre-standard from Blockchain Commons
    UR2 = 2     # UR 2.0 standard from Blockchain Commons


samplers = [
    { 'sampler': PsbtTxnSampler, 'flow': handle_psbt_data_format },
    { 'sampler': MultisigConfigSampler, 'flow': handle_import_multisig_config },
    { 'sampler': SeedSampler, 'flow': handle_seed_data_format },
    { 'sampler': HttpSampler, 'flow': handle_http },
    { 'sampler': SignMessageSampler, 'flow': handle_sign_message_format },
    # { 'sampler': AddressSampler, 'flow': handle_validate_address },
]

def get_flow_for_data(data, expected=None):
    for entry in samplers:
        if entry['sampler'].sample(data) == True:
            return entry['flow']
    return None
