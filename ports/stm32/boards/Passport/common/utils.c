// SPDX-FileCopyrightText: 2020 Foundation Devices, Inc. <hello@foundationdevices.com>
// SPDX-License-Identifier: GPL-3.0-or-later
//
// SPDX-FileCopyrightText: 2018 Coinkite, Inc. <coldcardwallet.com>
// SPDX-License-Identifier: GPL-3.0-only
//
/*
 * (c) Copyright 2018 by Coinkite Inc. This file is part of Coldcard <coldcardwallet.com>
 * and is covered by GPLv3 license found in COPYING.
 */
#include <stdio.h>
#include "utils.h"

// Return T if all bytes are 0xFF
//
bool check_all_ones(
    void *ptrV,
    int len
)
{
	uint8_t rv = 0xff;
	uint8_t *ptr = (uint8_t *)ptrV;

	for(; len; len--, ptr++)
    {
		rv &= *ptr;
	}

	return (rv == 0xff);
}

// Return T if all bytes are 0x00
//
bool check_all_zeros(
    void *ptrV,
    int len
)
{
	uint8_t rv = 0x0;
	uint8_t *ptr = (uint8_t *)ptrV;

	for (; len; len--, ptr++)
    {
		rv |= *ptr;
	}

	return (rv == 0x00);
}

// Equality check.
//
bool check_equal(
    void *aV,
    void *bV,
    int len
)
{
	uint8_t *left = (uint8_t *)aV;
	uint8_t *right = (uint8_t *)bV;
    uint8_t diff = 0;
    int i;

    for (i = 0; i < len; i++)
    {
        diff |= (left[i] ^ right[i]);
    }

    return (diff == 0);
}

// XOR-mixin more bytes; acc = acc XOR more for each byte
void xor_mixin(uint8_t *acc, uint8_t *more, int len)
{
    for(; len; len--, more++, acc++)
    {
        *(acc) ^= *(more);
    }
}


char hex_map[16] = {'0', '1', '2', '3', '4', '5', '6', '7',
	'8', '9', 'A', 'B', 'C', 'D', 'E', 'F', };

void to_hex(char* buf, uint8_t value) {
    buf[0] = hex_map[value >> 4];
    buf[1] = hex_map[value & 0xF];
    buf[2]=0;
}

// Assumes str is big enough to hold len*2 + 1 bytes
void bytes_to_hex_str(uint8_t* bytes, uint32_t len, char* str, uint32_t split_every, char split_char) {
    for (uint32_t i=0; i<len;) {
        to_hex((char*)str, bytes[i]);
        str += 2;
        i++;
        if (i % split_every == 0 && i != len) {
          str[0] = split_char;
          str++;
        }
    }
    *str = 0;
}

#ifndef PASSPORT_BOOTLOADER

void print_hex_buf(char* prefix, uint8_t* buf, int len) {
    printf(prefix);

    for (int i=0; i<len; i++) {
        printf("%02x", buf[i]);
    }

    putchar('\n');
}

void copy_bytes(uint8_t* dest, int dest_len, uint8_t* src, int src_len) {
    for (int i=0; i<src_len; i++) {
        if (i < dest_len) {
            dest[i] = src[i];
        }
    }
}

uint32_t getsp(void)
{
    register void *sp asm ("sp");
    return (uint32_t)sp;
}

void set_stack_sentinel() {
    uint32_t* eos = (uint32_t*)MIN_SP + 1;
    *eos = EOS_SENTINEL;
}

bool check_stack_sentinel() {
    uint32_t* eos = (uint32_t*)MIN_SP + 1;
    return *eos == EOS_SENTINEL;
}

int32_t max_diff = 0;

// true if stack is OK, false if not
bool check_stack(char* msg, bool print) {
    uint32_t sp = getsp();
    int32_t diff = (int32_t)(sp - MIN_SP);

    if (diff < 0){
        if (-diff > max_diff) {
            max_diff = -diff;
        }
    }

    bool sentinel_overwritten = !check_stack_sentinel();

    // Only print if there is a problem
    if (print) {
        printf("%s: (sp=0x%08lx, Diff=%ld, Max Diff=%ld : %s, %s)\n",
            msg,
            sp,
            diff,
            max_diff,
            sp <= MIN_SP ? "BLOWN!" : "OK",
            sentinel_overwritten ? "SENTINEL OVERWRITTEN!" : "OK");
    }

    return !sentinel_overwritten;
}

#endif /* PASSPORT_BOOTLOADER */
