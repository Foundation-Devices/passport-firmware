// SPDX-FileCopyrightText: 2020 Foundation Devices, Inc.
// <hello@foundationdevices.com> SPDX-License-Identifier: GPL-3.0-or-later
//
// splash.c - Splash screen shown at during initialization

#include "display.h"

#include "bootloader_graphics.h"

void show_splash(char* message)
{
    uint16_t x = SCREEN_WIDTH / 2 - splash_img.width / 2;
    uint16_t y = SCREEN_HEIGHT / 2 - splash_img.height / 2;

    display_clear(0);
    display_image(x, y, splash_img.width, splash_img.height, splash_img.data, DRAW_MODE_NORMAL);
    display_text(message, CENTER_X, SCREEN_HEIGHT - 68, &FontSmall, false);
    display_show();
}
