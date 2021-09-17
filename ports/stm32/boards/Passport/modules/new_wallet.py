# SPDX-FileCopyrightText: 2021 Foundation Devices, Inc. <hello@foundationdevices.com>
# SPDX-License-Identifier: GPL-3.0-or-later
#
# new_wallet.py - Single sig and multisig accounts feature for better organization and privacy/isolation
#

import common
from common import settings, system, dis
from wallets.sw_wallets import supported_software_wallets
from wallets.utils import (
    get_deriv_path_from_address_and_acct,
    get_addr_type_from_address,
    get_deriv_path_from_address_and_acct,
    get_deriv_path_from_addr_type_and_acct,
    get_addr_type_from_deriv)
from ux import ux_show_story, ux_confirm, ux_show_text_as_ur, ux_scan_qr_code
from multisig import MultisigWallet, TRUST_PSBT
from utils import (
    UXStateMachine,
    to_str,
    random_hex,
    is_valid_address,
    run_chooser,
    scan_for_address,
    save_next_addr,
    make_account_name_num,
    get_accounts,
    format_btc_address,
    is_valid_btc_address,
    do_address_verify)
from wallets.constants import *
from uasyncio import sleep_ms
from constants import DEFAULT_ACCOUNT_ENTRY

def find_wallet_by_label(label, default_value):
    for _, entry in enumerate(supported_software_wallets):
        if entry.get('label') == label:
            return entry

    return default_value

def find_sig_type_by_id(sw_wallet, id, default_value):
    if not sw_wallet:
        return default_value

    for entry in sw_wallet.get('sig_types', []):
        if entry.get('id') == id:
            return entry

    return default_value

def find_export_mode_by_id(sw_wallet, id, default_value):
    if not sw_wallet:
        return default_value

    for entry in sw_wallet.get('export_modes', []):
        if entry.get('id') == id:
            return entry

    return default_value

def wallet_supports_sig_type(sw_wallet, sig_type):
    if not sw_wallet:
        return False

    for entry in sw_wallet.get('sig_types', []):
        if entry.get('id') == sig_type:
            return True

    return False


async def pair_new_wallet(*a):
    pair_new_wallet_ux = NewWalletUX()
    await pair_new_wallet_ux.show()

def derive_address(deriv_path, addr_idx, addr_type, ms_wallet):
    import stash
    # print('deriv_path={} addr_idx={} ms_wallet={} ms_wallet={}'.format(deriv_path, addr_idx, ms_wallet, ms_wallet))

    with stash.SensitiveValues() as sv:
        if ms_wallet:
            # This "loop" runs once to get the value from the generator
            for (curr_idx, paths, curr_address, script) in ms_wallet.yield_addresses(addr_idx, 1):
                addr_path = '{}/0/{}'.format(deriv_path, curr_idx)
                return (addr_path, curr_address)

        else:
            addr_path = '0/{}'.format(addr_idx)  # Zero for non-change address
            full_path = '{}/{}'.format(deriv_path, addr_path)
            # print('full_path={}'.format(full_path))
            node = sv.derive_path(full_path)
            address = sv.chain.address(node, addr_type)
            # print('address = {}'.format(address))
            return (addr_path, address)

def get_addresses_in_range(start, end, addr_type, acct_num,  ms_wallet):
    # print('addr_type={} acct_num={} ms_wallet={}'.format(addr_type, acct_num, ms_wallet))

    entries = []
    for i in range(start, end):
        fmt = get_deriv_path_from_addr_type_and_acct(addr_type, acct_num, ms_wallet != None)
        deriv_path = fmt.format(acct_num)
        entry = derive_address(deriv_path, i, addr_type, ms_wallet)
        entries.append(entry)
    return entries

