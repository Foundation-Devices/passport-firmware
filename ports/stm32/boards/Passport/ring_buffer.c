// SPDX-FileCopyrightText: 2020 Foundation Devices, Inc.  <hello@foundationdevices.com>
// SPDX-License-Identifier: GPL-3.0-or-later
//

#include "ring_buffer.h"
#include <stdio.h>

/**
 * Code adapted from https://github.com/AndersKaloer/Ring-Buffer
 */

int ring_buffer_init(ring_buffer_t* buffer)
{
    buffer->size = MAX_RING_BUFFER_SIZE;
    buffer->size_plus1 = MAX_RING_BUFFER_SIZE + 1;
    buffer->head_index = 0;
    buffer->tail_index = 0;
    return 0;
}

void ring_buffer_enqueue(ring_buffer_t* buffer, uint8_t data)
{
    // printf("enqueue...H=%u T=%u Count=%u\n", buffer->head_index, buffer->tail_index, ring_buffer_num_items(buffer));
    if (ring_buffer_is_full(buffer)) {
        buffer->tail_index = ((buffer->tail_index + 1) % buffer->size_plus1);
    }

    buffer->buffer[buffer->head_index] = data;
    buffer->head_index = ((buffer->head_index + 1) % buffer->size_plus1);
}

uint8_t ring_buffer_dequeue(ring_buffer_t* buffer, uint8_t* data)
{
    if (ring_buffer_is_empty(buffer)) {
        return 0;
    }

    *data = buffer->buffer[buffer->tail_index];
    buffer->tail_index = ((buffer->tail_index + 1) % buffer->size_plus1);
    return 1;
}

uint8_t ring_buffer_peek(ring_buffer_t* buffer, uint8_t* data, ring_buffer_size_t index)
{
    if (index >= ring_buffer_num_items(buffer)) {
        // __enable_irq();
        return 0;
    }

    ring_buffer_size_t data_index = ((buffer->tail_index + index) % buffer->size_plus1);
    *data = buffer->buffer[data_index];
    return 1;
}

uint8_t ring_buffer_is_empty(ring_buffer_t* buffer)
{
    uint8_t result = (buffer->head_index == buffer->tail_index);
    return result;
}

uint8_t ring_buffer_is_full(ring_buffer_t* buffer)
{
    uint8_t num_items = ring_buffer_num_items(buffer);
    uint8_t result = num_items == buffer->size;
    return result;
}

ring_buffer_size_t ring_buffer_num_items(ring_buffer_t* buffer)
{
    uint8_t result = (buffer->head_index + buffer->size_plus1 - buffer->tail_index) % buffer->size_plus1;
    return result;
}
