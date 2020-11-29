// SPDX-FileCopyrightText: 2020 Foundation Devices, Inc.  <hello@foundationdevices.com>
// SPDX-License-Identifier: GPL-3.0-or-later
//

#include <string.h>

#include "stm32h7xx_hal.h"

#include "gpio.h"
#include "backlight.h"
#include "adc.h"
#include "camera-ovm7690.h"
#include "lcd-sharp-ls018B7dh02.h"
#include "image_conversion.h"
#include "py/mphal.h"

#define QR_IMAGE_SIZE (CAMERA_WIDTH * CAMERA_HEIGHT)
#define VIEWFINDER_IMAGE_SIZE ((240 * 303) / 8)

uint8_t qr[QR_IMAGE_SIZE];
uint8_t dp[VIEWFINDER_IMAGE_SIZE];

void Passport_board_init(void)
{
    gpio_init();
    backlight_init();
    lcd_init();
    camera_init();
    adc2_init();
    adc3_init();

#if 0
    backlight_intensity(250);
    camera_on();
    while (1)
    {
        camera_snapshot();
        convert_rgb565_to_grayscale_and_mono(camera_frame_buffer, qr, CAMERA_HEIGHT, CAMERA_WIDTH, dp, 240, 240);
        lcd_update(dp, 0);
        HAL_Delay(10);
    }
#endif
}

void Passport_board_early_init(void)
{
}
