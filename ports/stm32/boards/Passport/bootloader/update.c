// SPDX-FileCopyrightText: 2018 Coinkite, Inc. <coldcardwallet.com>
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
#include <stdlib.h>

#include "display.h"
#include "fwheader.h"
#include "hash.h"
#include "se-config.h"
#include "sha256.h"
#include "spiflash.h"
#include "splash.h"
#include "utils.h"

#include "se-atecc608a.h"
#include "verify.h"
#include "flash.h"
#include "update.h"
#include "ui.h"
#include "gpio.h"
#include "firmware-keys.h"

// Global so we can compare with it later in do_update()
static uint8_t spi_hdr_hash[HASH_LEN] = {0};

static void clear_update_from_spi_flash()
{
    uint8_t zeros[FW_HEADER_SIZE] = {0};

    spi_write(0, 256, zeros);
    spi_write(256, sizeof(zeros), zeros);
}

static void calculate_spi_hash(
    passport_firmware_header_t *hdr,
    uint8_t *hash,
    uint8_t hashlen
)
{
    SHA256_CTX ctx;
    uint32_t pos = FW_HEADER_SIZE + 256;  // Skip over the update hash page
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

static void calculate_spi_hdr_hash(
    passport_firmware_header_t *hdr,
    uint8_t *hash,
    uint8_t hashlen
)
{
    SHA256_CTX ctx;

    sha256_init(&ctx);
    sha256_update(&ctx, (uint8_t *)hdr, sizeof(passport_firmware_header_t));
    sha256_final(&ctx, hash);

    /* double SHA256 */
    sha256_init(&ctx);
    sha256_update(&ctx, hash, hashlen);
    sha256_final(&ctx, hash);
}

// Hash the spi hash with the device hash value -- used to prevent external attacker from beign able to insert a firmware
// update directly in external SPI flash. They won't be able to replicate this hash.
static void calculate_update_hash(
    uint8_t *spi_hash,
    uint8_t spi_hashlen,
    uint8_t *update_hash,
    uint8_t update_hashlen
)
{
    SHA256_CTX ctx;

    uint8_t device_hash[HASH_LEN];
    get_device_hash(device_hash);

    sha256_init(&ctx);
    sha256_update(&ctx, (uint8_t *)spi_hash, spi_hashlen);
    sha256_update(&ctx, device_hash, sizeof(device_hash));
    sha256_final(&ctx, update_hash);
}

static int do_update(uint32_t size)
{
    int rc;
    uint8_t flash_word_len = sizeof(uint32_t) * FLASH_NB_32BITWORD_IN_FLASHWORD;
    uint32_t pos;
    uint32_t addr;
    uint32_t data[FLASH_NB_32BITWORD_IN_FLASHWORD] __attribute__((aligned(8)));
    uint32_t total = FW_END - FW_START;
    uint8_t percent_done = 0;
    uint8_t last_percent_done = 255;
    uint8_t curr_spi_hdr_hash[HASH_LEN] = {0};
    uint32_t remaining_bytes_to_hash = sizeof(passport_firmware_header_t);
    secresult not_checked = SEC_TRUE;
    SHA256_CTX ctx;

    sha256_init(&ctx);

    flash_unlock();

    // Make sure header still fits in one page or this check will be more complex.
    if (sizeof(passport_firmware_header_t) > 256) {
        clear_update_from_spi_flash();
        ui_show_fatal_error("sizeof(passport_firmware_header_t) > 256");
    }

    for (pos = 0, addr = FW_START; pos < size; pos += flash_word_len, addr += flash_word_len)
    {
        // We read starting 256 bytes in as the first page holds the update request hash
        if (spi_read(pos + 256, sizeof(data), (uint8_t *)data) != HAL_OK)
        {
            rc = -1;
            break;
        }

        // TOCTOU check by hashing the header again and comparing to the hash we took earlier when we verified it.
        if (remaining_bytes_to_hash > 0) {
            // Calculate the running hash 32 bytes at a time until we reach sizeof(passport_firmware_header_t)
            size_t hash_size = MIN(remaining_bytes_to_hash, flash_word_len);
            sha256_update(&ctx, (uint8_t *)data, hash_size);
            remaining_bytes_to_hash -= hash_size;
        }

        if (not_checked == SEC_TRUE && remaining_bytes_to_hash == 0) {
            // Finalize the hash and check it
            sha256_final(&ctx, curr_spi_hdr_hash);

            /* double SHA256 */
            sha256_init(&ctx);
            sha256_update(&ctx, curr_spi_hdr_hash, HASH_LEN);
            sha256_final(&ctx, curr_spi_hdr_hash);

            // ui_show_hex_buffer("Prev Hash", spi_hdr_hash, HASH_LEN);
            // ui_show_hex_buffer("TOCTOU Hash", curr_spi_hdr_hash, HASH_LEN);

            // Compare the hashes
            if (memcmp(curr_spi_hdr_hash, spi_hdr_hash, HASH_LEN) != 0) {
                // Someone may be hacking on the SPI flash!
                clear_update_from_spi_flash();
                ui_show_fatal_error("\nSPI flash appears to have been actively modified during firmware update.");
            }
            not_checked = SEC_FALSE;
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

        /* Update the progress bar only if the percentage changed */
        percent_done = (uint8_t)((float)pos/(float)total * 100.0f);

        if (percent_done != last_percent_done)
        {
            display_progress_bar(PROGRESS_BAR_MARGIN, PROGRESS_BAR_Y, SCREEN_WIDTH - (PROGRESS_BAR_MARGIN * 2), PROGRESS_BAR_HEIGHT, percent_done);
            /* Showing just the lines that changed is much faster and avoids full-screen flicker */
            display_show_lines(PROGRESS_BAR_Y, PROGRESS_BAR_Y + PROGRESS_BAR_HEIGHT);
            last_percent_done = percent_done;
        }
    }

    /* Clear the remainder of flash */
    memset(data, 0, sizeof(data));
    for (; addr < FW_END; pos += flash_word_len, addr += flash_word_len)
    {
        if (addr % FLASH_SECTOR_SIZE == 0)
        {
            rc = flash_sector_erase(addr);
            if (rc < 0)
                break;
        }

        rc = flash_burn(addr, (uint32_t)data);
        if (rc < 0)
            break;

        /* Update the progress bar only if the percentage changed */
        percent_done = (uint8_t)((float)pos/(float)total * 100.0f);

        if (percent_done != last_percent_done)
        {
            display_progress_bar(PROGRESS_BAR_MARGIN, PROGRESS_BAR_Y, SCREEN_WIDTH - (PROGRESS_BAR_MARGIN * 2), PROGRESS_BAR_HEIGHT, percent_done);
            /* Showing just the lines that changed is much faster and avoids full-screen flicker */
            display_show_lines(PROGRESS_BAR_Y, PROGRESS_BAR_Y + PROGRESS_BAR_HEIGHT);
            last_percent_done = percent_done;
        }
    }

    /* Make sure the progress bar goes to 100 */
    display_progress_bar(PROGRESS_BAR_MARGIN, PROGRESS_BAR_Y, SCREEN_WIDTH - (PROGRESS_BAR_MARGIN * 2), PROGRESS_BAR_HEIGHT, 100);
    display_show_lines(PROGRESS_BAR_Y, PROGRESS_BAR_Y + PROGRESS_BAR_HEIGHT);

    flash_lock();
    return rc;
}

secresult is_firmware_update_present(void)
{
    passport_firmware_header_t hdr = {};

    if (spi_setup() != HAL_OK)
        return SEC_FALSE;

    // Skip first page of flash
    if (spi_read(256, sizeof(hdr), (void *)&hdr) != HAL_OK)
        return SEC_FALSE;

    if (!verify_header(&hdr))
        return SEC_FALSE;

    return SEC_TRUE;
}

void update_firmware(void)
{
    int rc;
    passport_firmware_header_t *internalhdr = FW_HDR;
    passport_firmware_header_t spihdr = {0};
    uint8_t internal_fw_hash[HASH_LEN] = {0};
    uint8_t spi_fw_hash[HASH_LEN] = {0};
    uint8_t current_board_hash[HASH_LEN] = {0};
    uint8_t new_board_hash[HASH_LEN] = {0};
    uint8_t actual_update_hash[HASH_LEN] = {0};
    uint8_t expected_update_hash[HASH_LEN] = {0};

    /*
     * If we fail to either setup the SPI bus or read the SPI flash
     * then just return...something is wrong in hardware but maybe it's
     * temporary.
     */
    if (spi_setup() != HAL_OK)
        return;

    // If the update was requested by the user, then there will be a hash in the first 32 bytes that combines
    // the firmware hash with the device hash.
    if (spi_read(0, HASH_LEN, (void *)&actual_update_hash) != HAL_OK)
        return;

    // Start reading one page in as there is a 32-byte hash in the first page
    if (spi_read(256, sizeof(spihdr), (void *)&spihdr) != HAL_OK)
        return;
    // ui_show_hex_buffer("SPI Hdr 1", (uint8_t*)&spihdr, 170);

    calculate_spi_hdr_hash(&spihdr, spi_hdr_hash, HASH_LEN);

    // ui_show_hex_buffer("SPI Hdr Hash", spi_hdr_hash, HASH_LEN);

    calculate_update_hash(spi_hdr_hash, sizeof(spi_hdr_hash), expected_update_hash, sizeof(expected_update_hash));

    // Ensure that the hashes match!
    if (memcmp(expected_update_hash, actual_update_hash, sizeof(expected_update_hash)) != 0) {
        // This looks like an unrequested update (i.e., a possible attack)
        goto out;
    }

    /* Verify firmware header in SPI flash and bail if it fails */
    if (!verify_header(&spihdr))
    {
        if (ui_show_message("Update Error", "The firmware update you chose has an invalid header and will not be installed.", "SHUTDOWN", "OK", true)){
            goto out;
        } else {
            display_clean_shutdown();
        }
    }

    /*
     * If the current firmeware verification passes then compare
     * timestamps and don't allow an earlier version. However, if the
     * internal firmware header verification fails then proceed with the
     * update...maybe the previous update attempt failed because we lost
     * power.
     *
     * We also allow going back and forth between user-signed firmware and Foundation-signed firmware.
     */
    if (verify_current_firmware(true) == SEC_TRUE)
    {
        if ((spihdr.signature.pubkey1 != FW_USER_KEY && internalhdr->signature.pubkey1 != FW_USER_KEY) &&
            (spihdr.info.timestamp < internalhdr->info.timestamp))
        {
            if (ui_show_message("Update Error", "This firmware update is older than the current firmware and will not be installed.", "SHUTDOWN", "OK", true))
                goto out;
            else
                display_clean_shutdown();
        }

        // Handle the firmware hash update
        uint8_t *fwptr = (uint8_t *)internalhdr + FW_HEADER_SIZE;
        hash_fw(&internalhdr->info, fwptr, internalhdr->info.fwlength, internal_fw_hash, sizeof(internal_fw_hash));
        hash_board(internal_fw_hash, sizeof(internal_fw_hash), current_board_hash, sizeof(current_board_hash));

        calculate_spi_hash(&spihdr, spi_fw_hash, sizeof(spi_fw_hash));

        /* Verify the signature and bail if it fails */
        if (verify_signature(&spihdr, spi_fw_hash, sizeof(spi_fw_hash)) == SEC_FALSE)
        {
            if (ui_show_message("Update Error", "The firmware update does not appear to be properly signed and will not be installed.\n\nThis can also occur if you lost power during a firmware update.", "SHUTDOWN", "OK", true))
                goto out;
            else
                display_clean_shutdown();
        }

        /*
         * Calculate a new board hash based on the SPI firmware and then
         * reprogram the board hash in the SE. If the update fails it
         * will be retried until it succeeds or the board is declared dead.
         */
        hash_board(spi_fw_hash, sizeof(spi_fw_hash), new_board_hash, sizeof(new_board_hash));

        #ifdef CONVERSION_BUILD
        /*
         * Conversion build is temporary and used to get current demo
         * boards which have 0's programmed for the board hash to be
         * properly programmed with a real board hash. Thereafter they
         * will only be able to update via SD card.
         * Delete this code once this has been done.
         */
        memset(current_board_hash, 0, sizeof(current_board_hash));
        #endif /* CONVERSION_BUILD */

        rc = se_program_board_hash(current_board_hash, new_board_hash, sizeof(new_board_hash));
        if (rc < 0) {
            if (ui_show_message("Update Error", "Unable to update the firmware hash in the Secure Element. Update will continue, but may not be successful.", "SHUTDOWN", "OK", true)){
                // Nothing to do
            } else {
                display_clean_shutdown();

            }
        }
    }

    // Draw the logo and message - progress bar gets drawn and updated periodically in do_update()
    show_splash("Updating Firmware...");

    rc = do_update(FW_HEADER_SIZE + spihdr.info.fwlength);
    if (rc < 0)
    {
        if (ui_show_message("Update Error", "Failed to install the firmware update.", "SHUTDOWN", "RESTART", true))
            passport_reset();
        else
            // TODO: Should we have an option here to clear the SPI flash and restart (we could run a verify_current_firmware() first to make sure it's safe to boot there
            display_clean_shutdown();
    }

out:
    clear_update_from_spi_flash();
}

secresult is_user_signed_firmware_installed(void)
{
    passport_firmware_header_t *hdr = FW_HDR;
    return (hdr->signature.pubkey1 == FW_USER_KEY && hdr->signature.pubkey2 == 0) ? SEC_TRUE : SEC_FALSE;
}
