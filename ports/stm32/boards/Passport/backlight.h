// SPDX-FileCopyrightText: 2020 Foundation Devices, Inc.  <hello@foundationdevices.com>
// SPDX-License-Identifier: GPL-3.0-or-later
//
// SPDX-FileCopyrightText: 2018 Coinkite, Inc.
// SPDX-License-Identifier: GPL-3.0-only
//
// Backlight driver for LED

#ifndef STM32_BACKLIGHT_H
#define STM32_BACKLIGHT_H

#include "stm32h7xx_hal.h"

#include <stdio.h>
#include <stdlib.h>

void backlight_init(void);
void backlight_intensity(uint16_t intensity);

#endif //STM32_BACKLIGHT_H
