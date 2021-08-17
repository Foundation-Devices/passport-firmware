# SPDX-FileCopyrightText: 2020 Foundation Devices, Inc. <hello@foundationdevices.com>
# SPDX-License-Identifier: GPL-3.0-or-later
#
# SPDX-FileCopyrightText: 2018 Coinkite, Inc. <coldcardwallet.com>
# SPDX-License-Identifier: GPL-3.0-only
#
# (c) Copyright 2018 by Coinkite Inc. This file is part of Coldcard <coldcardwallet.com>
# and is covered by GPLv3 license found in COPYING.
#
# ux.py - UX/UI related helper functions
#
# NOTE: do not import from main at top.

import gc

import utime
from display import Display, FontSmall, FontTiny
from uasyncio import sleep_ms
from uasyncio.queues import QueueEmpty
from common import system, dis
from data_codecs.qr_type import QRType
from data_codecs.qr_factory import get_qr_decoder_for_data, make_qr_encoder
from utils import is_alphanumeric_qr

LEFT_MARGIN = 8
RIGHT_MARGIN = 6
TOP_MARGIN = 12
VERT_SPACING = 10
MAX_WIDTH = Display.WIDTH - LEFT_MARGIN - \
    RIGHT_MARGIN - Display.SCROLLBAR_WIDTH

TEXTBOX_MARGIN = 6

# This signals the need to switch from current
# menu (or whatever) to show something new. The
# stack has already been updated, but the old
# top-of-stack code was waiting for a key event.
class AbortInteraction(Exception):
    pass


class UserInteraction:
    def __init__(self):
        self.stack = []

    def is_top_level(self):
        return len(self.stack) == 1

    def top_of_stack(self):
        return self.stack[-1] if self.stack else None

    def reset_to_root(self):
        root = self.stack[0]
        self.reset(root)

    def reset(self, new_ux):
        self.stack.clear()
        gc.collect()
        self.push(new_ux)

    async def interact(self):
        # this is called inside a while(1) all the time
        # - execute top of stack item
        try:
            await self.stack[-1].interact()
        except AbortInteraction:
            pass

    def push(self, new_ux):
        self.stack.append(new_ux)

    def replace(self, new_ux):
        old = self.stack.pop()
        del old
        self.stack.append(new_ux)

    def pop(self):
        if len(self.stack) < 2:
            # top of stack, do nothing
            return True

        old = self.stack.pop()
        del old


# Singleton. User interacts with this "menu" stack.
the_ux = UserInteraction()


def time_now_ms():
    import utime
    return utime.ticks_ms()

class KeyInputHandler:
    def __init__(self, down="", up="", long="", repeat_delay=None, repeat_speed=None, long_duration=2000):
        self.time_pressed = {}
        self.down = down
        self.up = up
        self.long = long
        self.repeat_delay = repeat_delay  # How long until repeat mode starts
        self.repeat_speed = repeat_speed  # How many ms between each repeat
        self.repeat_active = False
        self.long_duration = long_duration
        self.kcode_state = 0
        self.kcode_last_time_pressed = 0

    # Returns a dictionary of all pressed keys mapped to the elapsed time that each has been pressed.
    # This can be used for things like showing the progress bar for the Hold to Sign functionality.
    def get_all_pressed(self):
        now = time_now_ms()
        pressed = {}
        for key, start_time in self.time_pressed.items():
            pressed[key] = now - start_time
        return pressed

    def __update_kcode_state(self, expected_keys, actual_key):
        # print('kcode: state={} expected={} actual={}'.format(self.kcode_state, expected_key, actual_key))
        if actual_key in expected_keys:
            self.kcode_state += 1
            self.kcode_last_time_pressed = time_now_ms()
            # print('  state advanced to {}'.format(self.kcode_state))
        else:
            self.kcode_state = 0
            # print('  state reset to {}'.format(self.kcode_state))
            # If this key could start a new sequence, then call recursively so we don't skip it
            if actual_key == 'u':
                # print('  second chance for  {}'.format(actual_key))
                self.__check_kcode(actual_key)

    def __check_kcode(self, key):
        if self.kcode_state == 0:
            self.__update_kcode_state('u', key)
        elif self.kcode_state == 1:
            self.__update_kcode_state('u', key)
        elif self.kcode_state == 2:
            self.__update_kcode_state('d', key)
        elif self.kcode_state == 3:
            self.__update_kcode_state('d', key)
        elif self.kcode_state == 4:
            self.__update_kcode_state('l', key)
        elif self.kcode_state == 5:
            self.__update_kcode_state('r', key)
        elif self.kcode_state == 6:
            self.__update_kcode_state('l', key)
        elif self.kcode_state == 7:
            self.__update_kcode_state('r', key)
        elif self.kcode_state == 8:
            self.__update_kcode_state('xy', key)
        elif self.kcode_state == 9:
            self.__update_kcode_state('xy', key)

    # If the user seems to be entering the kcode, then the caller should
    # probably not perform the normal button processing
    def kcode_imminent(self):
        # print('kcode_immiment() = {}'.format(True if self.kcode_state >= 8 else False))
        return self.kcode_state >= 8

    def kcode_complete(self):
        # print('kcode_complete game = {}'.format(True if self.kcode_state == 10 else False))
        return self.kcode_state == 10

    def kcode_reset(self):
        # print('kcode_reset()')
        self.kcode_state = 0

    def is_pressed(self, key):
        return key in self.time_pressed

    def clear(self):
        from common import keypad
        keypad.clear_keys()

    # Reset internal state so that all pending kcodes and repeats are forgotten.
    def reset(self):
        self.time_pressed = {}
        self.kcode_state = 0
        self.kcode_last_time_pressed = 0
        self.repeat_active = False

    # New input function to be used in place of PressRelease and ux_press_release, ux_all_up and ux_poll_once.
    async def get_event(self):
        from common import keypad

        # This awaited sleep is necessary to give the simulator key code a chance to insert keys into the queue
        # Without it, the ux_poll_once() below will never find a key.
        await sleep_ms(5)

        # See if we have a character in the queue and if so process it
        # Poll for an event
        key, is_down = keypad.get_event()

        # if key != None:
        #     print('key={} is_down={}'.format(key, is_down))

        if key == None:
            # There was nothing in the queue, so handle the time-dependent events
            now = time_now_ms()
            for k in self.time_pressed:
                # print('k={}  self.down={}  self.repeat={}  self.time_pressed={}'.format(k, self.down, self.repeat, self.time_pressed))
                # Handle repeats
                if self.repeat_delay != None and k in self.down:
                    elapsed = now - self.time_pressed[k]
                    if self.repeat_active == False:
                        if elapsed >= self.repeat_delay:
                            self.repeat_active = True
                            self.time_pressed[k] = now
                            return (k, 'repeat')
                    else:
                        if elapsed >= self.repeat_speed:
                            self.time_pressed[k] = now
                            return (k, 'repeat')

                # Handle long press expiration
                if k in self.long:
                    elapsed = now - self.time_pressed[k]
                    if elapsed >= self.long_duration:
                        del self.time_pressed[k]
                        return (k, 'long_press')

            # Handle kcode timeout - User seemed to give up, so go back to normal key processing
            if self.kcode_state > 0 and now - self.kcode_last_time_pressed >= 3000:
                # print('Resetting kcode due to timeout')
                self.kcode_state = 0
            return None

        now = time_now_ms()

        # Handle the event
        if is_down:
            self.__check_kcode(key)

            # Check to see if we are interested in this key event
            if key in self.down:
                self.time_pressed[key] = now
                return (key, 'down')

            if key in self.long:
                self.time_pressed[key] = now

        else:  # up
            # Removing this will cancel long presses of the key as well
            if key in self.time_pressed:
                self.repeat_active = False
                del self.time_pressed[key]

            # Check to see if we are interested in this key event
            if key in self.up:
                return (key, 'up')


