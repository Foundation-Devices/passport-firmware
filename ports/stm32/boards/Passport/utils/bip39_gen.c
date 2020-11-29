// SPDX-FileCopyrightText: 2020 Foundation Devices, Inc.  <hello@foundationdevices.com>
// SPDX-License-Identifier: GPL-3.0-or-later
//

#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <stdio.h>

#define NUM_WORDS 2048
#define MAX_WORD_LEN 8

extern const char* words[];

#include <stdint.h>
#include <string.h>
#include <assert.h>

uint32_t letter_to_number(char ch) {
    if (ch >= 'a' && ch <= 'c') return 2;
    if (ch >= 'd' && ch <= 'f') return 3;
    if (ch >= 'g' && ch <= 'i') return 4;
    if (ch >= 'j' && ch <= 'l') return 5;
    if (ch >= 'm' && ch <= 'o') return 6;
    if (ch >= 'p' && ch <= 's') return 7;
    if (ch >= 't' && ch <= 'v') return 8;
    if (ch >= 'w' && ch <= 'z') return 9;
    assert(0);
    return 999;
}

uint32_t letter_to_offset(char ch) {
    if (ch >= 'a' && ch <= 'c') return ch - 'a';
    if (ch >= 'd' && ch <= 'f') return ch - 'd';
    if (ch >= 'g' && ch <= 'i') return ch - 'g';
    if (ch >= 'j' && ch <= 'l') return ch - 'j';
    if (ch >= 'm' && ch <= 'o') return ch - 'm';
    if (ch >= 'p' && ch <= 's') return ch - 'p';
    if (ch >= 't' && ch <= 'v') return ch - 't';
    if (ch >= 'w' && ch <= 'z') return ch - 'w';
    assert(0);
    return 999;
}


// Convert a seed word to its equivalent in keypad numbers - max will be 8 digits long
uint32_t word_to_keypad_numbers(char* word) {
  uint32_t result = 0;

  uint32_t len = strlen(word);

  for (uint32_t i=0; i<len; i++) {
    char letter = word[i];
    uint32_t n = letter_to_number(letter);
    result = result * 10 + n;
  }
  return result;
}

uint16_t word_to_bit_offsets(char* word) {
  uint16_t result = 0;

  uint32_t len = strlen(word);
  uint16_t shift = 14;

  for (uint32_t i=0; i<len; i++) {
    char letter = word[i];
    uint16_t n = letter_to_offset(letter);
    result = (n << shift) | result;
    shift -= 2;
  }
  return result;
}

void make_num_pairs_array() {
  printf("#include <stdint.h>\n\n");

  printf("typedef struct {\n");
  printf("  uint32_t keypad_digits;\n");
  printf("  uint16_t offsets;\n");
  printf("} word_info_t;\n\n");

  printf("word_info_t word_info[] = {\n");
  for (int i=0; i<NUM_WORDS; i++) {
    uint32_t nums = word_to_keypad_numbers((char*)words[i]);
    uint16_t offsets = word_to_bit_offsets((char*)words[i]);
    printf("  {%u, 0x%04x}%s //%s\n", nums, offsets, i == NUM_WORDS - 1 ? "" : ",", words[i]);
  }
  printf("};\n");
}

int main()
{
    make_num_pairs_array();
    return 0;
}

