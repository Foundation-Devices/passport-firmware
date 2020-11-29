/*
   SPDX-FileCopyrightText: 2020 Foundation Devices, Inc.  <hello@foundationdevices.com>
   SPDX-License-Identifier: GPL-3.0-or-later

   GNU linker script for STM32H753
*/

/* Specify the memory areas */
MEMORY
{
    FLASH (rx)      : ORIGIN = 0x08000000, LENGTH = 2048K
    FLASH_ISR (rx)  : ORIGIN = 0x08020800, LENGTH = 128K    /* sector 0, 128K */
    FLASH_TEXT (rx) : ORIGIN = 0x08040000, LENGTH = 1664K   /* sectors 6*128 + 7*128 (last 128K reserve for nvstore) */
    DTCM (xrw)      : ORIGIN = 0x20000000, LENGTH = 128K    /* Used for storage cache */
    RAM (xrw)       : ORIGIN = 0x24000000, LENGTH = 512K    /* AXI SRAM */
    /* SRAM4 is 64k of SRAM used for:
        - filesystem cache (2k at zero) (not yet implemented)
        - top 8k reserved for bootloader/call gate (not yet implemented)
        - manually-allocated for some runtime python stuff (see sram4.py) from bottom
    */
    SRAM4 (xrw)     : ORIGIN = 0x38000800, LENGTH = 22K
}

/* produce a link error if there is not this amount of RAM for these sections */
_minimum_stack_size = 2K;
_minimum_heap_size = 16K;

/* Define the stack.  The stack is full descending so begins just above last byte
   of RAM.  Note that EABI requires the stack to be 8-byte aligned for a call. */
_estack = ORIGIN(RAM) + LENGTH(RAM) - _estack_reserve;
_sstack = _estack - 32K; /* tunable */

/* RAM extents for the garbage collector */
_ram_start = ORIGIN(RAM);
_ram_end = ORIGIN(RAM) + LENGTH(RAM);
_heap_start = _ebss; /* heap starts just after statically allocated memory */
_heap_end = _sstack;
