# SPDX-FileCopyrightText: 2020 Foundation Devices, Inc. <hello@foundationdevices.com>
# SPDX-License-Identifier: GPL-3.0-or-later
#
# SPDX-FileCopyrightText: 2018 Coinkite, Inc. <coldcardwallet.com>
# SPDX-License-Identifier: GPL-3.0-only
#
# (c) Copyright 2018 by Coinkite Inc. This file is part of Coldcard <coldcardwallet.com>
# and is covered by GPLv3 license found in COPYING.
#
# menu.py - Implement an interactive menu system.
#
import gc
import utime

from display import Display, FontSmall
from uasyncio import sleep_ms
from ux import KeyInputHandler, the_ux, ux_shutdown


def start_chooser(chooser, title='Select', show_checks=True):
    # get which one to show as selected, list of choices, and fcn to call after
    selected, choices, setter = chooser()

    def picked(menu, picked, xx_self):
        menu.chosen = picked
        menu.show()
        await sleep_ms(200)     # visual feedback that we changed it
        setter(picked, choices[picked])

        the_ux.pop()

    # make a new menu, just for the choices
    m = MenuSystem([MenuItem(c, f=picked, has_submenu=show_checks) for c in choices],
                   chooser_mode=show_checks, chosen=selected, title=title)
    the_ux.push(m)

class MenuItem:
    def __init__(self, label, menu=None, f=None, chooser=None, arg=None, predicate=None, menu_title='Passport', action=None, has_submenu=True):
        self.label = label
        self.arg = arg
        self.menu_title = menu_title
        if menu:
            self.next_menu = menu
        if f:
            self.next_function = f
        if chooser:
            self.chooser = chooser
        if predicate:
            self.predicate = predicate
        if action:
            self.action = action
        self.has_submenu = has_submenu  # Used to determine whether to show the > wedge on the right side

    async def activate(self, menu, idx):

        if getattr(self, 'chooser', None):
            start_chooser(self.chooser, title=self.menu_title)

        else:
            # Run action if any (this is some side effect, like setting the current account when entering a menu)
            action = getattr(self, 'action', None)
            if action:
                action(label=self.label, arg=self.arg, menu_title=self.menu_title, index=idx)

            # nesting menus, and functions and so on.
            f = getattr(self, 'next_function', None)
            if f:
                rv = await f(menu, idx, self)
                if isinstance(rv, MenuSystem):
                    # XXX the function should do this itself
                    # go to new menu
                    the_ux.replace(rv)

            m = getattr(self, 'next_menu', None)

            if callable(m):
                m = await m(menu, idx, self)

            if isinstance(m, list):
                m = MenuSystem(m, title=self.menu_title)

            if m:
                the_ux.push(m)

