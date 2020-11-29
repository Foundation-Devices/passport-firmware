# SPDX-FileCopyrightText: 2020 Foundation Devices, Inc.  <hello@foundationdevices.com>
# SPDX-License-Identifier: GPL-3.0-or-later
#
# SPDX-FileCopyrightText: 2018 Coinkite, Inc.  <coldcardwallet.com>
# SPDX-License-Identifier: GPL-3.0-only
#
# (c) Copyright 2018 by Coinkite Inc. This file is part of Coldcard <coldcardwallet.com>
# and is covered by GPLv3 license found in COPYING.
#
# display.py - Screen rendering and brightness control
#

import foundation
from foundation import LCD
from foundation import Backlight
from foundation import Powermon
import framebuf
import uzlib
from graphics import Graphics
from passport_fonts import FontLarge, FontSmall, FontTiny, lookup
from uasyncio import sleep_ms


class Display:

    WIDTH = 230
    # Note for the Sharp display the frame buffer width has to be 240 to draw properly
    FB_WIDTH = 240
    LINE_SIZE_BYTES = 30
    HALF_WIDTH = WIDTH // 2
    HEIGHT = 303
    HALF_HEIGHT = HEIGHT // 2
    HEADER_HEIGHT = 38
    FOOTER_HEIGHT = 34
    SCROLLBAR_WIDTH = 6

    BATTERY_MAX = 3000
    BATTERY_MIN = 2500

    BYTES_PER_STRIP = WIDTH
    BUF_SIZE = BYTES_PER_STRIP * ((HEIGHT + 7) // 8)

    def __init__(self):
        # Setup frame buffer, in show we will call scrn.update(self.dis) to show the buffer
        self.scrn = LCD()

        self.dis = framebuf.FrameBuffer(bytearray(
            self.LINE_SIZE_BYTES * self.HEIGHT), self.FB_WIDTH, self.HEIGHT, framebuf.MONO_HLSB)

        self.backlight = Backlight()

        self.powermon = Powermon()
        self.v_avg = [3000 for i in range(10)]

        self.clear()
        self.show()

    def clear(self, invert=0):
        self.dis.fill(invert)

    def clear_rect(self, x, y, w, h):
        self.dis.fill_rect(x, y, w, h, 0)

    def show(self):
        self.scrn.update(self.dis)

    def hline(self, y, invert=1):
        self.dis.line(0, y, self.WIDTH, y, invert)

    def vline(self, x, invert=1):
        self.dis.line(x, 0, x, self.HEIGHT, invert)

    def hsegment(self, x1, x2, y, col):
        self.dis.line(x1, y, x2, y, col)

    def vsegment(self, x, y1, y2, col):
        self.dis.line(x, y1, x, y2, col)

    # Draw a filled rectangle with a border of a specified thickness
    def draw_rect(self, x, y, w, h, border_w, fill_color=0, border_color=None):
        if border_color == None:
            border_color = 1 if fill_color == 0 else 0

        # print("draw_rect() x={} y={} w={} h={} fill={} border={}".format(
        #     x, y, w, h, fill_color, border_color))
        if border_w > 0:
            self.dis.fill_rect(x, y, w, h, border_color)
        self.dis.fill_rect(x + border_w, y + border_w,
                           w - border_w * 2, h - border_w * 2, fill_color)

    def set_pixel(self, x, y, col):
        self.dis.fill_rect(x, y, 1, 1, col)

    def progress_bar(self, percent):
        # Horizontal progress bar
        # takes 0.0 .. 1.0 as fraction of doneness
        percent = max(0, min(1.0, percent))
        side_space = 10
        bottom_space = 40
        bar_height = 9
        bw = 2
        bw2 = bw * 2
        width = self.WIDTH - (side_space * 2) - bw2

        self.dis.fill_rect(side_space, self.HEIGHT - bottom_space, width, bar_height, 1)
        self.dis.fill_rect(side_space + bw,     self.HEIGHT - bottom_space + bw, width - bw2, bar_height - bw2, 0)
        self.dis.fill_rect(side_space + bw + 1, self.HEIGHT - bottom_space + bw + 1, int((width - bw2 - 2) * percent), bar_height - bw2 - 2, 1)

    def progress_bar_show(self, percent):
        self.progress_bar(percent)

    def set_brightness(self, val):
        # normal = 128, max brightness=254, off <= 10
        # This is be done with the backlight object (10 to 254 for val)
        self.backlight.intensity(val)

    def fullscreen(self, msg, percent=None, line2=None):
        # show a simple message "fullscreen".
        headingFont = FontSmall
        subheadingFont = FontTiny
        self.clear()
        if line2:
            y = self.HALF_HEIGHT - (headingFont.height // 2)
            self.text(None, y, msg, font=headingFont)
            y += headingFont.leading
            self.text(None, y, line2, font=subheadingFont)
        else:
            y = self.HALF_HEIGHT - (headingFont.height // 2)
            self.text(None, y, msg, font=headingFont)
        if percent is not None:
            self.progress_bar(percent)
        self.show()

    def splash(self):
        # Display a splash screen with some version numbers
        self.clear()
        self.icon(None, self.HALF_HEIGHT - 80, 'splash')

        # from version import get_mpy_version
        #         timestamp, label, *_ = get_mpy_version()

        timestamp, label, *_ = ('11/21/2020', '0.1.0', None)

        # Show version and timestamp info
        y = self.HEIGHT - FontTiny.leading - 4
        self.text(8,  y, 'Version ' + label, font=FontTiny)
        self.text(-8, y, timestamp, font=FontTiny)

        self.show()

    def width(self, msg, font):
        return sum(lookup(font, ord(ch)).advance for ch in msg)

    def icon_size(self, name):
        # see graphics.py (auto generated file) for names
        w, h, _bw, _wbits, _data = getattr(Graphics, name)
        return (w, h)

    def icon(self, x, y, name, invert=0):
        # see graphics.py (auto generated file) for names
        w, h, bw, wbits, data = getattr(Graphics, name)

        if wbits:
            data = uzlib.decompress(data, wbits)

        if invert:
            data = bytearray(i ^ 0xff for i in data)

        gly = framebuf.FrameBuffer(bytearray(data), w, h, framebuf.MONO_HLSB)

        if x is None:
            x = self.HALF_WIDTH - (w // 2)
        if y is None:
            y = self.HALF_HEIGHT - (h // 2)

        self.dis.blit(gly, x, y, invert)

        return (w, h)

    def image(self, x, y, w, h, img_data, invert=0):
        gly = framebuf.FrameBuffer(
            bytearray(img_data), w, h, framebuf.MONO_HLSB)

        if x is None:
            x = self.HALF_WIDTH - (w // 2)
        if y is None:
            y = self.HALF_HEIGHT - (h // 2)

        self.dis.blit(gly, x, y, invert)

        return (w, h)

    def char_width(self, ch, font=FontSmall):
        fn = lookup(font, ord(ch))
        return fn.advance

    def text_input(self, x, y, msg, font=FontSmall, invert=0, cursor_pos=None, visible_spaces=False, fixed_spacing=None, cursor_shape='line', max_chars_per_line=0):
        if max_chars_per_line > 0:
            # Split text into multiple lines and draw them separately
            lines = [msg[i:i+max_chars_per_line]
                     for i in range(0, len(msg), max_chars_per_line)]

            for line in lines:
                self.text(x, y, line, font, invert, cursor_pos,
                          visible_spaces, fixed_spacing, cursor_shape)
                y += font.leading
                cursor_pos -= max_chars_per_line

        else:
            self.text(x, y, msg, font, invert, cursor_pos,
                      visible_spaces, fixed_spacing, cursor_shape)

    def text(self, x, y, msg, font=FontSmall, invert=0, cursor_pos=None, visible_spaces=False, fixed_spacing=None, cursor_shape='line'):
        # Draw at x,y (top left corner of first letter)
        # using font. Use invert=1 to get reverse video

        if x is None or x < 0:
            # center/rjust
            w = self.width(msg, font)
            if x == None:
                x = max(0, self.HALF_WIDTH - (w // 2))
            else:
                # measure from right edge (right justify)
                x = max(0, self.WIDTH - w + 1 + x)

        if y < 0:
            # measure up from bottom edge
            y = self.HEIGHT - font.leading + 1 + y

            return x + (len(msg) * 8)

        curr_pos = 0
        for ch in msg:
            if visible_spaces and ch == ' ':
                ch = '_'  # TODO: Replace this with a difference character code that is not an ASCII symbol
            fn = lookup(font, ord(ch))
            if fn is None:
                # use last char in font as error char for junk we don't
                # know how to render
                fn = font.lookup(font.code_range.stop)
            # TODO: This is always the same per font - can reuse this buffer if there are performance issues
            bits = bytearray(fn.w * fn.h)
            bits[0:len(fn.bits)] = fn.bits
            if invert:
                bits = bytearray(i ^ 0xff for i in bits)
            gly = framebuf.FrameBuffer(bits, fn.w, fn.h, framebuf.MONO_HLSB)

            advance = fn.advance
            adjust = 0
            if fixed_spacing != None:
                # Adjust x to center the character within the fixed spacing
                adjust = (fixed_spacing - fn.advance) // 2
                x += adjust
                advance = fixed_spacing - adjust

            if cursor_pos != None and curr_pos == cursor_pos:
                # Draw the block cursor
                if cursor_shape == 'block':
                    # Invert the character under the block cursor if necessary
                    _invert = 0 if invert else 1
                    if _invert:
                        bits = bytearray(i ^ 0xff for i in bits)
                        gly = framebuf.FrameBuffer(
                            bits, fn.w, fn.h, framebuf.MONO_HLSB)

                    # Draw block
                    self.dis.fill_rect(
                        x - adjust, y, fixed_spacing, font.leading, _invert)

                    # Draw the character
                    self.dis.blit(gly, x + fn.x, y + font.ascent -
                                  fn.h - fn.y, _invert)
                else:
                    # Draw the line cursor
                    self.dis.fill_rect(x, y, 1, font.leading - 4, 1)
                    self.dis.blit(gly, x + fn.x, y +
                                  font.ascent - fn.h - fn.y, invert)
            else:
                # Just draw the character normally
                self.dis.blit(gly, x + fn.x, y +
                              font.ascent - fn.h - fn.y, invert)

            x += advance
            curr_pos += 1

        if cursor_shape == 'line' and cursor_pos == len(msg):
            # Draw the line cursor at the end if positioned at the end
            self.dis.fill_rect(x, y, 1, font.leading, 1)

        return x

    def scrollbar(self, scroll_percent, content_to_height_ratio):
        # Draw scrollbar only if the content doesn't fit on screen
        if content_to_height_ratio < 1:
            sb_width = 7
            sb_left = self.WIDTH - sb_width

            # Draw a rectangle background for the entire thing
            # NOTE: We go up one pixel to cover the header divider (looks better)
            self.dis.fill_rect(sb_left, self.HEADER_HEIGHT - 2,
                               sb_width, self.HEIGHT - self.HEADER_HEIGHT + 2, 1)
            self.dis.fill_rect(sb_left+1, self.HEADER_HEIGHT - 2,
                               sb_width - 2, self.HEIGHT - self.HEADER_HEIGHT + 2, 0)

            # Draw the scrollbar track
            self.icon(sb_left + 1, self.HEADER_HEIGHT - 3, 'scrollbar')

            # Draw the thumb in the right position
            mm = self.HEIGHT - self.HEADER_HEIGHT - self.FOOTER_HEIGHT + 4
            pos = min(int(mm * scroll_percent), mm) + self.HEADER_HEIGHT - 2
            thumb_height = min(int(mm * content_to_height_ratio), mm)
            thumb_width = sb_width - 2
            thumb_left = sb_left + 1
            self.dis.fill_rect(thumb_left, pos, thumb_width, thumb_height, 0)

            # Round the thumb corners
            self.set_pixel(thumb_left, pos, 1)
            self.set_pixel(thumb_left + 4, pos, 1)
            self.set_pixel(thumb_left, pos + thumb_height - 1, 1)
            self.set_pixel(thumb_left + 4, pos + thumb_height - 1, 1)

            # Draw separator lines above and below the thumb
            if scroll_percent > 0:
                self.hsegment(thumb_left, thumb_left + thumb_width, pos - 1, 1)

            if scroll_percent < 1:
                self.hsegment(thumb_left, thumb_left +
                              thumb_width, pos + thumb_height, 1)

            # Draw a thumb pattern in the middle
            notch_height = 3
            notch_width = 3

            # Reserve 3 pixels at the top and bottom (the 6 below)
            num_notches = min((thumb_height - 6) // notch_height, 9)

            notch_y = pos + (thumb_height // 2) - \
                (((num_notches - 1) * notch_height) // 2) - 1
            for i in range(num_notches):
                self.hsegment(thumb_left + 1, thumb_left +
                              notch_width, notch_y, 1)
                notch_y += notch_height

    def draw_header(self, title='Passport', wordmark=False, left_text=None):
        LEFT_MARGIN = 11
        title_y = 8

        # Fill background
        self.dis.fill_rect(0, 0, self.WIDTH, self.HEADER_HEIGHT, 0)
        self.hline(self.HEADER_HEIGHT - 4, 1)
        self.hline(self.HEADER_HEIGHT - 3, 1)
        self.hline(self.HEADER_HEIGHT - 2, 0)
        self.hline(self.HEADER_HEIGHT - 1, 0)

        # Title
        self.text(None, title_y, title, font=FontSmall, invert=0)

        # Left text
        if left_text != None:
            self.text(LEFT_MARGIN, title_y, left_text,
                      font=FontSmall, invert=0)

        # Get battery level and shift into array
        # for i in range(10):
        #     self.v_avg[i] = self.v_avg[i+1]
        for i in range(9,0,-1):
            self.v_avg[i] = self.v_avg[i-1]
        (current, voltage) = self.powermon.read()
        self.v_avg[0] = round(voltage * (44.7 + 22.1) / 44.7) # Voltage divider on PCB

        # Calculate average of array
        voltage_average = 0
        for i in range(10):
            voltage_average += self.v_avg[i]
            # print('v_avg[{}] = {}'.format(i, self.v_avg[i]))
        voltage_average = voltage_average / 10
        # print('voltage_average = {}'.format(voltage_average))

        # Normalize to battery operating range
        batteryLife = 100 # round(100 * (voltage_average - self.BATTERY_MIN) / (self.BATTERY_MAX - self.BATTERY_MIN))
        # print('batteryLife = {}'.format(batteryLife))
        
        battery_icon = self.get_battery_icon(batteryLife)
        batt_w, batt_h = self.icon_size(battery_icon)
        self.icon(self.WIDTH - batt_w - 11, ((self.HEADER_HEIGHT - 4) //
                                            2 - batt_h // 2) + 2, battery_icon, invert=0)

    def draw_button(self, x, y, w, h, label, font=FontTiny, invert=0):
        self.draw_rect(x, y, w, h, border_w=1,
                       fill_color=1 if invert else 0, border_color=1)

        label_w = self.width(label, font)
        x = x + (w // 2 - label_w // 2)
        y = y + (h // 2 - font.ascent // 2)
        self.text(x, y, label, font, invert)

    def draw_footer(self, left_btn='', right_btn='', left_down=False, right_down=False):
        btn_w = self.WIDTH // 2

        # Ignore up/down state if there is no label
        if left_btn == '':
            left_down = False

        if right_btn == '':
            right_down = False

        # Draw left button
        self.draw_button(-1, self.HEIGHT - self.FOOTER_HEIGHT + 1, btn_w + 1,
                         self.FOOTER_HEIGHT, left_btn, invert=1 if left_down else 0)

        # Draw right button
        self.draw_button(btn_w - 1, self.HEIGHT - self.FOOTER_HEIGHT + 1,
                         btn_w + 2, self.FOOTER_HEIGHT, right_btn, invert=1 if right_down else 0)

    def get_battery_icon(self, level):
        if level > 90:
            return 'battery_100'
        elif level >= 70:
            return 'battery_75'
        elif level >= 50:
            return 'battery_50'
        elif level >= 30:
            return 'battery_25'
        elif level >= 10:
            return 'battery_low'

    
