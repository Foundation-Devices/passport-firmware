# SPDX-FileCopyrightText: 2020 Foundation Devices, Inc. <hello@foundationdevices.com>
# SPDX-License-Identifier: GPL-3.0-or-later
#
# seed_entry_ux.py - UX related to seed phrase entry and verification
#
import pincodes
from display import Display, FontSmall, FontTiny
from common import dis, system
from uasyncio import sleep_ms
from utils import UXStateMachine, shuffle
from ux import KeyInputHandler, ux_show_story, ux_confirm
from trezorcrypto import bip39
from bip39_utils import get_words_matching_prefix, word_to_keypad_numbers

TEXTBOX_MARGIN = 6
PAGINATION_HEIGHT = Display.FOOTER_HEIGHT
MAX_WORDS_TO_DISPLAY = 4

# Separate state machines to keep
class SeedEntryUX(UXStateMachine):
    # States
    ENTER_WORDS = 1
    VALIDATE_SEED = 2
    INVALID_SEED = 3
    VALID_SEED = 4

    def __init__(self, title='Import Seed', seed_len=12, verify_phrase=None, validate_checksum=True, word_list='bip39'):
        super().__init__(self.ENTER_WORDS)
        self.title = title
        self.seed_len = seed_len
        self.verify_phrase = verify_phrase
        self.curr_word = 0
        self.words = []
        self.user_input = []
        self.is_seed_valid = False
        self.font = FontSmall
        self.pagination_font = FontTiny
        self.highlighted_word_index = 0
        self.last_word_lookup = ''
        self.validate_checksum = validate_checksum
        self.word_list = word_list
        self.selectable_words = None
        self.input = KeyInputHandler(down='23456789lrudxy*', up='xy')

        # Initialize input and word information
        num_words = len(self.words)
        for w in range(self.seed_len):
            if w < num_words:
                self.user_input.append(word_to_keypad_numbers(self.words[w]))
            else:
                # Assume blank input
                self.user_input.append('')
                self.words.append('')

        # Update state based on current info
        self.update()

    def render(self):
        system.turbo(True)
        dis.clear()

        dis.draw_header(self.title)

        # Draw the title
        y = Display.HEADER_HEIGHT + TEXTBOX_MARGIN
        dis.text(None, y, 'Enter Word {} of {}'.format(self.curr_word + 1, self.seed_len))
        y += self.font.leading

        # Draw a bounding box around the input text area
        dis.draw_rect(TEXTBOX_MARGIN, y, Display.WIDTH - (TEXTBOX_MARGIN * 2),
                      self.font.leading + 2, 1, fill_color=0, border_color=1)

        # Draw the text input
        dis.text_input(None, y + 4, self.user_input[self.curr_word], cursor_pos=len(self.user_input[self.curr_word]))

        # Draw a bounding box around the list of selectable words
        y += self.font.leading + TEXTBOX_MARGIN + 2
        dis.draw_rect(TEXTBOX_MARGIN, y, Display.WIDTH - (TEXTBOX_MARGIN * 2),
                      Display.HEIGHT - y - TEXTBOX_MARGIN - Display.FOOTER_HEIGHT - PAGINATION_HEIGHT, 1,
                      fill_color=0, border_color=1)

        # Draw the selectable words
        for i in range(len(self.selectable_words)):
            if i == self.highlighted_word_index:
                # Draw inverted text with rect to indicate that this word will be selected
                # when user presses SELECT button.
                dis.draw_rect(TEXTBOX_MARGIN, y, Display.WIDTH - (TEXTBOX_MARGIN * 2), self.font.leading, 0, fill_color=1)
                dis.text(None, y, self.selectable_words[i], invert=1)
            else:
                dis.text(None, y, self.selectable_words[i])

            y += self.font.leading - 1


        # Draw the pagination
        more_width, more_height = dis.icon_size('more_right')
        y = Display.HEIGHT - Display.FOOTER_HEIGHT - more_height - 12

        # Pagination constants
        PGN_COUNT = min(7, self.seed_len)
        PGN_MIDDLE = PGN_COUNT // 2
        PGN_SEP = 2
        PGN_W = 24
        PGN_H = 22
        x = (Display.WIDTH - ((PGN_W + PGN_SEP) * PGN_COUNT) + PGN_SEP) // 2
        y += 1

        # Calculate the framing of the pagination so that the curr_word is in the middle
        # whenever possible.
        # print('PGN_MIDDLE={} PGN_COUNT={} seed_len={} curr_word={}'.format(PGN_MIDDLE, PGN_COUNT, self.seed_len, self.curr_word))
        if self.curr_word <= PGN_MIDDLE:
            pgn_start = min(0, self.curr_word)
        elif self.curr_word <= self.seed_len - PGN_MIDDLE - 1:
            pgn_start = self.curr_word - PGN_MIDDLE
        else:
            pgn_start = self.seed_len - PGN_COUNT
        pgn_end = pgn_start + PGN_COUNT

        # Show icons only if there is something to that side to scroll to
        if pgn_start > 0:
            dis.icon(TEXTBOX_MARGIN, y + 4, 'more_left')
        if pgn_end < self.seed_len:
            dis.icon(Display.WIDTH - TEXTBOX_MARGIN - more_width, y + 4, 'more_right')

        for i in range(pgn_start, pgn_end):
            num_label = '{}'.format(i + 1)
            label_width = dis.width(num_label, self.pagination_font)
            tx = x + (PGN_W//2) - label_width // 2
            ty = y + 3
            invert_text = 0
            if i == self.curr_word:
                # Draw with an inverted rectangle
                dis.draw_rect(x, y, PGN_W, PGN_H, 0, fill_color=1)
                invert_text = 1
            elif len(self.words[i]) > 0:
                # Draw with a normal rectangle
                dis.draw_rect(x, y, PGN_W, PGN_H, 1, fill_color=0, border_color=1)

            dis.text(tx, ty, num_label, font=self.pagination_font, invert=invert_text)

            x += PGN_W + PGN_SEP

        dis.draw_footer('BACK', 'SELECT', self.input.is_pressed('x'), self.input.is_pressed('y'))

        dis.show()
        system.turbo(False)

    async def interact(self):
        # Wait for key inputs
        event = None
        while True:
            event = await self.input.get_event()

            if event != None:
                break

        if event != None:
            key, event_type = event

            if event_type == 'down':
                if key in '23456789':
                    self.user_input[self.curr_word] += key
                    c = self.user_input[self.curr_word] if len(self.user_input[self.curr_word]) > 0 else 'a'

                    # Reset highlight to the top whenever we change the input
                    self.highlighted_word_index = 0

                    # No word selected anymore since we changed the input
                    self.words[self.curr_word] = ''
                    self.selectable_words = None
                elif key == 'l':
                    self.curr_word = max(self.curr_word - 1, 0)
                    # print('curr_word={}'.format(self.curr_word))
                    self.highlighted_word_index = 0
                    self.selectable_words = None

                elif key == 'r':
                    if len(self.words[self.curr_word]) == 0:
                        # Assume the highlighted word is the selected one
                        self.words[self.curr_word] = self.selectable_words[self.highlighted_word_index]

                    self.curr_word = min(self.curr_word + 1, len(self.words) - 1)
                    self.highlighted_word_index = 0
                    self.selectable_words = None
                elif key == 'u':
                    self.highlighted_word_index = max(0, self.highlighted_word_index - 1)
                elif key == 'd':
                    self.highlighted_word_index = min(len(self.selectable_words) - 1, self.highlighted_word_index + 1)
                elif key == '*':
                    self.user_input[self.curr_word] = self.user_input[self.curr_word][0:-1]

                    # Indicate that user hasn't finalized this word yet
                    self.words[self.curr_word] = ''
                    self.selectable_words = None

            if event_type == 'up':
                if key == 'x':
                    cancel = await ux_confirm('Are you sure you want to cancel seed entry? All progress will be lost.')
                    if cancel:
                        self.is_seed_valid = False
                        return False
                elif key == 'y':
                    self.words[self.curr_word] = self.selectable_words[self.highlighted_word_index]

                    if self.curr_word < self.seed_len - 1:
                        self.curr_word += 1
                        self.highlighted_word_index = 0
                        self.selectable_words = None
                    else:
                        self.goto(self.VALIDATE_SEED)

        return True

    def update(self):
        # User could have moved forward or back in the pages or up and down in the selectable_words list
        # or typed a number.
        #
        # Update the selectable words according to the current state
        # print('words={} curr_word={}'.format(self.words, self.curr_word))
        if self.words[self.curr_word] != None and len(self.words[self.curr_word]) > 0:
            # print('single word case')
            # if a word has been selected, it will be stored here, so show that word
            self.selectable_words = [self.words[self.curr_word]]

            # Also, set the input to the numbers for this word so the two are in sync
            self.user_input[self.curr_word] = str(word_to_keypad_numbers(self.words[self.curr_word]))

            self.highlighted_word_index = 0
        else:
            # print('normal input case')
            # Only regenerate the word list when the action would cause the words to change.
            # Code above indicates this by setting the list to None.
            if self.selectable_words == None:
                # No word has been selected yet, so lookup the matches
                c = self.user_input[self.curr_word] if len(self.user_input[self.curr_word]) > 0 else '2'
                # print('c={}'.format(c))
                words = get_words_matching_prefix(c, MAX_WORDS_TO_DISPLAY*2, self.word_list)
                # print('words={}'.format(words))
                self.selectable_words = shuffle(words)
                # Sort so that exact matches come first and don't fall off the shorter list
                self.selectable_words.sort(key=lambda w: len(w))
                # print('shuffled={}'.format(words))
                self.selectable_words = self.selectable_words[:MAX_WORDS_TO_DISPLAY]
                # print('selectable_words={} MAX={}'.format(self.selectable_words, MAX_WORDS_TO_DISPLAY))
                self.last_word_lookup = c

        # print('selectable_words={}'.format(self.selectable_words))


    async def show(self):
        while True:
            # print('show: state={}'.format(self.state))
            if self.state == self.ENTER_WORDS:
                self.render()
                if await self.interact() == False:
                    return None
                self.update()

            elif self.state == self.VALIDATE_SEED:
                if not self.validate_checksum:
                    self.goto(self.VALID_SEED)
                elif len(self.words) == self.seed_len:
                    # Ensure that the checksum of the mnemonic words is correct
                    mnemonic = ' '.join(self.words)
                    # print('Checking mnemonic: "{}"'.format(mnemonic))
                    if bip39.check(mnemonic):
                        self.goto(self.VALID_SEED)
                    else:
                        self.goto(self.INVALID_SEED)

            elif self.state == self.VALID_SEED:
                # Return the words to the caller
                # print('seed = {}'.format(self.words))
                self.is_seed_valid = True
                return self.words

            elif self.state == self.INVALID_SEED:
                # Show a story that indicates the words are wrong - BACK to return to previous menu or RETRY to try again
                result = await ux_show_story('Seed phrase is invalid. One or more of your seed words is incorrect.',
                                             title='Invalid Seed', left_btn='BACK', right_btn='RETRY', center="True", center_vertically=True)
                if result == 'x':
                    cancel = await ux_confirm('Are you sure you want to cancel seed entry? All progress will be lost.')
                    if cancel:
                        self.is_seed_valid = False
                        return False
                elif result == 'y':
                    self.goto(self.ENTER_WORDS)

            else:
                while True:
                    # print('ERROR: Should never hit this else case!')
                    from uasyncio import sleep_ms
                    await sleep_ms(1000)
