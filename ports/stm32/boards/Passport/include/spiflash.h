/*
 * SPDX-FileCopyrightText: 2020 Foundation Devices, Inc.  <hello@foundationdevices.com>
 * SPDX-License-Identifier: GPL-3.0-or-later
 */
#ifndef _SPIFLASH_H_
#define _SPIFLASH_H_

#include "../stm32h7xx_hal_conf.h"

extern HAL_StatusTypeDef spi_setup(void);
extern HAL_StatusTypeDef spi_write(uint32_t addr, int len, const uint8_t *buf);
extern HAL_StatusTypeDef spi_read(uint32_t addr, int len, uint8_t *buf);

#endif /* _SPIFLASH_H_ */
