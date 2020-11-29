# SPDX-FileCopyrightText: 2020 Foundation Devices, Inc.  <hello@foundationdevices.com>
# SPDX-License-Identifier: GPL-3.0-or-later
#
# SPDX-FileCopyrightText: 2018 Coinkite, Inc.  <coldcardwallet.com>
# SPDX-License-Identifier: GPL-3.0-only
#
# "Bootloader" Makefile
#
# Targets:
#	all - make everything, look for dafu.elf inparticular
#	clean - delete intermediates
#	clobber - delete all build products
#

# Toolchain
TOOLCHAIN = arm-none-eabi-
CC = $(TOOLCHAIN)gcc
OBJDUMP = $(TOOLCHAIN)objdump
OBJCOPY = $(TOOLCHAIN)objcopy
NM = $(TOOLCHAIN)nm
SIZE = $(TOOLCHAIN)size

TOP = ../../..
MPY_TOP = $(TOP)/../..

# Headers for ST HAL
LIB_PATH = $(MPY_TOP)/lib
HAL_DRIVERS_PATH = $(MPY_TOP)/lib/stm32lib/STM32H7xx_HAL_Driver/Src
HAL_CMSIS_PATH = $(MPY_TOP)/lib/stm32lib/CMSIS/STM32H7xx/Source/Templates
PASSPORT_PATH = ..

VPATH  = $(HAL_DRIVERS_PATH)
VPATH += $(HAL_CMSIS_PATH)
VPATH += $(PASSPORT_PATH)/common
VPATH += $(PASSPORT_PATH)/common/micro-ecc

# Basename of all targets
TARGET_NAME = bootloader

# Source files. Important: Add them also to link-script.ld to control placement.
OBJS += startup.o
OBJS += main.o
OBJS += flash.o
OBJS += update.o
OBJS += verify.o
OBJS += se-atecc608a.o

OBJS += delay.o
OBJS += hash.o
OBJS += pprng.o
OBJS += se.o
OBJS += sha256.o
OBJS += spiflash.o
OBJS += uECC.o
OBJS += utils.o

OBJS += system_stm32h7xx.o

OBJS += stm32h7xx_hal.o
OBJS += stm32h7xx_hal_rcc.o
OBJS += stm32h7xx_hal_rcc_ex.o
OBJS += stm32h7xx_hal_gpio.o
OBJS += stm32h7xx_hal_cortex.o
OBJS += stm32h7xx_hal_pwr.o
OBJS += stm32h7xx_hal_pwr_ex.o
OBJS += stm32h7xx_hal_spi.o
OBJS += stm32h7xx_hal_dma.o

# Where we will end up in the memory map (at start of flash)
BL_FLASH_BASE = 0x08000000
BL_FLASH_SIZE = 0x20000
BL_FLASH_LAST = 0x08020000

# SRAM4 is reserved for us.
BL_SRAM_BASE = 0x38000000
BL_SRAM_SIZE = 0x00008000

# Final 2k bytes reserved for data (not code)
# - must be page-aligned, contains pairing secret
#BL_NVROM_BASE = 0x0801F000 # final area for ROM secrets
#BL_NVROM_SIZE = 0x1000
BL_NVROM_BASE = 0x081C0000 # temporary for development
BL_NVROM_SIZE = 0x1000

# Compiler flags.
CFLAGS  = -Wall --std=gnu99 -g
CFLAGS += -mthumb -mfpu=fpv4-sp-d16 -mfloat-abi=hard
CFLAGS += -ffunction-sections -fdata-sections
CFLAGS += -mtune=cortex-m7 -mcpu=cortex-m7 -DSTM32H753xx
CFLAGS += -I. -I$(PASSPORT_PATH)/include -I$(PASSPORT_PATH)/common/micro-ecc
CFLAGS += -DPASSPORT_BOOTLOADER
#CFLAGS += -DUSE_CRYPTO
CFLAGS += -DDEMO

# Pass in the locations of stuff
CFLAGS += -D BL_FLASH_BASE=$(BL_FLASH_BASE) -D BL_FLASH_SIZE=$(BL_FLASH_SIZE)
CFLAGS += -D BL_NVROM_BASE=$(BL_NVROM_BASE) -D BL_NVROM_SIZE=$(BL_NVROM_SIZE)
CFLAGS += -D BL_SRAM_BASE=$(BL_SRAM_BASE)   -D BL_SRAM_SIZE=$(BL_SRAM_SIZE) 
CFLAGS += -D BL_FLASH_LAST=$(BL_FLASH_LAST)

CC_SYMBOLS = -mcpu=cortex-m7

# Header file search path
INC_PATHS = $(LIB_PATH)/stm32lib/CMSIS/STM32H7xx/Include \
			$(LIB_PATH)/stm32lib/STM32H7xx_HAL_Driver/Inc \
			$(LIB_PATH)/cmsis/inc \
			$(TOP)/boards/Passport

CFLAGS += $(foreach INC,$(INC_PATHS),-I$(INC))

# Specialized linker-script here. Not the standard one!
#
LINKER_SCRIPT = link-script.ld

