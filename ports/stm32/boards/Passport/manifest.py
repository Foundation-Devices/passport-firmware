# SPDX-FileCopyrightText: 2020 Foundation Devices, Inc. <hello@foundationdevices.com>
# SPDX-License-Identifier: GPL-3.0-or-later
#

freeze('$(MPY_DIR)/drivers/dht', 'dht.py')
freeze('$(MPY_DIR)/drivers/display', ('lcd160cr.py', 'lcd160cr_test.py'))
freeze('$(MPY_DIR)/drivers/onewire', 'onewire.py')
freeze('$(MPY_DIR)/ports/stm32/boards/Passport/modules',
       ('common.py', 'main.py', 'keypad.py', 'display.py', 'graphics.py', 'passport_fonts.py', 'auth.py',
        'files.py', 'ux.py', 'version.py', 'flow.py', 'actions.py', 'utils.py', 'choosers.py',
        'menu.py', 'settings.py', 'sram4.py', 'sffile.py', 'collections/deque.py', 'uQR.py', 'constants.py',
        'callgate.py', 'pincodes.py', 'stash.py', 'login_ux.py', 'public_constants.py', 'seed.py', 'chains.py',
        'opcodes.py', 'bip39_utils.py', 'seed_entry_ux.py', 'sflash.py', 'snake.py', 'stacking_sats.py',
        'se_commands.py', 'serializations.py', 'seed_check_ux.py', 'export.py', 'compat7z.py', 'multisig.py', 'psbt.py',
        'periodic.py', 'exceptions.py', 'noise_source.py', 'self_test_ux.py', 'flash_cache.py',
        'history.py', 'accounts.py', 'log.py', 'descriptor.py', 'accept_terms_ux.py', 'new_wallet.py', 'stat.py',
        'uasyncio/__init__.py', 'uasyncio/core.py', 'uasyncio/queues.py', 'uasyncio/synchro.py', 'ie.py',
        'schema_evolution.py'))
freeze('$(MPY_DIR)/ports/stm32/boards/Passport/modules',
       ('ur1/__init__.py', 'ur1/bc32.py', 'ur1/bech32.py', 'ur1/bech32_version.py', 'ur1/decode_ur.py', 'ur1/encode_ur.py',
        'ur1/mini_cbor.py', 'ur1/utils.py'))
freeze('$(MPY_DIR)/ports/stm32/boards/Passport/modules',
       ('ur2/__init__.py', 'ur2/bytewords.py', 'ur2/cbor_lite.py', 'ur2/constants.py', 'ur2/crc32.py', 'ur2/fountain_decoder.py',
        'ur2/fountain_encoder.py', 'ur2/fountain_utils.py', 'ur2/random_sampler.py', 'ur2/ur_decoder.py', 'ur2/ur_encoder.py',
        'ur2/ur.py', 'ur2/utils.py', 'ur2/xoshiro256.py'))
freeze('$(MPY_DIR)/ports/stm32/boards/Passport/modules',
       ('data_codecs/__init__.py', 'data_codecs/data_format.py', 'data_codecs/data_decoder.py', 'data_codecs/data_encoder.py',
        'data_codecs/data_sampler.py', 'data_codecs/qr_factory.py', 'data_codecs/qr_codec.py', 'data_codecs/ur1_codec.py', 'data_codecs/ur2_codec.py',
        'data_codecs/multisig_config_sampler.py', 'data_codecs/psbt_txn_sampler.py', 'data_codecs/seed_sampler.py',
        'data_codecs/address_sampler.py', 'data_codecs/http_sampler.py', 'data_codecs/qr_type.py', 'data_codecs/sign_message_sampler.py'))
freeze('$(MPY_DIR)/ports/stm32/boards/Passport/modules',
       ('wallets/sw_wallets.py', 'wallets/bluewallet.py', 'wallets/electrum.py', 'wallets/constants.py', 'wallets/utils.py',
        'wallets/multisig_json.py', 'wallets/multisig_import.py', 'wallets/generic_json_wallet.py', 'wallets/sparrow.py',
        'wallets/bitcoin_core.py', 'wallets/wasabi.py', 'wallets/btcpay.py', 'wallets/gordian.py', 'wallets/lily.py',
        'wallets/fullynoded.py', 'wallets/dux_reserve.py', 'wallets/specter.py', 'wallets/casa.py', 'wallets/vault.py',
        'wallets/caravan.py', 'wallets/simple_bitcoin_wallet.py', 'wallets/nunchuk.py'))
