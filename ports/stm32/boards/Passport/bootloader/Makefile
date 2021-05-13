# SPDX-FileCopyrightText: 2020 Foundation Devices, Inc. <hello@foundationdevices.com>
# SPDX-License-Identifier: GPL-3.0-or-later
#
# SPDX-FileCopyrightText: 2018 Coinkite, Inc. <coldcardwallet.com>
# SPDX-License-Identifier: GPL-3.0-only
#
# "Bootloader" Makefile
#
# Targets:
#	all - make everything, look for dafu.elf inparticular
#	clean - delete intermediates
#	clobber - delete all build products
#

BOOTLOADER_VERSION = 1.05

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
VPATH += $(HAL_CMSIS_PATH)/gcc
VPATH += $(PASSPORT_PATH)/common
VPATH += $(PASSPORT_PATH)/common/micro-ecc

# Basename of all targets
TARGET_NAME = bootloader
TARGETDIR   = arm

# Source files. Important: Add them also to link-script.ld to control placement.
# Files specific to the bootloader
SOURCES  = startup_stm32h753xx.c
SOURCES += startup.c
SOURCES += bootloader_graphics.c
SOURCES += main.c
SOURCES += flash.c
SOURCES += splash.c
SOURCES += update.c
SOURCES += se-atecc608a.c
SOURCES += ui.c
SOURCES += verify.c
SOURCES += version_info.c

# Common files between bootloader and MP
SOURCES += backlight.c
SOURCES += delay.c
SOURCES += display.c
SOURCES += gpio.c
SOURCES += hash.c
SOURCES += lcd-sharp-ls018B7dh02.c
SOURCES += passport_fonts.c
SOURCES += pprng.c
SOURCES += se.c
SOURCES += sha256.c
SOURCES += spiflash.c
SOURCES += uECC.c
SOURCES += utils.c

SOURCES += system_stm32h7xx.c

SOURCES += stm32h7xx_hal.c
SOURCES += stm32h7xx_hal_rcc.c
SOURCES += stm32h7xx_hal_rcc_ex.c
SOURCES += stm32h7xx_hal_gpio.c
SOURCES += stm32h7xx_hal_cortex.c
SOURCES += stm32h7xx_hal_pwr.c
SOURCES += stm32h7xx_hal_pwr_ex.c
SOURCES += stm32h7xx_hal_spi.c
SOURCES += stm32h7xx_hal_dma.c

# Required for LCD support
SOURCES += stm32h7xx_hal_tim.c
SOURCES += stm32h7xx_hal_tim_ex.c

# Where we will end up in the memory map (at start of flash)
BL_FLASH_BASE = 0x08000000
BL_FLASH_SIZE = 0x20000
BL_FLASH_LAST = 0x08020000

# SRAM4 is reserved for us.
BL_SRAM_BASE = 0x20000000
BL_SRAM_SIZE = 0x00020000

# Final 1k bytes reserved for data (not code)
BL_NVROM_BASE = 0x0801FF00 # final area for ROM secrets
#BL_NVROM_BASE = 0x081C0000 # temporary for development
BL_NVROM_SIZE = 0x100

# Compiler flags.
CFLAGS  = -Wall -Werror --std=gnu99
CFLAGS += -Wno-address-of-packed-member
CFLAGS += -mthumb -mfpu=fpv4-sp-d16 -mfloat-abi=hard
CFLAGS += -ffunction-sections -fdata-sections
CFLAGS += -mtune=cortex-m7 -mcpu=cortex-m7 -DSTM32H753xx
CFLAGS += -I. -I$(PASSPORT_PATH)/include -I$(PASSPORT_PATH)/common/micro-ecc
CFLAGS += -DPASSPORT_BOOTLOADER
CFLAGS += -DUSE_CRYPTO
ifeq ($(findstring production,$(MAKECMDGOALS)),production)
CFLAGS += -DPRODUCTION_BUILD
endif
#CFLAGS += -DCONVERSION_BUILD
ifeq ($(findstring locked,$(MAKECMDGOALS)),locked)
CFLAGS += -DLOCKED
endif

# Pass in the locations of stuff
CFLAGS += -D BL_FLASH_BASE=$(BL_FLASH_BASE) -D BL_FLASH_SIZE=$(BL_FLASH_SIZE)
CFLAGS += -D BL_NVROM_BASE=$(BL_NVROM_BASE) -D BL_NVROM_SIZE=$(BL_NVROM_SIZE)
CFLAGS += -D BL_SRAM_BASE=$(BL_SRAM_BASE)   -D BL_SRAM_SIZE=$(BL_SRAM_SIZE)
CFLAGS += -D BL_FLASH_LAST=$(BL_FLASH_LAST)

