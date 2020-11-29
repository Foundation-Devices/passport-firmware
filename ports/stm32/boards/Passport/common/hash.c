// SPDX-FileCopyrightText: 2020 Foundation Devices, Inc.  <hello@foundationdevices.com>
// SPDX-License-Identifier: GPL-3.0-or-later
//
// SPDX-FileCopyrightText: 2018 Coinkite, Inc.  <coldcardwallet.com>
// SPDX-License-Identifier: GPL-3.0-only
//
#include <stdint.h>
#include <string.h>

#ifndef PASSPORT_COSIGN_TOOL
#include "stm32h7xx_hal.h"
#endif /* PASSPORT_COSIGN_TOOL */

#include "utils.h"
#include "fwheader.h"
#include "sha256.h"
#include "secrets.h"

#define UID_LEN     (96/8) /* 96 bits (Section 61.1 in STMH753 RM) */

void hash_fw(
    fw_info_t *hdr,
    uint8_t *fw,
    size_t fwlen,
    uint8_t *hash,
    uint8_t hashlen
)
{
    SHA256_CTX  ctx;

    sha256_init(&ctx);

    /* Checksum the header */
    sha256_update(&ctx, (uint8_t *)hdr, sizeof(fw_info_t));

    /* Checksum the firmware */
    sha256_update(&ctx, fw, fwlen);
    sha256_final(&ctx, hash);

    /* double SHA256 */
    sha256_init(&ctx);
    sha256_update(&ctx, hash, hashlen);
    sha256_final(&ctx, hash);
}

#ifndef PASSPORT_COSIGN_TOOL
void hash_board(
    uint8_t *fw_hash,
    uint8_t fw_hash_len,
    uint8_t *hash,
    uint8_t hashlen
)
{
    SHA256_CTX  ctx;
    FLASH_TypeDef *flash = (FLASH_TypeDef *)FLASH_R_BASE;
    uint32_t options = (uint32_t)(flash->OPTSR_CUR & FLASH_OPTSR_RDP_Msk);

    sha256_init(&ctx);
    /* Add in firmware signature */
    sha256_update(&ctx, fw_hash, fw_hash_len);
    /* Add SE serial number */
    sha256_update(&ctx, rom_secrets->se_serial_number, sizeof(rom_secrets->se_serial_number));
    /* Add option bytes */
    sha256_update(&ctx, (uint8_t *)&options, sizeof(uint32_t));
    /* Add unique device ID */
    sha256_update(&ctx, (uint8_t *)UID_BASE, UID_LEN);
    sha256_final(&ctx, hash);

    /* double SHA256 */
    sha256_init(&ctx);
    sha256_update(&ctx, hash, hashlen);
    sha256_final(&ctx, hash);
}
#endif /* PASSPORT_COSIGN_TOOL */
