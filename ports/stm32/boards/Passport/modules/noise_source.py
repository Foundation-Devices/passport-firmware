# SPDX-FileCopyrightText: 2020 Foundation Devices, Inc. <hello@foundationdevices.com>
# SPDX-License-Identifier: GPL-3.0-or-later
#
# noises_sources.py

# Matches up with the C definitions
# #define AVALANCHE_SOURCE 1
# #define MCU_RNG_SOURCE 2
# #define SE_RNG_SOURCE 4
# #define ALS_SOURCE 8

class NoiseSource:
    AVALANCHE = 1
    MCU = 2
    SE = 4
    AMBIENT_LIGHT_SENSOR = 8
    ALL = AVALANCHE | MCU | SE | AMBIENT_LIGHT_SENSOR