key_to_char_map_lower = {
    '2': 'abc',
    '3': 'def',
    '4': 'ghi',
    '5': 'jkl',
    '6': 'mno',
    '7': 'pqrs',
    '8': 'tuv',
    '9': 'wxyz',
    '0': ' ',
}

key_to_char_map_upper = {
    '2': 'ABC',
    '3': 'DEF',
    '4': 'GHI',
    '5': 'JKL',
    '6': 'MNO',
    '7': 'PQRS',
    '8': 'TUV',
    '9': 'WXYZ',
    '0': ' ',
}

key_to_char_map_numbers = {
    '1': '1',
    '2': '2',
    '3': '3',
    '4': '4',
    '5': '5',
    '6': '6',
    '7': '7',
    '8': '8',
    '9': '9',
    '0': '0 ',
}


# Class that implements a state machine for editing a text string like a passphrase.
# Takes KeyInputHandler events as state change events, along with elapsed time.

IDLE_KEY_TIMEOUT = 500

class TextInputHandler:
    def __init__(self, text="", num_only=False, max_length=None):
        self.text = [ch for ch in text]
        self.cursor_pos = len(self.text)  # Put cursor at the end if there is any initial text
        self.last_key_down_time = 0
        self.last_key = None
        self.next_map_index = 0
        self.curr_key_map = key_to_char_map_numbers if num_only else key_to_char_map_lower
        self.num_only = num_only
        self.max_length = max_length
        if self.max_length:
            # Make sure user-passed value doesn't exceed the max, if given
            self.text = self.text[0:self.max_length]

    def _next_key_map(self):
        if self.num_only:
            return

        if self.curr_key_map == key_to_char_map_lower:
            self.curr_key_map = key_to_char_map_upper
        elif self.curr_key_map == key_to_char_map_upper:
            self.curr_key_map = key_to_char_map_numbers
        elif self.curr_key_map == key_to_char_map_numbers:
            self.curr_key_map = key_to_char_map_lower

    def get_mode_description(self):
        if self.curr_key_map == key_to_char_map_lower:
            return 'a-z'
        elif self.curr_key_map == key_to_char_map_upper:
            return 'A-Z'
        elif self.curr_key_map == key_to_char_map_numbers:
            return '0-9'

    async def handle_event(self, event):
        now = time_now_ms()
        key, event_type = event
        if event_type == 'down':
            # Outer code handles these
            if key in 'xy':
                return

            # print("key={}".format(key))
            if key in '*#rl':
                if key == '#':
                    self._next_key_map()
                elif key == '*':
                    if self.cursor_pos > 0:
                        # Delete the character under the cursor
                        self.cursor_pos = max(self.cursor_pos-1, 0)
                        if len(self.text) > self.cursor_pos:
                            del self.text[self.cursor_pos]
                elif key == 'l':
                    self.cursor_pos = max(self.cursor_pos - 1, 0)
                elif key == 'r':
                    # Allow cursor_pos to go at most one past the end
                    self.cursor_pos = min(
                        self.cursor_pos + 1, len(self.text))

                # print('cursor_pos={} next_map_index={} key={} text={}'.format(
                #     self.cursor_pos, self.next_map_index, key, self.text))
                self.last_key_down_time = 0
                return

            # Check for symbols pop-up
            if key == '1' and self.curr_key_map != key_to_char_map_numbers:
                if self.max_length and len(self.text) >= self.max_length:
                    pass
                else:
                    # Show the symbols pop-up, otherwise fall through and handle '1' as a normal key press
                    symbol = await ux_show_symbols_popup('!')
                    if symbol == None:
                        return

                    # Insert the symbol
                    self.text.insert(self.cursor_pos, symbol)
                    self.cursor_pos += 1
                return

            if self.last_key == None:
                # print("first press of {}".format(key))
                # A new keypress, so insert the first character mapped to this key, unless max reached
                if self.max_length and len(self.text) >= self.max_length:
                    pass
                else:
                    self.text.insert(
                        self.cursor_pos, self.curr_key_map[key][self.next_map_index])
                    self.cursor_pos += 1
                    if len(self.curr_key_map[key]) == 1:
                        # Just immediate commit this key since there are no other possible choices to wait for
                        return

            elif self.last_key == key:
                # User is pressing the same key within the idle timeout, so cycle to the next key
                # making sure to wrap around if they keep going.
                self.next_map_index = (
                    self.next_map_index + 1) % len(self.curr_key_map[key])
                # Overwrite the last key
                self.text[self.cursor_pos -
                          1] = self.curr_key_map[key][self.next_map_index]

            else:
                if self.max_length and len(self.text) >= self.max_length:
                    pass
                else:
                    # User pressed a different key, but before the idle timeout, so we finalize the last
                    # character and start the next character as tentative.
                    self.cursor_pos += 1  # Finalize the last character
                    self.next_map_index = 0  # Reset the map index

                    # Append the new key
                    self.text.insert(
                        self.cursor_pos, self.curr_key_map[key][self.next_map_index])

            # Insert or overwrite the character
            # print('cursor_pos={} next_map_index={} key={} text={}'.format(
            #     self.cursor_pos, self.next_map_index, key, self.text))

            # Always record the value and time of the key, regardless of which case we were in above
            self.last_key = key
            self.last_key_down_time = now

    # This method should be called periodically (like event 10ms) if there is no key event.
    # Return True if a timeout occurred, so the caller can render the updated state.
    def check_timeout(self):
        now = time_now_ms()

        if self.last_key_down_time != 0 and now - self.last_key_down_time >= IDLE_KEY_TIMEOUT:
            # print("timeout!")
            # Reset for next key
            self.last_key_down_time = 0
            self.last_key = None
            self.last_index = -1
            self.next_map_index = 0
            return True

        return False

    def get_text(self):
        return "".join(self.text)

    def get_num(self):
        return int("".join(self.text))


async def ux_enter_text(title="Enter Text", label="Text", initial_text='', left_btn='BACK', right_btn='CONTINUE',
    num_only=False, max_length=None):
    from common import dis
    from display import FontSmall

    font = FontSmall

    input = KeyInputHandler(down='1234567890*#rlxy', up='xy')
    text_handler = TextInputHandler(text=initial_text, num_only=num_only, max_length=max_length)

    while 1:
        # redraw
        system.turbo(True)
        dis.clear()

        dis.draw_header(title, left_text=text_handler.get_mode_description())

        # Draw the title
        y = Display.HEADER_HEIGHT + TEXTBOX_MARGIN
        dis.text(None, y+2, label)

        # Draw a bounding box around the text area
        y += font.leading + TEXTBOX_MARGIN
        dis.draw_rect(TEXTBOX_MARGIN, y, Display.WIDTH - (TEXTBOX_MARGIN * 2),
                      Display.HEIGHT - y - TEXTBOX_MARGIN - Display.FOOTER_HEIGHT, 1, fill_color=0, border_color=1)

        # Draw the text and any other stuff
        y += 4
        dis.text_input(None, y, text_handler.get_text(),
                       cursor_pos=text_handler.cursor_pos, font=font)

        dis.draw_footer(left_btn, right_btn, input.is_pressed(
            'x'), input.is_pressed('y'))

        dis.show()
        system.turbo(False)

        # Wait for key inputs
        event = None
        while True:
            event = await input.get_event()

            if event != None:
                break

            # No event, so handle the idle timing
            if text_handler.check_timeout():
                break

        if event != None:
            key, event_type = event

            # Check for footer button actions first
            if event_type == 'down':
                await text_handler.handle_event(event)

            if event_type == 'up':
                if key == 'x':
                    return None
                if key == 'y':
                    return text_handler.get_num() if num_only else text_handler.get_text()


symbol_rows = [
    '!@#$%^&*',
    '+/-=\\?|~',
    '_"`\',.:;',
    '()[]{}<>',
]


