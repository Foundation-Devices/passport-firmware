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
 * SPDX-FileCopyrightText: 2020 Foundation Devices, Inc.  <hello@foundationdevices.com>
 * SPDX-License-Identifier: GPL-3.0-or-later
 */
#include <errno.h>
#include <string.h>
#include <stdio.h>
#include "stm32h7xx_hal.h"
#include "stm32h7xx_hal_uart.h"
#include "stm32h7xx_hal_uart_ex.h"

#include "utils.h"
#include "pprng.h"
#include "sha256.h"
#include "secrets.h"
#include "se.h"
#include "se-config.h"

#include "se-atecc608a.h"

// Selectable debug level; keep them as comments regardless
#if 0
// break on any error: not helpful since some are normal
# define ERR(msg)            BREAKPOINT;
# define ERRV(val, msg)       BREAKPOINT;
#else
# define ERR(msg)
# define ERRV(val, msg)
#endif

// Must be exactly 32 chars:
// static const char *copyright_msg = "Copyright 2020- by Foundati Inc.";

// keep this in place.
#define RET_IF_BAD(rv)		do { if(rv) return rv; } while(0)

bool se_probe()
{
    int chk;

    se_sleep();
    se_wake();

    // Expect 0x11
    chk = se_read1();
    if (chk != SE_AFTER_WAKE)
        return false;
    se_sleep();

    return true;
}

// Do Info(p1=2) command, and return result.
//
uint16_t se_get_info(void)
{
    int rc;

    // not doing error checking here
    se_write(OP_Info, 0x2, 0, NULL, 0);
    // note: always returns 4 bytes, but most are garbage and unused.
    uint8_t tmp[4];
    rc = se_read(tmp, 4);
    se_sleep();
    if (rc < 0)
        return -1;

    return (tmp[0] << 8) | tmp[1];
}

// Load Tempkey with a specific value. Resulting Tempkey cannot be
// used with many commands/keys, but is needed for signing.
//
int se_load_nonce(uint8_t *nonce)
{
    uint8_t rc;

    // p1=3
    se_write(OP_Nonce, 3, 0, nonce, 32);          // 608a ok
    rc = se_read1();
    se_sleep();
    if (rc != 0)
        return -1;
    return 0;
}

// Sign a message (already digested)
//
int se_sign(uint8_t keynum, uint8_t msg_hash[32], uint8_t signature[64])
{
    int rc;

    rc = se_load_nonce(msg_hash);
    if (rc < 0)
        return -1;

    se_write(OP_Sign, 0x80, keynum, NULL, 0);
    rc = se_read(signature, 64);
    se_sleep();
    if (rc < 0)
        return -1;

    return 0;
}

// Just read a one-way counter.
//
int se_get_counter(uint32_t *result, uint8_t counter_number)
{
    int rc;

    se_write(OP_Counter, 0x0, counter_number, NULL, 0);
    rc = se_read((uint8_t *)result, 4);
    se_sleep();
    if (rc < 0)
        return -1;

    // IMPORTANT: Always verify the counter's value because otherwise
    // nothing prevents an active MitM changing the value that we think
    // we just read.
    uint8_t     digest[32];
    rc = se_gendig_counter(counter_number, *result, digest);
    if (rc < 0)
        return -1;

    if (!se_is_correct_tempkey(digest))
        return -1;

    return 0;
}

// Add-to and return a one-way counter's value. Have to go up in
// single-unit steps, but can we loop.
//
int se_add_counter(uint32_t *result, uint8_t counter_number, int incr)
{
    int rc;
    int rval = 0;

    for (int i = 0; i < incr; i++) {
        se_write(OP_Counter, 0x1, counter_number, NULL, 0);
        rc = se_read((uint8_t *)result, 4);
        if (rc < 0)
        {
            rval = -1;
            goto out;
        }
    }
    
    // IMPORTANT: Always verify the counter's value because otherwise
    // nothing prevents an active MitM changing the value that we think
    // we just read. They could also stop us increamenting the counter.

    uint8_t     digest[32];
    rc = se_gendig_counter(counter_number, *result, digest);
    if (rc < 0)
    {
        rval = -1;
        goto out;
    }

    if (!se_is_correct_tempkey(digest))
        rval = -1;

out:
    se_sleep();
    return rval;
}

