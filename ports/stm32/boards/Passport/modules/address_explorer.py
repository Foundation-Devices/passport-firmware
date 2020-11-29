# SPDX-FileCopyrightText: 2020 Foundation Devices, Inc.  <hello@foundationdevices.com>
# SPDX-License-Identifier: GPL-3.0-or-later
#
# SPDX-FileCopyrightText: 2018 Coinkite, Inc.  <coldcardwallet.com>
# SPDX-License-Identifier: GPL-3.0-only
#
# (c) Copyright 2018 by Coinkite Inc. This file is part of Coldcard <coldcardwallet.com>
# and is covered by GPLv3 license found in COPYING.
#
# address_explorer.py
#
# Address Explorer menu functionality
#
import chains
import stash
from actions import goto_top_menu
from display import FontTiny
from menu import MenuItem, MenuSystem, start_chooser
from public_constants import AFC_BECH32
from ux import the_ux, ux_show_story

SCREEN_CHAR_WIDTH = const(16)


async def choose_first_address(*a):
    # Choose from a truncated list of index 0 common addresses, remember
    # the last address the user selected and use it as the default
    from common import settings, dis
    chain = chains.current_chain()

    dis.fullscreen('Loading...')

    with stash.SensitiveValues() as sv:

        def truncate_address(addr):
            # Truncates address to width of screen, replacing middle chars
            middle = "-"
            leftover = SCREEN_CHAR_WIDTH - len(middle)
            start = addr[0:(leftover+1) // 2]
            end = addr[len(addr) - (leftover // 2):]
            return start + middle + end

        # Create list of choices (address_index_0, path, addr_fmt)
        choices = []
        for name, path, addr_fmt in chains.CommonDerivations:
            if '{coin_type}' in path:
                path = path.replace('{coin_type}', str(chain.b44_cointype))
            subpath = path.format(account=0, change=0, idx=0)
            node = sv.derive_path(subpath, register=False)
            address = chain.address(node, addr_fmt)
            choices.append((truncate_address(address), path, addr_fmt))

            dis.progress_bar_show(len(choices) / len(chains.CommonDerivations))

        stash.blank_object(node)

    picked = None

    async def clicked(_1, _2, item):
        if picked is None:
            picked = item.arg
        the_ux.pop()

    items = [MenuItem(address, f=clicked, arg=i) for i, (address, path, addr_fmt)
             in enumerate(choices)]
    menu = MenuSystem(items, title='Address List')
    menu.goto_idx(settings.get('axi', 0))
    the_ux.push(menu)

    await menu.interact()

    if picked is None:
        return None

    # update last clicked address
    settings.set('axi', picked)
    address, path, addr_fmt = choices[picked]

    return (path, addr_fmt)


async def show_n_addresses(path, addr_fmt, start, n):
    # Displays n addresses from start
    from common import dis
    import version

    def make_msg(start):
        msg = ''
        if start == 0:
            msg = "Press 1 to save to MicroSD."
            msg += '\n\n'
        msg += "Addresses %d..%d:\n\n" % (start, start + n - 1)

        addrs = []
        chain = chains.current_chain()

        dis.fullscreen('Loading...')

        with stash.SensitiveValues() as sv:

            for idx in range(start, start + n):
                subpath = path.format(account=0, change=0, idx=idx)
                node = sv.derive_path(subpath, register=False)
                addr = chain.address(node, addr_fmt)
                addr1 = addr[:16]
                addr2 = addr[16:]
                addrs.append(addr)

                msg += "%s =>\n  %s\n  %s\n\n" % (subpath, addr1, addr2)

                dis.progress_bar_show(idx/n)

            stash.blank_object(node)

        msg += "Press 9 to see next group.\nPress 7 to see prev. group."

        return msg, addrs

    msg, addrs = make_msg(start)

    while 1:
        ch = await ux_show_story(msg, right_btn='VIEW QR', font=FontTiny)

        if ch == '1':
            # save addresses to microSD signal
            await make_address_summary_file(path, addr_fmt)
            # .. continue on same screen in case they want to write to multiple cards

        if ch == 'x':
            return

        if ch == 'y':
            from ux import show_qr_codes
            await show_qr_codes(addrs, bool(addr_fmt & AFC_BECH32), start)
            continue

        if ch == '7' and start > 0:
            # go backwards in explorer
            start -= n
        elif ch == '9':
            # go forwards
            start += n

        msg, addrs = make_msg(start)


def generate_address_csv(path, addr_fmt, n):
    # Produce CSV file contents as a generator

    yield '"Index","Payment Address","Derivation"\n'

    ch = chains.current_chain()

    with stash.SensitiveValues() as sv:
        for idx in range(n):
            subpath = path.format(account=0, change=0, idx=idx)
            node = sv.derive_path(subpath, register=False)

            yield '%d,"%s","%s"\n' % (idx, ch.address(node, addr_fmt), subpath)

        stash.blank_object(node)


async def make_address_summary_file(path, addr_fmt, fname_pattern='addresses.txt'):
    # write addresses into a text file on the microSD
    from common import dis
    from files import CardSlot, CardMissingError
    from actions import needs_microsd

    # simple: always set number of addresses.
    # - takes 60 seconds, to write 250 addresses on actual hardware
    count = 250

    dis.fullscreen('Saving 0-%d' % count)

    # generator function
    body = generate_address_csv(path, addr_fmt, count)

    # pick filename and write
    try:
        with CardSlot() as card:
            fname, nice = card.pick_filename(fname_pattern)

            # do actual write
            with open(fname, 'wb') as fd:
                for idx, part in enumerate(body):
                    fd.write(part.encode())

                    if idx % 5 == 0:
                        dis.progress_bar_show(idx / count)

    except CardMissingError:
        await needs_microsd()
        return
    except Exception as e:
        await ux_show_story('Failed to write!\n\n\n'+str(e))
        return

    msg = '''Address summary file written:\n\n%s''' % nice
    await ux_show_story(msg)


async def address_explore(*a):
    # explore addresses based on derivation path chosen
    # by proxy external index=0 address
    while 1:
        ch = await ux_show_story('''\
The following menu lists the first payment address \
produced by various common wallet systems.

Choose the address that your desktop or mobile wallet \
has shown you as the first receive address.

WARNING: Please understand that exceeding the gap limit \
of your wallet, or choosing the wrong address on the next screen \
may make it very difficult to recover your funds.''')

        if ch == 'y':
            break
        if ch == 'x':
            return

    picked = await choose_first_address()
    if picked is None:
        return

    path, addr_fmt = picked

    await show_n_addresses(path, addr_fmt, 0, 10)

# EOF
