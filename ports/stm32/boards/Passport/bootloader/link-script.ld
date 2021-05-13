/*
  SPDX-FileCopyrightText: 2020 Foundation Devices, Inc. <hello@foundationdevices.com>
  SPDX-License-Identifier: GPL-3.0-or-later

  SPDX-FileCopyrightText: 2018 Coinkite, Inc. <coldcardwallet.com>
  SPDX-License-Identifier: GPL-3.0-only
*/

/* Memory layout for bootloader internal flash storage configuration:

    FLASH_ISR   .isr_vector

    FLASH_TEXT  .text
    FLASH_TEXT  .data

    RAM         .text
    RAM         .data
    RAM         .bss
    RAM         .stack
*/

OUTPUT_FORMAT("elf32-littlearm", "elf32-littlearm", "elf32-littlearm")
OUTPUT_ARCH(arm)
SEARCH_DIR(.)

/* Memory Spaces Definitions */
MEMORY
{
    rom     (rx)  : ORIGIN = BL_FLASH_BASE, LENGTH = BL_FLASH_SIZE
    ram     (rwx) : ORIGIN = BL_SRAM_BASE,  LENGTH = BL_SRAM_SIZE
    itcm    (rwx) : ORIGIN = 0x00000000,    LENGTH = 0x10000
}

/* The stack size used by the bootloader. */
STACK_SIZE = DEFINED(STACK_SIZE) ? STACK_SIZE : DEFINED(__stack_size__) ? __stack_size__ : 0x8000;

/* Section Definitions */
SECTIONS
{
    .isr_vector :
    {
        . = ALIGN(4);
        KEEP(*(.isr_vector)) /* Startup code */
        . = ALIGN(4);
    } > rom

    .text :
    {
        . = ALIGN(4);
        _sfixed = .;
        KEEP(*(.entry_code))

        . = ALIGN(256);
        /* important: this pulls in library (libgcc) stuff here */
        KEEP(*(.text .text.* .gnu.linkonce.t.*))
        *(.rodata .rodata* .gnu.linkonce.r.*)

        . = ALIGN(4);
        _efixed = .;            /* End of text section */

    } > rom

    /* .ARM.exidx is sorted, so has to go in its own output section. */
    PROVIDE_HIDDEN (__exidx_start = .);
    .ARM.exidx :
    {
      *(.ARM.exidx* .gnu.linkonce.armexidx.*)
    } > rom
    PROVIDE_HIDDEN (__exidx_end = .);

    . = ALIGN(4);
    _etext = .;

    _siram = LOADADDR(.ramfunc);
    .ramfunc :
    {
        . = ALIGN(4);
        _sram = .;
        
        *(.ramfunc .ramfunc.*);

        . = ALIGN(4);
        _eram = .;
    } >itcm AT> rom

    /* used by the startup to initialize data */
    _sidata = LOADADDR(.data);

    /* This is the initialized data section
    The program executes knowing that the data is in the RAM
    but the loader puts the initial values in the FLASH (inidata).
    It is one task of the startup to copy the initial values from FLASH to RAM. */
    .data :
    {
        . = ALIGN(4);
        _sdata = .;        /* create a global symbol at data start; used by startup code in order to initialise the .data section in RAM */
        *(.data*)          /* .data* sections */

        . = ALIGN(4);
        _edata = .;        /* define a global symbol at data end; used by startup code in order to initialise the .data section in RAM */
    } >ram AT> rom

    /* .bss section which is used for uninitialized data */
    .bss (NOLOAD) :
    {
        . = ALIGN(4);
        _sbss = . ;
        _szero = .;
        *(.bss .bss.*)
        *(COMMON)
        . = ALIGN(4);
        _ebss = . ;
        _ezero = .;
    } > ram

    /* stack section */
    .stack (NOLOAD):
    {
        . = ALIGN(8);
        _sstack = .;
        . = . + STACK_SIZE;
        . = ALIGN(8);
        _estack = .;
    } > ram

    /* Some very manual linking! I've tried doing it right, and couldn't get it to work well */
    addr_rom_secrets = BL_NVROM_BASE;

    . = ALIGN(4);
    _end = . ;
}
