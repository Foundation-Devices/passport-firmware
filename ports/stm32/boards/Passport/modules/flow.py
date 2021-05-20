# SPDX-FileCopyrightText: 2020 Foundation Devices, Inc. <hello@foundationdevices.com>
# SPDX-License-Identifier: GPL-3.0-or-later
#
# SPDX-FileCopyrightText: 2018 Coinkite, Inc. <coldcardwallet.com>
# SPDX-License-Identifier: GPL-3.0-only
#
# (c) Copyright 2018 by Coinkite Inc. This file is part of Coldcard <coldcardwallet.com>
# and is covered by GPLv3 license found in COPYING.
#
# flow.py - Menu structure
#
import version
from actions import *
# from address_explorer import address_explore
from choosers import *
from common import settings
from menu import MenuItem
from public_constants import AF_P2WPKH
from multisig import make_multisig_menu
from wallets.utils import has_export_mode
from export import view_backup_password
from utils import is_new_wallet_in_progress, get_accounts
from new_wallet import pair_new_wallet
from ie import show_browser

FirmwareMenu = [
    MenuItem('Update Firmware', f=update_firmware),
    MenuItem('Current Version', f=show_version),
]

SDCardMenu = [
    MenuItem('Format Card', f=format_sd_card),
    MenuItem('List Files', f=list_files),
    MenuItem('Export Summary', f=export_summary),
]

def archived_accounts_exist():
    accounts = get_accounts()
    for account in accounts:
        if account.get('status') == 'r':
            return True
    return False

def has_secrets():
    from common import pa
    return not pa.is_secret_blank()

AdvancedMenu = [
    MenuItem('Change PIN', f=change_pin),
    MenuItem('Passphrase', menu_title='Passphrase', chooser=enable_passphrase_chooser),
    MenuItem('Sign Text File', predicate=has_secrets, f=sign_message_on_sd),
    MenuItem('MicroSD Settings', menu=SDCardMenu),
    MenuItem('View Seed Words', f=view_seed_words, predicate=lambda: settings.get('words', True)),
    MenuItem('Developer PubKey', f=import_user_firmware_pubkey),
    MenuItem('Erase Passport', f=erase_wallet, arg=True)
]

BackupMenu = [
    MenuItem('Create Backup', f=make_microsd_backup),
    MenuItem('Verify Backup', f=verify_microsd_backup),
    MenuItem('View Password', f=view_backup_password),
    MenuItem('Restore Backup', f=restore_microsd_backup),
]

SettingsMenu = [
    MenuItem('About', f=about_info),
    MenuItem('Firmware', menu=FirmwareMenu),
    MenuItem('Backup', menu=BackupMenu),
    MenuItem('Screen Brightness', chooser=brightness_chooser),
    MenuItem('Auto Shutdown', chooser=shutdown_timeout_chooser),
    MenuItem('Multisig', menu=make_multisig_menu, arg='Multisig'),
    MenuItem('Accounts', menu=make_accounts_menu, arg='Accounts'),
    MenuItem('Advanced', menu=AdvancedMenu, menu_title='Advanced')
]

NoWalletSettingsMenu = [
    MenuItem('About', f=about_info),
    MenuItem('Firmware', menu=FirmwareMenu),
    MenuItem('Screen Brightness', chooser=brightness_chooser),
    MenuItem('Auto Shutdown', chooser=shutdown_timeout_chooser),
    MenuItem('Change PIN', f=change_pin),
]

# ManageAcctMenu = [
#     MenuItem('About', f=account_info),
#     MenuItem('Export by QR', f=export_wallet_qr, predicate=lambda:has_export_mode('qr')),
#     MenuItem('Export by microSD', f=export_wallet_microsd, predicate=lambda: has_export_mode('microsd')),
#     MenuItem('Rename', f=rename_account),
#     MenuItem('Archive', f=archive_account)
# ]

def not_account_zero():
    return common.active_account.get('acct_num') > 0

AccountMenu = [
    MenuItem('Rename', f=rename_account),
    MenuItem('Delete', f=delete_account, predicate=not_account_zero),
]

SeedLengthMenu = [
    MenuItem('24-Word Seed', f=restore_wallet_from_seed, arg=24),
    MenuItem('18-Word Seed', f=restore_wallet_from_seed, arg=18),
    MenuItem('12-Word Seed', f=restore_wallet_from_seed, arg=12),
]

# Has PIN, but no secret seed yet
NoSeedMenu = [
    MenuItem('Create New Seed', f=create_new_seed),
    MenuItem('Restore Seed', menu=SeedLengthMenu, menu_title='Seed Length'),
    MenuItem('Restore Backup', f=restore_microsd_backup),
    MenuItem('Settings', menu=NoWalletSettingsMenu, menu_title='Settings'),
]