async def ux_show_symbols_popup(title="Enter Passphrase"):
    from common import dis
    from display import FontSmall
    # print('ux_show_symbols_popup()')
    font = FontSmall

    input = KeyInputHandler(down='rlduxy', up='xy')
    text_handler = TextInputHandler()

    cursor_row = 0
    cursor_col = 0

    num_symbols_per_row = 8
    num_rows = len(symbol_rows)
    h_margin = 12
    v_margin = 10
    char_spacing = 22
    width = num_symbols_per_row * char_spacing + (2 * h_margin)
    height = num_rows * font.leading + (2 * v_margin)

    while 1:
        system.turbo(True)

        # redraw
        x = Display.WIDTH // 2 - width // 2
        y = Display.HEIGHT - Display.FOOTER_HEIGHT - height - 14

        dis.draw_rect(x, y, width, height, 2, 0, 1)

        x += h_margin
        y += v_margin

        # Draw the grid of symbols
        curr_row = 0
        for symbols in symbol_rows:
            dis.text(x, y, symbols,
                     cursor_pos=(cursor_col if curr_row ==
                                 cursor_row else None),
                     font=font,
                     fixed_spacing=char_spacing,
                     cursor_shape='block')
            curr_row += 1
            y += font.leading

        dis.draw_footer('CANCEL', 'SELECT', input.is_pressed(
            'x'), input.is_pressed('y'))

        dis.show()

        system.turbo(False)

        # Wait for key inputs
        event = None
        while True:
            event = await input.get_event()

            if event != None:
                break

            # No event, so handle the idle timing
            if text_handler.check_timeout():
                break

        num_symbols = len(symbol_rows[cursor_row])
        if event != None:
            key, event_type = event

            # Check for footer button actions first
            if event_type == 'down':
                if key == 'u':
                    cursor_row = (cursor_row - 1) % num_rows
                elif key == 'd':
                    cursor_row = (cursor_row + 1) % num_rows
                elif key == 'l':
                    cursor_col = (cursor_col - 1) % num_symbols
                elif key == 'r':
                    cursor_col = (cursor_col + 1) % num_symbols

            if event_type == 'up':
                if key == 'x':
                    return None
                if key == 'y':
                    return symbol_rows[cursor_row][cursor_col]


# NOTE: This function factors in the scrollbar width even if the scrollbar might not end up being shown,
#       because the line breaking code uses it BEFORE knowing if scrolling is required.
def chars_per_line(font):
    return (Display.WIDTH - LEFT_MARGIN - Display.SCROLLBAR_WIDTH) // font.advance

def word_wrap(ln, font):
    from common import dis
    max_width = Display.WIDTH - LEFT_MARGIN - \
        RIGHT_MARGIN - Display.SCROLLBAR_WIDTH

    while ln:
        sp = 0
        last_space = 0
        line_width = 0
        first_non_space = 0

        # Strip out leading and trailing spaces
        ln = ln.strip()

        while sp < len(ln):
            ch = ln[sp]
            if ch.isspace():
                last_space = sp
            ch_w = dis.char_width(ch, font)
            line_width += ch_w
            if line_width >= max_width:
                # If we found a space, we can break there, but if we didn't
                # then just break before we went over.
                if last_space != 0:
                    sp = last_space
                break
            sp += 1

        line = ln[first_non_space:sp]
        ln = ln[sp:]

        yield line


async def ux_show_story(msg, title='Passport', sensitive=False, font=FontSmall, escape='', left_btn='BACK',
                        right_btn='CONTINUE', scroll_label=None, left_btn_enabled=True, right_btn_enabled=True,
                        center_vertically=False, center=False, overlay=None, clear_keys=False):
    from common import dis, keypad
    from utils import split_by_char_size

    system.turbo(True)

    # Clear the keys before starting
    if clear_keys:
        keypad.clear_keys()

    lines = split_by_char_size(msg, font)

    # trim blank lines at end
    while not lines[-1]:
        lines = lines[:-1]

    top = 0
    H = (Display.HEIGHT - Display.HEADER_HEIGHT -
         Display.FOOTER_HEIGHT) // font.leading
    max_visible_lines = (Display.HEIGHT - Display.HEADER_HEIGHT - Display.FOOTER_HEIGHT) // font.leading

    input = KeyInputHandler(down='rldu0xy', up='xy' + escape, repeat_delay=250, repeat_speed=10)

    system.turbo(False)

    allow_right_btn_action = True
    turbo = None  # We rely on this being 3 states: None, False, True
    while 1:
        # redraw
        dis.clear()

        dis.draw_header(title)

        y = Display.HEADER_HEIGHT

        # Only take center_vertically into account if there are more lines than will fit on the page
        if len(lines) <= max_visible_lines and center_vertically:
            avail_height = (Display.HEIGHT -
                            Display.HEADER_HEIGHT - Display.FOOTER_HEIGHT)
            text_height = len(lines) * font.leading - font.descent
            y += avail_height // 2 - text_height // 2


        content_to_height_ratio = H / len(lines)
        show_scrollbar= True if content_to_height_ratio < 1 else False

        last_to_show = min(top+H+1, len(lines))
        for ln in lines[top:last_to_show]:
            x = LEFT_MARGIN if not center else None
            dis.text(x, y, ln, font=font, scrollbar_visible=show_scrollbar)

            y += font.leading

        if show_scrollbar:
            dis.scrollbar(top / len(lines), content_to_height_ratio)

        # Show the scroll_label if given and if we have not reached the bottom yet
        scroll_enable_right_btn = True
        right_btn_label = right_btn
        if scroll_label != None:
            if H + top < len(lines):
                scroll_enable_right_btn = False
                right_btn_label = scroll_label

        dis.draw_footer(left_btn, right_btn_label,
                        input.is_pressed('x'), input.is_pressed('y'))

        # Draw overlay image, if any
        if overlay:
            (x, y, image) = overlay
            dis.icon(x, y, image)

        dis.show()

        # We only want to turn it off once rather than whenever it's False, so we
        # set to None to avoid turning turbo off again.
        if turbo == False:
            system.turbo(False)
            turbo = None

        # Wait for key inputs
        event = None
        while True:
            while True:
                event = await input.get_event()

                if event != None:
                    break

            key, event_type = event
            # print('key={} event_type={}'.format(key, event_type))

            if event_type == 'down' or event_type == 'repeat':
                system.turbo(True)
                turbo = True

                if key == 'u':
                    top = max(0, top-1)
                    break
                elif key == 'd':
                    if len(lines) > H:
                        top = min(len(lines) - H, top+1)
                    break
                elif key == 'y':
                    if event_type == 'repeat':
                        allow_right_btn_action = False
                    elif event_type == 'down':
                        allow_right_btn_action = True

                    if not scroll_enable_right_btn:
                        if len(lines) > H:
                            top = min(len(lines) - H, top+1)
                        else:
                            continue
                    break
                elif key in 'xy':
                    # allow buttons to redraw for pressed state
                    break
                else:
                    continue

            if event_type == 'down':
                if key == '0':
                    top = 0
                    break
                else:
                    continue

            if event_type == 'up':
                turbo = False  # We set to False here, but actually turn off after rendering
                if key in escape:
                    return key

                # No left_btn means don't exit on the 'x' key
                if left_btn_enabled and (key == 'x'):
                    return key

                if key == 'y':
                    if scroll_enable_right_btn:
                        if right_btn_enabled and allow_right_btn_action:
                            return key
                        break
                    else:
                        if len(lines) > H:
                            top = min(len(lines) - H, top+1)
                            break
                        else:
                            continue

async def ux_confirm(msg, title='Passport', negative_btn='NO', positive_btn='YES', center=True, center_vertically=True, scroll_label=None):
    resp = await ux_show_story(msg, title=title, center=center, center_vertically=center_vertically, left_btn=negative_btn, right_btn=positive_btn, scroll_label=scroll_label)
    return resp == 'y'