class NewWalletUX(UXStateMachine):
    def __init__(self):
        # States
        self.SELECT_ACCOUNT = 1
        self.SELECT_SW_WALLET = 2
        self.SELECT_SIG_TYPE = 3
        self.SELECT_ADDR_TYPE = 4
        self.SELECT_EXPORT_MODE = 5
        self.PAIRING_MESSAGE = 6
        self.EXPORT_TO_QR = 7
        self.EXPORT_TO_MICROSD = 8
        self.IMPORT_MULTISIG_CONFIG_FROM_QR = 9
        self.IMPORT_MULTISIG_CONFIG_FROM_MICROSD = 10
        self.SCAN_RX_ADDRESS_VERIFICATION_INTRO = 11
        self.SCAN_RX_ADDRESS = 12
        self.SHOW_RX_ADDRESSES_VERIFICATION_INTRO = 13
        self.SHOW_RX_ADDRESSES = 14
        self.CONFIRMATION = 15
        self.RESUME_PROGRESS = 16

        self.acct_num = None
        self.sw_wallet = None
        self.sig_type = None
        self.export_mode = None
        self.acct_info = None  # Info from the create_wallet() call
        self.verified = False
        self.deriv_path = None   # m/84'/0'/123'  Used to derive the HDNode
        self.multisig_wallet = None
        self.exported = False
        self.next_addr = 0
        self.addr_type = None
        self.progress_made = False

        # print('NewWalletUX()')

        first_state = self.restore_from_progress()
        super().__init__(first_state)

    def restore_from_progress(self):
        progress = settings.get('wallet_prog', None)
        if progress != None:
            # Reload the previous progress
            self.sw_wallet = find_wallet_by_label(progress.get('sw_wallet'), None)
            self.sig_type = find_sig_type_by_id(self.sw_wallet, progress.get('sig_type'), None)
            self.export_mode = find_export_mode_by_id(self.sw_wallet, progress.get('export_mode'), None)
            self.acct_info = progress.get('acct_info')
            self.acct_num = progress.get('acct_num')
            self.verified = progress.get('verified', False)
            self.deriv_path = progress.get('deriv_path')
            self.multisig_wallet = MultisigWallet.get_by_id(progress.get('multisig_id'))
            self.exported = progress.get('exported', False)
            self.next_addr = progress.get('next_addr', 0)
            self.addr_type = progress.get('addr_type', None)

            if self.acct_num != None:
                self.progress_made = True

            return self.RESUME_PROGRESS
        else:
            return self.SELECT_ACCOUNT

    def __repr__(self):
        return """NewWalletUX: sw_wallet={}, sig_type={}, export_mode={},
  acct_info={}, acct_num={}, verified={},
  deriv_path={}, addr_type={}, multisig_wallet={},
  exported={}, next_addr={}""".format(
        self.sw_wallet,
        self.sig_type,
        self.export_mode,
        self.acct_info,
        self.acct_num,
        self.verified,
        self.deriv_path,
        self.addr_type,
        self.multisig_wallet,
        self.exported,
        self.next_addr)

    async def confirm_abort(self):
        # If user hasn't made any progress at all, then no need to confirm anything. Just back out.
        if not self.progress_made:
            return True

        result = await ux_confirm('Are you sure you want to cancel pairing the new wallet?\n\nAll progress will be lost.')
        if result:
            self.abort_wallet_progress()
        return result

    def get_account_description(self, acct_num):
        accounts = get_accounts()
        for acct in accounts:
            curr_acct_num = acct.get('acct_num')
            if curr_acct_num == acct_num:
                return make_account_name_num(acct.get('name'), acct_num)
        return 'Unknown Acct ({})'.format(acct_num)

    # Account chooser
    def account_chooser(self):
        choices = []
        values = []

        accounts = get_accounts()
        accounts.sort(key=lambda a: a.get('acct_num', 0))

        for acct in accounts:
            acct_num = acct.get('acct_num')
            account_name_num = make_account_name_num(acct.get('name'), acct_num)
            choices.append(account_name_num)
            values.append(acct_num)

        def select_account(index, text):
            self.acct_num = values[index]

        return 0, choices, select_account

    # Local choosers for wallet configuration
    def sw_wallet_chooser(self):
        choices = []
        values = []
        for w in supported_software_wallets:
            # Include in the list if this is account 0, or (if not account 0), then if it supports single-sig
            # In the flow, we will automatically pick single-sig in this case.
            if self.acct_num == 0 or wallet_supports_sig_type(w, 'single-sig'):
                choices.append(w['label'])
                values.append(w)

        def select_sw_wallet(index, text):
            self.sw_wallet = values[index]

        return 0, choices, select_sw_wallet

    def sig_type_chooser(self):
        choices = []
        values = []

        for sig_type in self.sw_wallet['sig_types']:
            choices.append(sig_type['label'])
            values.append(sig_type)

        def select_sig_type(index, text):
            self.sig_type = values[index]

        return 0, choices, select_sig_type

    def export_mode_chooser(self):
        choices = []
        values = []

        for export_mode in self.sw_wallet['export_modes']:
            choices.append(export_mode['label'])
            values.append(export_mode)

        def select_export_mode(index, text):
            self.export_mode = values[index]
            # print('self.export_mode[\'id\']={}, self.export_mode={}'.format(self.export_mode['id'], self.export_mode))

        return 0, choices, select_export_mode

    def singlesig_addr_type_chooser(self):
        from public_constants import AF_P2WPKH, AF_P2WPKH_P2SH, AF_CLASSIC
        choices = ['Native Segwit', 'P2SH-Segwit', 'Legacy (P2PKH)']
        values = [AF_P2WPKH, AF_P2WPKH_P2SH, AF_CLASSIC]

        def select_addr_type(index, text):
            self.addr_type = values[index]

        return 0, choices, select_addr_type

    def get_custom_text(self, field, default_text):
        if self.sw_wallet:
            ct = self.sw_wallet.get('custom_text')
            if ct:
                return ct.get(field, default_text)

        return default_text

    def infer_wallet_info(self, address=None, ms_wallet=None):
        # Ensure we have an addr_type, if possible yet
        if not self.addr_type:
            if self.sig_type['addr_type']:
                self.addr_type = self.sig_type['addr_type']
            elif self.acct_info and len(self.acct_info) == 1:
                self.addr_type = self.acct_info[0]['fmt']

        # If we now have the necessary parts, build the deriv_path
        if self.addr_type != None:
            self.deriv_path = get_deriv_path_from_addr_type_and_acct(self.addr_type, self.acct_num, self.is_multisig())

        # If we didn't figure out the deriv_path yet, try to do it now
        if not self.deriv_path:
            if self.acct_info and len(self.acct_info) == 1:
                self.deriv_path = self.acct_info[0]['deriv']

            elif address:
                # We can derive it from the address now
                if not self.addr_type:  # Should be a redundant condition
                    self.addr_type = get_addr_type_from_address(address, self.is_multisig())

                self.deriv_path = get_deriv_path_from_address_and_acct(address, self.acct_num, self.is_multisig())

                if ms_wallet != None:
                    assert self.deriv_path == ms_wallet.my_deriv

            elif ms_wallet:
                # If the address was skipped, but we have the multisig wallet, get the derivation from it directly
                self.deriv_path = ms_wallet.my_deriv

                # If we still don't have the addr_type, we should be able to infer it from the deriv_path
                if not self.addr_type:
                    self.addr_type = get_addr_type_from_deriv(self.deriv_path)

    def prepare_to_export(self):
        system.show_busy_bar()

        self.infer_wallet_info()

        # We know the wallet type and sig type now so we can create the export data
        (data, self.acct_info) = self.sig_type['create_wallet'](
            sw_wallet=self.sw_wallet,
            addr_type=self.addr_type,
            acct_num=self.acct_num,
            multisig=self.is_multisig(),
            legacy=self.sig_type.get('legacy', False))

        self.infer_wallet_info()

        system.hide_busy_bar()

        # print('prepared data={} self.acct_info={}'.format(to_str(data), self.acct_info))
        # print('self.acct_info={}'.format(self.acct_info))
        return data

    async def import_multisig_config(self, data):
        from utils import show_top_menu, problem_file_line
        from auth import maybe_enroll_xpub

        try:
            maybe_enroll_xpub(config=data)
            await show_top_menu()

            return not common.is_new_wallet_a_duplicate

        except Exception as e:
            await ux_show_story('Invalid multisig configuration data.\n\n{}\n{}'.format(e, problem_file_line(e)), title='Error')
            return False

    def save_new_wallet_progress(self):
        progress = {
            'sw_wallet': self.sw_wallet['label'] if self.sw_wallet else None,
            'sig_type': self.sig_type['id'] if self.sig_type else None,
            'export_mode': self.export_mode['id'] if self.export_mode else None,
            'acct_info': self.acct_info,
            'acct_num': self.acct_num,
            'deriv_path': self.deriv_path,
            'verified': self.verified,
            'multisig_id': self.multisig_wallet.id if self.multisig_wallet else None,
            'exported': self.exported,
            'next_addr': self.next_addr,
            'addr_type': self.addr_type
        }
        settings.set('wallet_prog', progress)
        # print('Saving progress={}'.format(to_str(progress)))

    def abort_wallet_progress(self):
        # Make sure to delete the multisig wallet if it was created and we are now aborting
        if self.multisig_wallet:
            MultisigWallet.delete_by_id(self.multisig_wallet.id)
        settings.remove('wallet_prog')
        common.new_multisig_wallet = None
        common.is_new_wallet_a_duplicate = False

    def reset_wallet_progress(self):
        settings.remove('wallet_prog')
        common.new_multisig_wallet = None
        common.is_new_wallet_a_duplicate = False

    def is_multisig(self):
        return self.sig_type['id'] == 'multisig'

    def goto_address_verification_method(self, save_curr=True):
        method = self.sw_wallet.get('address_validation_method', 'scan_rx_address')
        if method == 'scan_rx_address':
            self.goto(self.SCAN_RX_ADDRESS_VERIFICATION_INTRO, save_curr=save_curr)
        elif method == 'show_addresses':
            self.goto(self.SHOW_RX_ADDRESSES_VERIFICATION_INTRO, save_curr=save_curr)

    def choose_multisig_import_mode(self):
        if 'mulitsig_import_mode' in self.export_mode:
            if self.export_mode['mulitsig_import_mode'] == EXPORT_MODE_QR:
                self.goto(self.IMPORT_MULTISIG_CONFIG_FROM_QR, save_curr=False)
            else:
                self.goto(self.IMPORT_MULTISIG_CONFIG_FROM_MICROSD, save_curr=False)
        elif self.export_mode['id'] == EXPORT_MODE_QR:
            self.goto(self.IMPORT_MULTISIG_CONFIG_FROM_QR, save_curr=False)
        else:
            self.goto(self.IMPORT_MULTISIG_CONFIG_FROM_MICROSD, save_curr=False)

    def is_address_verification_skip_enabled(self):
        if 'skip_address_validation' in self.sw_wallet:
            if self.sw_wallet['skip_address_validation'] == 'True':
                return True
            else:
                return False
        else:
            return False

    def is_skip_multisig_import_enabled(self):
        if 'skip_multisig_import' in self.sw_wallet:
            if self.sw_wallet['skip_multisig_import'] == 'True':
                return True
            else:
                return False
        else:
            return False

    def is_force_multisig_policy_enabled(self):
        if 'force_multisig_policy' in self.sw_wallet:
            if self.sw_wallet['force_multisig_policy'] == 'True':
                return True
            else:
                return False
        else:
            return False

    async def show(self):
        while True:
            # print('show: state={}'.format(self.state))
            if self.state == self.SELECT_ACCOUNT:
                self.acct_num = None
                accounts = get_accounts()
                if len(accounts) == 1:
                    self.acct_num = 0
                    self.goto(self.SELECT_SW_WALLET, save_curr=False)
                    continue

                await run_chooser(self.account_chooser, 'Account', show_checks=False)
                if self.acct_num == None:
                    if await self.confirm_abort():
                        return
                    else:
                        continue

                self.goto(self.SELECT_SW_WALLET)
                self.progress_made = True

            elif self.state == self.SELECT_SW_WALLET:
                # Choose a wallet from the available list
                self.sw_wallet = None

                await run_chooser(self.sw_wallet_chooser, 'Pair Wallet', show_checks=False)
                if self.sw_wallet == None:
                    if not self.goto_prev():
                        return
                    else:
                        continue

                # Save the progress so that we can resume later
                self.save_new_wallet_progress()

                self.goto(self.SELECT_SIG_TYPE)

            elif self.state == self.SELECT_SIG_TYPE:
                save_curr = True
                # We can skip this step if there is only one sig type
                if self.acct_num > 0:
                    # print('Non-zero accounts only support single-sig...skipping')
                    self.sig_type = find_sig_type_by_id(self.sw_wallet, 'single-sig', None)
                    save_curr = False
                elif len(self.sw_wallet['sig_types']) == 1:
                    # print('Only 1 sig type...skipping')
                    self.sig_type = self.sw_wallet['sig_types'][0]
                    save_curr = False
                else:
                    # Choose a wallet from the available list
                    self.sig_type = None

                    await run_chooser(self.sig_type_chooser, 'Type', show_checks=False)
                    if self.sig_type == None:
                        if not self.goto_prev():
                            return
                        continue

                    # See what we can infer so far
                    self.infer_wallet_info()

                    # Save the progress so that we can resume later
                    self.save_new_wallet_progress()

                    # print('self.sig_type={}'.format(self.sig_type))

                # NOTE: Nothing uses this option at the moment, but leaving it here in case we need it for a
                #       new wallet later.
                if self.sw_wallet.get('options', {}).get('select_addr_type', False):
                    self.goto(self.SELECT_ADDR_TYPE, save_curr=save_curr)
                else:
                    self.goto(self.SELECT_EXPORT_MODE, save_curr=save_curr)

            elif self.state == self.SELECT_ADDR_TYPE:
                # This step is normally only included for custom wallets or low-level wallets (e.g., electrum, bitcoin core)
                await run_chooser(self.singlesig_addr_type_chooser, 'Address Type', show_checks=False)
                if self.addr_type == None:
                    if not self.goto_prev():
                        return
                    continue

                # See what we can infer so far
                self.infer_wallet_info()

                # Save the progress so that we can resume later
                self.save_new_wallet_progress()

                self.goto(self.SELECT_EXPORT_MODE)

            elif self.state == self.SELECT_EXPORT_MODE:
                save_curr = True
                # We can skip this step if there is only a single export mode
                if len(self.sw_wallet['export_modes']) == 1:
                    # print('Only 1 export mode...skipping')
                    self.export_mode = self.sw_wallet['export_modes'][0]
                    # print('self.export_mode[\'id\']={}, self.export_mode={}'.format(self.export_mode['id'], self.export_mode))
                    save_curr = False
                else:
                    self.export_mode = None
                    await run_chooser(self.export_mode_chooser, 'Export By', show_checks=False)
                    if self.export_mode == None:
                        if not self.goto_prev():
                            return
                        continue

                # Save the progress so that we can resume later
                self.save_new_wallet_progress()

                self.goto(self.PAIRING_MESSAGE, save_curr=save_curr)

            elif self.state == self.PAIRING_MESSAGE:
                # Get the right message - use default if no custom value provided
                if self.export_mode['id'] == EXPORT_MODE_QR:
                    msg = self.get_custom_text('pairing_qr', 'Next, scan the QR code on the following screen into {}.'.format(self.sw_wallet['label']))
                elif self.export_mode['id'] == EXPORT_MODE_MICROSD:
                    ext = self.export_mode.get('ext_multisig', '.json') if self.is_multisig() else self.export_mode.get('ext', '.json')
                    msg = self.get_custom_text('pairing_microsd', 'Next, Passport will save a {} file to your microSD card to use with {}.'.format(ext, self.sw_wallet['label']))

                # Show pairing help text to the user
                result = await ux_show_story(msg, title='Pairing', scroll_label='MORE', center=True, center_vertically=True)
                if result == 'x':
                    if not self.goto_prev():
                        return
                    continue

                # Save the progress so that we can resume later
                self.save_new_wallet_progress()

                # Next state
                if self.export_mode['id'] == EXPORT_MODE_QR:
                    self.goto(self.EXPORT_TO_QR)
                elif self.export_mode['id'] == EXPORT_MODE_MICROSD:
                    self.goto(self.EXPORT_TO_MICROSD)

            elif self.state == self.EXPORT_TO_QR:
                data = self.prepare_to_export()

                # TODO: Do we need to encode the data to text for QR here? Some formats might not be text.

                qr_type = self.export_mode['qr_type']
                await ux_show_text_as_ur(title='Export QR', qr_text=data, qr_type=qr_type, left_btn='DONE')
                # Only way to get out is DONE, so no need to check result

                # Save the progress so that we can resume later
                self.exported = True
                self.save_new_wallet_progress()

                # If multisig, we need to import the quorum/config info first, else go right to validating the first
                # receive address from the wallet.
                if self.is_multisig():
                    # Only perform multisig import if wallet does not prevent it
                    if self.is_skip_multisig_import_enabled():
                        continue
                    else:
                        self.choose_multisig_import_mode()

                # Only perform address validation if wallet does not prevent it
                if self.is_address_verification_skip_enabled():
                    if self.is_force_multisig_policy_enabled():
                        result = await ux_show_story('For compatibility with {}, Passport will set your multisig policy to Skip Verification.\n{}'.format(self.sw_wallet['label']),
                        left_btn='NEXT',
                        center=True,
                        center_vertically=True)
                        if result == 'x':
                            if not self.goto_prev():
                                return
                        else:
                            settings.set('multisig_policy', TRUST_PSBT)
                            self.goto(self.CONFIRMATION)
                    else:
                        self.goto(self.CONFIRMATION)
                else:
                    self.goto_address_verification_method(save_curr=False)

            elif self.state == self.EXPORT_TO_MICROSD:
                from files import CardSlot
                from utils import xfp2str

                data = self.prepare_to_export()
                data_hash = bytearray(32)
                system.sha256(data, data_hash)
                fname = ''

                # Write the data to SD with the filename the wallet prefers
                filename_pattern = self.export_mode['filename_pattern_multisig'] if self.is_multisig() else self.export_mode['filename_pattern']
                try:
                    with CardSlot() as card:
                        # Make a filename with the option of injecting the sd path, hash of the data, acct num, random number
                        fname = filename_pattern.format(sd=card.get_sd_root(),
                                                        hash=data_hash,
                                                        acct=self.acct_num,
                                                        random=random_hex(8),
                                                        xfp=xfp2str(settings.get('xfp')).lower())
                        # print('Saving to fname={}'.format(fname))

                        # Write the data
                        with open(fname, 'wb') as fd:
                            fd.write(data)

                except Exception as e:
                    # includes CardMissingError
                    import sys
                    sys.print_exception(e)
                    # catch any error
                    ch = await ux_show_story('Unable to export wallet file. Please insert a formatted microSD card.\n\n' +
                                                str(e), title='Error', right_btn='RETRY', center=True, center_vertically=True)
                    if ch == 'x':
                        return

                    # Wrap around and try again
                    continue

                # Save the progress so that we can resume later
                self.exported = True
                self.save_new_wallet_progress()

                base_filename = fname.split(card.get_sd_root() + '/', 1)[1]
                result = await ux_show_story('Saved file to your microSD card.\n{}'.format(base_filename),
                                            title='Success',
                                            left_btn='NEXT',
                                            center=True,
                                            center_vertically=True)
                await sleep_ms(1000)

                # If multisig, we need to import the quorum/config info first, else go right to validating the first
                # receive address from the wallet.
                if self.is_multisig():
                    # Only perform multisig import if wallet does not prevent it
                    if self.is_skip_multisig_import_enabled():
                        continue
                    else:
                        self.choose_multisig_import_mode()

                # Only perform address validation if wallet does not prevent it
                if self.is_address_verification_skip_enabled():
                    if self.is_force_multisig_policy_enabled():
                        result = await ux_show_story('For compatibility with {}, Passport will set your multisig policy to Skip Verification.\n{}'.format(self.sw_wallet['label']),
                        left_btn='NEXT',
                        center=True,
                        center_vertically=True)
                        if result == 'x':
                            if not self.goto_prev():
                                return
                        else:
                            settings.set('multisig_policy', TRUST_PSBT)
                            self.goto(self.CONFIRMATION)
                    else:
                        self.goto(self.CONFIRMATION)
                else:
                    self.goto_address_verification_method(save_curr=False)

            elif self.state == self.IMPORT_MULTISIG_CONFIG_FROM_QR:
                while True:
                    msg = self.get_custom_text('multisig_import_qr', 'Next, import the multisig configuration from {} via QR code.'.format(self.sw_wallet['label']))
                    result = await ux_show_story(msg, title='Import Multisig', scroll_label="MORE", center=True, center_vertically=True)
                    if result == 'x':
                        if not self.goto_prev():
                            return
                        break

                    # Import the config info and save to settings
                    common.new_multisig_wallet = None
                    common.is_new_wallet_a_duplicate = False

                    data = await self.sig_type['import_qr']()
                    if data == None:
                        continue

                    # Now try to import the config data
                    result = await self.import_multisig_config(data)
                    if result == False:
                        self.abort_wallet_progress()
                        dis.fullscreen('Not Imported')
                        await sleep_ms(1000)
                        return

                    # Success
                    self.multisig_wallet = common.new_multisig_wallet
                    # print('**********************************************************************')
                    # print('multisig_wallet={}'.format(to_str(self.multisig_wallet)))
                    # print('**********************************************************************')

                    # See what we can infer so far
                    self.infer_wallet_info(ms_wallet=self.multisig_wallet)

                    # Save the progress so that we can resume later
                    self.save_new_wallet_progress()

                    self.goto_address_verification_method()
                    break

            elif self.state == self.IMPORT_MULTISIG_CONFIG_FROM_MICROSD:
                while True:
                    msg = self.get_custom_text('multisig_import_microsd', 'Next, import the multisig configuration from {} via microSD card.'.format(self.sw_wallet['label']))
                    result = await ux_show_story(msg, title='Import Multisig', scroll_label="MORE", center=True, center_vertically=True)
                    if result == 'x':
                        if not self.goto_prev():
                            return
                        break

                    # Import the config info and save to settings
                    common.new_multisig_wallet = None
                    common.is_new_wallet_a_duplicate = False

                    data = await self.sig_type['import_microsd']()
                    if data == None:
                        continue

                    # Now try to import the config data
                    result = await self.import_multisig_config(data)
                    if result == False:
                        self.abort_wallet_progress()
                        dis.fullscreen('Not Imported')
                        await sleep_ms(1000)
                        return

                    # Success
                    self.multisig_wallet = common.new_multisig_wallet

                    self.infer_wallet_info(ms_wallet=self.multisig_wallet)

                    # Save the progress so that we can resume later
                    self.save_new_wallet_progress()

                    self.goto_address_verification_method()

                    # Regardless of whether they used QR or microSD for import, they need to use QR for address validation
                    break

            elif self.state == self.SCAN_RX_ADDRESS_VERIFICATION_INTRO:
                msg = self.get_custom_text('scan_receive_addr', '''Next, let's check that the wallet was paired successfully.

Generate a new receive address in {} and scan the QR code on the next page.'''.format(self.sw_wallet['label']))
                result = await ux_show_story(msg, title='Verify Address', scroll_label="MORE", center=True, center_vertically=True)
                if result == 'x':
                    if not self.goto_prev():
                        return
                    continue

                self.goto(self.SCAN_RX_ADDRESS)

            elif self.state == self.SCAN_RX_ADDRESS:
                # Scan the address to be verified - should be a normal QR code
                system.turbo(True)
                address = await ux_scan_qr_code('Verify Address')
                system.turbo(False)

                if address == None:
                    # User backed out without scanning an address
                    result = await ux_confirm('No address was scanned. Do you want to skip address verification?')
                    if result:
                        # Skipping address scan
                        self.infer_wallet_info(ms_wallet=self.multisig_wallet)
                        self.save_new_wallet_progress()
                        self.goto(self.CONFIRMATION)
                    else:
                        result = await ux_confirm('Retry address verification?', negative_btn='BACK', positive_btn='RETRY')
                        if not result:
                            self.goto_prev()
                    continue

                address, is_valid_btc = await is_valid_btc_address(address)
                if is_valid_btc == False:
                    if not self.goto_prev():
                        return
                    continue

                # Use address to nail down deriv_path and addr_type, if not yet known
                self.infer_wallet_info(address=address)

                result = do_address_verify(self.acct_num, address, self.addr_type, self.deriv_path, self.multisig_wallet)
                if result == False:
                    result = await ux_show_story('Do you want to SKIP address verification or SCAN another address?', title='Not Found', left_btn='SKIP',
                                                 right_btn='SCAN', center=True, center_vertically=True)
                    if result == 'x':
                        # Skipping address scan
                        self.infer_wallet_info(ms_wallet=self.multisig_wallet)
                        self.goto(self.CONFIRMATION)
                else:
                    # Address was found!
                    self.verified = True
                    self.goto(self.CONFIRMATION)
                    continue
            
                # else loop around and scan again

            elif self.state == self.SHOW_RX_ADDRESSES_VERIFICATION_INTRO:
                msg = self.get_custom_text('show_receive_addr', '''Next, let's check that {name} was paired successfully.

{name} should display a list of addresses associated with this wallet.

Compare them with the addresses shown on the next screen to make sure they match.'''.format(name=self.sw_wallet['label']))
                result = await ux_show_story(msg, title='Verify Address', scroll_label="MORE", center=True, center_vertically=True)
                if result == 'x':
                    if not self.goto_prev():
                        return
                    continue

                self.goto(self.SHOW_RX_ADDRESSES)

            elif self.state == self.SHOW_RX_ADDRESSES:
                from display import FontTiny
                NUM_ADDRESSES = 3
                system.show_busy_bar()
                dis.fullscreen('Generating Addresses...')
                addresses = get_addresses_in_range(0, NUM_ADDRESSES, self.addr_type, self.acct_num, self.multisig_wallet)
                system.hide_busy_bar()

                msg = 'First {} Addresses'.format(NUM_ADDRESSES)

                for entry in addresses:
                    deriv_path, address = entry
                    msg += '\n\n{}\n{}'.format(deriv_path, address)

                await ux_show_story(msg, title='Verify', center=True, font=FontTiny)
                if result == 'x':
                    if not self.goto_prev():
                        return
                else:
                    self.goto(self.CONFIRMATION)

            elif self.state == self.CONFIRMATION:
                # Reset so we don't offer to resume again later
                self.reset_wallet_progress()

                # Offer to backup if a multisig wallet was added
                if self.multisig_wallet:
                    from export import offer_backup
                    await offer_backup()

                dis.fullscreen('Pairing Complete')
                await sleep_ms(1000)

                return

            elif self.state == self.RESUME_PROGRESS:
                msg = 'Passport was in the middle of creating a new account with the following selections:\n\n'

                if self.acct_num != None:
                    msg += '- {}\n'.format(self.get_account_description(self.acct_num))

                if self.sw_wallet:
                    msg += '- {}\n'.format(self.sw_wallet['label'])

                if self.sig_type:
                    msg += '- {}\n'.format(self.sig_type['label'])

                if self.export_mode:
                    msg += '- {}\n'.format(self.export_mode['label'])

                msg += '\nWould you like to RESUME creating this new account from where you left off, or CANCEL and lose all progress?'

                result = await ux_show_story(msg, title='Resume?', left_btn='CANCEL', right_btn='RESUME', scroll_label="MORE")

                if result == 'x':
                    if await self.confirm_abort():
                        return
                    else:
                        continue

                # print('Resuming New Wallet flow: self={}'.format(to_str(self)))

                # Resume based on where the user left off before
                if not self.sw_wallet:
                    self.goto(self.SELECT_SW_WALLET)
                    continue
                elif not self.sig_type:
                    self.goto(self.SELECT_SIG_TYPE)
                    continue
                elif not self.export_mode:
                    self.goto(self.SELECT_EXPORT_MODE)
                    continue
                elif not self.exported:
                    self.goto(self.PAIRING_MESSAGE)
                    continue

                if self.is_multisig():
                    if self.is_skip_multisig_import_enabled():
                        continue
                    else:
                        # Need to import the multisig wallet
                        self.choose_multisig_import_mode()
                        continue

                if not self.verified:
                    if self.is_address_verification_skip_enabled():
                        if self.is_force_multisig_policy_enabled():
                            result = await ux_show_story('For compatibility with {}, Passport will set your multisig policy to Skip Verification.\n{}'.format(self.sw_wallet['label']),
                            left_btn='NEXT',
                            center=True,
                            center_vertically=True)
                            if result == 'x':
                                if not self.goto_prev():
                                    return
                            else:
                                settings.set('multisig_policy', TRUST_PSBT)
                                self.goto(self.CONFIRMATION)
                        else:
                            self.goto(self.CONFIRMATION)
                    else:
                        self.goto(self.SCAN_RX_ADDRESS)
                        continue
