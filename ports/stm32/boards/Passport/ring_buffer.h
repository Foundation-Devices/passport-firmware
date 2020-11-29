// SPDX-FileCopyrightText: 2020 Foundation Devices, Inc.  <hello@foundationdevices.com>
// SPDX-License-Identifier: GPL-3.0-or-later
//

#ifndef RING_BUFFER_H_
#define RING_BUFFER_H_

#include <stddef.h>
#include <stdint.h>
#include <stdlib.h>

#define MAX_RING_BUFFER_SIZE 16

typedef uint8_t ring_buffer_size_t;

typedef struct _ring_buffer_t {
    // No dynamic allocation
    int buffer[MAX_RING_BUFFER_SIZE + 1];
    int size;
    int size_plus1;
    ring_buffer_size_t tail_index;
    ring_buffer_size_t head_index;
} ring_buffer_t;

/**
 * Initializes or resets the ring buffer.
 * @param buffer The ring buffer to initialize.
 * @return 0 if successful; -1 otherwise.
 */
int ring_buffer_init(ring_buffer_t* buffer);

/**
 * Adds a byte to a ring buffer.
 * @param buffer The buffer in which the data should be placed.
 * @param data The byte to place.
 */
void ring_buffer_enqueue(ring_buffer_t* buffer, uint8_t data);

/**
 * Returns the oldest byte in a ring buffer.
 * @param buffer The buffer from which the data should be returned.
 * @param data A pointer to the location at which the data should be placed.
 * @return 1 if data was returned; 0 otherwise.
 */
uint8_t ring_buffer_dequeue(ring_buffer_t* buffer, uint8_t* data);

/**
 * Peeks a ring buffer, i.e. returns an element without removing it.
 * @param buffer The buffer from which the data should be returned.
 * @param data A pointer to the location at which the data should be placed.
 * @param index The index to peek.
 * @return 1 if data was returned; 0 otherwise.
 */
uint8_t ring_buffer_peek(ring_buffer_t* buffer, uint8_t* data, ring_buffer_size_t index);

/**
 * Returns whether a ring buffer is empty.
 * @param buffer The buffer for which it should be returned whether it is empty.
 * @return 1 if empty; 0 otherwise.
 */
uint8_t ring_buffer_is_empty(ring_buffer_t* buffer);

/**
 * Returns whether a ring buffer is full.
 * @param buffer The buffer for which it should be returned whether it is full.
 * @return 1 if full; 0 otherwise.
 */
uint8_t ring_buffer_is_full(ring_buffer_t* buffer);

/**
 * Returns the number of items in a ring buffer.
 * @param buffer The buffer for which the number of items should be returned.
 * @return The number of items in the ring buffer.
 */
ring_buffer_size_t ring_buffer_num_items(ring_buffer_t* buffer);

#endif
