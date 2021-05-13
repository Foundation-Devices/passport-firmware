// SPDX-FileCopyrightText: 2020 Foundation Devices, Inc.
// <hello@foundationdevices.com> SPDX-License-Identifier: GPL-3.0-or-later
//
// ui.h - Simple UI elements for the bootloader

#include <stdint.h>
#include <stdbool.h>

// UI elements
void ui_draw_header(char* title);
void ui_draw_footer(char* left_btn, bool is_left_pressed, char* right_btn, bool is_right_pressed);
void ui_draw_button(uint16_t x, uint16_t y, uint16_t w, uint16_t h, char* label, bool is_pressed);
void ui_draw_wrapped_text(uint16_t x, uint16_t y, uint16_t max_width, char* text, bool center);
bool ui_show_message(char* title, char* message, char* left_btn, char*right_btn, bool center);
void ui_show_fatal_error(char* message);
void ui_show_hex_buffer(char* title, uint8_t* buf, uint32_t length);
