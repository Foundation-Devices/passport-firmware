// SPDX-FileCopyrightText: 2020 Foundation Devices, Inc.
// <hello@foundationdevices.com> SPDX-License-Identifier: GPL-3.0-or-later
//
// display.c - Display rendering functions for the Passport bootloader
#include <string.h>

#include "display.h"
#include "keypad-adp-5587.h"
#include "gpio.h"

static uint8_t disp_buf[SCREEN_BYTES_PER_LINE * SCREEN_HEIGHT];

static uint8_t get_image_pixel(int16_t x, int16_t y, uint16_t w, uint16_t h, uint8_t* image, uint8_t default_color)
{
    if (x < 0 || x >= w || y < 0 || y >= h) {
        return default_color;
    }

    uint16_t w_bytes = (w + 7) / 8;
    uint16_t offset = (y * w_bytes) + x / 8;
    uint8_t bit = 1 << (7 - x % 8);

    return ((image[offset] & bit) == 0) ? 0 : 1;
}

static void set_pixel(int16_t x, int16_t y, uint8_t c)
{
    if (x < 0 || x >= SCREEN_WIDTH || y < 0 || y >= SCREEN_HEIGHT) {
      return;
    }

    uint16_t offset = (y * SCREEN_BYTES_PER_LINE) + x / 8;
    uint8_t bit = 1 << (7 - x % 8);
    if (c == 1) {
        disp_buf[offset] |= bit;
    } else {
        disp_buf[offset] &= ~bit;
    }
}

uint16_t display_measure_text(char* text, Font* font)
{
  uint16_t width = 0;
  uint16_t slen = strlen(text);
  for (int i=0; i<slen; i++){
    GlyphInfo glyphInfo;
    glyph_lookup(font, text[i], &glyphInfo);
    width += glyphInfo.advance;
  }
  return width;
}

void display_fill_rect(int16_t x, int16_t y, int16_t w, int16_t h, uint8_t color)
{
    for (int dy = y; dy < y + h; dy++) {
        for (int dx = x; dx < x + w; dx++) {
            set_pixel(dx, dy, color);
        }
    }
}

void display_text(char* text, int16_t x, int16_t y, Font* font, bool invert)
{
    if (x == CENTER_X) {
      uint16_t text_width = display_measure_text(text, font);
      x = SCREEN_WIDTH/2 - text_width/2;
    }

    uint16_t slen = strlen(text);
    for (int i=0; i<slen; i++) {
      GlyphInfo glyphInfo;
      glyph_lookup(font, text[i], &glyphInfo);

      // y + font.ascent - fn.h - fn.y
      display_image(x + glyphInfo.x, y + font->ascent - glyphInfo.h - glyphInfo.y, glyphInfo.w, glyphInfo.h, glyphInfo.bitmap,
                    invert ? DRAW_MODE_WHITE_ONLY | DRAW_MODE_INVERT : DRAW_MODE_WHITE_ONLY);
      x += glyphInfo.advance;
    }
}

uint16_t display_get_char_width(char ch, Font* font)
{
    GlyphInfo glyphInfo;
    glyph_lookup(font, ch, &glyphInfo);
    return glyphInfo.advance;
}

void display_rect(int16_t x, int16_t y, int16_t w, int16_t h, u_int8_t color)
{
    // Draw the top and bottom
    int16_t y_bottom = y + h - 1;
    for (int dx = x; dx < x + w; dx++) {
        set_pixel(dx, y, color);
        set_pixel(dx, y_bottom, color);
    }

    // Draw the sides - repeats the top and bottom pixels to avoid special case
    // code for short rectangles
    int16_t x_right = x + w - 1;
    for (int dy = y; dy < y + w; dy++) {
        set_pixel(x, dy, color);
        set_pixel(x_right, dy, color);
    }
}

// Very simple and inefficient image drawing, but should be fast enough for our
// limited use.
void display_image(uint16_t x, uint16_t y, uint16_t image_w, uint16_t image_h, uint8_t* image, uint8_t mode)
{
    // Iterate over the image bounds
    for (int dy = 0; dy < image_h; dy++) {
        for (int dx = 0; dx < image_w; dx++) {
            uint8_t color = get_image_pixel(dx, dy, image_w, image_h, image, 0);
            if (((mode & DRAW_MODE_BLACK_ONLY) && color == 1) || ((mode & DRAW_MODE_WHITE_ONLY) && color == 0)) {
              // Skip this pixel if we are not supposed to draw it
              continue;
            }
            if (mode & DRAW_MODE_INVERT) {
              color = !color;
            }

            set_pixel(x + dx, y + dy, color);
        }
    }
}

// Assumes it's the only thing on these lines, so it does not retain any other
// image that might have been rendered there.
void display_progress_bar(uint16_t x, uint16_t y, uint16_t w, uint16_t h, uint8_t percent)
{
    // Clear whole line first
    display_fill_rect(0, y, SCREEN_WIDTH-1, h, 0);

    display_fill_rect(x, y, w, h, 1);
    display_fill_rect(x + 2, y + 2, w - 4, h - 4, 0);
    display_fill_rect(x + 3, y + 3, (w * percent) / 100 - 6, h - 6, 1);
}

void display_show(void)
{
    // Disable IRQs so keypad events don't interrupt display drawing
    __disable_irq();
    lcd_update(disp_buf, true);
    __enable_irq();

#ifndef DEBUG
    // Clear the keypad interrupt so that it will retrigger if it had any events while
    // interrupts were disabled, else it will hang the controller since it's waiting
    // for the previous interrupt to be acknowledged.
    keypad_write(KBD_ADDR, KBD_REG_INT_STAT, 0xFF);
#endif /* DEBUG */
}

void display_show_lines(uint16_t y_start, uint16_t y_end)
{
    if (y_start >= SCREEN_HEIGHT) {
       return;
    }

    if (y_end >= SCREEN_HEIGHT) {
        y_end = SCREEN_HEIGHT - 1;
    }

    for (uint16_t y=y_start; y<=y_end; y++) {
      lcd_prebuffer_line(y, &disp_buf[y * SCREEN_BYTES_PER_LINE], true);
    }

    lcd_update_line_range(y_start, y_end);
}

void display_clear(uint8_t color)
{
    memset(disp_buf, color == 0 ? 0x00 : 0xFF, SCREEN_BYTES_PER_LINE * SCREEN_HEIGHT);
}

void display_init(bool clear)
{
    lcd_init(clear);
}

// Clear the memory display and then shutdown
void display_clean_shutdown()
{
    display_clear(0);
    display_show();
    passport_shutdown();
}
