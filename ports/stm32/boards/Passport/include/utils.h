/*
 * SPDX-FileCopyrightText: 2020 Foundation Devices, Inc.  <hello@foundationdevices.com>
 * SPDX-License-Identifier: GPL-3.0-or-later
 */
#ifndef _UTILS_H_
#define _UTILS_H_

#include <stdbool.h>
#include <stdint.h>

#define MIN(a,b)		(((a)<(b))?(a):(b))
#define MAX(a,b)		(((a)>(b))?(a):(b))
#define CLAMP(x,mn,mx)	(((x)>(mx))?(mx):( ((x)<(mn)) ? (mn) : (x)))
#define SGN(x)          (((x)<0)?-1:(((x)>0)?1:0))
#define ABS(x)      	(((x)<0)?-(x):(x))

#define LOCKUP_FOREVER()    while(1) { __WFI(); }

extern bool check_all_ones(void *ptrV, int len);
extern bool check_all_zeros(void *ptrV, int len);
extern bool check_equal(void *aV, void *bV, int len);
extern void xor_mixin(uint8_t *acc, uint8_t *more, int len);

#endif /* _UTILS_H_ */
