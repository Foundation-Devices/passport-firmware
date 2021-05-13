// SPDX-FileCopyrightText: 2020 Foundation Devices, Inc.
// <hello@foundationdevices.com> SPDX-License-Identifier: GPL-3.0-or-later
//
// ui.c - Simple UI elements for the bootloader

#include <string.h>

#include "ui.h"
#include "gpio.h"
#include "delay.h"
#include "utils.h"
#include "display.h"
#include "passport_fonts.h"
#include "ring_buffer.h"
#include "lcd-sharp-ls018B7dh02.h"

#define HEADER_HEIGHT 40
#define FOOTER_HEIGHT 32
#define SIDE_MARGIN 4
#define TOP_MARGIN 4

void ui_draw_header(char* title) {
    uint16_t title_y = 10;

    // Title
    display_text(title, CENTER_X, title_y, &FontSmall, false);

    // Divider
    display_fill_rect(0, HEADER_HEIGHT-4, SCREEN_WIDTH, 2, 1);
}

void ui_draw_button(uint16_t x, uint16_t y, uint16_t w, uint16_t h, char* label, bool is_pressed) {
    if (is_pressed) {
        display_fill_rect(x, y, w, h, 1);
    } else {
        display_rect(x, y, w, h, 1);
    }

    // Measure text and center it in the button
    uint16_t label_width = display_measure_text(label, &FontTiny);

    x = x + (w / 2 - label_width / 2);
    y = y + (h / 2 - FontTiny.ascent / 2);

    display_text(label, x, y - 1, &FontTiny, is_pressed);
}

void ui_draw_footer(char* left_btn, bool is_left_pressed, char* right_btn, bool is_right_pressed) {

    uint16_t btn_w = SCREEN_WIDTH / 2;

    // Draw left button
    ui_draw_button(-1, SCREEN_HEIGHT - FOOTER_HEIGHT + 1, btn_w + 1,
                   FOOTER_HEIGHT, left_btn, is_left_pressed);

    // Draw right button
    ui_draw_button(btn_w - 1, SCREEN_HEIGHT - FOOTER_HEIGHT + 1,
                   btn_w + 2, FOOTER_HEIGHT, right_btn, is_right_pressed);
}

void ui_draw_wrapped_text(uint16_t x, uint16_t y, uint16_t max_width, char* text, bool center) {
    // Buffer to hold each wrapped line
    char line[80];
    uint16_t curr_y = y;

    while (*text != 0) {
        uint16_t sp = 0;
        uint16_t last_space = 0;
        uint16_t line_width = 0;
        uint16_t first_non_space = 0;
        uint16_t text_len = strlen(text);
        uint16_t sp_skip = 0;

        // Skip leading spaces
        while (true) {
            if (text[sp] == ' ') {
                sp++;
                first_non_space = sp;
            } else if (text[sp] == '\n') {
                sp++;
                first_non_space = sp;
                curr_y += FontSmall.leading;
            } else {
                break;
            }
        }

        while (sp < text_len) {
            char ch = text[sp];
            if (ch == ' ') {
                last_space = sp;
            }
            else if (ch == '\n') {
                // Time to break the line - Skip over this character after copying and rendering the line with sp_skip
                sp_skip = 1;
                break;
            }

            uint16_t ch_width = display_get_char_width(ch, &FontSmall);
            line_width += ch_width;
            if (line_width >= max_width) {
                // If we found a space, we can break there, but if we didn't
                // then just break before we go over.
                if (last_space != 0) {
                    sp = last_space;
                }
                break;
            }
            sp++;
        }

        // Copy to prepare for rendering
        strncpy(line, text + first_non_space, sp-first_non_space);
        line[sp-first_non_space] = 0;
        text = text + sp + sp_skip;


        // Draw the line
        display_text(line, center ? CENTER_X : SIDE_MARGIN, curr_y, &FontSmall, false);

        curr_y += FontSmall.leading;
    }
}

#ifndef DEBUG
static bool poll_for_key(uint8_t* p_key, bool* p_is_key_down) {
    uint8_t key;
    uint8_t count = ring_buffer_dequeue(&key);

    if (count == 0) {
        return false;
    }

    *p_key = key & 0x7F;
    *p_is_key_down = (key & 0x80) ? true : false;

    return true;
}
#endif // DEBUG

// Show message and then delay or wait for button press
bool ui_show_message(char* title, char* message, char* left_btn, char *right_btn, bool center) {
    bool exit = false;
    bool result = false;
    bool is_left_pressed = false;
    bool is_right_pressed = false;

    do {
        display_clear(0);

        // Draw the text
        ui_draw_wrapped_text(SIDE_MARGIN, HEADER_HEIGHT + TOP_MARGIN, SCREEN_WIDTH - SIDE_MARGIN * 2, message, center);

        // Draw the header
        ui_draw_header(title);

        // Draw the footer
        ui_draw_footer(left_btn, is_left_pressed, right_btn, is_right_pressed);
        display_show();

#ifdef DEBUG
        delay_ms(5000);
        result = true;
    } while (exit);
#else
        // Only poll if we are not exiting
        if (!exit) {
            // Poll for key
            uint8_t key;
            bool is_key_down;
            bool key_read;
            do {
                key_read = poll_for_key(&key, &is_key_down);
            } while (!key_read);

            // Handle key
            if (key_read) {
                if (is_key_down) {
                    switch (key) {
                        case 99: // 'y'
                            is_right_pressed = true;
                            break;

                        case 113: // 'x'
                            is_left_pressed = true;
                            break;
                    }
                } else {
                    switch (key) {
                        case 99: // 'y'
                            is_right_pressed = false;
                            exit = true;
                            result = true;
                            continue;

                        case 113: // 'x'
                            is_left_pressed = false;
                            exit = true;
                            result = false;
                            continue;
                    }
                }
            } else {
                delay_ms(50);
            }
        }
    } while (!exit);
#endif // DEBUG

    return result;
}

// Show the error message and give user the option to SHUTDOWN, or view
// CONTACT information. Then have option to go BACK to the error.
// NOTE: This function never returns!
void ui_show_fatal_error(char* error) {
    bool show_error = true;

    while (true) {
        if (show_error) {
            // Show the error
            if (ui_show_message("Fatal Error", error, "CONTACT", "SHUTDOWN", true)) {
                display_clean_shutdown();
            } else {
                show_error = false;
            }
        } else {
            // Show Contact Info
            if (ui_show_message("Contact", "\nContact us at:\n\nhello@foundationdevices.com",
                "BACK", "SHUTDOWN", true)) {
                display_clean_shutdown();
            } else {
                show_error = true;
            }
        }
    }
}

void ui_show_hex_buffer(char* title, uint8_t* data, uint32_t length) {
    char buf[512];
    bytes_to_hex_str(data, length, buf, 8, '\n');
    ui_show_message(title, buf, "SHUTDOWN", "CONTINUE", true);
}
