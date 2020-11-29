# SPDX-FileCopyrightText: 2020 Foundation Devices, Inc.  <hello@foundationdevices.com>
# SPDX-License-Identifier: GPL-3.0-or-later
#
# se_commands.py - Constants used to identify commands for Foundation.System.dispatch()
#
# Would be better if these were defined in Foundation.System directly using MP to export
# them.  That way the constant could be shared with C, but it was not clear if that can
# be achieved in MP.

# Main commands
CMD_GET_BOOTLOADER_VERSION = const(0)
CMD_GET_FIRMWARE_HASH = const(1)
CMD_UPGRADE_FIRMWARE  = const(2)
CMD_RESET = const(3)
CMD_LED_CONTROL = const(4)
CMD_IS_BRICKED = const(5)
CMD_READ_SE_SLOT = const(15)
CMD_GET_ANTI_PHISHING_WORDS = const(16)
CMD_GET_RANDOM_BYTES = const(17)
CMD_PIN_CONTROL = const(18)
CMD_GET_SE_CONFIG = const(20)
CMD_FIRMWARE_CONTROL = const(21)
CMD_GET_SUPPLY_CHAIN_VALIDATION_WORDS = const(22)
CMD_FACTORY_SETUP = const(-1)


# Subcommands for CMD_LED_CONTROL
LED_READ = const(0)
LED_SET_RED = const(1)
LED_SET_GREEN = const(2)
LED_ATTEMPT_TO_SET_GREEN = const(3)

# Subcommands for CMD_PIN_CONTROL
PIN_SETUP = const(0)
PIN_ATTEMPT = const(1)
PIN_CHANGE = const(2)
PIN_GET_SECRET = const(3)
PIN_GREENLIGHT_FIRMWARE = const(4)
PIN_LONG_SECRET = const(5)

# Subcommands for CMD_FIRMWARE_CONTROL
GET_MIN_FIRMWARE_VERSION = const(0)
GET_IS_FIRMWARE_DOWNGRADE = const(1)  # May not be used
UPDATE_HIGH_WATERMARK = const(2)
GET_HIGH_WATERMARK = const(3)  # May not be used
