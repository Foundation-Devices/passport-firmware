# SPDX-FileCopyrightText: 2020 Foundation Devices, Inc. <hello@foundationdevices.com>
# SPDX-License-Identifier: GPL-3.0-or-later
#
# seed_check_ux.py - UX related to seed phrase entry and verification
#
import random
from display import Display, FontSmall, FontTiny
from common import dis, system
from uasyncio import sleep_ms
from utils import UXStateMachine
from ux import KeyInputHandler, ux_show_story, ux_confirm
import random

TEXTBOX_MARGIN = 6
PAGINATION_HEIGHT = Display.FOOTER_HEIGHT
MAX_WORDS_TO_DISPLAY = 4
NUM_SELECTABLE_WORDS = 5

# Separate state machines to keep
class SeedCheckUX(UXStateMachine):
    # States
    SELECT_WORDS = 1
    SEED_CHECK_COMPLETE = 4

    def __init__(self, title='Check Seed', seed_words=[], cancel_msg=None):
        super().__init__(self.SELECT_WORDS)
        self.title = title
        self.seed_words = seed_words
        self.seed_len = len(seed_words)
        self.curr_word = 0
        self.is_check_valid = False
        self.font = FontSmall
        self.pagination_font = FontTiny
        self.highlighted_word_index = 0
        self.selectable_words = None
        self.show_check = False
        self.show_error = False
        self.cancel_msg = cancel_msg if cancel_msg != None else '''Are you sure you want to cancel the seed check?

You will be unable to recover this wallet without the correct seed.'''

        self.input = KeyInputHandler(down='udxy', up='xy')

        # Update state based on current info
        self.update()

    def render(self):
        system.turbo(True)
        dis.clear()

        dis.draw_header(self.title)

        # Draw the title
        y = Display.HEADER_HEIGHT + TEXTBOX_MARGIN + 4
        dis.text(None, y, 'Select Word {} of {}'.format(self.curr_word + 1, self.seed_len))
        y += self.font.leading + 4

        # Draw a bounding box around the list of selectable words
        dis.draw_rect(TEXTBOX_MARGIN, y, Display.WIDTH - (TEXTBOX_MARGIN * 2),
                      NUM_SELECTABLE_WORDS * (self.font.leading - 1), 1,
                      fill_color=0, border_color=1)

        # Draw the selectable words
        for i in range(len(self.selectable_words)):
            if i == self.highlighted_word_index:
                # Draw inverted text with rect to indicate that this word will be selected
                # when user presses SELECT button.
                dis.draw_rect(TEXTBOX_MARGIN, y, Display.WIDTH - (TEXTBOX_MARGIN * 2), self.font.leading, 0, fill_color=1)
                dis.text(None, y+2, self.selectable_words[i], invert=1)

                # Draw a check mark if the word is correct
                if self.show_check:
                    dis.icon(TEXTBOX_MARGIN + 6, y + 6, 'selected', invert=True)
                elif self.show_error:
                    dis.icon(TEXTBOX_MARGIN + 6, y + 6, 'x', invert=True)

            else:
                dis.text(None, y+1, self.selectable_words[i])

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
            elif i < self.curr_word:
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
                if key == 'u':
                    self.highlighted_word_index = max(0, self.highlighted_word_index - 1)
                elif key == 'd':
                    self.highlighted_word_index = min(len(self.selectable_words) - 1, self.highlighted_word_index + 1)

            if event_type == 'up':
                if key == 'x':
                    abort = await ux_confirm(self.cancel_msg)
                    if abort:
                        return False
                elif key == 'y':
                    if self.seed_words[self.curr_word] == self.selectable_words[self.highlighted_word_index]:
                        # Word is correct, so draw checkmark
                        self.show_check = True
                        self.render()
                        self.show_check = False
                        await sleep_ms(500)

                        # Next word?
                        if self.curr_word < self.seed_len - 1:
                            self.curr_word += 1
                            self.highlighted_word_index = 0
                            self.selectable_words = None
                        else:
                            # All words have been validated
                            self.goto(self.SEED_CHECK_COMPLETE)
                    else:
                        self.show_error = True

        return True

    def update(self):
        if self.selectable_words == None:
            system.turbo(True)
            self.selectable_words = []
            # Choose random words and the seed word
            indexes = []
            for i in range(len(self.seed_words)):
                if i != self.curr_word:
                    indexes.append(i)

            for i in range(NUM_SELECTABLE_WORDS):
                r = random.randint(0, len(indexes) - 1)
                seed_index = indexes[r]
                self.selectable_words.append(self.seed_words[seed_index])
                indexes.remove(seed_index)

            # Replace one index at random with the expected word
            r = random.randint(0, NUM_SELECTABLE_WORDS - 1)
            self.selectable_words[r] = self.seed_words[self.curr_word]
            system.turbo(False)

    async def show(self):
        while True:
            # print('show: state={}'.format(self.state))
            if self.state == self.SELECT_WORDS:
                self.render()
                self.show_error = False
                if await self.interact() == False:
                    return False
                self.update()

            elif self.state == self.SEED_CHECK_COMPLETE:
                self.is_check_valid = True
                return True

            else:
                while True:
                    # print('ERROR: Should never hit this else case!')
                    from uasyncio import sleep_ms
                    await sleep_ms(1000)