// Use old SHA256 command from 508A, but with new flags.
//
int se_hmac32(uint8_t keynum, uint8_t msg[32], uint8_t digest[32])
{
    int rc;

    // Start SHA w/ HMAC setup
    se_write(OP_SHA, 4, keynum, NULL, 0);        // 4 = HMAC_Init
    rc = se_read1();
    if (rc != 0)
        return -1;

    // send the contents to be hashed
    se_write(OP_SHA, (3<<6) | 2, 32, msg, 32); // 2 = Finalize, 3=Place output
    rc = se_read(digest, 32);
    se_sleep();
    return rc;
}

// Return the serial number: it's 9 bytes, altho 3 are fixed.
//
int se_get_serial(uint8_t serial[6])
{
    int rc;
    uint8_t temp[32];

    se_write(OP_Read, 0x80, 0x0, NULL, 0);
    rc = se_read(temp, 32);
    se_sleep();
    if (rc < 0)
        return -1;

    // reformat to 9 bytes.
    uint8_t ts[9];
    memcpy(ts, &temp[0], 4);
    memcpy(&ts[4], &temp[8], 5);

    // check the hard-coded values
    if ((ts[0] != 0x01) || (ts[1] != 0x23) || (ts[8] != 0xEE)) return 1;

    // save only the unique bits.
    memcpy(serial, ts+2, 6);

    return 0;
}

// Construct a digest over one of the two counters. Track what we think
// the digest should be, and ask the chip to do the same. Verify we match
// using MAC command (done elsewhere).
//
int se_gendig_counter(int counter_num, const uint32_t expected_value, uint8_t digest[32])
{
    int rc;
    uint8_t num_in[20], tempkey[32];

    rng_buffer(num_in, sizeof(num_in));

    rc = se_pick_nonce(num_in, tempkey);
    if (rc < 0)
        return -1;

    //using Zone=4="Counter" => "KeyID specifies the monotonic counter ID"
    se_write(OP_GenDig, 0x4, counter_num, NULL, 0);
    rc = se_read1();
    se_sleep();
    if (rc != 0)
        return -1;
#if 0
    se_keep_alive();
#endif
    // we now have to match the digesting (hashing) that has happened on
    // the chip. No feedback at this point if it's right tho.
    //
    //   msg = hkey + b'\x15\x02' + ustruct.pack("<H", slot_num)
    //   msg += b'\xee\x01\x23' + (b'\0'*25) + challenge
    //   assert len(msg) == 32+1+1+2+1+2+25+32
    //
    SHA256_CTX ctx;
    sha256_init(&ctx);

    uint8_t zeros[32] = { 0 };
    uint8_t args[8] = { OP_GenDig, 0x4, counter_num, 0,  0xEE, 0x01, 0x23, 0x0 };

    sha256_update(&ctx, zeros, 32);
    sha256_update(&ctx, args, sizeof(args));
    sha256_update(&ctx, (const uint8_t *)&expected_value, 4);
    sha256_update(&ctx, zeros, 20);
    sha256_update(&ctx, tempkey, 32);
    sha256_final(&ctx, digest);

    return 0;
}


int se_encrypted_read32(int data_slot, int blk,
                    int read_kn, const uint8_t read_key[32], uint8_t data[32])
{
    int rc;
    uint8_t digest[32];

    rc = se_pair_unlock();
    if (rc < 0)
        return -1;

    rc = se_gendig_slot(read_kn, read_key, digest);
    if (rc < 0)
        return -1;

    // read nth 32-byte "block"
    se_write(OP_Read, 0x82, (blk << 8) | (data_slot<<3), NULL, 0);
    rc = se_read(data, 32);
    se_sleep();
    if (rc < 0)
        return -1;

    xor_mixin(data, digest, 32);

    return 0;
}

int se_encrypted_read(int data_slot, int read_kn, const uint8_t read_key[32], uint8_t *data, int len)
{
    int rc;
#ifdef FIXME
    // not clear if chip supports 4-byte encrypted reads
    ASSERT((len == 32) || (len == 72));
#endif
    rc = se_encrypted_read32(data_slot, 0, read_kn, read_key, data);
    if (rc < 0)
        return -1;

    if (len == 32)
        return 0;

    rc = se_encrypted_read32(data_slot, 1, read_kn, read_key, data+32);
    if (rc < 0)
        return -1;

    uint8_t tmp[32];
    rc = se_encrypted_read32(data_slot, 2, read_kn, read_key, tmp);
    if (rc < 0)
        return -1;

    memcpy(data+64, tmp, 72-64);

    return 0;
}