# async def ux_dramatic_pause(msg, seconds):
#     from common import dis, system
#
#     # show a full-screen msg, with a dramatic pause + progress bar
#     n = seconds * 8
#     dis.fullscreen(msg)
#     for i in range(n):
#         system.progress_bar((i*100)//n)
#         await sleep_ms(125)

def blocking_sleep(ms):
    start = utime.ticks_ms()
    while (1):
        now = utime.ticks_ms()
        if now - start >= ms:
            return


def save_error_log(msg, filename):
    from files import CardSlot, CardMissingError

    wrote_to_sd = False
    try:
        with CardSlot() as card:
            # Full path and short filename
            fname, nice = card.get_file_path(filename)
            with open(fname, 'wb') as fd:
                line = 'Saved %s to microSD' % nice
                fd.write(msg)
                wrote_to_sd = True
    except CardMissingError:
        line = 'Insert microSD to save log'
    except Exception:
        line = 'Failed to save %s' % filename
    return wrote_to_sd, line

def ux_show_fatal(msg):
    from common import dis
    from display import FontTiny

    font = FontTiny

    ch_per_line = chars_per_line(font)

    lines = []

    for ln in msg.split('\n'):
        if len(ln) > ch_per_line:
            lines.extend(word_wrap(ln, font))
        else:
            # ok if empty string, just a blank line
            lines.append(ln)

    # Draw
    top = 0
    max_visible_lines = (
        Display.HEIGHT - Display.HEADER_HEIGHT) // font.leading + 1
    num_lines = len(lines)
    max_top = max(0, num_lines - max_visible_lines)

    PER_LINE_DELAY = 500
    LONG_DELAY = 2000
    INITIAL_DELAY = 5000
    delay = INITIAL_DELAY
    direction = 1

    # Write
    filename = 'error.log'
    wrote_to_sd, lines[0] = save_error_log(msg, filename)
    while (1):
        system.turbo(True)

        # Draw
        dis.clear()
        dis.draw_header('Error')

        # Draw the subset of lines that is visible
        y = Display.HEADER_HEIGHT
        for ln in lines[top:top+max_visible_lines]:
            dis.text(LEFT_MARGIN, y, ln, font=font)
            y += font.leading

        dis.show()
        system.turbo(False)

        blocking_sleep(delay)

        # More lines than can be displayed - early exit if no scrolling needed
        if num_lines <= max_visible_lines:
            return

        # Change direction if we reach the top or bottom
        if direction == 1:
            top = min(max_top, top + 1)
            if top == max_top:
                direction = -1
        else:
            top = max(0, top - 1)
            if top == 0:
                direction = 1

        delay = PER_LINE_DELAY
        if top == 0 or top == max_top:
            if wrote_to_sd is False:
                wrote_to_sd, lines[0] = save_error_log(msg, filename)
            delay = LONG_DELAY


def show_fatal_error(msg):
    all_lines = msg.split('\n')[0:]

    # Remove lines we don't want to shorten
    lines = all_lines[1:-2]

    # Insert lines we want to add for readability or keep from the original msg
    lines.insert(0, "")
    lines.insert(1, "")
    lines.append("")
    lines.append(all_lines[-2])

    ux_show_fatal("\n".join(lines))


def restore_menu():
    # redraw screen contents after disrupting it w/ non-ux things (usb upload)
    m = the_ux.top_of_stack()

    if hasattr(m, 'update_contents'):
        m.update_contents()

    if hasattr(m, 'show'):
        m.show()


def abort_and_goto(m):
    import common
    common.keypad.clear_keys()
    the_ux.reset(m)


def abort_and_push(m):
    common.keypad.clear_keys()
    the_ux.push(m)


# async def show_qr_codes(addrs, is_alnum, start_n):
#     o = QRDisplay(addrs, is_alnum, start_n)
#     await o.interact_bare()


# class QRDisplay(UserInteraction):
#     # Show a QR code for (typically) a list of addresses. Can only work on Mk3
#
#     def __init__(self, addrs, is_alnum, start_n=0,path='', account=0, change=0):
#         self.is_alnum = is_alnum
#         self.idx = 0             # start with first address
#         self.invert = False      # looks better, but neither mode is ideal
#         self.addrs = addrs
#         self.start_n = start_n
#         self.qr_data = None
#         self.left_down = False
#         self.right_down = False
#         self.input = KeyInputHandler(down='xyudlr', up='xy')
#
#     def render_qr(self, msg):
#         # Version 2 would be nice, but can't hold what we need, even at min error correction,
#         # so we are forced into version 3 = 29x29 pixels
#         # - see <https://www.qrcode.com/en/about/version.html>
#         # - to display 29x29 pixels, we have to double them up: 58x58
#         # - not really providing enough space around it
#         # - inverted QR (black/white swap) still readable by scanners, altho wrong
#
#         from utils import imported
#
#         with imported('uQR') as uqr:
#             if self.is_alnum:
#                 # targeting 'alpha numeric' mode, typical len is 42
#                 ec = uqr.ERROR_CORRECT_Q
#                 assert len(msg) <= 47
#             else:
#                 # has to be 'binary' mode, altho shorter msg, typical 34-36
#                 ec = uqr.ERROR_CORRECT_M
#                 assert len(msg) <= 42
#
#             q = uqr.QRCode(version=3, box_size=1, border=0,
#                            mask_pattern=3, error_correction=ec)
#             if self.is_alnum:
#                 here = uqr.QRData(msg.upper().encode('ascii'),
#                                   mode=uqr.MODE_ALPHA_NUM, check_data=False)
#             else:
#                 here = uqr.QRData(msg.encode('ascii'),
#                                   mode=uqr.MODE_8BIT_BYTE, check_data=False)
#             q.add_data(here)
#             q.make(fit=False)
#
#             self.qr_data = q.get_matrix()
#
#     def redraw(self):
#         # Redraw screen.
#         from common import dis, system
#         from display import FontTiny
#
#         system.turbo(True)
#         font = FontTiny
#         inv = self.invert
#
#         # what we are showing inside the QR
#         msg, path = self.addrs[self.idx]
#
#         # make the QR, if needed.
#         if not self.qr_data:
#             # dis.busy_bar(True)
#             self.render_qr(msg)
#
#         # Draw display
#         if inv:
#             dis.dis.fill_rect(0, 0, Display.WIDTH,
#                               Display.HEIGHT - Display.FOOTER_HEIGHT + 1, 1)
#         else:
#             dis.clear()
#
#         y = TOP_MARGIN
#
#         # Draw the derivation path
#         if len(self.addrs) > 1:
#             dis.text(None, y, path, font, invert=inv)
#             y += font.leading + VERT_SPACING
#
#         w = 29          # because version=3
#         module_size = 5  # Each "dot" in a QR code is called a module
#         pixel_width = w * module_size
#         frame_width = pixel_width + (module_size * 2)
#
#         # QR code offsets
#         XO = (Display.WIDTH - pixel_width) // 2
#         YO = y
#         dis.dis.fill_rect(XO - module_size, YO -
#                           module_size, frame_width, frame_width, 0 if inv else 1)
#
#         # Draw the actual QR code
#         data = self.qr_data
#         for qx in range(w):
#             for qy in range(w):
#                 px = data[qx][qy]
#                 X = (qx*module_size) + XO
#                 Y = (qy*module_size) + YO
#                 dis.dis.fill_rect(X, Y, module_size,
#                                   module_size, px if inv else (not px))
#
#         # Show the data encoded by the QR code
#         y += w*module_size + VERT_SPACING + 3
#
#         MAX_ADDR_CHARS_PER_LINE = 16
#         for i in range(0, len(msg), MAX_ADDR_CHARS_PER_LINE):
#             dis.text(None, y, msg[i:i+MAX_ADDR_CHARS_PER_LINE], font, inv)
#             y += font.leading
#
#         dis.draw_footer('BACK', 'INVERT', self.input.is_pressed(
#             'x'), self.input.is_pressed('y'))
#         dis.show()
#         system.turbo(False)
#
#     async def interact_bare(self):
#
#         self.redraw()
#         while 1:
#             event = await self.input.get_event()
#
#             if event != None:
#                 key, event_type = event
#                 if event_type == 'down':
#                     if key == 'u' or key == 'l':
#                         if self.idx > 0:
#                             self.idx -= 1
#                             self.qr_data = None
#                     elif key == 'd' or key == 'r':
#                         if self.idx != len(self.addrs)-1:
#                             self.idx += 1
#                             self.qr_data = None
#                     elif key in 'xy':
#                         # Allow buttons to redraw in pressed state
#                         pass
#                     else:
#                         continue
#                 elif event_type == 'up':
#                     if key == 'x':
#                         self.redraw()
#                         break
#                     elif key == 'y':
#                         self.invert = not self.invert
#             else:
#                 continue
#
#             self.redraw()
#
#     async def interact(self):
#         await self.interact_bare()
#         the_ux.pop()


