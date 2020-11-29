# SPDX-FileCopyrightText: 2020 Foundation Devices, Inc.  <hello@foundationdevices.com>
# SPDX-License-Identifier: GPL-3.0-or-later
#

USE_MBOOT ?= 0

# MCU settings
MCU_SERIES = h7
CMSIS_MCU = STM32H753xx
MICROPY_FLOAT_IMPL = double
AF_FILE = boards/stm32h753_af.csv

LD_FILES = boards/Passport/passport.ld boards/common_ifs.ld
TEXT0_ADDR = 0x08020800

# MicroPython settings
MICROPY_PY_LWIP = 1
MICROPY_PY_USSL = 1
MICROPY_SSL_MBEDTLS = 1

FROZEN_MANIFEST = boards/Passport/manifest.py

CFLAGS_MOD += -Iboards/$(BOARD)/trezor-firmware/crypto
CFLAGS_MOD += -DMICROPY_PY_TREZORCRYPTO=1 -DBITCOIN_ONLY=1 -DAES_128=1 -DAES_192=1
SRC_MOD += $(addprefix boards/$(BOARD)/trezor-firmware/crypto/,\
				bignum.c ecdsa.c curves.c secp256k1.c nist256p1.c memzero.c \
				hmac.c pbkdf2.c \
				bip32.c bip39.c base58.c base32.c segwit_addr.c \
				address.c script.c \
				ripemd160.c sha2.c sha3.c hasher.c \
				blake256.c blake2b.c blake2s.c \
				aes/aescrypt.c aes/aeskey.c aes/aestab.c aes/aes_modes.c \
				ed25519-donna/curve25519-donna-32bit.c \
				ed25519-donna/curve25519-donna-helpers.c \
				ed25519-donna/modm-donna-32bit.c \
				ed25519-donna/ed25519-donna-basepoint-table.c \
				ed25519-donna/ed25519-donna-32bit-tables.c \
				ed25519-donna/ed25519-donna-impl-base.c \
				ed25519-donna/ed25519.c \
				ed25519-donna/curve25519-donna-scalarmult-base.c \
				ed25519-donna/ed25519-keccak.c \
				ed25519-donna/ed25519-sha3.c \
				chacha20poly1305/chacha20poly1305.c \
				chacha20poly1305/chacha_merged.c \
				chacha20poly1305/poly1305-donna.c \
				chacha20poly1305/rfc7539.c \
				shamir.c groestl.c slip39.c rand.c rfc6979.c \
				hmac_drbg.c )

# settings that apply only to crypto C-lang code
build-Passport/boards/Passport/crypto/%.o: CFLAGS_MOD += \
	-DUSE_BIP39_CACHE=0 -DBIP32_CACHE_SIZE=0 -DUSE_BIP32_CACHE=0 -DBIP32_CACHE_MAXDEPTH=0 \
	-DRAND_PLATFORM_INDEPENDENT=1 -DUSE_BIP39_GENERATE=0 -DUSE_BIP32_25519_CURVES=0

CFLAGS_MOD += -Iboards/$(BOARD)/trezor-firmware/core/embed/extmod/modtrezorcrypto -Iboards/$(BOARD)/trezor-firmware/core
SRC_MOD += $(addprefix boards/$(BOARD)/trezor-firmware/core/embed/extmod/modtrezorcrypto/, modtrezorcrypto.c crc.c)

BL_NVROM_BASE = 0x081c0000
BL_NVROM_SIZE = 0x20000
CFLAGS_MOD += -DBL_NVROM_BASE=$(BL_NVROM_BASE) -DBL_NVROM_SIZE=$(BL_NVROM_SIZE)
CFLAGS_MOD += -Iboards/$(BOARD)/include

# include code common to both the bootloader and firmware
SRC_MOD += $(addprefix boards/$(BOARD)/common/,\
				delay.c \
                                lcd-sharp-ls018B7dh02.c \
				pprng.c \
				se.c \
				sha256.c \
				spiflash.c \
				utils.c )
