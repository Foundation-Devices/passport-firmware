// SPDX-FileCopyrightText: 2018 Coinkite, Inc.  <coldcardwallet.com>
// SPDX-License-Identifier: GPL-3.0-only
//
/*
 * (c) Copyright 2018 by Coinkite Inc. This file is part of Coldcard <coldcardwallet.com>
 * and is covered by GPLv3 license found in COPYING.
 *
 * update.c -- firmware update processing
 *
 */
#include <string.h>

#include "fwheader.h"
#include "sha256.h"
#include "spiflash.h"
#include "utils.h"

#include "verify.h"
#include "flash.h"
#include "update.h"

static void calculate_spi_hash(
    passport_firmware_header_t *hdr,
    uint8_t *hash,
    uint8_t hashlen
)
{
    SHA256_CTX ctx;
    uint32_t pos = FW_HEADER_SIZE;
    uint32_t remaining = hdr->info.fwlength;
    uint8_t *buf = (uint8_t *)D1_AXISRAM_BASE; /* Working memory */

    sha256_init(&ctx);
    
    sha256_update(&ctx, (uint8_t *)&hdr->info, sizeof(fw_info_t));

    while (remaining > 0)
    {
        size_t bufsize;

        if (remaining >= 8192)
            bufsize = 8192;
        else
            bufsize = remaining;

        if (spi_read(pos, bufsize, buf) != HAL_OK)
            goto out;

        sha256_update(&ctx, buf, bufsize);
        remaining -= bufsize;
        pos += bufsize;
    }

    sha256_final(&ctx, hash);

    /* double SHA256 */
    sha256_init(&ctx);
    sha256_update(&ctx, hash, hashlen);
    sha256_final(&ctx, hash);

out:
    return;
}

static int do_update(uint32_t size)
{
    int rc;
    uint8_t flash_word_len = sizeof(uint32_t) * FLASH_NB_32BITWORD_IN_FLASHWORD;
    uint32_t pos;
    uint32_t addr;
    uint32_t data[FLASH_NB_32BITWORD_IN_FLASHWORD] __attribute__((aligned(8)));

    flash_unlock();

    for (pos = 0, addr = FW_START; pos < size; pos += flash_word_len, addr += flash_word_len)
    {
        if (spi_read(pos, sizeof(data), (uint8_t *)data) != HAL_OK)
        {
            rc = -1;
            break;
        }

        if (addr % FLASH_SECTOR_SIZE == 0)
        {
            rc = flash_sector_erase(addr);
            if (rc < 0)
                break;
        }

        rc = flash_burn(addr, (uint32_t)data);
        if (rc < 0)
            break;
    }

    flash_lock();
    return rc;
}

bool is_firmware_update_present(void)
{
    passport_firmware_header_t hdr = {};

    if (spi_setup() != HAL_OK)
        return false;

    if (spi_read(0, sizeof(hdr), (void *)&hdr) != HAL_OK)
        return false;

    if (!verify_header(&hdr))
        return false;

    return true;
}

void update_firmware(void)
{
    int rc;
    passport_firmware_header_t *internalhdr = FW_HDR;
    passport_firmware_header_t spihdr = {0};
    uint8_t fw_hash[HASH_LEN] = {0};
    uint8_t zeros[FW_HEADER_SIZE] = {0};
    
    if (spi_setup() != HAL_OK)
        return;

    if (spi_read(0, sizeof(spihdr), (void *)&spihdr) != HAL_OK)
        return;


    if (!verify_header(&spihdr))
        goto out;

    /* Don't allow downgrades */
    if (spihdr.info.timestamp <= internalhdr->info.timestamp)
        goto out;
        
    calculate_spi_hash(&spihdr, fw_hash, sizeof(fw_hash));

    if (!verify_signature(&spihdr, fw_hash, sizeof(fw_hash)))
        goto out;

    rc = do_update(FW_HEADER_SIZE + spihdr.info.fwlength);
    if (rc < 0)
        return; /* Don't erase SPI...maybe it will work next time */

out:
    spi_write(0, sizeof(zeros), zeros);
}