async def ux_show_text_as_ur(title='QR Code', qr_text='', qr_type=QRType.UR2, qr_args=None, msg=None, left_btn='BACK', right_btn='RESIZE'):
    # print('ux_show_text_as_ur: qr_type: {}'.format(qr_type))
    o = DisplayURCode(title, qr_text, qr_type, qr_args=qr_args, msg=msg, left_btn=left_btn, right_btn=right_btn)
    result = await o.interact_bare()
    gc.collect()
    return result

def qr_get_module_size_for_version(version):
    # 1 -> 21
    # 2 -> 25
    # etc.
    return version * 4 + 17

def qr_buffer_size_for_version(version):
    size = qr_get_module_size_for_version(version)
    return ((size * size) + 7) // 8


class DisplayURCode(UserInteraction):

    # Show a QR code or a series of codes in Blockchain Commons' UR format
    # Purpose is to allow a QR code to be scanned, so we make it as big as possible
    # given our screen size, but if it's too big, we display a series of images
    # instead.
    def __init__(self, title, qr_text, qr_type, qr_args=None, msg=None, left_btn='DONE', right_btn='RESIZE', is_binary=False):
        self.title = title
        self.qr_text = qr_text
        self.input = KeyInputHandler(down='xy', up='xy')
        self.last_version = 0
        self.msg = msg
        self.left_btn = left_btn
        self.right_btn = right_btn

        self.num_supported_sizes = 0
        self.qr_version_idx = 0 # "version" for QR codes essentially maps to the size
        self.render_id = 0
        self.last_render_id = -1;
        self.qr_type = qr_type
        # print('DisplayURCode: qr_type: {}'.format(qr_type))
        self.qr_args = qr_args
        self.is_binary = is_binary

        system.turbo(True)
        self.generate_qr_data()
        self.qr_data = None
        system.turbo(False)

    def generate_qr_data(self):
        dis.fullscreen('Generating QR')
        system.show_busy_bar()
        # Instantiate the right type of QR encoder - always make a new one
        self.qr_encoder = make_qr_encoder(self.qr_type, self.qr_args)
        self.num_supported_sizes = self.qr_encoder.get_num_supported_sizes()

        # We collect before and after to ensure the most available memory
        gc.collect()

        max_len = self.qr_encoder.get_max_len(self.qr_version_idx)
        self.qr_encoder.encode(self.qr_text, is_binary=self.is_binary, max_fragment_len=max_len)

        gc.collect()
        system.hide_busy_bar()

    def set_next_density(self):
        self.last_version = 0;
        self.qr_version_idx = (self.qr_version_idx + 1) % self.num_supported_sizes

    def get_frame_delay(self):
        if self.qr_version_idx == 0:
            return 200
        else:
            return 250

    def render_qr(self, data):
        from utils import imported, bytes_to_hex_str

        # print('data: {}'.format(bytes_to_hex_str(data)))

        if self.last_render_id != self.render_id:
            self.last_render_id = self.render_id

            # Release old buffer and collect so we can reuse that memory
            self.qr_data = None
            gc.collect()

            # Render QR data to buffer
            # print('qr={}'.format(data.upper()))
            encoded_data = data.encode('ascii')
            if self.qr_type != QRType.QR:
                encoded_data = encoded_data.upper()
            ll = len(encoded_data)

            from foundation import QRCode
            qrcode = QRCode()


            version = qrcode.fit_to_version(ll, is_alphanumeric_qr(encoded_data))

            # Don't go to a smaller QR code, even if it means repeated data since it looks weird
            # to change the QR code size
            if self.last_version > version:
                version = self.last_version
            else:
                self.last_version = version

            buf_size = qr_buffer_size_for_version(version)
            self.modules_count = qr_get_module_size_for_version(version)
            # print('fit_to_version({}) = {}  buffer size = {}'.format(ll, version,buf_size))

            # TODO: Use correct buffer size here or just allocate once outside the loop (largest possible size)
            out_buf = bytearray(2000)
            result = qrcode.render(encoded_data, version, 0, out_buf)

            self.qr_data = out_buf

    def redraw(self):
        # Redraw screen
        from common import dis
        from display import FontTiny

        system.turbo(True)
        TOP_MARGIN = 7
        font = FontTiny

        data = self.qr_encoder.next_part()
        # print('data={}'.format(data))
        self.render_qr(data)

        # Draw QR display
        dis.clear()
        dis.draw_header(self.title)
        # dis.draw_header(self.title, left_text='{}/{}'.format(self.curr_part + 1, len(self.parts)))
        y = Display.HEADER_HEIGHT + TOP_MARGIN

        w = self.modules_count
        # print('modules_count={}'.format(w))

        if self.msg:
            module_pixel_width = (Display.WIDTH - 60) // w
        else:
            module_pixel_width = (Display.WIDTH - 20) // w

        # print('module_pixel_width={}'.format(module_pixel_width))

        total_pixel_width = w * module_pixel_width
        frame_width = total_pixel_width + (module_pixel_width * 2)

        # QR code offsets
        XO = (Display.WIDTH - total_pixel_width) // 2

        # Center vertically now that we have no label underneath
        YO = ((Display.HEIGHT - Display.HEADER_HEIGHT - Display.FOOTER_HEIGHT) - total_pixel_width ) // 2 + Display.HEADER_HEIGHT
        dis.dis.fill_rect(XO - module_pixel_width, YO -
                          module_pixel_width, frame_width, frame_width, 0)

        # Draw the actual QR code
        # print('qr_data = {}'.format(self.qr_data))
        if self.qr_data != None:
            for qy in range(w):
                for qx in range(w):
                    offset = qy * self.modules_count + qx
                    px = (self.qr_data[offset >> 3]) & (1 << (7 - (offset & 0x07)))

                    X = (qx*module_pixel_width) + XO
                    Y = (qy*module_pixel_width) + YO
                    dis.dis.fill_rect(X, Y, module_pixel_width, module_pixel_width, px)

        # Draw message
        if self.msg != None:
            dis.text(None, Display.HEIGHT - Display.FOOTER_HEIGHT - 20, self.msg, font=FontTiny)

        dis.draw_footer(
            self.left_btn,
            self.right_btn,
            self.input.is_pressed('x'),
            self.input.is_pressed('y')
        )
        dis.show()
        system.turbo(False)

    async def interact_bare(self):
        self.redraw()

        while 1:
            event = await self.input.get_event()
            if event != None:
                # print('event={}'.format(event))
                key, event_type = event
                if event_type == 'up':
                    if key == 'x':
                        self.redraw()
                        return 'x'
                    elif key == 'y':
                        if self.right_btn == 'RESIZE':
                            system.turbo(True)
                            self.set_next_density()
                            self.generate_qr_data()
                            self.render_id += 1
                            system.turbo(False)
                        else:
                            # User has something else in mind
                            self.redraw()
                            return 'y'
            else:
                # Only need to check timer and advance part number if we have more than one part
                # if len(self.parts) > 1:
                # Show the next part after a short delay to control speed
                await sleep_ms(self.get_frame_delay())
                self.render_id += 1
                self.redraw()
                continue

            self.redraw()

    async def interact(self):
        await self.interact_bare()
        the_ux.pop()


