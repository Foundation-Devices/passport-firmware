// SPDX-FileCopyrightText: 2018 Coinkite, Inc.  <coldcardwallet.com>
// SPDX-License-Identifier: GPL-3.0-only
//
/*
 * (c) Copyright 2018 by Coinkite Inc. This file is part of Coldcard <coldcardwallet.com>
 * and is covered by GPLv3 license found in COPYING.
 *
 * verify.c -- Check signatures on firmware images in flash.
 *
 */
#include <stdlib.h>
#include <string.h>

#include "utils.h"
#include "sha256.h"
#include "firmware-keys.h"
#include "hash.h"
#include "delay.h"
#include "uECC.h"
#include "se.h"
#include "se-atecc608a.h"

#include "update.h"
#include "verify.h"

bool verify_header(passport_firmware_header_t *hdr)
{
    if (hdr->info.magic != FW_HEADER_MAGIC) goto fail;
    if (hdr->info.timestamp == 0) goto fail;
    if (hdr->info.fwversion[0] == 0x0) goto fail;
    if (hdr->info.fwlength == 0x0) goto fail;
#ifdef USE_CRYPTO
    if (hdr->signature.pubkey1 == 0) goto fail;
    if (hdr->signature.pubkey1 > FW_MAX_PUB_KEYS) goto fail;
    if (hdr->signature.pubkey2 == 0) goto fail;
    if (hdr->signature.pubkey2 > FW_MAX_PUB_KEYS) goto fail;
#endif /* USE_CRYPTO */

    return true;

fail:
    return false;
}

bool verify_signature(
    passport_firmware_header_t *hdr,
    uint8_t *fw_hash,
    uint32_t hashlen
)
{
#ifdef USE_CRYPTO
    int rc;

    rc = uECC_verify(approved_pubkeys[hdr->signature.pubkey1],
                     fw_hash, hashlen,
                     hdr->signature.signature1, uECC_secp256k1());
    if (rc == 0)
        return false;

    rc = uECC_verify(approved_pubkeys[hdr->signature.pubkey2],
                     fw_hash, hashlen,
                     hdr->signature.signature2, uECC_secp256k1());
    if (rc == 0)
        return false;

    return true;
#else
    return true;
#endif /* USE_CRYPTO */
}

bool verify_current_firmware(void)
{
    int rc;
    uint8_t fw_hash[HASH_LEN];
    uint8_t board_hash[HASH_LEN];
    passport_firmware_header_t *fwhdr = (passport_firmware_header_t *)FW_HDR;
    uint8_t *fwptr = (uint8_t *)fwhdr + FW_HEADER_SIZE;

    if (!verify_header(fwhdr))
        goto fail;

    hash_fw(&fwhdr->info, fwptr, fwhdr->info.fwlength, fw_hash, sizeof(fw_hash));

    if (!verify_signature(fwhdr, fw_hash, sizeof(fw_hash)))
        goto fail;

#ifdef DEMO
    memset(board_hash, 0, sizeof(board_hash));
#else
    hash_board(fw_hash, sizeof(fw_hash), board_hash, sizeof(board_hash));
#endif /* DEMO */
    rc = se_set_gpio_secure(board_hash);
    if (rc < 0)
         goto fail;

    return true;

fail:
    return false;
}

// EOF
