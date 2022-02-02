# SPDX-FileCopyrightText: 2020 Foundation Devices, Inc. <hello@foundationdevices.com>
# SPDX-License-Identifier: GPL-3.0-or-later
#
# SPDX-FileCopyrightText: 2018 Coinkite, Inc. <coldcardwallet.com>
# SPDX-License-Identifier: GPL-3.0-only
#
# (c) Copyright 2018 by Coinkite Inc. This file is part of Coldcard <coldcardwallet.com>
# and is covered by GPLv3 license found in COPYING.
#
# utils.py
#

import gc, sys, ustruct, trezorcrypto
from ubinascii import unhexlify as a2b_hex
from ubinascii import hexlify as b2a_hex
from ubinascii import a2b_base64, b2a_base64
import common

B2A = lambda x: str(b2a_hex(x), 'ascii')

RECEIVE_ADDR = 0
CHANGE_ADDR = 1

class imported:
    # Context manager that temporarily imports
    # a list of modules.
    # LATER: doubtful this saves any memory when all the code is frozen.

    def __init__(self, *modules):
        self.modules = modules

    def __enter__(self):
        # import everything required
        rv = tuple(__import__(n) for n in self.modules)

        return rv[0] if len(self.modules) == 1 else rv

    def __exit__(self, exc_type, exc_value, traceback):

        for n in self.modules:
            if n in sys.modules:
                del sys.modules[n]

        # recovery that tasty memory.
        gc.collect()

def pretty_delay(n):
    # decode # of seconds into various ranges, need not be precise.
    if n < 120:
        return '%d seconds' % n
    n /= 60
    if n < 60:
        return '%d minutes' % n
    n /= 60
    if n < 48:
        return '%.1f hours' % n
    n /= 24
    return 'about %d days' % n