# async def ux_enter_number(prompt, max_value):
#     # return the decimal number which the user has entered
#     # - default/blank value assumed to be zero
#     # - clamps large values to the max
#     from common import dis
#     from display import FontTiny, FontSmall
#     from math import log
#
#     # allow key repeat on X only
#     press = PressRelease('1234567890y')
#
#     footer = "X to DELETE, or OK when DONE."
#     y = 26
#     value = ''
#     max_w = int(log(max_value, 10) + 1)
#
#     while 1:
#         dis.clear()
#         dis.text(0, 0, prompt)
#
#         # text centered
#         if value:
#             bx = dis.text(None, y, value)
#             dis.icon(bx+1, y+11, 'space')
#         else:
#             dis.icon(64-7, y+11, 'space')
#
#         dis.text(None, -1, footer, FontTiny)
#         dis.show()
#
#         # ========================================
#         # ========================================
#         # ========================================
#         # ========================================
#         # TODO: Replace with KeyInputHandler
#         # ========================================
#         # ========================================
#         # ========================================
#         # ========================================
#
#         ch = await press.wait()
#         if ch == 'y':
#
#             if not value:
#                 return 0
#             return min(max_value, int(value))
#
#         elif ch == 'x':
#             if value:
#                 value = value[0:-1]
#             else:
#                 # quit if they press X on empty screen
#                 return 0
#         else:
#             if len(value) == max_w:
#                 value = value[0:-1] + ch
#             else:
#                 value += ch
#
#             # cleanup leading zeros and such
#             value = str(int(value))


async def ux_scan_qr_code(title):
    import common
    from common import dis, qr_buf, viewfinder_buf
    from display import FontSmall
    from utils import save_qr_code_image

    import utime
    from constants import VIEWFINDER_WIDTH, VIEWFINDER_HEIGHT, CAMERA_WIDTH, CAMERA_HEIGHT

    from foundation import Camera, QR

    font = FontSmall

    # Create the Camera connection
    cam = Camera()
    cam.enable()

    # Create QR decoder
    qr = QR(CAMERA_WIDTH, CAMERA_HEIGHT, qr_buf)
    qr_code = None
    data = None
    error = None

    input = KeyInputHandler(up='xy', down='xy')

    fps_start = utime.ticks_us()
    frame_count = 0

    qr_decoder = None
    progress = None

    while True:
        frame_start = utime.ticks_us()
        snapshot_start = frame_start
        result = cam.snapshot(qr_buf, CAMERA_WIDTH, CAMERA_HEIGHT,
                              viewfinder_buf, VIEWFINDER_WIDTH, VIEWFINDER_HEIGHT)
        snapshot_end = utime.ticks_us()

        if not result:
            # print("ERROR: cam.copy_capture() returned False!")
            await ux_show_story('Unable to capture image with camera.', title='Error')
            return None

        draw_start = utime.ticks_us();
        dis.clear()

        dis.draw_header(title)

        dis.image(0, Display.HEADER_HEIGHT, VIEWFINDER_WIDTH,
                  VIEWFINDER_HEIGHT, viewfinder_buf)

        OFFSET = 6
        SIZE = 30
        THICKNESS = 6
        LEFT_X = OFFSET
        RIGHT_X = Display.WIDTH - OFFSET * 2
        Y = Display.HEADER_HEIGHT + OFFSET

        right_label = progress if progress != None else 'SCANNING...'
        dis.draw_footer('BACK', right_label,
                        left_down=input.is_pressed('x'), right_down=input.is_pressed('y'))
        draw_end = utime.ticks_us();

        show_start = utime.ticks_us();
        dis.show()
        show_end = utime.ticks_us();

        # Look for QR codes in the image
        decode_start = utime.ticks_us()
        data = qr.find_qr_codes()
        # print('find_qr_codes() out')
        decode_end = utime.ticks_us()

        # Don't try decoding if we are in Snapshot mode...user is probably using this as a viewfinder
        if not common.snapshot_mode_enabled and data != None:
            # print('data={}'.format(data))

            # See if this looks like a ur code
            ur_start = utime.ticks_us()
            try:
                if qr_decoder == None:
                    # We need to find out what type of QR this is and have the factory make a decoder for us
                    qr_decoder = get_qr_decoder_for_data(data)

                # We should be guaranteed to have a qr_decoder here since basic QR accepts any data format
                qr_decoder.add_data(data)

                # See if there was any error
                error = qr_decoder.get_error()
                if error != None:
                    # print('ERROR: error={}'.format(error))
                    data = None
                    break

                if qr_decoder.is_complete():
                    data = qr_decoder.decode()
                    # print('data: |{}|'.format(data))

                    # Set the last QRType so that signed transactions know what to encode as
                    common.last_scanned_qr_type = qr_decoder.get_data_format()
                    common.last_scanned_ur_prefix = qr_decoder.get_ur_prefix()
                    # print('common.last_scanned_qr_type={}'.format(common.last_scanned_qr_type))
                    # print('common.last_scanned_ur_prefix={}'.format(common.last_scanned_ur_prefix))
                    break

                progress = '{} OF {}'.format(qr_decoder.received_parts(), qr_decoder.total_parts())

            except Exception as e:
                # print('Failed to parse UR!')
                import sys
                # print('Exception: {}'.format(e))
                sys.print_exception(e)
                break

            ur_end = utime.ticks_us()

            # print('ur decode: {}us'.format(ur_end - ur_start))

        # Check for key input to see if we should back out
        key_start = utime.ticks_us()
        event = await input.get_event()
        if event != None:
            key, event_type = event
            if event_type == 'up':
                if key == 'x':
                    data = None
                    break
        key_end = utime.ticks_us()

        frame_count += 1
        now = utime.ticks_us()

        snapshot_ms = (snapshot_end - snapshot_start) / 1000
        draw_ms = (draw_end - draw_start) / 1000
        show_ms = (show_end - show_start) / 1000
        decode_ms = (decode_end - decode_start) / 1000
        key_ms = (key_end - key_start) / 1000
        total_ms = snapshot_ms + draw_ms + show_ms + decode_ms + key_ms
        measured_frame_ms = (now - frame_start) / 1000
        fps = frame_count / ((now - fps_start) / 1000000)

        print_stats = False
        if print_stats and frame_count % 10 == 0:
            print_start = utime.ticks_us()
            print('Frame Stats:')
            print('  {:>3.2f}ms  Snapshot'.format(snapshot_ms))
            print('  {:>3.2f}ms  Draw'.format(draw_ms))
            print('  {:>3.2f}ms  Update to Screen'.format(show_ms))
            print('  {:>3.2f}ms  Decode'.format(decode_ms))
            print('  {:>3.2f}ms  Check keys'.format(key_ms))
            print('  --------')
            print('  {:>3.2f}ms  Total of the above\n'.format(total_ms))

            print('  {:>3.2f}ms  Total measured frame time'.format(measured_frame_ms))
            print('  {:>3.2f}ms  Missing time\n'.format(measured_frame_ms - total_ms))
            print('  {:>3.2f}fps Frame rate'.format(fps))
            print_end = utime.ticks_us()
            print_ms = (print_end - print_start) / 1000

            print('  {:03.1f}ms  Print time'.format(print_ms))

    # Turn off camera after capturing is done!
    cam.disable()


    return data


