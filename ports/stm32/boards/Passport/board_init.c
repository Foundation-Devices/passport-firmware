// SPDX-FileCopyrightText: 2020 Foundation Devices, Inc. <hello@foundationdevices.com>
// SPDX-License-Identifier: GPL-3.0-or-later
//

#include <string.h>

#include "stm32h7xx_hal.h"

#include "adc.h"
#include "backlight.h"
#include "camera-ovm7690.h"
#include "display.h"
#include "frequency.h"
#include "gpio.h"
#include "image_conversion.h"
#include "lcd-sharp-ls018B7dh02.h"
#include "busy_bar.h"
#include "se.h"
#include "utils.h"
#include "se.h"

#define QR_IMAGE_SIZE (CAMERA_WIDTH * CAMERA_HEIGHT)
#define VIEWFINDER_IMAGE_SIZE ((240 * 303) / 8)

uint8_t qr[QR_IMAGE_SIZE];
uint8_t dp[VIEWFINDER_IMAGE_SIZE];

void
Passport_board_init(void)
{
    /* Enable the console UART */
    frequency_update_console_uart();
    printf("[%s]\n", __func__);
    printf("%lu, %lu, %lu, %lu, %lu\n", HAL_RCC_GetSysClockFreq(), SystemCoreClock, HAL_RCC_GetHCLKFreq(), HAL_RCC_GetPCLK1Freq(), HAL_RCC_GetPCLK2Freq());

    set_stack_sentinel();

    gpio_init();
    // backlight_init();  Not necessary as we call backlight_minimal_init() from the Backlight class in modfoundation.c
    display_init(false);
    camera_init();
    adc_init();
    busy_bar_init();
    se_setup();

    // check_stack("Passport_board_init() complete", true);
}

void
Passport_board_early_init(void)
{}
