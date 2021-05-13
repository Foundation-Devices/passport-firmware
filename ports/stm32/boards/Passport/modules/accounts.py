# SPDX-FileCopyrightText: 2021 Foundation Devices, Inc. <hello@foundationdevices.com>
# SPDX-License-Identifier: GPL-3.0-or-later
#
# accounts.py - Single sig and multisig accounts feature for better organization and privacy/isolation
#

from menu import MenuSystem, MenuItem
from flow import SettingsMenu, AccountMenu
import stash
import common
from common import settings, system
from utils import UXStateMachine, to_json, to_str, save_new_account, make_account_name_num, account_exists, get_accounts
from wallets.utils import get_next_account_num
from ux import ux_enter_text, ux_show_story
from constants import DEFAULT_ACCOUNT_ENTRY, MAX_ACCOUNT_NAME_LEN

# from wallets.constants import *

# Set the account reference in common and update xfp/xpub with the current account
def set_active_account(label=None, arg=None, menu_title=None, index=None):
    account = arg
    # print('Setting active_account={}'.format(account))
    common.active_account = account

def clear_active_account(label=None, arg=None, menu_title=None, index=None):
    # print('Clearing active_account')
    common.active_account = None

async def new_account(*a):
    new_account_ux = NewAccountUX()
    await new_account_ux.show()


class NewAccountUX(UXStateMachine):
    def __init__(self):
        # States
        self.SELECT_ACCOUNT_NUM = 1
        self.ENTER_ACCOUNT_NAME = 2

        self.account_num = 0
        self.account_name = ''
        super().__init__(self.SELECT_ACCOUNT_NUM)

    async def show(self):
        while True:
            # print('show: state={}'.format(self.state))
            if self.state == self.SELECT_ACCOUNT_NUM:
                # Pick the next expected acct_num as the default value here
                next_acct_num = get_next_account_num()

                acct_num = await ux_enter_text(
                    title="Account",
                    label="Account Number",
                    initial_text='{}'.format(next_acct_num),
                    left_btn='BACK',
                    right_btn='ENTER',
                    num_only=True,
                    max_length=9)

                if acct_num == None:
                    return

                # Use the entered account number
                self.account_num = acct_num

                self.goto(self.ENTER_ACCOUNT_NAME)

            elif self.state == self.ENTER_ACCOUNT_NAME:
                # Default the name to the label as a starting point for the user
                self.account_name = ''

                name = await ux_enter_text(
                    'Account Name',
                    label='New Account Name',
                    initial_text=self.account_name,
                    right_btn='SAVE',
                    max_length=MAX_ACCOUNT_NAME_LEN)
                if name == None:
                    self.goto_prev()
                    continue

                # See if an account with this name already exists
                if account_exists(name):
                    result = await ux_show_story('An account with the name "{}" already exists. Please choose a different name.'.format(name),
                        title='Duplicate', center=True, center_vertically=True, right_btn='RENAME')
                    if result == 'x':
                        self.goto_prev()
                    else:
                        self.account_name = name  # Start off with the name the user entered
                        continue

                await save_new_account(name, self.account_num)
                return

MAX_ACCOUNTS = 20
def max_accounts_reached():
    accounts = get_accounts()
    return len(accounts) >= MAX_ACCOUNTS

class AllAccountsMenu(MenuSystem):

    @classmethod
    def construct(cls):
        # Dynamic menu with user-defined names of accounts
        # from actions import import_multisig_from_sd, import_multisig_from_qr

        rv = []
        try:
            accounts = get_accounts()

            # print('accounts={}'.format(to_str(accounts)))

            for acct in accounts:
                acct_num = acct.get('acct_num')
                name_num = make_account_name_num(acct.get('name'), acct_num)
                rv.append(
                    MenuItem(
                        name_num,
                        menu=AccountMenu,
                        menu_title=name_num,
                        action=set_active_account,
                        arg=acct))

            # Show Resume or new account menu depending on status
            rv.append(MenuItem('New Account', f=new_account, predicate=lambda: not max_accounts_reached()))
        except Exception as e:
            # print('accounts={}'.format(accounts))
            print('e={}'.format(e))
            rv.append(MenuItem('<Account Data Corrupted>', f=lambda: None))

        # print('rv={}'.format(rv))
        return rv

    def update_contents(self):
        # Reconstruct the list of wallets on this dynamic menu, because
        # we added or changed them and are showing that same menu again.
        tmp = self.construct()
        self.replace_items(tmp, True)
        # Clear active account, if any, usually when menu is activated after returning from an account submenu
        if common.active_account != None:
            clear_active_account()
