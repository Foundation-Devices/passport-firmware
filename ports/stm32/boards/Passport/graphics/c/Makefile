# SPDX-FileCopyrightText: 2020 Foundation Devices, Inc. <hello@foundationdevices.com>
# SPDX-License-Identifier: GPL-3.0-or-later
#
# SPDX-FileCopyrightText: 2018 Coinkite, Inc. <coldcardwallet.com>
# SPDX-License-Identifier: GPL-3.0-only
#
# (c) Copyright 2018 by Coinkite Inc. This file is part of Coldcard <coldcardwallet.com>
# and is covered by GPLv3 license found in COPYING.

all: bootloader_graphics.c firmware_graphics.c

BOOTLOADER_SOURCES = splash.png

bootloader_graphics.c: Makefile $(BOOTLOADER_SOURCES) cbuild.py
	python3 cbuild.py bootloader_graphics $(BOOTLOADER_SOURCES)

FIRMWARE_SOURCES =  $(wildcard busybar*.png)

firmware_graphics.c: Makefile $(FIRMWARE_SOURCES) cbuild.py
	python3 cbuild.py firmware_graphics $(FIRMWARE_SOURCES)


up: all
	(cd ../shared; make up)