ifeq ($(findstring debug,$(MAKECMDGOALS)),debug)
OBJDIR = $(TARGETDIR)/debug
CFLAGS += -g -DDEBUG
LDFLAGS += -g
else
OBJDIR = $(TARGETDIR)/release
CFLAGS += -O2
# Add keypad support for release builds
SOURCES += keypad-adp-5587.c
SOURCES += ring_buffer.c
SOURCES += stm32h7xx_hal_i2c.c
endif

OBJECTS = $(addprefix $(OBJDIR)/,$(SOURCES:.c=.o))

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

LDFLAGS += -flto -Wl,--gc-sections -specs=nano.specs -Wl,-T$(LINKER_SCRIPT)
LDFLAGS += -nostartfiles
LDFLAGS += -Wl,--defsym,BL_FLASH_BASE=$(BL_FLASH_BASE)
LDFLAGS += -Wl,--defsym,BL_FLASH_SIZE=$(BL_FLASH_SIZE)
LDFLAGS += -Wl,--defsym,BL_NVROM_BASE=$(BL_NVROM_BASE)
LDFLAGS += -Wl,--defsym,BL_NVROM_SIZE=$(BL_NVROM_SIZE)
LDFLAGS += -Wl,--defsym,BL_SRAM_BASE=$(BL_SRAM_BASE)
LDFLAGS += -Wl,--defsym,BL_SRAM_SIZE=$(BL_SRAM_SIZE)
LDFLAGS += -Wl,-Map=$(OBJDIR)/$(TARGET_NAME).map

ASFLAGS += -Wa,--defsym,BL_FLASH_BASE=$(BL_FLASH_BASE) -Wa,--defsym,BL_FLASH_SIZE=$(BL_FLASH_SIZE)
ASFLAGS += -Wa,--defsym,BL_SRAM_BASE=$(BL_SRAM_BASE) -Wa,--defsym,BL_SRAM_SIZE=$(BL_SRAM_SIZE)

TARGET_ELF = $(OBJDIR)/$(TARGET_NAME).elf
TARGETS    = $(OBJDIR)/$(TARGET_NAME).bin

all: version $(TARGETS)

debug: version $(TARGETS)

locked: version $(TARGETS)

production: version $(TARGETS)

# recompile on any change, because with a small project like this...
$(OBJECTS): Makefile

$(TARGETS): $(TARGET_ELF) Makefile

# link step
$(TARGET_ELF): $(OBJECTS) $(LINKER_SCRIPT) Makefile
	$(CC) $(CFLAGS) $(LDFLAGS) -o $(TARGET_ELF) $(OBJECTS)
	$(SIZE) -Ax $@

$(OBJDIR)/%.o:  %.s
	@rm -f $@
	@[ -d $(dir $@) ] || mkdir -p $(dir $@)
	$(CC) $(CFLAGS) -c -o $@ $<

$(OBJDIR)/%.o:  %.c
	@rm -f $@
	@[ -d $(dir $@) ] || mkdir -p $(dir $@)
	$(CC) $(CFLAGS) -c -MMD -MP -o $@ $<

# raw binary, forced to right size, pad w/ 0xff
$(OBJDIR)/%.bin: $(TARGET_ELF)
	$(OBJCOPY) -O binary --pad-to $$(($(BL_FLASH_LAST) - $(BL_NVROM_SIZE)))  --gap-fill 0x00 $< $@.tmp
	dd bs=$$(($(BL_FLASH_SIZE) * 1024)) count=1 if=$@.tmp of=$@
	@$(RM) $@.tmp

ifneq ($(MAKECMDGOALS),clean)
-include $(OBJECTS:.o=.d)
endif

# make a 'release' build
release: code-committed check-fontawesome clean all capture
release: CFLAGS += -DRELEASE=1 -Werror

clean:
	@$(RM) -r $(TARGETDIR)

version:
	@$(TOP)/boards/Passport/tools/version_info/version_info version_info.c $(BOOTLOADER_VERSION)
	@[ -d $(dir $(OBJDIR)/version_info.o) ] || mkdir -p $(dir $(OBJDIR)/version_info.o)
	$(CC) $(CFLAGS) -c -MMD -MP -o $(OBJDIR)/version_info.o version_info.c

.PHONY: all clean install version
.SECONDARY:
