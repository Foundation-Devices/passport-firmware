/*
 * SPDX-FileCopyrightText: 2020 Foundation Devices, Inc. <hello@foundationdevices.com>
 * SPDX-License-Identifier: GPL-3.0-or-later
 */
#ifndef _UTILS_H_
#define _UTILS_H_

#include <stdbool.h>
#include <stdint.h>

#ifndef MIN
    #define MIN(a,b)		(((a)<(b))?(a):(b))
    #define MAX(a,b)		(((a)>(b))?(a):(b))
#endif
#define CLAMP(x,mn,mx)	(((x)>(mx))?(mx):( ((x)<(mn)) ? (mn) : (x)))
#define SGN(x)          (((x)<0)?-1:(((x)>0)?1:0))
#define ABS(x)      	(((x)<0)?-(x):(x))

#define LOCKUP_FOREVER()    while(1) { __WFI(); }

extern bool check_all_ones(void *ptrV, int len);
extern bool check_all_zeros(void *ptrV, int len);
extern bool check_equal(void *aV, void *bV, int len);
extern void xor_mixin(uint8_t *acc, uint8_t *more, int len);
extern void to_hex(char* buf, uint8_t value);
extern void bytes_to_hex_str(uint8_t* bytes, uint32_t len, char* str, uint32_t split_every, char split_char);


#ifndef PASSPORT_BOOTLOADER
extern void print_hex_buf(char* prefix, uint8_t* buf, int len);
#endif

extern void copy_bytes(uint8_t* src, int src_len, uint8_t* dest, int dest_len);

#ifndef PASSPORT_BOOTLOADER
#define MIN_SP 0x24074000
#define EOS_SENTINEL 0xDEADBEEF

void set_stack_sentinel();
bool check_stack_sentinel();
uint32_t getsp(void);
bool check_stack(char* msg, bool print);

#endif

#endif /* _UTILS_H_ */
