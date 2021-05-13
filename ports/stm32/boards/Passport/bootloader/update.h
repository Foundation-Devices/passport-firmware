// SPDX-FileCopyrightText: 2018 Coinkite, Inc. <coldcardwallet.com>
// SPDX-License-Identifier: GPL-3.0-only
//
#pragma once

#include <stdint.h>

extern void update_firmware(void);
extern secresult is_firmware_update_present(void);
extern secresult is_user_signed_firmware_installed(void);
