// SPDX-FileCopyrightText: 2020 Foundation Devices, Inc. <hello@foundationdevices.com>
// SPDX-License-Identifier: GPL-3.0-or-later
//
// LCD driver for Sharp LS018B7DH02 monochrome display

#ifndef __LCD_H__
#define __LCD_H__

#include "stm32h7xx_hal.h"

#include <stdio.h>
#include <stdlib.h>
#include <stdbool.h>

#define SCREEN_WIDTH 230
#define SCREEN_HEIGHT 303
#define SCREEN_BYTES_PER_LINE (240 / 8)
#define SCREEN_BUF_SIZE (SCREEN_BYTES_PER_LINE * SCREEN_HEIGHT)

typedef struct
{
    uint8_t header[2];
    union {
        uint8_t pixels[SCREEN_BYTES_PER_LINE];
        uint16_t pixels_u16[SCREEN_BYTES_PER_LINE / 2];
    };
} ScreenLine;

typedef struct
{
    ScreenLine lines[SCREEN_HEIGHT];
    uint16_t dummy;
} Screen;

// Data structures for lcd_test pattern creation
typedef struct _LCDTestLine {
    uint8_t pixels[SCREEN_BYTES_PER_LINE];
} LCDTestLine;

typedef struct _LCDTestScreen {
    LCDTestLine lines[SCREEN_HEIGHT];
} LCDTestScreen;

void lcd_init(bool clear);
void lcd_deinit(void);
void lcd_clear(bool invert);
void lcd_update(uint8_t* screen_data, bool invert);
void lcd_test(void);
void lcd_prebuffer_line(uint16_t y, uint8_t* line_data, bool invert);
void lcd_update_line_range(uint16_t y_start, uint16_t y_end);

#endif /* __LCD_H__ */
