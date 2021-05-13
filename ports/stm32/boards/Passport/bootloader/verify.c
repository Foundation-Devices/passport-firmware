// SPDX-FileCopyrightText: 2018 Coinkite, Inc. <coldcardwallet.com>
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
#include <stdint.h>
#include <string.h>

#include "delay.h"
#include "firmware-keys.h"
#include "hash.h"
#include "se.h"
#include "se-config.h"
#include "sha256.h"
#include "uECC.h"
#include "utils.h"

#include "se-atecc608a.h"
#include "verify.h"

secresult verify_header(passport_firmware_header_t *hdr)
{
    if (hdr->info.magic != FW_HEADER_MAGIC) goto fail;
    if (hdr->info.timestamp == 0) goto fail;
    if (hdr->info.fwversion[0] == 0x0) goto fail;
    if (hdr->info.fwlength < FW_HEADER_SIZE) goto fail;

#ifdef USE_CRYPTO
    // if (hdr->signature.pubkey1 == 0) goto fail;
    if ((hdr->signature.pubkey1 != FW_USER_KEY) && (hdr->signature.pubkey1 > FW_MAX_PUB_KEYS)) goto fail;
    if (hdr->signature.pubkey1 != FW_USER_KEY)
    {
        // if (hdr->signature.pubkey2 == 0) goto fail;
        if (hdr->signature.pubkey2 > FW_MAX_PUB_KEYS) goto fail;
    }
#endif /* USE_CRYPTO */

    return SEC_TRUE;

fail:
    return SEC_FALSE;
}

secresult verify_signature(
    passport_firmware_header_t *hdr,
    uint8_t *fw_hash,
    uint32_t hashlen
)
{
#ifdef USE_CRYPTO
    int rc;

    if (hdr->signature.pubkey1 == FW_USER_KEY)
    {
        uint8_t user_public_key[72] = {0};

        /*
         * It looks like the user signed this firmware so, in order to
         * validate, we need to get the public key from the SE.
         */
        se_pair_unlock();
        rc = se_read_data_slot(KEYNUM_user_fw_pubkey, user_public_key, sizeof(user_public_key));
        if (rc < 0)
            return SEC_FALSE;

        rc = uECC_verify(user_public_key,
                         fw_hash, hashlen,
                         hdr->signature.signature1, uECC_secp256k1());
        if (rc == 0)
            return SEC_FALSE;
    }
    else
    {
        rc = uECC_verify(approved_pubkeys[hdr->signature.pubkey1],
                         fw_hash, hashlen,
                         hdr->signature.signature1, uECC_secp256k1());
        if (rc == 0)
            return SEC_FALSE;

        rc = uECC_verify(approved_pubkeys[hdr->signature.pubkey2],
                         fw_hash, hashlen,
                         hdr->signature.signature2, uECC_secp256k1());
        if (rc == 0)
            return SEC_FALSE;
    }

    return SEC_TRUE;
#else
    return SEC_TRUE;
#endif /* USE_CRYPTO */
}

secresult verify_current_firmware(
    bool process_led
)
{
    uint8_t fw_hash[HASH_LEN];
    passport_firmware_header_t *fwhdr = (passport_firmware_header_t *)FW_HDR;
    uint8_t *fwptr = (uint8_t *)fwhdr + FW_HEADER_SIZE;

    if (!verify_header(fwhdr))
        return ERR_INVALID_FIRMWARE_HEADER;

    hash_fw(&fwhdr->info, fwptr, fwhdr->info.fwlength, fw_hash, sizeof(fw_hash));

    if (verify_signature(fwhdr, fw_hash, sizeof(fw_hash)) == SEC_FALSE)
        return ERR_INVALID_FIRMWARE_SIGNATURE;

#ifdef PRODUCTION_BUILD
    if (process_led)
    {
        int rc;
        uint8_t board_hash[HASH_LEN];

        hash_board(fw_hash, sizeof(fw_hash), board_hash, sizeof(board_hash));

        rc = se_set_gpio_secure(board_hash);
        if (rc < 0)
             return ERR_UNABLE_TO_UPDATE_FIRMWARE_HASH_IN_SE;
    }
#endif /* PRODUCTION_BUILD */

    return SEC_TRUE;
}

// EOF
