# SPDX-FileCopyrightText: 2020 Foundation Devices, Inc.  <hello@foundationdevices.com>
# SPDX-License-Identifier: GPL-3.0-or-later
#
from hashlib import sha256

def sha256_hash(data):
    m = sha256()
    m.update(data)
    return m.digest()

def compose3(f, g, h):
    return lambda x: f(g(h(x)))
