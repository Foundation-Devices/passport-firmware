# SPDX-FileCopyrightText: 2020 Foundation Devices, Inc. <hello@foundationdevices.com>
# SPDX-License-Identifier: GPL-3.0-or-later
#

# Get the async event loop to pass in where needed
loop = None

# System
system = None

# Keypad
keypad = None

# Internal flash-based settings
settings = None

# External SPI flash cache
flash_cache = None

# Display
dis = None

# Camera buffers
qr_buf = None
viewfinder_buf = None

# PinAttempts
pa = None

# External SPI Flash
sf = None

# Avalanche noise source
noise = None

# Battery level
battery_voltage = 0
battery_level = 100

# Demo
demo_active = False
demo_count = 0

# Last time the user interacted (i.e., pressed/released any key)
import utime
last_activity_time = utime.ticks_ms()

# Screenshot mode
screenshot_mode_enabled = False

# Snapshot mode
snapshot_mode_enabled = False

# Power monitor
powermon = None

# Battery Monitor
enable_battery_mon = False

# Active account
active_account = None

# Multisig wallet to associate with New Account flow
new_multisig_wallet = None
is_new_wallet_a_duplicate = False

# The QRTYpe of the last QR code that was scanned
last_scanned_qr_type = None
last_scanned_ur_prefix = None
