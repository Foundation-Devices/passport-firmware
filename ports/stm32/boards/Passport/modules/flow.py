# SPDX-FileCopyrightText: 2020 Foundation Devices, Inc.  <hello@foundationdevices.com>
# SPDX-License-Identifier: GPL-3.0-or-later
#
# SPDX-FileCopyrightText: 2018 Coinkite, Inc.  <coldcardwallet.com>
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
# from multisig import make_multisig_menu

def has_secrets():
    from common import pa
    return not pa.is_secret_blank()


ExportWalletMenu = [
    # Alphabetical order
    MenuItem('BlueWallet', f=xpub_qr),
    MenuItem('BTCPay', f=electrum_skeleton),
    MenuItem('Casa', f=electrum_skeleton),
    MenuItem('Electrum', f=electrum_skeleton),
    MenuItem('Fully Noded', f=electrum_skeleton),
    MenuItem('Gordian', f=electrum_skeleton),
    MenuItem('Lily', f=electrum_skeleton),
    MenuItem('Sparrow', f=electrum_skeleton),
    MenuItem('Specter', f=electrum_skeleton),
    MenuItem('Wasabi', f=wasabi_skeleton),
    MenuItem('Other', f=electrum_skeleton),
]

UpdateMenu = [
    MenuItem('Update Firmware', f=microsd_upgrade),
    MenuItem('Current Version', f=show_version),
]

SDCardMenu = [
    #MenuItem("Verify Backup", f=verify_backup),
    #MenuItem("Backup System", f=backup_everything),
    MenuItem("Dump Summary", f=dump_summary),
    MenuItem('Export Wallet', menu=ExportWalletMenu),
    #MenuItem('Sign Text File', predicate=has_secrets, f=sign_message_on_sd),
    #MenuItem('Upgrade From SD', f=microsd_upgrade),
    MenuItem('Format Card', f=wipe_sd_card),
    MenuItem('List Files', f=list_files),
]

AdvancedMenu = [
    MenuItem('Change PIN', f=change_pin),
    MenuItem("MicroSD Settings", menu=SDCardMenu),
    MenuItem("List Addresses", f=coming_soon),
    MenuItem('View Seed Words', f=view_seed_words,
             predicate=lambda: settings.get('words', True)),
    MenuItem("Erase Wallet", f=clear_seed),

    # TODO: Don't we want to allow for this?
    # MenuItem('Lock Down Seed', f=convert_bip39_to_bip32,
    #          predicate=lambda: settings.get('words', True)),
]

BackupMenu = [
    MenuItem("Create Backup", menu=coming_soon), #f=backup_everything),
    MenuItem("Verify Backup", menu=coming_soon), #f=verify_backup),
    MenuItem("Restore Backup", menu=coming_soon), #f=restore_everything),
]

SettingsMenu = [
    MenuItem("About", f=view_ident),
    MenuItem('Pair External Wallet', menu=ExportWalletMenu, menu_title='Pair Wallet'),
    MenuItem('Sign Text File', predicate=has_secrets, f=sign_message_on_sd),
    MenuItem("Update Firmware", menu=UpdateMenu),
    MenuItem('Backup Passport', menu=BackupMenu),
    MenuItem('Multisig Settings', menu=coming_soon), # make_multisig_menu),
    MenuItem('Screen Brightness', chooser=brightness_chooser),
    MenuItem('Auto Shutdown', chooser=idle_timeout_chooser),
    MenuItem('Advanced Settings', menu=AdvancedMenu, menu_title='Advanced')
]

NoWalletSettingsMenu = [
    MenuItem("About", f=view_ident),
    MenuItem("Update Firmware", menu=UpdateMenu),
    MenuItem('Screen Brightness', chooser=brightness_chooser),
    MenuItem('Auto Shutdown', chooser=idle_timeout_chooser),
    MenuItem('Change PIN', f=change_pin),
]

# User has not entered a PIN yet - Need to be able to update firmware
NoPINMenu = [
    MenuItem('Select PIN', f=initial_pin_setup),
    MenuItem('Update Firmware', menu=UpdateMenu),
]

ImportMenu = [
    MenuItem("24 Words", menu=start_seed_import, arg=24),
    MenuItem("18 Words", menu=start_seed_import, arg=18),
    MenuItem("12 Words", menu=start_seed_import, arg=12),
    MenuItem("Import XPRV", f=import_xprv),
    MenuItem("Dice Rolls", f=import_from_dice),
]

# has PIN, but no secret seed yet
NoWalletMenu = [
    MenuItem('New Wallet', f=create_new_wallet),
    MenuItem('Import Wallet', f=import_wallet, arg=24),
    MenuItem('Settings', menu=NoWalletSettingsMenu),
]

DeveloperMenu = [
    MenuItem('Battery Monitor', f=battery_mon),
    MenuItem('Pair External Wallet', menu=ExportWalletMenu, menu_title='Pair Wallet'),
    MenuItem('New Wallet', f=create_new_wallet),
    MenuItem('Import Wallet', f=import_wallet, arg=24),
    MenuItem('View Seed Words', f=view_seed_words,
             predicate=lambda: settings.get('words', True)),
    MenuItem('Select PIN', f=initial_pin_setup),
    MenuItem('Login', f=block_until_login),
    MenuItem('Update XPUB/XFP', f=update_xpub),
    MenuItem('Update Firmware', f=microsd_upgrade),
    MenuItem('Format SD Card', f=wipe_sd_card),
    MenuItem('Enter 12-Word Seed', f=enter_seed_phrase, arg=12),
    MenuItem('Enter 24-Word Seed', f=enter_seed_phrase, arg=24),
    MenuItem('Sign with QR Code', f=sign_tx_from_qr, arg="Scan QR Code"),
    MenuItem('Dump Settings', menu=dump_settings),
    MenuItem('Get Serial', f=se_get_version),
    MenuItem('Get Config.', f=se_get_config),
    MenuItem('Gen. Random', f=gen_random),
    MenuItem('Power Mon.', f=show_power_monitor),
    MenuItem('Board Rev.', f=show_board_rev),
    MenuItem("UR Unit Tests", f=test_ur),
    MenuItem("Test UR Encoder", f=test_ur_encoder),
    MenuItem('Factory Setup', f=factory_setup),

    # Run these three to do a "factory reset"
    MenuItem('Erase User Settings', f=erase_user_settings),
    MenuItem("Erase Wallet", f=clear_seed_no_reset),
    MenuItem('Set Blank PIN',f=set_blank_pin),

    MenuItem('Erase ROM Secrets', f=erase_rom_secrets),
    MenuItem('Test UR1.0', f=test_ur1),
]

MainMenu = [
    MenuItem('9 Developer Menu', menu=DeveloperMenu),
    MenuItem('Sign with QR Code', f=sign_tx_from_qr, arg="Scan QR Code"),
    MenuItem('Sign with microSD', f=sign_tx_from_sd),
    MenuItem('Verify Address', f=coming_soon, arg="Verify Address"),
    MenuItem('Enter Passphrase', f=enter_passphrase, arg="Passphrase"),
    MenuItem('Settings', menu=SettingsMenu),
]

GamesMenu = [
    MenuItem('Developer Menu', menu=DeveloperMenu),
    MenuItem('Snakamoto', f=play_snake),
    MenuItem('StackSats', f=play_stacksats)
]