def pretty_short_delay(sec):
    # precise, shorter on screen display
    if sec >= 3600:
        return '%2dh %2dm %2ds' % (sec //3600, (sec//60) % 60, sec % 60)
    else:
        return '%2dm %2ds' % ((sec//60) % 60, sec % 60)

def pop_count(i):
    # 32-bit population count for integers
    # from <https://stackoverflow.com/questions/9829578>
    i = i - ((i >> 1) & 0x55555555)
    i = (i & 0x33333333) + ((i >> 2) & 0x33333333)

    return (((i + (i >> 4) & 0xF0F0F0F) * 0x1010101) & 0xffffffff) >> 24

def get_filesize(fn):
    # like os.path.getsize()
    import uos
    return uos.stat(fn)[6]

def is_dir(fn):
    from stat import S_ISDIR
    import uos
    mode = uos.stat(fn)[0]
    # print('is_dir() mode={}'.format(mode))
    return S_ISDIR(mode)

class HexWriter:
    # Emulate a file/stream but convert binary to hex as they write
    def __init__(self, fd):
        self.fd = fd
        self.pos = 0
        self.checksum = trezorcrypto.sha256()

    def __enter__(self):
        self.fd.__enter__()
        return self

    def __exit__(self, *a, **k):
        self.fd.seek(0, 3)          # go to end
        self.fd.write(b'\r\n')
        return self.fd.__exit__(*a, **k)

    def tell(self):
        return self.pos

    def write(self, b):
        self.checksum.update(b)
        self.pos += len(b)

        self.fd.write(b2a_hex(b))

    def seek(self, offset, whence=0):
        assert whence == 0          # limited support
        self.pos = offset
        self.fd.seek((2*offset), 0)

    def read(self, ll):
        b = self.fd.read(ll*2)
        if not b:
            return b
        assert len(b)%2 == 0
        self.pos += len(b)//2
        return a2b_hex(b)

    def readinto(self, buf):
        b = self.read(len(buf))
        buf[0:len(b)] = b
        return len(b)

class Base64Writer:
    # Emulate a file/stream but convert binary to Base64 as they write
    def __init__(self, fd):
        self.fd = fd
        self.runt = b''

    def __enter__(self):
        self.fd.__enter__()
        return self

    def __exit__(self, *a, **k):
        if self.runt:
            self.fd.write(b2a_base64(self.runt))
        self.fd.write(b'\r\n')
        return self.fd.__exit__(*a, **k)

    def write(self, buf):
        if self.runt:
            buf = self.runt + buf
        rl = len(buf) % 3
        self.runt = buf[-rl:] if rl else b''
        if rl < len(buf):
            tmp = b2a_base64(buf[:(-rl if rl else None)])
            # library puts in newlines!?
            assert tmp[-1:] == b'\n', tmp
            assert tmp[-2:-1] != b'=', tmp
            self.fd.write(tmp[:-1])

def swab32(n):
    # endian swap: 32 bits
    return ustruct.unpack('>I', ustruct.pack('<I', n))[0]

def xfp2str(xfp):
    # Standardized way to show an xpub's fingerprint... it's a 4-byte string
    # and not really an integer. Used to show as '0x%08x' but that's wrong endian.
    return b2a_hex(ustruct.pack('<I', xfp)).decode().upper()

def str2xfp(txt):
    # Inverse of xfp2str
    return ustruct.unpack('<I', a2b_hex(txt))[0]

def problem_file_line(exc):
    # return a string of just the filename.py and line number where
    # an exception occured. Best used on AssertionError.
    import uio, sys, ure

    tmp = uio.StringIO()
    sys.print_exception(exc, tmp)
    lines = tmp.getvalue().split('\n')[-3:]
    del tmp

    # convert:
    #   File "main.py", line 63, in interact
    #    into just:
    #   main.py:63
    #
    # on simulator, huge path is included, remove that too

    rv = None
    for ln in lines:
        mat = ure.match(r'.*"(/.*/|)(.*)", line (.*), ', ln)
        if mat:
            try:
                rv = mat.group(2) + ':' + mat.group(3)
            except: pass

    return rv or str(exc) or 'Exception'

def cleanup_deriv_path(bin_path, allow_star=False):
    # Clean-up path notation as string.
    # - raise exceptions on junk
    # - standardize on 'prime' notation (34' not 34p, or 34h)
    # - assume 'm' prefix, so '34' becomes 'm/34', etc
    # - do not assume /// is m/0/0/0
    # - if allow_star, then final position can be * or *' (wildcard)
    import ure
    from public_constants import MAX_PATH_DEPTH
    try:
        s = str(bin_path, 'ascii').lower()
    except UnicodeError:
        raise AssertionError('must be ascii')

    # empty string is valid
    if s == '': return 'm'

    s = s.replace('p', "'").replace('h', "'")
    mat = ure.match(r"(m|m/|)[0-9/']*" + ('' if not allow_star else r"(\*'|\*|)"), s)
    assert mat.group(0) == s, "invalid characters"

    parts = s.split('/')

    # the m/ prefix is optional
    if parts and parts[0] == 'm':
        parts = parts[1:]

    if not parts:
        # rather than: m/
        return 'm'

    assert len(parts) <= MAX_PATH_DEPTH, "too deep"

    for p in parts:
        assert p != '' and p != "'", "empty path component"
        if allow_star and '*' in p:
            # - star or star' can be last only (checked by regex above)
            assert p == '*' or p == "*'", "bad wildcard"
            continue
        if p[-1] == "'":
            p = p[0:-1]
        try:
            ip = int(p, 10)
        except:
            ip = -1
        assert 0 <= ip < 0x80000000 and p == str(ip), "bad component: "+p

    return 'm/' + '/'.join(parts)

def keypath_to_str(bin_path, prefix='m/', skip=1):
    # take binary path, like from a PSBT and convert into text notation
    rv = prefix + '/'.join(str(i & 0x7fffffff) + ("'" if i & 0x80000000 else "")
                            for i in bin_path[skip:])
    return 'm' if rv == 'm/' else rv

def str_to_keypath(xfp, path):
    # Take a numeric xfp, and string derivation, and make a list of numbers,
    # like occurs in a PSBT.
    # - no error checking here

    rv = [xfp]
    for i in path.split('/'):
        if i == 'm': continue
        if not i: continue      # trailing or duplicated slashes

        if i[-1] == "'":
            here = int(i[:-1]) | 0x80000000
        else:
            here = int(i)

        rv.append(here)

    return rv

def match_deriv_path(patterns, path):
    # check for exact string match, or wildcard match (star in last position)
    # - both args must be cleaned by cleanup_deriv_path() already
    # - will accept any path, if 'any' in patterns
    if 'any' in patterns:
        return True

    for pat in patterns:
        if pat == path:
            return True

        if pat.endswith("/*") or pat.endswith("/*'"):
            if pat[-1] == "'" and path[-1] != "'": continue
            if pat[-1] == "*" and path[-1] == "'": continue

            # same hardness so check up to last component of path
            if pat.split('/')[:-1] == path.split('/')[:-1]:
                return True

    return False

class DecodeStreamer:
    def __init__(self):
        self.runt = bytearray()

    def more(self, buf):
        # Generator:
        # - accumulate into mod-N groups
        # - strip whitespace
        for ch in buf:
            if chr(ch).isspace(): continue
            self.runt.append(ch)
            if len(self.runt) == 128*self.mod:
                yield self.a2b(self.runt)
                self.runt = bytearray()

        here = len(self.runt) - (len(self.runt) % self.mod)
        if here:
            yield self.a2b(self.runt[0:here])
            self.runt = self.runt[here:]

class HexStreamer(DecodeStreamer):
    # be a generator that converts hex digits into binary
    # NOTE: mpy a2b_hex doesn't care about unicode vs bytes
    mod = 2
    def a2b(self, x):
        return a2b_hex(x)

class Base64Streamer(DecodeStreamer):
    # be a generator that converts Base64 into binary
    mod = 4
    def a2b(self, x):
        return a2b_base64(x)

class UXStateMachine:
    def __init__(self, initial_state, machine_name=None):
        # print('UXStateMachine init: initial_state={}'.format(initial_state))
        self.state = initial_state
        self.prev_states = []

    def goto(self, new_state, save_curr=True):
        # print('Go from {} to {}'.format(self.state, new_state))
        if save_curr:
            self.prev_states.append(self.state)
        self.state = new_state

    # Transition back to previous state
    def goto_prev(self):
        # print('goto_prev: prev_states={}'.format(self.prev_states))
        if len(self.prev_states) > 0:
            prev_state = self.prev_states.pop()
            # print('Go BACK from {} to {}'.format(self.state, prev_state))
            # if self.machine_name != None:
            #     print('{}: Go from {} to PREVIOUS state {}'.format(self.machine_name, self.state, prev_state))
            # else:
            #     print('Go from {} to PREVIOUS state {}'.format(self.state, prev_state))
            self.state = prev_state
            return True
        else:
            return False

    async def show(self):
        pass

def get_month_str(month):
    if month == 1:
        return "January"
    elif month == 2:
        return "February"
    elif month == 3:
        return "March"
    elif month == 4:
        return "April"
    elif month == 5:
        return "May"
    elif month == 6:
        return "June"
    elif month == 7:
        return "July"
    elif month == 8:
        return "August"
    elif month == 9:
        return "September"
    elif month == 10:
        return "October"
    elif month == 11:
        return "November"
    elif month == 12:
        return "December"

def randint(a, b):
    import struct
    from common import noise
    from noise_source import NoiseSource

    buf = bytearray(4)
    noise.random_bytes(buf, NoiseSource.MCU)
    num = struct.unpack_from(">I", buf)[0]

    result = a + (num % (b-a+1))
    return result

def bytes_to_hex_str(s):
    return str(b2a_hex(s), 'ascii')

# Pass a string pattern like 'foo-{}.txt' and the {} will be replaced by a random 4 bytes hex number
def random_filename(card, pattern):
    from noise_source import NoiseSource
    buf = bytearray(4)
    common.noise.random_bytes(buf, NoiseSource.MCU)
    fn = pattern.format(b2a_hex(buf).decode('utf-8'))
    return '{}/{}'.format(card.get_sd_root(), fn)

def to_json(o):
    import ujson
    s = ujson.dumps(o)
    parts = s.split(', ')
    lines = ',\n'.join(parts)
    return lines

def to_str(o):
    s = '{}'.format(o)
    parts = s.split(', ')
    lines = ',\n'.join(parts)
    return lines

def random_hex(num_chars):
    import random

    rand = bytearray((num_chars + 1)//2)
    for i in range(len(rand)):
        rand[i] = random.randint(0, 255)
    s = b2a_hex(rand).decode('utf-8').upper()
    return s[:num_chars]

def truncate_string_to_width(name, font, max_pixel_width):
    from common import dis
    if max_pixel_width <= 0:
        # print('WARNING: Invalid max_pixel_width passed to truncate_string_to_width(). Must be > 0.')
        return name

    while True:
        actual_width = dis.width(name, font)
        if actual_width < max_pixel_width:
            return name
        name = name[0:-1]

# The multisig import code is implemented as a menu, and we are coming from a state machine.
# We want to be able to show the topmost menu that was pushed onto the stack here and wait for it to exit.
# This is a hack. Side effect is that the top menu shows briefly after menu exits.
async def show_top_menu():
    from ux import the_ux
    c = the_ux.top_of_stack()
    await c.interact()

# TODO: For now this just checks the front bytes, but it could ensure the whole thing is valid
def is_valid_address(address):
    # Valid addresses: 1 , 3 , bc1, tb1, m, n, 2
    address = address.lower()
    return  (len(address) > 3) and \
            ((address[0] == '1') or \
            (address[0] == '2') or \
            (address[0] == '3') or \
            (address[0] == 'm') or \
            (address[0] == 'n') or \
            (address[0] == 'b' and address[1] == 'c' and address[2] == '1') or \
            (address[0] == 't' and address[1] == 'b' and address[2] == '1'))


# Return array of bytewords where each byte in buf maps to a word
# There are 256 bytewords, so this maps perfectly.
def get_bytewords_for_buf(buf):
    from ur2.bytewords import get_word
    words = []
    for b in buf:
        words.append(get_word(b))

    return words

# We need an async way for the chooser menu to be shown. This does a local call to interact(), which gives
# us exactly that. Once the chooser completes, the menu stack returns to the way it was.
async def run_chooser(chooser, title, show_checks=True):
    from ux import the_ux
    from menu import start_chooser
    start_chooser(chooser, title=title, show_checks=show_checks)
    c = the_ux.top_of_stack()
    await c.interact()

# Return the elements of a list in a random order in a new list
def shuffle(list):
    import random
    new_list = []
    list_len = len(list)
    while list_len > 0:
        i = random.randint(0, list_len-1)
        element = list.pop(i)
        new_list.append(element)
        list_len = len(list)

    return new_list

def ensure_folder_exists(path):
    import uos
    try:
        # print('Creating folder: {}'.format(path))
        uos.mkdir(path)
    except Exception as e:
        # print('Folder already exists: {}'.format(e))
        return

def file_exists(path):
    import os
    from stat import S_ISREG

    try:
        s = os.stat(path)
        mode = s[0]
        return S_ISREG(mode)
    except OSError as e:
        return False

def folder_exists(path):
    import os
    from stat import S_ISDIR

    try:
        s = os.stat(path)
        mode = s[0]
        return S_ISDIR(mode)
    except OSError as e:
        return False

# Derive addresses from the specified path until we find the address or have tried max_to_check addresses
# If single sig, we need `path`.
# If multisig, we need `ms_wallet`, but not `path`
def find_address(path, start_address_idx, address, addr_type, ms_wallet, is_change, max_to_check=100, reverse=False):
    import stash

    try:
        with stash.SensitiveValues() as sv:
            if ms_wallet:
                # NOTE: Can't easily reverse order here, so this is slightly less efficient
                for (curr_idx, paths, curr_address, script) in ms_wallet.yield_addresses(start_address_idx, max_to_check, change_idx=1 if is_change else 0):
                    # print('curr_idx={}: paths={} curr_address = {}'.format(curr_idx, paths, curr_address))

                    if curr_address == address:
                        return (curr_idx, paths)  # NOTE: Paths are the full paths of the addresses of each signer

            else:
                r = range(start_address_idx, start_address_idx + max_to_check)
                if reverse:
                    r = reversed(r)

                for curr_idx in r:
                    addr_path = '{}/{}/{}'.format(path, is_change, curr_idx)  # Zero for non-change address
                    # print('addr_path={}'.format(addr_path))
                    node = sv.derive_path(addr_path)
                    curr_address = sv.chain.address(node, addr_type)
                    # print('curr_idx={}: path={} addr_type={} curr_address = {}'.format(curr_idx, addr_path, addr_type, curr_address))
                    if curr_address == address:
                        return (curr_idx, addr_path)
        return (-1, None)
    except Exception as e:
        # Any address handling exceptions result in no address found
        return (-1, None)

def get_accounts():
    from common import settings
    from constants import DEFAULT_ACCOUNT_ENTRY
    accounts = settings.get('accounts', [DEFAULT_ACCOUNT_ENTRY])
    accounts.sort(key=lambda a: a.get('acct_num', 0))
    return accounts

# Only call when there is an active account
def set_next_addr(new_addr):
    if not common.active_account:
        return

    common.active_account.next_addr = new_addr

    accounts = get_accounts()
    for account in accounts:
        if account('id') == common.active_account.id:
            account['next_addr'] = new_addr
            common.settings.set('accounts', accounts)
            common.settings.save()
            break

# Only call when there is an active account
def account_exists(name):
    accounts = get_accounts()
    for account in accounts:
        if account.get('name') == name:
            return True

    return False


def make_next_addr_key(acct_num, addr_type, is_change):
    return '{}/{}{}'.format(acct_num, addr_type, '/1' if is_change else '')

def get_next_addr(acct_num, addr_type, is_change):
    from common import settings
    next_addrs = settings.get('next_addrs', {})
    key = make_next_addr_key(acct_num, addr_type, is_change)
    return next_addrs.get(key, 0)

# Save the next address to use for the specific account and address type
def save_next_addr(acct_num, addr_type, addr_idx, is_change, force_update=False):
    from common import settings
    next_addrs = settings.get('next_addrs', {})
    key = make_next_addr_key(acct_num, addr_type, is_change)

    # Only save the found index if it's newer
    if next_addrs.get(key, -1) < addr_idx or force_update:
        next_addrs[key] = addr_idx
        settings.set('next_addrs', next_addrs)

def get_prev_address_range(range, max_size):
    low, high = range
    size = min(max_size, low)
    return ((low - size, low), size)

def get_next_address_range(range, max_size):
    low, high = range
    return ((high, high + max_size), max_size)

async def scan_for_address(acct_num, address, addr_type, deriv_path, ms_wallet):
    from common import system, dis
    from ux import ux_show_story

    # print('Address to verify = {}'.format(address))

    # print('ms_wallet={}'.format(to_str(ms_wallet)))

    # We always check this many addresses, but we split them 50/50 until we reach 0 on the low end,
    # then we use the rest for the high end.
    NUM_TO_CHECK = 50

    # Setup the initial ranges
    a = [get_next_addr(acct_num, addr_type, False), get_next_addr(acct_num, addr_type, True)]

    low_range = [(a[RECEIVE_ADDR], a[RECEIVE_ADDR]), (a[CHANGE_ADDR], a[CHANGE_ADDR])]
    high_range = [(a[RECEIVE_ADDR], a[RECEIVE_ADDR]), (a[CHANGE_ADDR], a[CHANGE_ADDR])]
    low_size = [0, 0]
    high_size = [0, 0]

    while True:
        # Try next batch of addresses
        for is_change in range(0, 2):
            low_range[is_change], low_size[is_change] = get_prev_address_range(low_range[is_change], NUM_TO_CHECK // 2)
            high_range[is_change], high_size[is_change] = get_next_address_range(high_range[is_change], NUM_TO_CHECK - low_size[is_change])

        # See if the address is valid
        addr_idx = -1
        is_change = 0

        system.show_busy_bar()
        dis.fullscreen('Searching Addresses...')

        for is_change in range(0, 2):
            # Check downwards
            if low_size[is_change] > 0:
                # print('Check low range')
                (addr_idx, path_info) = find_address(
                    deriv_path,
                    low_range[is_change][0],
                    address,
                    addr_type,
                    ms_wallet,
                    is_change,
                    max_to_check=low_size[is_change],
                    reverse=True)

            # Exit if already found
            if addr_idx >= 0:
                break

            # Check upwards
            # print('Check high range')
            (addr_idx, path_info) = find_address(
                deriv_path,
                high_range[is_change][0],
                address,
                addr_type,
                ms_wallet,
                is_change,
                max_to_check=high_size[is_change])

            if addr_idx >= 0:
                break

        system.hide_busy_bar()

        # Was the address found?
        if addr_idx >= 0:
            return addr_idx, True if is_change else False
        else:
            # Address was not found in that batch of 100, so offer to keep searching
            msg = 'Address Not Found\n\nPassport checked '

            # Build a merged range for receive and one for change addresses
            merged_range = []
            for is_change in range(0, 2):
                msg += '{} addresses {}-{}{}'.format(
                    'change' if is_change == 1 else 'receive', low_range[is_change][0], high_range[is_change][1] - 1,
                    '.' if is_change == 1 else ' and ')

            msg += '\n\nContinue searching?'

            result = await ux_show_story(msg, title='Verify', left_btn='NO', right_btn='YES',
                center=True, center_vertically=True)
            if result == 'x':
                return -1, False

async def is_valid_btc_address(address):
    from ux import ux_show_story

    # Strip prefix if present
    if address[0:8].lower() == 'bitcoin:':
        address = address[8:]

    if not is_valid_address(address):
        await ux_show_story('That is not a valid Bitcoin address.', title='Error', left_btn='BACK',
             right_btn='SCAN', center=True, center_vertically=True)
        return address, False
    else:
        return address, True

async def do_address_verify(acct_num, address, addr_type, deriv_path, multisig_wallet):
    from common import system
    from ux import ux_show_story

    system.turbo(True)
    # Scan addresses to see if it's valid
    addr_idx, is_change = await scan_for_address(acct_num, address, addr_type, deriv_path, multisig_wallet)
    if addr_idx >= 0:
        # Remember where to start from next time
        save_next_addr(acct_num, addr_type, addr_idx, is_change)
        address = format_btc_address(address, addr_type)
        result = await ux_show_story('''Address Verified!

{}

This is a {} address at index {}.'''.format(address, 'change' if is_change == 1 else 'receive',  addr_idx),
                        title='Verify',
                        left_btn='BACK',
                        right_btn='CONTINUE',
                        center=True,
                        center_vertically=True)
        system.turbo(False)
        return True
    else:
        system.turbo(False)
        return False


def is_new_wallet_in_progress():
    from common import settings
    ap = settings.get('wallet_prog', None)
    return ap != None

def is_screenshot_mode_enabled():
    from common import screenshot_mode_enabled
    return screenshot_mode_enabled

async def do_rename_account(acct_num, new_name):
    from common import settings
    from export import auto_backup
    from constants import DEFAULT_ACCOUNT_ENTRY

    accounts = get_accounts()
    for account in accounts:
        if account.get('acct_num') == acct_num:
            account['name'] = new_name
            break

    settings.set('accounts', accounts)
    await settings.save()
    await auto_backup()

async def do_delete_account(acct_num):
    from common import settings
    from export import auto_backup

    accounts = get_accounts()
    accounts = list(filter(lambda acct: acct.get('acct_num') != acct_num, accounts))
    settings.set('accounts', accounts)
    await settings.save()
    await auto_backup()

async def save_new_account(name, acct_num):
    from common import settings
    from export import offer_backup
    from constants import DEFAULT_ACCOUNT_ENTRY

    accounts = get_accounts()
    accounts.append({'name': name, 'acct_num': acct_num})
    settings.set('accounts', accounts)
    await settings.save()
    await offer_backup()

def make_account_name_num(name, num):
    return '{} (#{})'.format(name, num)


# Save the QR code image in PPM (Portable Pixel Map) -- a very simple format that doesn't need a big library to be included.
def save_qr_code_image(qr_buf):
    from files import CardSlot
    from utils import random_hex
    from constants import CAMERA_WIDTH, CAMERA_HEIGHT

    common.system.turbo(True)

    try:
        with CardSlot() as card:
            # Need to use get_sd_root() here to prefix the /sd/ or we get EPERM errors
            fname = '{}/qr-{}.ppm'.format(card.get_sd_root(), random_hex(4))
            # print('Saving QR code image to: {}'.format(fname))

            # PPM file format
            # http://paulbourke.net/dataformats/ppm/
            with open(fname, 'wb') as fd:
                hdr = '''P6
# Created by Passport
{} {}
255\n'''.format(CAMERA_WIDTH, CAMERA_HEIGHT)

                # Write the header
                fd.write(bytes(hdr, 'utf-8'))

                line = bytearray(CAMERA_WIDTH)  # One byte per pixel
                pixel = bytearray(3)

                # Write the pixels
                for y in range(CAMERA_HEIGHT):
                    # print('QR Line {}'.format(y))
                    for x in range(CAMERA_WIDTH):
                        g = qr_buf[y*CAMERA_WIDTH + x]
                        pixel[0] = g
                        pixel[1] = g
                        pixel[2] = g
                        fd.write(pixel)

    except Exception as e:
        print('EXCEPTION: {}'.format(e))
        # This method is not async, so no error or warning if you don't have an SD card inserted

    # print('QR Image saved.')
    common.system.turbo(False)

alphanumeric_chars = {
    '0', '1', '2', '3', '4', '5', '6', '7', '8', '9',
    'A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L', 'M',
    'N', 'O', 'P', 'Q', 'R', 'S', 'T', 'U', 'V', 'W', 'X', 'Y', 'Z',
    ' ', '$',  '%',  '*',  '+',  '-',  '.',  '/',  ':'
}

def is_char_alphanumeric(ch):
    # print('Lookup ch={}'.format(ch))
    return ch in alphanumeric_chars

# Alphanumeric QR codes contain only the following characters:
#
#   0–9, A–Z (upper-case only), space, $, %, *, +, -, ., /, :
def is_alphanumeric_qr(buf):
    for ch in buf:
        is_alpha = is_char_alphanumeric(chr(ch))
        # print('is_alpha "{}" == {}'.format(ch, is_alpha))
        if not is_alpha:
            return False

    return True

async def needs_microsd():
    from ux import ux_show_story
    # Standard msg shown if no SD card detected when we need one.
    return await ux_show_story("Please insert a microSD card.", title='MicroSD', center=True, center_vertically=True)

def format_btc_address(address, addr_type):
    from public_constants import AF_P2WPKH

    if addr_type == AF_P2WPKH:
        width = 14
    else:
        width = 16

    return split_to_lines(address, width)

def get_backups_folder_path(card):
    return '{}/backups'.format(card.get_sd_root())

def is_all_zero(buf):
    for b in buf:
        if b != 0:
            return False
    return True

def split_to_lines(s, width):
    return '\n'.join([s[i:i+width] for i in range(0, len(s), width)])

def split_by_char_size(msg, font):
    from display import Display
    from ux import MAX_WIDTH, word_wrap
    from common import dis

    lines = []
    for ln in msg.split('\n'):
        if dis.width(ln, font) > MAX_WIDTH:
            lines.extend(word_wrap(ln, font))
        else:
            # ok if empty string, just a blank line
            lines.append(ln)
    return lines

# EOF