int se_read_data_slot(int slot_num, uint8_t *data, int len)
{
    int rc;
    int rval = 0;
#ifdef FIXME
    ASSERT((len == 4) || (len == 32) || (len == 72));
#endif
    // zone => data
    // only reading first block of 32 bytes. ignore the rest
    se_write(OP_Read, (len == 4 ? 0x00 : 0x80) | 2, (slot_num<<3), NULL, 0);
    rc = se_read(data, (len == 4) ? 4 : 32);
    if (rc < 0)
    {
        rval = -1;
        goto out;
    }
    
    if (len == 72) {
        // read second block
        se_write(OP_Read, 0x82, (1<<8) | (slot_num<<3), NULL, 0);
        rc = se_read(data+32, 32);
        if (rc < 0)
        {
            rval = -1;
            goto out;
        }

        // read third block, but only using part of it
        uint8_t     tmp[32];
        se_write(OP_Read, 0x82, (2<<8) | (slot_num<<3), NULL, 0);
        rc = se_read(tmp, 32);
        if (rc < 0)
        {
            rval = -1;
            goto out;
        }

        memcpy(data+64, tmp, 72-64);
    }

out:
    se_sleep();
    return rval;
}

int se_destroy_key(int keynum)
{
    int rc;
    uint8_t numin[20];

    // Load tempkey with a known (random) nonce value
    rng_buffer(numin, sizeof(numin));
    se_write(OP_Nonce, 0, 0, numin, 20);

    // Nonce command returns the RNG result, not contents of TempKey,
    // but since we are destroying, no need to calculate what it is.
    uint8_t randout[32];
    rc = se_read(randout, 32);
    if (rc < 0)
        return -1;

    // do a "DeriveKey" operation, based on that!
    se_write(OP_DeriveKey, 0x00, keynum, NULL, 0);
    rc = se_read1();
    se_sleep();
    if (rc != 0)
        return -1;
    return 0;
}

// Do on-chip hashing, with lots of iterations.
//
// - using HMAC-SHA256 with keys that are known only to the 608a.
// - rate limiting factor here is communication time w/ 608a, not algos.
// - caution: result here is not confidential
// - cost of each iteration, approximately: 8ms
// - but our time to do each iteration is limited by software SHA256 in se_pair_unlock
//
int se_stretch_iter(
    const uint8_t *start,
    uint8_t *end,
    int iterations
)
{
#ifdef FIXME
    ASSERT(start != end);           // we can't work inplace
#endif
    memcpy(end, start, 32);

    for (int i = 0; i < iterations; i++) {
        // must unlock again, because pin_stretch is an auth'd key
        if (se_pair_unlock())
            return -2;

        int rv = se_hmac32(KEYNUM_pin_stretch, end, end);
        if (rv < 0)
            return -1;
    }

    return 0;
}

// Apply HMAC using secret in chip as a HMAC key, then encrypt
// the result a little because read in clear over bus.
//
int se_mixin_key(
    uint8_t keynum,
    uint8_t *start,
    uint8_t *end
)
{
    int rc;

#ifdef FIXME
    ASSERT(start != end);           // we can't work in place
#endif
    rc = se_pair_unlock();
    if (rc < 0)
        return -1;

    if (keynum != 0) {
        rc = se_hmac32(keynum, start, end);
        if (rc < 0)
            return -1;
    } else {
        memset(end, 0, 32);
    }

    // Final value was just read over bus w/o any protection, but
    // we won't be using that, instead, mix in the pairing secret.
    //
    // Concern: what if mitm gave us some zeros or other known pattern here. We will
    // use the value provided in cleartext[sic--it's not] write back shortly (to test it).
    // Solution: one more SHA256, and to be safe, mixin lots of values!

    SHA256_CTX ctx;

    sha256_init(&ctx);
    sha256_update(&ctx, rom_secrets->pairing_secret, 32);
    sha256_update(&ctx, start, 32);
    sha256_update(&ctx, &keynum, 1);
    sha256_update(&ctx, end, 32);
    sha256_final(&ctx, end);

    return 0;
}
