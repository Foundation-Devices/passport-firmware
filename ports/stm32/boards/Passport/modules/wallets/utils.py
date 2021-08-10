# SPDX-FileCopyrightText: 2021 Foundation Devices, Inc. <hello@foundationdevices.com>
# SPDX-License-Identifier: GPL-3.0-or-later
#
# utils.py - Wallet utils
#

import chains
import common
from common import settings
from public_constants import AF_CLASSIC, AF_P2SH, AF_P2WPKH_P2SH, AF_P2WSH_P2SH, AF_P2WPKH, AF_P2WSH
from constants import DEFAULT_ACCOUNT_ENTRY
import stash
from log import log
from utils import get_accounts

# Dynamic find the next account number rather than storing it - we never want to skip an account number
# since that would create gaps and potentially make recovering funds harder if we exceeded the gap limit.
def get_next_account_num():
    accts = get_accounts()

    acct_nums = []
    for acct in accts:
        acct_nums.append(acct['acct_num'])

    acct_nums.sort()
    curr_acct_num = 0

    # This should normally be sequentially sorted from 0 onward, monotonically increasing by 1.
    # If we find it is not then there's a hole in the sequence and we can use it.
    # That should only happen if the user manually adds custom accounts that cause a gap in the range.
    for i in range(len(acct_nums)):
        if acct_nums[curr_acct_num] != curr_acct_num:
            return curr_acct_num
        curr_acct_num += 1

    return curr_acct_num

# TODO: Make this a data table and drive these function from it
# P2PKH / Classic  1    Single  Base58 check    x   m/44'/0'/{acct}
# P2SH P2WPKH      3    Single  Base58 check    y   m/49'/0'/{acct}
# P2WPKH           bc1  Single  Bech32          z   m/84'/0'/{acct}

def get_addr_type_from_address(address, is_multisig):
    if len(address) < 26:
        return None

    if address[0] == '1':
        return AF_P2SH if is_multisig else AF_CLASSIC
    elif address[0] == '3':
        return AF_P2WSH_P2SH if is_multisig else AF_P2WPKH_P2SH
    elif address[0] == 'b' and address[1] == 'c' and address[2] == '1':
        return AF_P2WSH if is_multisig else AF_P2WPKH

    return None

def get_bip_num_from_addr_type(addr_type, is_multisig):
    if is_multisig:
        if addr_type == AF_P2WSH_P2SH:
            return 48
        elif addr_type == AF_P2WSH:
            return 48
    else:
        if addr_type == AF_CLASSIC:
            return 44
        elif addr_type == AF_P2WPKH:
            return 84
        elif addr_type == AF_P2WPKH_P2SH:
            return 49
        else:
            raise ValueError(addr_type)

def get_addr_type_from_deriv(path):
    type_str = get_addr_type_from_deriv_path(path)
    subpath = get_part_from_deriv_path(path, 4)

    if type_str == '44':
        return AF_CLASSIC
    elif type_str == '49':
        return AF_P2WPKH_P2SH
    elif type_str == '84':
        return AF_P2WPKH
    elif type_str == '48':
        if subpath == '1':
            return AF_P2WSH_P2SH
        elif subpath == '2':
            return AF_P2WSH

    return None

def get_deriv_fmt_from_address(address, is_multisig):
    # print('get_deriv_fmt_from_address(): address={} is_multisig={}'.format(address, is_multisig))
    if len(address) < 26:
        return None

    # Map the address prefix to a standard derivation path and insert the account number
    if is_multisig:
        if address[0] == '3':
            return "m/48'/{coin_type}'/{acct}'/1'"
        elif address[0] == 'b' and address[1] == 'c' and address[2] == '1':
            return "m/48'/{coin_type}'/{acct}'/2'"
    else:
        if address[0] == '1':
            return "m/44'/{coin_type}'/{acct}'"
        elif address[0] == '3':
            return "m/49'/{coin_type}'/{acct}'"
        elif address[0] == 'b' and address[1] == 'c' and address[2] == '1':
            return "m/84'/{coin_type}'/{acct}'"

    return None

def get_deriv_fmt_from_addr_type(addr_type, is_multisig):
    # print('get_deriv_fmt_from_addr_type(): addr_type={} is_multisig={}'.format(addr_type, is_multisig))

    # Map the address prefix to a standard derivation path and insert the account number
    if is_multisig:
        if addr_type == AF_P2WSH_P2SH:
            return "m/48'/{coin_type}'/{acct}'/1'"
        elif addr_type == AF_P2WSH:
            return "m/48'/{coin_type}'/{acct}'/2'"
    else:
        if addr_type == AF_CLASSIC:
            return "m/44'/{coin_type}'/{acct}'"
        elif addr_type == AF_P2WPKH_P2SH:
            return "m/49'/{coin_type}'/{acct}'"
        elif addr_type == AF_P2WPKH:
            return "m/84'/{coin_type}'/{acct}'"

    return None

def get_deriv_path_from_addr_type_and_acct(addr_type, acct_num, is_multisig):
    chain = chains.current_chain()
    # print('get_deriv_path_from_addr_type_and_acct(): addr_type={} acct={} is_multisig={}'.format(addr_type, acct_num, is_multisig))
    fmt = get_deriv_fmt_from_addr_type(addr_type, is_multisig)
    if fmt != None:
        return fmt.format(coin_type=chain.b44_cointype,acct=acct_num)

    return None

# For single sig only
def get_deriv_path_from_address_and_acct(address, acct, is_multisig):
    chain = chains.current_chain()
    # print('get_deriv_path_from_address_and_acct(): address={} acct={} is_multisig={}'.format(address, acct, is_multisig))
    fmt = get_deriv_fmt_from_address(address, is_multisig)
    if fmt != None:
        return fmt.format(coin_type=chain.b44_cointype,acct=acct)

    return None

def get_acct_num_from_deriv_path(path):
    parts = path.split('/')
    if parts[3][-1] == "'":
        return int(parts[3][0:-1])
    else:
        return int(parts[3])

def get_addr_type_from_deriv_path(path):
    parts = path.split('/')
    if parts[1][-1] == "'":
        return int(parts[1][0:-1])
    else:
        return int(parts[1])

def get_part_from_deriv_path(path, index):
    parts = path.split('/')
    if parts[index][-1] == "'":
        return int(parts[index][0:-1])
    else:
        return int(parts[index])

def has_export_mode(mode_id):
    acct = common.active_account
    if acct:
        for mode in acct.sw_wallet['export_modes']:
            if mode['id'] == mode_id:
                return True

    return False

def get_export_mode(sw_wallet, mode_id):
    for mode in sw_wallet['export_modes']:
        if mode['id'] == mode_id:
            # log('Returning mode={}'.format(mode))
            return mode
    return None
