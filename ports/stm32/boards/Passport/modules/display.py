# SPDX-FileCopyrightText: 2020 Foundation Devices, Inc. <hello@foundationdevices.com>
# SPDX-License-Identifier: GPL-3.0-or-later
#
# SPDX-FileCopyrightText: 2018 Coinkite, Inc. <coldcardwallet.com>
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
from passport_fonts import FontSmall, FontTiny, lookup
from uasyncio import sleep_ms
from common import system

class Display:

    WIDTH = 230
    # Note for the Sharp display the frame buffer width has to be 240 to draw properly
    FB_WIDTH = 240
    LINE_SIZE_BYTES = 30
    HALF_WIDTH = WIDTH // 2
    HEIGHT = 303
    HALF_HEIGHT = HEIGHT // 2
    HEADER_HEIGHT = 40
    FOOTER_HEIGHT = 32
    SCROLLBAR_WIDTH = 8

    BATTERY_MAX = 3000
    BATTERY_MIN = 2500

    BYTES_PER_STRIP = WIDTH
    BUF_SIZE = BYTES_PER_STRIP * ((HEIGHT + 7) // 8)

    def __init__(self):
        # Setup frame buffer, in show we will call scrn.update(self.dis) to show the buffer
        self.dis = framebuf.FrameBuffer(bytearray(
            self.LINE_SIZE_BYTES * self.HEIGHT), self.FB_WIDTH, self.HEIGHT, framebuf.MONO_HLSB)

        self.scrn = LCD(self.dis)

        self.backlight = Backlight()

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

    def set_brightness(self, val):
        # 0-100 are valid
        if val >= 0 and val <= 100:
            self.backlight.intensity(val)

    def fullscreen(self, msg, percent=None, line2=None):
        system.turbo(True)

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
        system.turbo(False)

    def splash(self, message=None, progress=None):
        system.turbo(True)

        # Display a splash screen with some version numbers
        self.clear()
        logo_w, logo_h = self.icon_size('splash')
        self.icon(None, self.HALF_HEIGHT - logo_h//2, 'splash')
        if message != None:
            y = self.HEIGHT - 68  # Same position as in the bootloader splash
            self.text(None,  y, message, font=FontSmall)

        if progress != None:
            self.progress_bar(progress)
        self.show()
        system.turbo(False)

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
            # TODO: Improve this by splitting lines based on actual pixel widths instead of max_chars_per_line
            # Split text into multiple lines and draw them separately
            lines = [msg[i:i+max_chars_per_line]
                     for i in range(0, len(msg), max_chars_per_line)]

            # Special case to draw cursor by itself when no text is entered yet
            if len(lines) == 0:
                self.text(x, y, '', font, invert, cursor_pos,
                          visible_spaces, fixed_spacing, cursor_shape)
            else:
                for line in lines:
                    self.text(x, y, line, font, invert, cursor_pos,
                              visible_spaces, fixed_spacing, cursor_shape)
                    y += font.leading
                    cursor_pos -= max_chars_per_line

        else:
            self.text(x, y, msg, font, invert, cursor_pos,
                      visible_spaces, fixed_spacing, cursor_shape)

    def text(self, x, y, msg, font=FontSmall, invert=0, cursor_pos=None, visible_spaces=False, fixed_spacing=None, cursor_shape='line', scrollbar_visible=False):
        # Draw at x,y (top left corner of first letter)
        # using font. Use invert=1 to get reverse video

        if x is None or x < 0:
            # center/rjust
            w = self.width(msg, font)
            if x == None:
                x = max(0, self.HALF_WIDTH - (w // 2))
                if scrollbar_visible:
                    x = x - self.SCROLLBAR_WIDTH // 2
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
                ch = '_'
            fn = lookup(font, ord(ch))
            if fn is None:
                # Use last char in font as error char for junk we don't know how to render
                fn = font.lookup(font.code_range.stop)
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
            # We add one for the left border, but everything else is based on the constant
            sb_left = self.WIDTH - (self.SCROLLBAR_WIDTH + 1)

            # Draw a rectangle background for the entire thing
            # NOTE: We go up one pixel to cover the header divider (looks better)
            self.dis.fill_rect(sb_left, self.HEADER_HEIGHT - 2,
                               self.SCROLLBAR_WIDTH + 1, self.HEIGHT - self.HEADER_HEIGHT + 2, 1)
            self.dis.fill_rect(sb_left+1, self.HEADER_HEIGHT - 2,
                               self.SCROLLBAR_WIDTH - 1, self.HEIGHT - self.HEADER_HEIGHT + 2, 0)

            # Draw the scrollbar track
            bg_w, bg_h = self.icon_size('scrollbar')
            for i in range((self.SCROLLBAR_WIDTH + bg_w//2) // bg_w):
                self.icon(sb_left + (bg_w * i) + 1, self.HEADER_HEIGHT - 3, 'scrollbar')

            # Draw the thumb in the right position
            mm = self.HEIGHT - self.HEADER_HEIGHT - self.FOOTER_HEIGHT + 4
            pos = min(int(mm * scroll_percent), mm) + self.HEADER_HEIGHT - 2
            thumb_height = min(int(mm * content_to_height_ratio), mm)
            thumb_width = self.SCROLLBAR_WIDTH - 1
            thumb_left = sb_left + 1
            self.dis.fill_rect(thumb_left, pos, thumb_width, thumb_height, 0)

            # Round the thumb corners
            self.set_pixel(thumb_left, pos, 1)
            self.set_pixel(thumb_left + self.SCROLLBAR_WIDTH - 2, pos, 1)
            self.set_pixel(thumb_left, pos + thumb_height - 1, 1)
            self.set_pixel(thumb_left + self.SCROLLBAR_WIDTH - 2, pos + thumb_height - 1, 1)

            # Draw separator lines above and below the thumb
            if scroll_percent > 0:
                self.hsegment(thumb_left, thumb_left + thumb_width, pos - 1, 1)

            if scroll_percent < 1:
                self.hsegment(thumb_left, thumb_left +
                              thumb_width, pos + thumb_height, 1)

            # Draw a thumb pattern in the middle
            notch_height = 3
            notch_width = self.SCROLLBAR_WIDTH - 3

            # Reserve 3 pixels at the top and bottom (the 6 below)
            num_notches = min((thumb_height - 6) // notch_height, 9)

            notch_y = pos + (thumb_height // 2) - \
                (((num_notches - 1) * notch_height) // 2) - 1
            for i in range(num_notches):
                self.hsegment(thumb_left + 1, thumb_left +
                              notch_width, notch_y, 1)
                notch_y += notch_height

    def draw_header(self, title='Passport', wordmark=False, left_text=None):
        import stash
        import common
        from utils import truncate_string_to_width
        from common import battery_level, battery_voltage, demo_active, demo_count
        LEFT_MARGIN = 11
        title_y = 10

        # Fill background
        self.dis.fill_rect(0, 0, self.WIDTH, self.HEADER_HEIGHT, 0)
        self.hline(self.HEADER_HEIGHT - 4, 1)
        self.hline(self.HEADER_HEIGHT - 3, 1)
        self.hline(self.HEADER_HEIGHT - 2, 0)
        self.hline(self.HEADER_HEIGHT - 1, 0)

        # Title - restrict length so it doesn't overwrite battery or left text
        MAX_HEADER_TITLE_WIDTH = self.WIDTH - 68
        title = truncate_string_to_width(title, FontSmall, MAX_HEADER_TITLE_WIDTH )
        self.text(None, title_y, title, font=FontSmall, invert=0)

        # Left text
        left_text_y = title_y + 5
        if demo_active:
            left_text = '{}'.format(demo_count)

        if common.snapshot_mode_enabled:
            self.text(6, left_text_y, 'Cam', font=FontTiny, invert=0)
        elif common.enable_battery_mon:
            # Draw some stats rather than other left_text
            v = str(int(battery_voltage))
            p ='{}%'.format(int(battery_level))
            self.text(6, title_y - 5, v, font=FontTiny, invert=0)
            self.text(6, title_y + 9, p, font=FontTiny, invert=0)

        elif left_text != None:
            self.text(LEFT_MARGIN, left_text_y, left_text, font=FontTiny, invert=0)
        else:
            left_x = 2
            if stash.bip39_passphrase:
                pass_w, pass_h = self.icon_size('passphrase_icon')
                self.icon(4, ((self.HEADER_HEIGHT - 4) // 2 - pass_h // 2) + 2, 'passphrase_icon', invert=0)
                left_x += pass_w + 2

        battery_icon = self.get_battery_icon(battery_level)
        batt_w, batt_h = self.icon_size(battery_icon)
        self.icon(self.WIDTH - batt_w - 6, ((self.HEADER_HEIGHT - 4) //
                                            2 - batt_h // 2) + 3, battery_icon, invert=0)

    def draw_button(self, x, y, w, h, label, font=FontTiny, invert=0):
        self.draw_rect(x, y, w, h, border_w=1,
                       fill_color=1 if invert else 0, border_color=1)

        label_w = self.width(label, font)
        x = x + (w // 2 - label_w // 2)
        y = y + (h // 2 - font.ascent // 2)
        self.text(x, y - 1, label, font, invert)

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
        else:
            return 'battery_low'

    # Save a screenshot in PPM (Portable Pixel Map) -- a very simple format
    # that doesn't need a big library to be included.
    def screenshot(self):
        from files import CardSlot
        from noise_source import NoiseSource
        from utils import bytes_to_hex_str
        import common

        common.system.turbo(True)
        white = b'\xEE'
        black = b'\x00'

        fname_rnd = bytearray(4)

        # Just use MCU nois source as it's faster and this is not a security-related use
        common.noise.random_bytes(fname_rnd, NoiseSource.MCU)

        try:
            with CardSlot() as card:
                # Need to use get_sd_root() here to prefix the /sd/ or we get EPERM errors
                fname = '{}/screenshot-{}.pgm'.format(card.get_sd_root(), bytes_to_hex_str(fname_rnd))
                print('Saving screenshot to: {}'.format(fname))

                with open(fname, 'wb') as fd:
                    hdr = '''P5
# Created by Passport
{} {}
255\n'''.format(self.WIDTH, self.HEIGHT)

                    # Write the header
                    fd.write(bytes(hdr, 'utf-8'))

                    # Write the pixels
                    for y in range(self.HEIGHT):
                        for x in range(self.WIDTH):
                            p = self.dis.pixel(x, y)
                            fd.write(black if p else white)

        except Exception as e:
            print('EXCEPTION: {}'.format(e))
            # This method is not async, so no error or warning if you don't have an SD card inserted

        print('Screenshot saved.')
        common.system.turbo(False)

    # Save a camera snapshot in PPM (Portable Pixel Map) -- a very simple format
    # that doesn't need a big library to be included.
    def snapshot(self):
        from files import CardSlot
        from utils import random_hex
        import common
        from common import qr_buf, viewfinder_buf
        from constants import VIEWFINDER_WIDTH, VIEWFINDER_HEIGHT, CAMERA_WIDTH, CAMERA_HEIGHT
        from foundation import Camera

        common.system.turbo(True)

        # Create the Camera connection
        cam = Camera()
        cam.enable()

        # Take the picture - no viewfinder for now
        result = cam.snapshot(qr_buf, CAMERA_WIDTH, CAMERA_HEIGHT,
                              viewfinder_buf, VIEWFINDER_WIDTH, VIEWFINDER_HEIGHT)

        try:
            with CardSlot() as card:
                # Need to use get_sd_root() here to prefix the /sd/ or we get EPERM errors
                fname = '{}/snapshot-{}.ppm'.format(card.get_sd_root(), random_hex(4))
                # print('Saving camera snapshot to: {}'.format(fname))

                # PPM file format
                # http://paulbourke.net/dataformats/ppm/
                with open(fname, 'wb') as fd:
                    hdr = '''P6
# Created by Passport
{} {}
255\n'''.format(396, 330)

                    # Write the header
                    fd.write(bytes(hdr, 'utf-8'))

                    line = bytearray(396 * 2)  # Two bytes per pixel
                    pixel = bytearray(3)

                    # Write the pixels
                    for y in range(330):
                        # print('Line {}'.format(y))
                        result = cam.get_line_data(line, y)
                        if not result:
                            print('ERROR: Unable to get line data for line {}!'.format(y))
                            common.system.turbo(False)
                            return

                        for x in range(396):
                            rgb565 = (line[x*2 + 1] << 8) | line[x*2]
                            pixel[0] = (rgb565 & 0xF800) >> 8
                            pixel[1] = (rgb565 & 0x07E0) >> 3
                            pixel[2] = (rgb565 & 0x001F) << 3
                            fd.write(pixel)

        except Exception as e:
            print('EXCEPTION: {}'.format(e))
            # This method is not async, so no error or warning if you don't have an SD card inserted

        # print('Camera snapshot saved.')
        common.system.turbo(False)
