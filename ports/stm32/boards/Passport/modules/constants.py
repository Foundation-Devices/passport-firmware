# SPDX-FileCopyrightText: 2020 Foundation Devices, Inc. <hello@foundationdevices.com>
# SPDX-License-Identifier: GPL-3.0-or-later
#

CAMERA_WIDTH = 330
CAMERA_HEIGHT = 396

VIEWFINDER_WIDTH = 240
VIEWFINDER_HEIGHT = 240

# External SPI Flash constants

# Must write with a multiple of this size
SPI_FLASH_PAGE_SIZE = 256

# Must erase with a multiple of these sizes
SPI_FLASH_SECTOR_SIZE = 4096
SPI_FLASH_BLOCK_SIZE = 65536
SPI_FLASH_TOTAL_SIZE = 2048 * 1024

# Flash cache
FLASH_CACHE_TOTAL_SIZE = 256 * 1024
FLASH_CACHE_START = SPI_FLASH_TOTAL_SIZE - FLASH_CACHE_TOTAL_SIZE
FLASH_CACHE_END = SPI_FLASH_TOTAL_SIZE
FLASH_CACHE_BLOCK_SIZE = 16 * 1024
FLASH_CACHE_CHECKSUM_SIZE = 32
FLASH_CACHE_MAX_JSON_LEN = FLASH_CACHE_BLOCK_SIZE - FLASH_CACHE_CHECKSUM_SIZE

# Flash usage for PSBT signing
PSBT_MAX_SIZE = (SPI_FLASH_TOTAL_SIZE - FLASH_CACHE_TOTAL_SIZE)  # Total size available for both input and output

# Flash firmware constants
FW_MAX_SIZE = SPI_FLASH_TOTAL_SIZE - FLASH_CACHE_TOTAL_SIZE
FW_HEADER_SIZE = 2048
FW_ACTUAL_HEADER_SIZE = 170 # passport_firmware_header_t uses this many bytes

MAX_PASSPHRASE_LENGTH = 64
MAX_ACCOUNT_NAME_LEN = 20
MAX_MULTISIG_NAME_LEN = 20

DEFAULT_ACCOUNT_ENTRY = {'name': 'Primary', 'acct_num': 0}

# Unit types for labeling conversions
UNIT_TYPE_BTC = 0
UNIT_TYPE_SATS = 1

# Maximum amount of characters in a text entry screen
MAX_MESSAGE_LEN = 64