async def ux_show_story_sequence(stories):
    story_idx = 0

    while 1:
        s = stories[story_idx]

        key = await ux_show_story(
            s.get('msg'),
            title=s.get('title', 'Passport'),
            sensitive=s.get('sensitive', False),
            left_btn=s.get('left_btn', 'BACK'),
            right_btn=s.get('right_btn', 'CONTINUE'),
            center=s.get('center', False),
            center_vertically=s.get('center_vertically', False),
            scroll_label=s.get('scroll_label', None),
            clear_keys=s.get('clear_keys', False))

        if key == 'x':
            if story_idx == 0:
                return 'x'
            else:
                story_idx -= 1

        elif key == 'y':
            if story_idx == len(stories) - 1:
                return 'y'
            else:
                story_idx += 1


async def ux_show_word_list(title, words, heading1='', heading2=None, left_aligned_center=False, left_btn='NO', right_btn='YES'):
    from common import dis

    font = FontSmall
    input = KeyInputHandler(up='xy', down='xy')

    # Figure out horizonal start - we want to center based on the longest word
    x = None
    if left_aligned_center:
        longest_word_width = 0
        for word in words:
            px_width = dis.width(word, font)
            if px_width > longest_word_width:
                longest_word_width = px_width
        x = Display.HALF_WIDTH - (longest_word_width // 2)

    while True:
        system.turbo(True)
        dis.clear()

        dis.draw_header(title)

        y = Display.HEADER_HEIGHT + TOP_MARGIN

        dis.text(None, y, heading1, font=font)
        y += font.leading

        if heading2 != None:
            dis.text(None, y, heading2, font=font)
            y += font.leading * 2
        else:
            y += font.leading

        # Show the word list
        for word in words:
            dis.text(x, y, word, font=font)
            y += font.leading

        dis.draw_footer(left_btn=left_btn,
                        right_btn=right_btn,
                        left_down=input.is_pressed('x'),
                        right_down=input.is_pressed('y'))

        dis.show()
        system.turbo(False)

        while 1:
            event = await input.get_event()
            if event != None:
                break

        key, event_type = event

        if event_type == 'up':
            if key in 'xy':
                return key

async def ux_enter_pin(title, heading='Enter PIN', left_btn='BACK', right_btn='ENTER', left_btn_function=None,
        hide_attempt_counter=False, is_new_pin=False):
    from common import dis, pa
    import pincodes

    SHOW_SECURITY_WORDS_AT_LEN = 4
    MIN_PIN_LEN = 6
    MAX_PIN_LEN = 12
    LARGE_BOX_LIMIT = 6

    POPUP_WIDTH = Display.WIDTH - 40

    font = FontSmall
    input = KeyInputHandler(up='xy0123456789', down='xy0123456789*')

    show_security_words = False
    security_words_confirmed = False
    show_short_pin_message = False
    pin = ''
    pressed = False
    security_label = 'NEXT' if is_new_pin else 'CONFIRM'

    def draw_popup(title, lines, y):
        POPUP_HEIGHT = FontSmall.leading * 4
        popup_x = Display.HALF_WIDTH - POPUP_WIDTH // 2

        dis.draw_rect(popup_x, y, POPUP_WIDTH, FontSmall.leading + 2, border_w=0, fill_color=1)
        dis.draw_rect(popup_x, y+FontSmall.leading, POPUP_WIDTH, POPUP_HEIGHT - FontSmall.leading, border_w=2)

        dis.text(None, y+3, title, font=FontSmall, invert=True)
        y += int(FontSmall.leading * 1.5)

        for line in lines:
            dis.text(None, y, line, font=FontSmall)
            y += FontSmall.leading

        return y

    def draw_security_words_popup(title1, title2, words, y):
        POPUP_HEIGHT = FontSmall.leading * 2
        popup_x = Display.HALF_WIDTH - POPUP_WIDTH // 2

        dis.draw_rect(popup_x, y, POPUP_WIDTH, FontSmall.leading * 2 + 2, border_w=0, fill_color=1)
        dis.draw_rect(popup_x, y+FontSmall.leading*2, POPUP_WIDTH, POPUP_HEIGHT, border_w=2)

        dis.text(None, y+3, title1, font=FontSmall, invert=True)
        y += int(FontSmall.leading)-1
        dis.text(None, y+3, title2, font=FontSmall, invert=True)
        y += int(FontSmall.leading * 1.5) + 2

        dis.text(None, y, words, font=FontSmall)

        return y

    while True:
        system.turbo(True)

        dis.clear()
        dis.draw_header(title)

        y = dis.HEADER_HEIGHT + 8
        dis.text(None, y, heading, font=FontSmall)
        y += FontSmall.leading - 2

        num_filled = len(pin)
        # print('num_filled={} pressed={}'.format(num_filled, pressed))
        if (num_filled < LARGE_BOX_LIMIT) or (num_filled == LARGE_BOX_LIMIT and not pressed):
            empty_box = 'pw_empty_box_lg'
            pressed_box = 'pw_pressed_box_lg'
            filled_box = 'pw_filled_box_lg'
            MAX_PIN_BOXES_TO_DISPLAY = LARGE_BOX_LIMIT
            y += 3
        else:
            empty_box = 'pw_empty_box_sm'
            pressed_box = 'pw_pressed_box_sm'
            filled_box = 'pw_filled_box_sm'
            MAX_PIN_BOXES_TO_DISPLAY = MAX_PIN_LEN
            y += 14

        PIN_BOX_W, PIN_BOX_H = dis.icon_size(empty_box)
        PIN_BOX_SPACING = (dis.WIDTH - PIN_BOX_W *
                           MAX_PIN_BOXES_TO_DISPLAY) // (MAX_PIN_BOXES_TO_DISPLAY + 1)
        PIN_BOX_ADVANCE = PIN_BOX_W + PIN_BOX_SPACING

        if num_filled >= 1:
            total_width = (num_filled * PIN_BOX_W) + ((num_filled - 1) * PIN_BOX_SPACING)
        else:
            total_width = 0
        # print('total_width =  {}'.format(total_width))

        if pressed and num_filled > 0:
            total_width += PIN_BOX_SPACING + PIN_BOX_W
            # print('total_width increased to = {}'.format(total_width))

        # Have a width when PIN is empty and nothing pressed
        if total_width == 0:
            total_width = PIN_BOX_W

        x = Display.HALF_WIDTH - (total_width // 2)
        for _idx in range(num_filled):
            dis.icon(x, y, filled_box)
            x += PIN_BOX_ADVANCE

        if pressed:
            # print('pressed case')
            dis.icon(x, y, pressed_box)
        elif len(pin) == 0:
            # print('draw empty box')
            dis.icon(x, y, empty_box)

        # Show remaining attempts if not hidden and if there was at least one failure
        if not hide_attempt_counter and pa.attempts_left < pa.max_attempts:
            dis.text(None, Display.HEIGHT - Display.HEADER_HEIGHT - FontTiny.leading + 3, '{} attempts remaining'.format(pa.attempts_left), font=FontTiny)

        # Since box size can vary, we advance a constant here and center the box in that space based on height above
        y = 128

        if show_short_pin_message:
            y = draw_popup('Info', ['PIN must be at','least 6 digits'], y)

        # Show the security word list if key is held down
        elif show_security_words:
            if not security_words:
                try:
                    security_words = pincodes.PinAttempt.anti_phishing_words(pin[0:SHOW_SECURITY_WORDS_AT_LEN].encode())
                except Exception as e:
                    security_words = ['Unable to','retrieve']
                    # print("Exception getting anti-phishing words: {}".format(e))

            if is_new_pin:
                y = draw_security_words_popup('Remember these', 'Security Words', '  '.join(security_words), y)
            else:
                y = draw_security_words_popup('Recognize these', 'Security Words?', '  '.join(security_words), y)
        else:
            # Clear them so we reload next time (numbers may have changed)
            security_words = None


        dis.draw_footer(left_btn, security_label if show_security_words else right_btn, input.is_pressed('x'), input.is_pressed('y'))

        dis.show()
        system.turbo(False)

        # Interaction
        while True:
            event = await input.get_event()

            if event != None:
                break

        key, event_type = event

        if event_type == 'down':
            # Hide the short pin message as soon as any other key is pressed
            show_short_pin_message = False

            if key == '*':
                if pin and len(pin) > 0:
                    pin = pin[:-1]

                if len(pin) <= SHOW_SECURITY_WORDS_AT_LEN:
                    security_words_confirmed = False

            elif key in '0123456789':
                if not show_security_words:
                    if len(pin) < MAX_PIN_LEN:
                        pressed = True

        elif event_type == 'up':
            if key == 'x':
                return None

            elif key == 'y':
                if show_security_words:
                    show_security_words = False
                    security_words_confirmed = True
                    continue

                elif len(pin) < MIN_PIN_LEN:
                    # they haven't given enough yet
                    show_short_pin_message = True
                    continue
                else:
                    # print('RETURNING PIN = {}'.format(pin))
                    return pin

            elif key in '0123456789':
                if not show_security_words:
                    pressed = False

                    # Add the number to the PIN or replace the last digit
                    if len(pin) == MAX_PIN_LEN:
                        pass
                    else:
                        pin += key

        # Decide whether to show the security words
        if not security_words_confirmed:
            show_security_words = len(pin) == SHOW_SECURITY_WORDS_AT_LEN


async def ux_shutdown():
    from common import system
    confirm = await ux_confirm("Are you sure you want to shutdown?", center=True, center_vertically=True)
    if confirm:
        # print('SHUTTING DOWN!')
        system.shutdown()
        return

Keypad = [
    ['1', '2', '3'],
    ['4', '5', '6'],
    ['7', '8', '9'],
    ['*', '0', '#'],
]

KeyState = {
    '1': {'pressed': False, 'released': False},
    '2': {'pressed': False, 'released': False},
    '3': {'pressed': False, 'released': False},
    '4': {'pressed': False, 'released': False},
    '5': {'pressed': False, 'released': False},
    '6': {'pressed': False, 'released': False},
    '7': {'pressed': False, 'released': False},
    '8': {'pressed': False, 'released': False},
    '9': {'pressed': False, 'released': False},
    '0': {'pressed': False, 'released': False},
    '*': {'pressed': False, 'released': False},
    '#': {'pressed': False, 'released': False},
    'l': {'pressed': False, 'released': False},
    'r': {'pressed': False, 'released': False},
    'u': {'pressed': False, 'released': False},
    'd': {'pressed': False, 'released': False},
    'x': {'pressed': False, 'released': False},
    'y': {'pressed': False, 'released': False},
}

async def ux_keypad_test(*a):
    from common import dis
    from display import FontSmall

    SIDE_MARGIN = 20
    NUMKEY_HGAP = 10
    NUMKEY_VGAP = 5
    KEY_WIDTH = ((Display.WIDTH - (SIDE_MARGIN*2) - (2 * NUMKEY_HGAP)) // 3)
    KEY_HEIGHT = 24

    font = FontSmall

    # Hold x or y for one second to exit keypad test
    input = KeyInputHandler(down='1234567890*#rludxy', up='1234567890*#rludxy', long='xy',
        long_duration=1000)

    def draw_key(key, key_x, key_y, small=False, vertical=False):
        state = KeyState.get(key)
        pressed = state.get('pressed')
        released = state.get('released')
        w = KEY_WIDTH if not small else KEY_WIDTH // 2
        dis.draw_rect(key_x, key_y,
            w, KEY_HEIGHT, 4 if pressed else 2,
            fill_color=1 if released else 0 , border_color=1)
        if not small:
            dis.text(key_x + 22, key_y + 1, key, invert=1 if released else 0)
        else:
            dis.text(key_x + 9, key_y + 1, key, invert=1 if released else 0)

    while True:
        # Redraw
        system.turbo(True)
        dis.clear()

        dis.draw_header('Keypad Test')

        # Draw the title
        y = Display.HEADER_HEIGHT + TEXTBOX_MARGIN
        dis.text(None, y, 'Press Each Key')
        y += font.leading

        # Draw the select and back buttons
        draw_key('u', Display.HALF_WIDTH - KEY_WIDTH // 4, y, small=True)
        draw_key('d', Display.HALF_WIDTH - KEY_WIDTH // 4, y + NUMKEY_VGAP + KEY_HEIGHT, small=True)
        draw_key('l', Display.HALF_WIDTH - KEY_WIDTH // 4 - NUMKEY_HGAP - KEY_WIDTH//2, y + (NUMKEY_VGAP + KEY_HEIGHT)//2, small=True)
        draw_key('r', Display.HALF_WIDTH - KEY_WIDTH // 4 + NUMKEY_HGAP + KEY_WIDTH//2, y + (NUMKEY_VGAP + KEY_HEIGHT)//2, small=True)
        draw_key('x', SIDE_MARGIN, y + (NUMKEY_VGAP + KEY_HEIGHT)//2, small=True)
        draw_key('y', Display.WIDTH - SIDE_MARGIN - KEY_WIDTH//2, y + (NUMKEY_VGAP + KEY_HEIGHT)//2, small=True)

        y += 80

        # Draw the Numeric keypad grid
        for row in range(len(Keypad)):
            for col in range(len(Keypad[row])):
                key = Keypad[row][col]
                key_x = SIDE_MARGIN + (col *(KEY_WIDTH + NUMKEY_HGAP))
                key_y = y + row * (KEY_HEIGHT + NUMKEY_VGAP)
                draw_key(key, key_x, key_y)

        dis.draw_footer('BACK', 'NEXT', input.is_pressed('x'), input.is_pressed('y'))

        dis.show()
        system.turbo(False)

        # Wait for key inputs
        event = None
        while True:
            event = await input.get_event()
            if event != None:
                break

        if event != None:
            key, event_type = event
            state = KeyState.get(key)

            # Check for footer button actions first
            if event_type == 'down':
                state['pressed'] = True

            if event_type == 'up':
                state['released'] = True

            if event_type == 'long_press':
                return key


async def ux_draw_alignment_grid(title='Align Screen'):
    from common import dis
    from display import FontSmall

    NUM_VERTICAL_LINES = 7
    NUM_HORIZONTAL_LINES = 14
    GRID_WIDTH =  Display.WIDTH // (NUM_VERTICAL_LINES + 1)
    GRID_HEIGHT = Display.HEIGHT // (NUM_HORIZONTAL_LINES + 1)
    # print('GRID_WIDTH={}'.format(GRID_WIDTH))
    # print('GRID_HEIGHT={}'.format(GRID_HEIGHT))

    font = FontSmall

    input = KeyInputHandler(down='xy', up='xy')
    pressed = {}

    while True:
        # Redraw
        system.turbo(True)
        dis.clear()

        # dis.draw_header(title)
        # dis.draw_footer('BACK', 'NEXT', input.is_pressed('x'), input.is_pressed('y'))

        # Draw an inset rectangle around the outside
        dis.draw_rect(2, 2, Display.WIDTH-4, Display.HEIGHT-4, 1, fill_color=0, border_color=1)

        # Draw vertical lines
        for col in range(NUM_VERTICAL_LINES):
            x = (col + 1) * GRID_WIDTH
            dis.vline(x)

        # Draw Horizontal lines
        for row in range(NUM_HORIZONTAL_LINES):
            y = (row + 1) * GRID_HEIGHT
            dis.hline(y)

        dis.show()
        system.turbo(False)

        # Wait for key inputs
        event = None
        while True:
            event = await input.get_event()
            if event != None:
                break

        if event != None:
            key, event_type = event
            state = KeyState.get(key)

            # Exit if key pressed
            if event_type == 'down':
                pressed[key] = True

            if event_type == 'up':
                # We may have come to this screen from a longpress on the keypad test screen
                # in which case an up will come that we DON'T want to act on. The local input
                # won't have transitioned the key to pressed state yet, so use this to differentiate.
                if key in pressed:
                    return key
