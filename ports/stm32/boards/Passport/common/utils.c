// SPDX-FileCopyrightText: 2020 Foundation Devices, Inc.  <hello@foundationdevices.com>
// SPDX-License-Identifier: GPL-3.0-or-later
//
// SPDX-FileCopyrightText: 2018 Coinkite, Inc.  <coldcardwallet.com>
// SPDX-License-Identifier: GPL-3.0-only
//
/*
 * (c) Copyright 2018 by Coinkite Inc. This file is part of Coldcard <coldcardwallet.com>
 * and is covered by GPLv3 license found in COPYING.
 */
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
