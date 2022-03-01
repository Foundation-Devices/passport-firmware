# SPDX-FileCopyrightText: 2020 Foundation Devices, Inc. <hello@foundationdevices.com>
# SPDX-License-Identifier: GPL-3.0-or-later
#
# sign_message_sampler.py
#
# Sampler for messages to be signed
# Currently used for health checks by Casa
#

from .data_sampler import DataSampler
from ubinascii import hexlify as b2a_hex
from utils import cleanup_deriv_path

class SignMessageSampler(DataSampler):
    # Check if the given bytes look like a message to sign + '\n' + derivation path
    # Return True if it matches or False if not.
    @classmethod
    def sample(cls, data):
        # print('SignMessageSampler: data={}'.format(data))
        deriv_split = data.split('\n')
        # print('SignMessageSampler: split data={}'.format(deriv_split))

        try:
            deriv = cleanup_deriv_path(deriv_split[1])
        except BaseException as exc:
            print('Invalid derivation path string. Error: {}'.format(exc))

        if deriv != None:
            return True

        return False

    # Number of bytes required to successfully recognize this format
    # Message can be any length 1 byte or more
    # Plus one byte for \n
    # Plus at least 5 bytes for a derivation path: e.g., m/44'
    @classmethod
    def min_sample_size(cls):
        return 7