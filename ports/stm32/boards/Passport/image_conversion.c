// SPDX-FileCopyrightText: 2020 Foundation Devices, Inc. <hello@foundationdevices.com>
// SPDX-License-Identifier: GPL-3.0-or-later
//

#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "image_conversion.h"

#define INVERT_IMAGE

// This is designed only for resizing smaller and is a low-quality resize,
// but it should be quite fast.
void resize_by_nearest_neighbor(
    uint8_t *grayscale, uint32_t gray_width, uint32_t gray_height, uint16_t y_start,
    uint8_t *mono, uint32_t mono_width, uint32_t mono_height)
{
    float step = (float)gray_width / (float)mono_width;
    // printf("gray_width=%lu gray_height=%lu mono_width=%lu mono_height=%lu y_start=%u step=%f\n", gray_width, gray_height, mono_width, mono_height, y_start, step);
    // float src_y = y_start;
    // float src_x = 0;
    uint32_t mono_span = mono_width >> 3;

    // Clear the mono buffer
#ifdef INVERT_IMAGE
    memset(mono, 0xFF, (mono_width * mono_height) >> 3);
#else
    memset(mono, 0x00, (mono_width * mono_height) >> 3);
#endif

    for (uint32_t y = 0; y < mono_height; y++)
    {
        for (uint32_t x = 0; x < mono_width; x++)
        {
            uint32_t offset = ((uint32_t)((float)(y + y_start)* step) * (uint32_t)gray_width) + (uint32_t)((float)x * step);
            uint8_t gray = grayscale[offset];

            // if (x < 5) {
            //     printf("[%02lx]=%02x ", offset, gray);
            // }

            // Mask the value in it
            if (gray > 64)
            {
                uint32_t mono_offset = (y * mono_span) + (x >> 3);
                uint8_t *p_byte = &mono[mono_offset];

                uint8_t bit = x % 8;
#ifdef INVERT_IMAGE
                *p_byte ^= 1 << (7 - bit);
#else
                *p_byte |= 1 << (7 - bit);
#endif
            }
            // src_x += step;
        }
        // printf("\n");

        // src_y += step;
    }
}

/*
// This is designed only for resizing smaller and is a low-quality resize,
// but it should be quite fast.
void resize_by_nearest_neighbor(
    uint8_t *grayscale, uint32_t gray_width, uint32_t gray_height, uint16_t y_start,
    uint8_t *mono, uint32_t mono_width, uint32_t mono_height)
{
    float step = (float)gray_width / (float)mono_width;
    // uint32_t mono_span = mono_width / 8;
    
    // Clear the mono buffer
#ifdef INVERT_IMAGE
    memset(mono, 0xFF, (mono_width * mono_height) >> 3);
#else
    memset(mono, 0x00, (mono_width * mono_height) >> 3);
#endif

    for (uint32_t y = 0; y < mono_height; y++)
    {
        uint32_t src_y = y + y_start;
        uint32_t src_offset = (uint32_t)((float)(src_y * step)) * (uint32_t)gray_width;

        for (uint32_t x = 0; x < mono_width; x++)
        {
            uint8_t gray = grayscale[src_offset];

            if (gray > 128)
            {
                // Draw the pixel as white
                uint32_t mono_offset = (y << 5) - (y << 1) + (x >> 3);  // NOTE: Hardcoded for a span of 30 bytes (240 pixels)
                // uint32_t mono_offset = (y * mono_span) + (x >> 3);
                uint8_t *p_byte = &mono[mono_offset];

                uint8_t bit = x % 8;
#ifdef INVERT_IMAGE
                *p_byte ^= 1 << (7 - bit);
#else
                *p_byte |= 1 << (7 - bit);
#endif
            }
            src_offset += (uint32_t)step;
        }
    }
}
*/

void convert_rgb565_to_grayscale_and_mono(
    uint16_t *rgb565,
    uint8_t *grayscale,
    uint32_t gray_width,
    uint32_t gray_height,
    uint8_t *mono,
    uint32_t mono_width,
    uint32_t mono_height)
{
    uint32_t src_row_span = gray_height; // 1 uint16_t (2 bytes) per pixel
    // uint32_t gray_row_span = gray_width; // 1 byte per pixel
    // uint32_t mono_row_span = mono_width / 8; // 1 bit per pixel
    assert(mono_width % 8 == 0);

    // uint32_t mono_start_x = (gray_width - mono_width) / 2;

    // #define PRINT_IMAGE

    // Intentionally using width with y and height with x since image sensor is rotated vs. grayscale buffer
    for (uint32_t y = 0; y < gray_width; y++)
    {
        for (uint32_t x = 0; x < gray_height; x++)
        {
            uint16_t pixel = rgb565[(y * src_row_span) + x];

            uint16_t r = (pixel & 0xF800) >> 8;
            // uint16_t g = (pixel & 0x07E0) >> 3;
            // uint16_t b = pixel & 0x001F << 3;
            // uint16_t sum = r + g + b;
            // uint16_t element = (sum * 341) >> 10;  // Equivalent to dividing by 3
            uint8_t gray = (uint8_t) r;

// #define OPTIMIZATIONS
// #ifdef OPTIMIZATIONS
//             uint16_t r = (pixel & 0xF800) >> 8;
//             uint16_t g = (pixel & 0x07E0) >> 3;
//             uint16_t b = pixel & 0x001F << 3;
//             uint16_t sum = r + g + b;
//             uint16_t element = (sum * 341) >> 10;  // Equivalent to dividing by 3
//             uint8_t gray = (uint8_t) element;
// #else
//             uint16_t r = (pixel & 0xF800) >> 11;
//             uint16_t g = (pixel & 0x07E0) >> 5;
//             uint16_t b = pixel & 0x001F;
//             uint16_t sum = (r << 1) + g + (b << 1);
//             uint16_t element = sum / 3;
//             uint8_t gray = element << 2;
// #endif

            // Rotate coordinates for grayscale image and set pixel
            uint32_t dest_y = gray_height - x;
            uint32_t dest_x = y;
            grayscale[dest_y * gray_width + dest_x] = gray;
        }
    }

    resize_by_nearest_neighbor(grayscale, gray_width, gray_height, 33, mono, mono_width, mono_height);
}