class MenuSystem:

    def __init__(self, menu_items, chooser_mode=False, chosen=None, should_cont=None, space_indicators=False, title="Passport"):
        self.should_continue = should_cont or (lambda: True)
        self.original_items = menu_items
        self.replace_items(menu_items)
        self.space_indicators = space_indicators
        self.chooser_mode = chooser_mode
        self.chosen = chosen
        self.title = title
        self.input = KeyInputHandler(down='udxy', up='udxy', repeat_delay=250, repeat_speed=10)
        self.shutdown_btn_enabled = False
        self.turbo = None  # We rely on this being 3 states: None, False, True

        # Setup font
        self.font = FontSmall
        # number of full lines per screen
        self.max_lines = (
            Display.HEIGHT - Display.HEADER_HEIGHT - Display.FOOTER_HEIGHT) // self.font.leading

        if chosen is not None:
            self.goto_idx(chosen)

    # subclasses: override us
    #
    def late_draw(self, dis):
        pass

    def early_draw(self, dis):
        pass

    # Submenus can override this
    def update_contents(self):
        self.replace_items(self.original_items, True)

    def replace_items(self, menu_items, keep_position=False):
        # only safe to keep position if you know number of items isn't changing
        if not keep_position:
            self.cursor = 0
            self.ypos = 0

        self.items = [m for m in menu_items if not getattr(
            m, 'predicate', None) or m.predicate()]
        self.count = len(self.items)

        # If we removed items, make sure the cursor is still visible
        while self.cursor >= self.count:
            self.cursor -= 1

    def show(self):
        from common import dis, system

        #
        # Redraw the menu.
        #
        dis.clear()

        # subclass hook
        self.early_draw(dis)

        # Header
        wm = True if self.title == None else False
        dis.draw_header(self.title)

        menu_item_height = self.font.leading
        menu_item_left = 6
        sel_w, sel_h = dis.icon_size('selected')
        if self.chooser_mode:
            menu_item_left += sel_w

        show_scrollbar = True if self.count > self.max_lines else False

        x, y = (menu_item_left, Display.HEADER_HEIGHT)
        for n in range(self.ypos + self.max_lines + 1):
            if n+self.ypos >= self.count:
                break
            menu_item = self.items[n+self.ypos]
            msg = menu_item.label
            is_sel = (self.cursor == n+self.ypos)
            if is_sel:
                wedge_w, wedge_h = dis.icon_size('wedge')
                dis.dis.fill_rect(0, y, Display.WIDTH, menu_item_height - 1, 1)

                dis.text(x, y + 2, msg, font=self.font, invert=1)

                if not self.chooser_mode and menu_item.has_submenu:
                    wedge_offset = 12 if show_scrollbar else 6
                    icon_x = dis.WIDTH - wedge_w - wedge_offset
                    dis.dis.fill_rect(
                        icon_x - 2,
                        y,
                        Display.WIDTH - (icon_x - 2),
                        menu_item_height - 1,
                        1)
                    dis.icon(
                        icon_x,
                        y + (menu_item_height - wedge_h) // 2,
                        'wedge',
                        invert=1)
            else:
                dis.text(x, y + 2, msg, font=self.font)

            if msg[0] == ' ' and self.space_indicators:
                dis.icon(x-2, y + 11, 'space', invert=is_sel)

            if self.chooser_mode and self.chosen is not None and (n+self.ypos) == self.chosen:
                dis.icon(2, y + 6, 'selected', invert=is_sel)

            y += menu_item_height
            if y > Display.HEIGHT - Display.FOOTER_HEIGHT:
                break

        # subclass hook
        self.late_draw(dis)

        if show_scrollbar:
            dis.scrollbar(self.ypos / self.count, self.max_lines / self.count)

        self.shutdown_btn_enabled = the_ux.is_top_level()
        left_btn = 'SHUTDOWN' if self.shutdown_btn_enabled else 'BACK'
        dis.draw_footer(left_btn, 'SELECT', self.input.is_pressed('x'),
                        self.input.is_pressed('y'))

        dis.show()

        # We only want to turn it off once rather than whenever it's False, so we
        # set to None to avoid turning turbo off again.
        if self.turbo == False:
            system.turbo(False)
            self.turbo = None

    def down(self):
        if self.cursor < self.count-1:
            self.cursor += 1
        if self.cursor - self.ypos > (self.max_lines-1):
            self.ypos += 1

    def up(self):
        if self.cursor > 0:
            self.cursor -= 1
            if self.cursor < self.ypos:
                self.ypos -= 1

    def top(self):
        self.cursor = 0
        self.ypos = 0

    def goto_n(self, n):
        # goto N from top of (current) screen
        # change scroll only if needed to make it visible
        self.cursor = max(min(n + self.ypos, self.count-1), 0)
        self.ypos = max(self.cursor - n, 0)

    def goto_idx(self, n):
        # skip to any item, force cursor near middle of screen
        # NOTE: If we get a string error here, it probably means we have
        #       passed the title to a MenuSystem() call as the second parameter instead of as a named parameter
        n = self.count-1 if n >= self.count else n
        n = 0 if n < 0 else n
        self.cursor = n
        if n < self.max_lines - 1:
            self.ypos = 0
        else:
            self.ypos = n - 2

    def page(self, n):
        # relative page dn/up
        if n == 1:
            for i in range(self.max_lines):
                self.down()
        else:
            for i in range(self.max_lines):
                self.up()

    # events
    def on_cancel(self):
        # override me
        if the_ux.pop():
            # top of stack (main top-level menu)
            self.top()

    async def activate(self, idx):
        # Activate a specific choice in our menu.
        if idx is None:
            # "go back" or cancel or something
            if self.shutdown_btn_enabled:
                if not self.input.kcode_imminent():
                    await ux_shutdown()
            else:
                self.on_cancel()
        else:
            if idx >= 0 and idx < self.count:
                ch = self.items[idx]

                await ch.activate(self, idx)

    async def interact(self):
        # Only public entry point: do stuff.
        while self.should_continue() and the_ux.top_of_stack() == self:
            ch = await self.wait_choice()
            gc.collect()
            await self.activate(ch)


    async def wait_choice(self):
        # Wait until a menu choice is picked; let them move around
        # the menu, keep redrawing it and so on.

        key = None

        while 1:
            # Give the menu predicates another chance to run in case they changed
            self.update_contents()

            self.show()

            start = utime.ticks_ms()
            event = None
            while True:
                event = await self.input.get_event()

                if event != None:
                    break

                # Redraw the display if no menu input has occurred
                # for a while. Gives the battery icon a chance to update.
                end = utime.ticks_ms()
                if end - start >= 60000:
                    event = (None, None)
                    break

            key, event_type = event
            # print('key={} event_type={}'.format(key, event_type))

            if event_type == 'down' or event_type == 'repeat':

                if event_type == 'down':
                    from common import system
                    system.turbo(True)
                    self.turbo = True

                if not self.input.kcode_imminent():
                    if key == 'u':
                        self.up()
                    elif key == 'd':
                        self.down()

            if event_type == 'up':
                self.turbo = False  # We set to False here, but actually turn off after rendering
                if self.input.kcode_complete():
                    self.input.kcode_reset();
                    # print('SHOW SECRET EXTRAS MENU!')
                    from flow import ExtrasMenu
                    menu_item = MenuItem('Extras', ExtrasMenu, menu_title='Extras')
                    await menu_item.activate(self, 0)
                    return -1  # So that the caller does nothing
                elif not self.input.kcode_imminent():
                    if key == 'y':
                        # selected
                        return self.cursor
                    elif key == 'x':
                        # abort/nothing selected/back out?
                        return None

# EOF
