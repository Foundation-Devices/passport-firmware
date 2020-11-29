// SPDX-FileCopyrightText: 2020 Foundation Devices, Inc.  <hello@foundationdevices.com>
// SPDX-License-Identifier: GPL-3.0-or-later
//
// SPDX-FileCopyrightText: 2018 Coinkite, Inc.  <coldcardwallet.com>
// SPDX-License-Identifier: GPL-3.0-only
//
/*
 * (c) Copyright 2018 by Coinkite Inc. This file is part of Coldcard <coldcardwallet.com>
 * and is covered by GPLv3 license found in COPYING.
 *
 * dispatch.c
 *
 * This code runs in an area of flash protected from viewing. It has limited entry
 * point (via a special callgate) and checks state carefully before running other stuff.
 *
 */
#include <errno.h>
#include <stdint.h>
#include <string.h>
#include <stdio.h>

#include "stm32h7xx_hal.h"

#include "utils.h"
#include "delay.h"
#include "pprng.h"
#include "se.h"
#include "sha256.h"

#include "version.h"
#include "gpio.h"
#include "se-atecc608a.h"
#include "pins.h"
#include "dispatch.h"

#define D1_AXISRAM_SIZE_MAX        ((uint32_t)0x00080000U)

// memset4()
//
static inline void memset4(uint32_t *dest, uint32_t value, uint32_t byte_len)
{
    for(; byte_len; byte_len-=4, dest++) {
        *dest = value;
    }
}

// wipe_all_sram()
//
static void wipe_all_sram(void)
{
#ifndef FIXME
    return;
#else
    const uint32_t noise = 0xdeadbeef;

    // wipe all of SRAM (except our own memory, which was already wiped)
    memset4((void *)D1_AXISRAM_BASE, noise, D1_AXISRAM_SIZE_MAX);
    memset4((void *)SRAM2_BASE, noise, SRAM2_SIZE - BL_SRAM_SIZE);
#endif /* FIXME */
}

// fatal_error(const char *msg)
//
    void
fatal_error(const char *msgvoid)
{
#ifdef FIXME
    oled_setup();
    oled_show(screen_fatal);
#endif
    // Maybe should do a reset after a delay, like with
    // the watchdog timer or something.
    LOCKUP_FOREVER();
}

// fatal_mitm()
//
void fatal_mitm(void)
{
#ifdef FIXME
    oled_setup();
    oled_show(screen_mitm);
#endif
#ifdef RELEASE
    wipe_all_sram();
#endif
    printf("====================================!\n");
    printf("FATAL MITM ATTACK!  LOOPING FOREVER!\n");
    printf("====================================!\n");
    LOCKUP_FOREVER();
}

static int good_addr(const uint8_t *b, int minlen, int len, bool readonly)
{
    uint32_t x = (uint32_t)b;

    if (minlen) {
        if (!b) return EFAULT;               // gave no buffer
        if (len < minlen) return ERANGE;     // too small
    }
        
    if ((x >= D1_AXISRAM_BASE) && ((x - D1_AXISRAM_BASE) < D1_AXISRAM_SIZE_MAX)) {
        // inside SRAM1, okay
        return 0;
    }

    if (!readonly) {
        return EPERM;
    }
#ifdef FIXME
    if ((x >= FIRMWARE_START) && (x - FIRMWARE_START) < FW_MAX_LENGTH) {
        // inside flash of main firmware (happens for QSTR's)
        return 0;
    }
#endif /* FIXME */
    return EACCES;
}

// se_dispatch()
//
// A C-runtime compatible env. is running, so do some work.
//
    __attribute__ ((used))
