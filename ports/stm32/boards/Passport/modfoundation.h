// SPDX-FileCopyrightText: 2020 Foundation Devices, Inc. <hello@foundationdevices.com>
// SPDX-License-Identifier: GPL-3.0-or-later
//

#ifndef STM32_MODFOUNDATION_H
#define STM32_MODFOUNDATION_H
#include "py/obj.h"

extern ring_buffer_t keybuf;

extern const mp_obj_type_t lcd_type;
extern const mp_obj_type_t backlight_type;
extern const mp_obj_type_t keypad_type;
#endif //STM32_MODFOUNDATION_H
