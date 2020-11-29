// SPDX-FileCopyrightText: 2020 Foundation Devices, Inc.  <hello@foundationdevices.com>
// SPDX-License-Identifier: GPL-3.0-or-later
//
// SPDX-FileCopyrightText: 2018 Coinkite, Inc.  <coldcardwallet.com>
// SPDX-License-Identifier: GPL-3.0-only
//
#pragma once

#include <stdint.h>

#define FW_START            (BL_FLASH_LAST)
#define FW_HEADER_SIZE      2048
#define FW_HEADER_MAGIC     0x50415353
#define FW_HDR              ((passport_firmware_header_t *)(FW_START))

#define HASH_LEN            32
#define SIGNATURE_LEN       64

typedef struct __attribute__ ((packed))
{
    uint32_t    magic;
    uint32_t    timestamp;
    uint8_t     fwversion[8];
    uint32_t    fwlength;
} fw_info_t;

typedef struct __attribute__ ((packed))
{
    uint32_t    pubkey1;
    uint8_t     signature1[SIGNATURE_LEN];
    uint32_t    pubkey2;
    uint8_t     signature2[SIGNATURE_LEN];
} fw_signature_t;

typedef struct __attribute__ ((packed))
{
    fw_info_t info;
    fw_signature_t signature;
} passport_firmware_header_t;