from noise_source import NoiseSource

DeveloperMenu = [
    # MenuItem('Settings Error 2', f=generate_settings_error2),
    # MenuItem('Settings Error', f=generate_settings_error),
    MenuItem('Clear OVC', f=clear_ovc),
    MenuItem('Test UR1', f=test_ur1),
    MenuItem('Reset Device', f=reset_device),
    MenuItem('Test Battery Calcs', f=test_battery_calcs),
    # MenuItem('Test Folder', f=test_folders),
    # MenuItem('Test Enter Number', f=test_num_entry),
    MenuItem('Settings', menu=SettingsMenu),
    MenuItem('Clear Accts/Multisig', f=clear_accts),
    MenuItem('Dump Settings', menu=dump_settings),
    MenuItem('Dump Flash Cache', menu=dump_flash_cache),
    MenuItem('Toggle Battery Mon', f=toggle_battery_mon),
    MenuItem('Toggle Screenshot', f=toggle_screenshot_mode),
    MenuItem('Toggle Snapshot', f=toggle_snapshot_mode),
    MenuItem('Write Flash Cache', f=test_write_flash_cache),
    MenuItem('Read Flash Cache', f=test_read_flash_cache),
    MenuItem('Supply Chain Test', f=supply_chain_challenge),
    # MenuItem('Address Explorer', f=address_explore),
    MenuItem('Import User PubKey', f=import_user_firmware_pubkey),
    MenuItem('Read User PubKey', f=read_user_firmware_pubkey),
    MenuItem('Test Derive Addrs', f=test_derive_addresses),
    MenuItem('Test Seed Check', f=test_seed_check),
    MenuItem('Enter Passphrase', f=enter_passphrase, arg='Passphrase'),
    MenuItem('Random: All', f=gen_random, arg=NoiseSource.ALL),
    # MenuItem('Random: All Except SE', f=gen_random, arg=NoiseSource.AVALANCHE | NoiseSource.MCU | NoiseSource.AMBIENT_LIGHT_SENSOR),
    MenuItem('Random: Avalanche', f=gen_random, arg=NoiseSource.AVALANCHE),
    MenuItem('Read Ambient', f=read_ambient),
    # MenuItem('Battery Monitor', f=battery_mon),
    MenuItem('Create New Seed', f=create_new_seed),
    MenuItem('Restore SD Card', f=restore_microsd_backup),
    MenuItem('View Seed Words', f=view_seed_words, predicate=lambda: settings.get('words', True)),
    MenuItem('Select PIN', f=initial_pin_setup),
    MenuItem('Login', f=block_until_login),
    MenuItem('Update XPUB/XFP', f=update_xpub),
    MenuItem('Update Firmware', f=update_firmware),
    MenuItem('Format SD Card', f=format_sd_card),
    MenuItem('Enter 12-Word Seed', f=enter_seed_phrase, arg=12),
    MenuItem('Enter 24-Word Seed', f=enter_seed_phrase, arg=24),
    MenuItem('Sign with QR Code', f=magic_scan, arg='Scan QR Code'),
    MenuItem('Get Config.', f=se_get_config),
    MenuItem('Power Mon.', f=show_power_monitor),
    MenuItem('Board Rev.', f=show_board_rev),
    MenuItem('UR Unit Tests', f=test_ur),
    MenuItem('Test UR Encoder', f=test_ur_encoder),

    # Run these three to do a "factory reset"
    MenuItem('Erase User Settings', f=erase_user_settings),
    MenuItem('Erase Passport', f=erase_wallet, arg=False),
    # MenuItem('Set Blank PIN', f=set_blank_pin),

    MenuItem('Test UR1.0', f=test_ur1),
]

MainMenu = [
    # MenuItem('Developer Menu', menu=DeveloperMenu),
    # MenuItem('Start/Stop Demo', f=toggle_demo),
    MenuItem('Sign with QR Code', f=magic_scan, arg='Scan QR Code'),
    MenuItem('Sign with microSD', f=sign_tx_from_sd),
    MenuItem('Verify Address', f=verify_address, arg='Verify Address'),
    # Show Resume or Pair Wallet menu depending on status
    MenuItem('Resume Pair Wallet', f=pair_new_wallet, predicate=is_new_wallet_in_progress),
    MenuItem('Pair Wallet', f=pair_new_wallet, predicate=lambda: not is_new_wallet_in_progress(), arg='Pair Wallet'),
    MenuItem('Settings', menu=SettingsMenu, menu_title='Settings'),
]

ExtrasMenu = [
    # MenuItem('Developer Menu', menu=DeveloperMenu),
    MenuItem('Snakamoto', f=play_snake),
    MenuItem('Stacking Sats', f=play_stacking_sats),
    MenuItem('Internet Browser', f=show_browser)
]
