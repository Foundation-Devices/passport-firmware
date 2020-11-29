# SPDX-FileCopyrightText: 2020 Foundation Devices, Inc.  <hello@foundationdevices.com>
# SPDX-License-Identifier: GPL-3.0-or-later
#

freeze('$(MPY_DIR)/drivers/dht', 'dht.py')
freeze('$(MPY_DIR)/drivers/display', ('lcd160cr.py', 'lcd160cr_test.py'))
freeze('$(MPY_DIR)/drivers/onewire', 'onewire.py')
freeze('$(MPY_DIR)/ports/stm32/boards/Passport/modules',
       ('common.py', 'main.py', 'keypad.py', 'display.py', 'graphics.py', 'passport_fonts.py', 'auth.py',
        'files.py', 'ux.py', 'version.py', 'flow.py', 'actions.py', 'utils.py', 'choosers.py', 'address_explorer.py',
        'menu.py', 'settings.py', 'sram4.py', 'sffile.py', 'collections/deque.py', 'uQR.py', 'constants.py',
        'callgate.py', 'pincodes.py', 'stash.py', 'login_ux.py', 'public_constants.py', 'seed.py', 'chains.py', 'opcodes.py',
        'bip39_utils.py', 'seed_phrase_ux.py', 'sflash.py', 'snake.py', 'stacksats.py', 'se_commands.py', 'serializations.py',
        'backups.py', 'compat7z.py', 'multisig.py', 'psbt.py', 'battery_mon.py',
        'uasyncio/__init__.py', 'uasyncio/core.py', 'uasyncio/queues.py', 'uasyncio/synchro.py'))
freeze('$(MPY_DIR)/ports/stm32/boards/Passport/modules',
       ('ur/__init__.py', 'ur/bytewords.py', 'ur/cbor_lite.py', 'ur/constants.py', 'ur/crc32.py', 'ur/fountain_decoder.py',
        'ur/fountain_encoder.py', 'ur/fountain_utils.py', 'ur/random_sampler.py', 'ur/ur_decoder.py', 'ur/ur_encoder.py',
        'ur/ur.py', 'ur/utils.py', 'ur/xoshiro256.py'))
freeze('$(MPY_DIR)/ports/stm32/boards/Passport/modules',
       ('ur1/__init__.py', 'ur1/bc32.py', 'ur1/bech32.py', 'ur1/bech32_version.py', 'ur1/decode_ur.py', 'ur1/encode_ur.py',
        'ur1/mini_cbor.py', 'ur1/utils.py'))
