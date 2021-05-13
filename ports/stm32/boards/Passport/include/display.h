// SPDX-FileCopyrightText: 2020 Foundation Devices, Inc. <hello@foundationdevices.com>
// SPDX-License-Identifier: GPL-3.0-or-later
//
// display.h - Display rendering functions for the Passport bootloader
#pragma once

#include "lcd-sharp-ls018B7dh02.h"
#include "passport_fonts.h"

// Pass this constant to center text horizontally
#define CENTER_X      32767

// Bitmap draw mode bitmask
#define DRAW_MODE_NORMAL 0
#define DRAW_MODE_INVERT 1
#define DRAW_MODE_WHITE_ONLY 2
#define DRAW_MODE_BLACK_ONLY 4

#define PROGRESS_BAR_HEIGHT 9
#define PROGRESS_BAR_MARGIN 10
#define PROGRESS_BAR_Y (SCREEN_HEIGHT - 40)

extern void display_init(bool clear);
extern uint16_t display_measure_text(char* text, Font* font);
extern uint16_t display_get_char_width(char ch, Font* font);
extern void display_text(char* text, int16_t x, int16_t y, Font* font, bool invert);
extern void display_fill_rect(int16_t x, int16_t y, int16_t w, int16_t h, u_int8_t color);
extern void display_rect(int16_t x, int16_t y, int16_t w, int16_t h, u_int8_t color);
extern void display_image(uint16_t x, uint16_t y, uint16_t image_w, uint16_t image_h, uint8_t* image, uint8_t mode);
extern void display_progress_bar(uint16_t x, uint16_t y, uint16_t w, uint16_t h, uint8_t percent);
extern void display_show(void);
extern void display_show_lines(uint16_t y_start, uint16_t y_end);
extern void display_clear(uint8_t color);
extern void display_clean_shutdown(void);
