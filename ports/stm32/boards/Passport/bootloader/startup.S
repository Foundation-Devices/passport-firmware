/*
  SPDX-FileCopyrightText: 2020 Foundation Devices, Inc.  <hello@foundationdevices.com>
  SPDX-License-Identifier: GPL-3.0-or-later

  SPDX-FileCopyrightText: 2018 Coinkite, Inc.  <coldcardwallet.com>
  SPDX-License-Identifier: GPL-3.0-only
*/
/* starting value for the top of our stack. */
#define OUR_STACK      (BL_SRAM_BASE+BL_SRAM_SIZE)

    .thumb
    .syntax unified

    .text
    .section .entry_code

    .global     reset_entry
    .global     vector_table

vector_table:
    .word       OUR_STACK               /* initial stack value: near top of SRAM4 */
    .word       reset_entry             /* verify: must be odd, to indicate Thumb mode */
    .word       NMI_Handler             /* placeholder / debug aid */
    .word       HardFault_Handler
    .word       MemManage_Handler
    .word       BusFault_Handler
    .word       UsageFault_Handler
    .word       0
    .word       0
    .word       0
    .word       0
    .word       SVC_Handler
    .word       DebugMon_Handler
    .word       0
    .word       PendSV_Handler
    .word       SysTick_Handler


    /*
     * Debug aids: just die but in a way a debugger can maybe see why.
     * Note that this is just for bootloader operation. The real vector
     * table is in the micropython configuration.
     */

    .type       NMI_Handler, %function 
NMI_Handler:
    bkpt        1

    .type       HardFault_Handler, %function 
HardFault_Handler:
    bkpt        2

    .type       MemManage_Handler, %function 
MemManage_Handler:
    bkpt        3

    .type       BusFault_Handler, %function 
BusFault_Handler:
    bkpt        4

    .type       UsageFault_Handler, %function 
UsageFault_Handler:
    bkpt        5

    .type       SVC_Handler, %function 
SVC_Handler:
    bkpt        6

    .type       DebugMon_Handler, %function 
DebugMon_Handler:
    bkpt        7

    .type       PendSV_Handler, %function 
PendSV_Handler:
    bkpt        8
    b           .

    .align      2
    .type       reset_entry, %function       // critical to have this, marks thumb entry pt
reset_entry:

    /* Load the stack pointer */
    ldr  sp, =_estack

    /* Initialise the data section */
    ldr  r1, =_sidata
    ldr  r2, =_sdata
    ldr  r3, =_edata
    b    .data_copy_entry
.data_copy_loop:
    ldr  r0, [r1], #4 /* Should be 4-aligned to be as fast as possible */
    str  r0, [r2], #4
.data_copy_entry:
    cmp  r2, r3
    bcc  .data_copy_loop

    /* Zero out the BSS section */
    movs r0, #0
    ldr  r1, =_sbss
    ldr  r2, =_ebss
    b    .bss_zero_entry
.bss_zero_loop:
    str  r0, [r1], #4 /* Should be 4-aligned to be as fast as possible */
.bss_zero_entry:
    cmp  r1, r2
    bcc  .bss_zero_loop

    /* Initialise the sram section */
    ldr  r1, =_siram
    ldr  r2, =_sram
    ldr  r3, =_eram
    b    .ram_copy_entry
.ram_copy_loop:
    ldr  r0, [r1], #4 /* Should be 4-aligned to be as fast as possible */
    str  r0, [r2], #4
.ram_copy_entry:
    cmp  r2, r3
    bcc  .ram_copy_loop

    bl      main

    /* 
     * get a ptr to real code
     * load R1 with 0x08020800 value: start of firmware
     */
    movw    r1, (0x08020800 >> 12)
    lsl     r1, 12
    orr.w   r1, r1, #0x800

    /* set stack pointer to their preference */
    ldr     r0, [r1]
    mov     sp, r0

#if 0 /* Disabled
       * We cannot change to user mode here because the micropython code
       * depends on being in supervisor mode. SystemInit() is invoked
       * from the Reset_Handler() and the vector table (along with other
       * SCB accesses) is set at the start of stm32_main()...both
       * important things in the startup processing.
       */
    /* We are in supervisor mode out of reset...drop down to user mode */
    mrs     r3, CONTROL
    orr.w   r3, r3, #1
    msr     CONTROL, r3
#endif

    /* Read reset vector, and jump to it. */
    mov     r0, 1           /* set reset_mode arg: 1=normal? */
    ldr     lr, [r1, 4]
    bx      lr

    .end
