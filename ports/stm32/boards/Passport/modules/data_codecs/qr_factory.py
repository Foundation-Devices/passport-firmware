# SPDX-FileCopyrightText: 2020 Foundation Devices, Inc. <hello@foundationdevices.com>
# SPDX-License-Identifier: GPL-3.0-or-later
#
# qr_factory.py
#
# QR decoders
#

from .qr_codec import QREncoder, QRDecoder, QRSampler
from .ur1_codec import UR1Encoder, UR1Decoder, UR1Sampler
from .ur2_codec import UR2Encoder, UR2Decoder, UR2Sampler
from .qr_type import QRType

qrs = [
    {'name': 'UR2', 'type': QRType.UR2, 'encoder': UR2Encoder, 'decoder': UR2Decoder, 'sampler': UR2Sampler},
    {'name': 'UR1',  'type': QRType.UR1, 'encoder': UR1Encoder, 'decoder': UR1Decoder, 'sampler': UR1Sampler},
    {'name': 'QR',  'type': QRType.QR,  'encoder': QREncoder,  'decoder': QRDecoder,  'sampler': QRSampler},
]

def make_qr_encoder(qr_type, args):
    for entry in qrs:
        if entry['type'] == qr_type:
            return entry['encoder'](args)
    return None

def make_qr_decoder(qr_type):
    for entry in qrs:
        if entry['type'] == qr_type:
            return entry['decoder']()
    return None

# Given a data sample, return the QRType of it
def get_qr_type_for_data(data):
    for entry in qrs:
        if entry['sampler'].sample(data) == True:
            # print('Selecting QR decoder type: {}'.format(entry['name']))
            return entry['type']
    return None

def get_qr_decoder_for_data(data):
    qr_type = get_qr_type_for_data(data)
    return make_qr_decoder(qr_type)