LDFLAGS += -flto -Wl,--gc-sections --specs=nano.specs -Wl,-T$(LINKER_SCRIPT)
LDFLAGS += -nostartfiles
LDFLAGS += -Wl,--defsym,BL_FLASH_BASE=$(BL_FLASH_BASE)
LDFLAGS += -Wl,--defsym,BL_FLASH_SIZE=$(BL_FLASH_SIZE)
LDFLAGS += -Wl,--defsym,BL_NVROM_BASE=$(BL_NVROM_BASE)
LDFLAGS += -Wl,--defsym,BL_NVROM_SIZE=$(BL_NVROM_SIZE)
LDFLAGS += -Wl,--defsym,BL_SRAM_BASE=$(BL_SRAM_BASE)
LDFLAGS += -Wl,--defsym,BL_SRAM_SIZE=$(BL_SRAM_SIZE)
LDFLAGS += -Wl,-Map=$(TARGET_NAME).map

ASFLAGS += -Wa,--defsym,BL_FLASH_BASE=$(BL_FLASH_BASE) -Wa,--defsym,BL_FLASH_SIZE=$(BL_FLASH_SIZE)
ASFLAGS += -Wa,--defsym,BL_SRAM_BASE=$(BL_SRAM_BASE) -Wa,--defsym,BL_SRAM_SIZE=$(BL_SRAM_SIZE)

TARGET_ELF = $(TARGET_NAME).elf
TARGETS = $(TARGET_NAME).bin

all: $(TARGETS)

# recompile on any change, because with a small project like this...
$(OBJS): Makefile

$(TARGETS): $(TARGET_ELF) Makefile

# link step
$(TARGET_ELF): $(OBJS) $(LINKER_SCRIPT) Makefile
	$(CC) $(CFLAGS) -o $(TARGET_ELF) $(LDFLAGS) $(OBJS)
	$(SIZE) -Ax $@

%.o:  %.S
	$(CC) $(CFLAGS) -c -o $@ $<

%.o:  %.c
	$(CC) $(CFLAGS) -c -MMD -MP -o $@ $<

# raw binary, forced to right size, pad w/ 0xff
%.bin: $(TARGET_ELF)
	$(OBJCOPY) -O binary --pad-to $(BL_FLASH_LAST) --gap-fill 0xff $< $@.tmp
	dd bs=$$(($(BL_FLASH_SIZE) * 1024)) count=1 if=$@.tmp of=$@
	@$(RM) $@.tmp

ifneq ($(MAKECMDGOALS),clean)
-include $(OBJS:.o=.d)
endif

# make a 'release' build
release: code-committed check-fontawesome clean all capture
release: CFLAGS += -DRELEASE=1 -Werror

check-fontawesome:
	# You must have commerical license for Font Awesome (altho fallback looks ok)
	test -f assets/FontAwesome5Pro-Light-300.otf

.PHONY: code-committed
code-committed:
	@echo ""
	@echo "Are all changes commited already?"
	git diff --stat --exit-code .
	@echo '... yes'

# these files are what we capture and store for each release.
DELIVERABLES = $(TARGET_NAME).bin

checksums.txt: $(DELIVERABLES)
	shasum -a 256 $(DELIVERABLES) > $@

# Track released versions
.PHONY: capture
capture: version.txt version-full.txt $(DELIVERABLES) checksums.txt
	V=`cat version.txt` && cat checksums.txt > releases/$$V.txt && cat version-full.txt >> releases/$$V.txt && mkdir -p releases/$$V; cp $(DELIVERABLES) releases/$$V
	@echo
	@echo "      Version: " `cat version.txt`
	@echo
	V=`cat version.txt` && git tag -am "Bootloader version $$V" "bootloader-"$$V
	git add -f releases/*/bootloader.* releases/*.txt

# Pull out the version string from binary object (already linked in) and 
# construct a text file (version.txt) with those contents
version.txt version-full.txt: version.o Makefile
	$(OBJCOPY) -O binary -j .rodata.version_string version.o version-tmp.txt
	cat version-tmp.txt | sed -e 's/ .*//' | sed -e 's/ .*//' > version.txt
	cat version-tmp.txt | tr '\0' '\n' > version-full.txt
	@echo
	@echo "Version string: " `cat version-full.txt`
	@echo
	$(RM) version-tmp.txt

# nice version numbers.
BUILD_TIME = $(shell date '+%Y%m%d.%H%M%S')
BRANCH = $(shell git rev-parse --abbrev-ref HEAD)
SHA_VERSION = $(shell git rev-parse --short HEAD)
GIT_HASH = "$(BRANCH)@$(SHA_VERSION)"
version.o: CFLAGS += -DBUILD_TIME='"$(BUILD_TIME)"' -DGIT_HASH='$(GIT_HASH)'
version.o: Makefile

clean:
	$(RM) $(OBJS)
	$(RM) $(OBJS:.o=.d)

clobber: clean
	$(RM) $(TARGETS)

debug:
	@echo CFLAGS = $(CFLAGS)
	@echo 
	@echo OBJS = $(OBJS)
