# SPDX-FileCopyrightText: 2020 Foundation Devices, Inc. <hello@foundationdevices.com>
# SPDX-License-Identifier: GPL-3.0-or-later
#
# ur2_codec.py
#
# UR 2.0 Codec
#
import math
import re

from .data_encoder import DataEncoder
from .data_decoder import DataDecoder
from .data_sampler import DataSampler
from .qr_type import QRType

from ur2.ur_decoder import URDecoder
from ur2.ur_encoder import UREncoder

from ur2.cbor_lite import CBORDecoder
from ur2.cbor_lite import CBOREncoder

from ur2.ur import UR
from utils import to_str

class UR2Decoder(DataDecoder):
    def __init__(self):
        self.decoder = URDecoder()

    # Decode the given data into the expected format
    def add_data(self, data):
        try:
            return self.decoder.receive_part(data)
        except Exception as e:
            print('EXCEPTION: {}'.format(e))
            return False

    def received_parts(self):
        return len(self.decoder.received_part_indexes())

    def total_parts(self):
        return self.decoder.expected_part_count()

    def is_complete(self):
        return self.decoder.is_complete()

    def get_error(self):
        if self.decoder.is_failure():
            return self.decoder.result_error()
        else:
            return None

    def get_ur_prefix(self):
        return self.decoder.expected_type()

    def decode(self):
        try:
            message = self.decoder.result_message()
            # print('UR2: message={}'.format(message.cbor))
            cbor_decoder = CBORDecoder(message.cbor)
            (data, length) = cbor_decoder.decodeBytes()
            # print('UR2: data={}'.format(data))
            return data
        except Exception as e:
            self.error = '{}'.format(e)
            # print('CBOR decode error: {}'.format(e))
            return None

    def get_data_format(self):
        return QRType.UR2

class UR2Encoder(DataEncoder):
    def __init__(self, args):
        self.qr_sizes = [280, 100, 70]
        self.type = None
        if isinstance(args, dict):
            self.prefix = args['prefix'] or 'bytes'
        else:
            self.prefix = 'bytes'

    def get_num_supported_sizes(self):
        return len(self.qr_sizes)

    def get_max_len(self, index):
        if index < 0 or index >= len(self.qr_sizes):
            return 0
        return self.qr_sizes[index]

    # Encode the given data
    def encode(self, data, is_cbor=False, max_fragment_len=500):
        if not is_cbor:
            encoder = CBOREncoder()
            # print('UR2: data={}'.format(to_str(data)))
            encoder.encodeBytes(data)
            data = encoder.get_bytes()
        # TODO: Need to change this interface most likely to allow for different types like crypto-psbt
        ur_obj = UR(self.prefix, data)
        self.ur_encoder = UREncoder(ur_obj, max_fragment_len)

    # UR2.0's next_part() returns the initial pieces split into max_fragment_len bytes, but then switches over to
    # an infinite series of encodings that combine various pieces of the data in an attempt to fill in any holes missed.
    def next_part(self):
        return self.ur_encoder.next_part()

    # Return any error message if decoding or adding data failed for some reason
    def get_error(self):
        return None

class UR2Sampler(DataSampler):
    # Check if the given bytes look like UR1 data
    # Return True if it matches or False if not
    @classmethod
    def sample(cls, data):
        try:
            # Rather than try a complex regex here, we just let the decoder try to decode and if it fails.
            # it must not be UR2.
            decoder = URDecoder()
            result = decoder.receive_part(data)
            return result
        except e:
            return False

    # Number of bytes required to successfully recognize this format
    @classmethod
    def min_sample_size(cls):
        return 20
