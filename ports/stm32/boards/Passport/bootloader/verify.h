// SPDX-FileCopyrightText: 2018 Coinkite, Inc.  <coldcardwallet.com>
// SPDX-License-Identifier: GPL-3.0-only
//
/*
 * (c) Copyright 2018 by Coinkite Inc. This file is part of Coldcard <coldcardwallet.com>
 * and is covered by GPLv3 license found in COPYING.
 */
#pragma once

#include <stdbool.h>

#include "fwheader.h"

extern bool verify_current_firmware(void);
extern bool verify_header(passport_firmware_header_t *hdr);
extern bool verify_signature(passport_firmware_header_t *hdr, uint8_t *fw_hash, uint32_t hashlen);
extern void verify_min_version(uint8_t *min_version);

