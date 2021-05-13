# SPDX-FileCopyrightText: 2020 Foundation Devices, Inc. <hello@foundationdevices.com>
# SPDX-License-Identifier: GPL-3.0-or-later
#
# bip39_utils.py - Utility functions for working with BIP39 seed phrases
#

# Map from keypad letters to keypad numbers
letter_to_number = {
  'a': 2,
  'b': 2,
  'c': 2,
  'd': 3,
  'e': 3,
  'f': 3,
  'g': 4,
  'h': 4,
  'i': 4,
  'j': 5,
  'k': 5,
  'l': 5,
  'm': 6,
  'n': 6,
  'o': 6,
  'p': 7,
  'q': 7,
  'r': 7,
  's': 7,
  't': 8,
  'u': 8,
  'v': 8,
  'w': 9,
  'x': 9,
  'y': 9,
  'z': 9,
}

# Convert a seed word to its equivalent in keypad numbers
def word_to_keypad_numbers(word):
  result = 0
  for letter in word:
    n = letter_to_number[letter]
    result = result * 10 + n
  return result


def get_words_matching_prefix(prefix, max=5, word_list='bip39'):
    from foundation import bip39

    # This actually handles bytewords too, depsite the name :(
    bip = bip39()
    matches = bip.get_words_matching_prefix(prefix, max, word_list)
    return matches.split(',')