int se_dispatch(
    int method_num,
    uint8_t *buf_io,
    int len_in,
    uint32_t arg2,
    uint32_t incoming_sp,
    uint32_t incoming_lr
)
{
    int rv = 0;

    // Important:
    // - range check pointers so we aren't tricked into revealing our secrets
    // - check buf_io points to main SRAM, and not into us!
    // - range check len_in tightly
    // - calling convention only gives me enough for 4 args to this function, so 
    //   using read/write in place.
    // - use arg2 use when a simple number is needed; never a pointer!
    // - mpy may provide a pointer to flash if we give it a qstr or small value, and if
    //   we're reading only, that's fine.

    if (len_in > 1024) {     // arbitrary max, increase as needed
        rv = ERANGE;
        goto fail;
    }

    // Use these macros
#define REQUIRE_IN_ONLY(x)   if ((rv = good_addr(buf_io, (x), len_in, true))) { goto fail; }
#define REQUIRE_OUT(x)       if ((rv = good_addr(buf_io, (x), len_in, false))) { goto fail; }

    printf("se_dispatch() method_num=%d\n", method_num);
    switch(method_num) {
        case CMD_GET_BOOTLOADER_VERSION: {
            REQUIRE_OUT(64);

            // Return my version string
            memset(buf_io, 0, len_in);
#ifdef FIXME
            strlcpy((char *)buf_io, version_string, len_in);
#else
            memcpy(buf_io, version_string, len_in);
#endif
            rv = strlen(version_string);

            break;
        }
#ifdef FIXME
        case CMD_GET_FIRMWARE_HASH: {
            // Perform SHA256 over ourselves, with 32-bits of salt, to imply we 
            // haven't stored valid responses.
            REQUIRE_OUT(32);

            SHA256_CTX  ctx;
            sha256_init(&ctx);
            sha256_update(&ctx, (void *)&arg2, 4);
            sha256_update(&ctx, (void *)BL_FLASH_BASE, BL_FLASH_SIZE);
            sha256_final(&ctx, buf_io);

            break;
        }
#endif /* FIXME */
#ifdef FIXME
        case CMD_UPGRADE_FIRMWARE: {
            const uint8_t   *scr;
            bool secure = flash_is_security_level2();

            // Go into DFU mode. It's a one-way trip.
            // Also used to show some "fatal" screens w/ memory wipe.

            switch (arg2) {
                default:
                case 0:  // TODO: define constants once these are understood
                    // enter DFU for firmware upgrades
                    if (secure) {
                        // we cannot support DFU in secure mode anymore
                        rv = EPERM;
                        goto fail;
                    }
                    scr = screen_dfu;
                    break;
                case 1:
                    // in case some way for Micropython to detect it.
                    scr = screen_downgrade;
                    break;
                case 2:
                    scr = screen_blankish;
                    break;
                case 3:
                    scr = screen_brick;
                    secure = true;      // no point going into DFU, if even possible
                    break;
            }

            oled_setup();
            oled_show(scr);

            wipe_all_sram();

            if (secure) {
                // just die with that message shown; can't start DFU
                LOCKUP_FOREVER();
            } else {
                // Cannot just call enter_dfu() because it doesn't work well
                // once Micropython has configured so much stuff in the chip.

                // Leave a reminder to ourselves
                memcpy(dfu_flag->magic, REBOOT_TO_DFU, sizeof(dfu_flag->magic));
                dfu_flag->screen = scr;

                // reset system
                NVIC_SystemReset();

                // NOT-REACHED
            }
            break;
        }
#endif /* FIXME */
        case CMD_RESET:
            // logout: wipe all of memory and lock up. Must powercycle to recover.
            switch (arg2) { 
                case 0:
                case 2:
#ifdef FIXME
                    oled_show(screen_logout);
#endif /* FIXME */
                    break;
                case 1:
                    // leave screen untouched
                    break;
            }

            wipe_all_sram();

            if (arg2 == 2) {
                // need some time to show OLED contents
                delay_ms(100);

                // reboot so we can "login" again
                NVIC_SystemReset();

                // NOT-REACHED (but ok if it does)
            }

            // wait for an interrupt which will never happen (ie. sleep)
            LOCKUP_FOREVER()
            break;

        case CMD_IS_BRICKED:     
            // Are we a brick?
            // if the pairing secret doesn't work anymore, that
            // means we've been bricked.
            // TODO: also report hardware issue, and non-configured states
            se_setup();
            rv = (se_pair_unlock() != 0);
            break;

        case CMD_READ_SE_SLOT: {
            // Read a dataslot directly. Will fail on 
            // encrypted slots.
            if (len_in != 4 && len_in != 32 && len_in != 72) {
                rv = ERANGE;
            } else {
                REQUIRE_OUT(4);

                se_setup();
                if (se_read_data_slot(arg2 & 0xf, buf_io, len_in)) {
                    rv = EIO;
                }
            }
            
            break;
        }

        case CMD_GET_ANTI_PHISHING_WORDS: {
            // Provide the 2 words for anti-phishing.
            REQUIRE_OUT(MAX_PIN_LEN);

            // arg2: length of pin.
            if ((arg2 < 1) || (arg2 > MAX_PIN_LEN)) {
                rv = ERANGE;
            } else {
                if (anti_phishing_words((char *)buf_io, arg2, (uint32_t *)buf_io)) {
                    rv = EIO;
                }
            }
            break;
        }

        case CMD_GET_SUPPLY_CHAIN_VALIDATION_WORDS: {
            // Provide a hash to use for the supply chain validation words'
            if (supply_chain_validation_words((char *)buf_io, arg2, (uint32_t *)buf_io)) {
                rv = EIO;
            }
            break;
        }

        case CMD_GET_RANDOM_BYTES:
            rng_buffer(buf_io, len_in);
            break;

        case CMD_PIN_CONTROL: {
            // Try login w/ PIN.
            REQUIRE_OUT(PIN_ATTEMPT_SIZE_V1);
            pinAttempt_t *args = (pinAttempt_t *)buf_io;

            switch (arg2) {
                case PIN_SETUP:
                    rv = pin_setup_attempt(args);
                    break;
                case PIN_ATTEMPT:
                    rv = pin_login_attempt(args);
                    break;
                case PIN_CHANGE:
                    rv = pin_change(args);
                    break;
                case PIN_GET_SECRET:
                    rv = pin_fetch_secret(args);
                    break;
                case PIN_LONG_SECRET:
                    rv = pin_long_secret(args);
                    break;

                default:
                    rv = ENOENT;
                    break;
            }

            break;
        }

        case CMD_GET_SE_CONFIG:
            // Read out entire config dataspace
            REQUIRE_OUT(128);

            se_setup();
            rv = se_config_read(buf_io);
            if(rv) {
                rv = EIO;
            } 
            break;

        default:
            rv = ENOENT;
            break;
    }
#undef REQUIRE_IN_ONLY
#undef REQUIRE_OUT

fail:

    // Precaution: we don't want to leave ATECC508A authorized for any specific keys,
    // perhaps due to an error path we didn't see. Always reset the chip.
    se_reset_chip();

    return rv;
}

