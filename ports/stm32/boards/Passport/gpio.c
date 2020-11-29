// SPDX-FileCopyrightText: 2020 Foundation Devices, Inc.  <hello@foundationdevices.com>
// SPDX-License-Identifier: GPL-3.0-or-later
//

#include "stm32h7xx_hal.h"

void gpio_init(void)
{
    GPIO_InitTypeDef GPIO_InitStruct = { 0 };

    HAL_GPIO_WritePin(GPIOA, GPIO_PIN_1, 1);

    /* Configure the MRESET line */
    GPIO_InitStruct.Pin = GPIO_PIN_1;
    GPIO_InitStruct.Mode = GPIO_MODE_OUTPUT_PP;
    GPIO_InitStruct.Pull = GPIO_NOPULL;
    GPIO_InitStruct.Speed = GPIO_SPEED_FREQ_LOW;
    HAL_GPIO_Init(GPIOA, &GPIO_InitStruct);


    HAL_GPIO_WritePin(GPIOB, GPIO_PIN_2, 0);

    /* Configure the PWR_SHDN line */
    GPIO_InitStruct.Pin = GPIO_PIN_2;
    GPIO_InitStruct.Mode = GPIO_MODE_OUTPUT_PP;
    GPIO_InitStruct.Pull = GPIO_NOPULL;
    GPIO_InitStruct.Speed = GPIO_SPEED_FREQ_LOW;
    HAL_GPIO_Init(GPIOB, &GPIO_InitStruct);
}

void passport_reset(void)
{
    HAL_GPIO_WritePin(GPIOA, GPIO_PIN_1, 0);
}

void passport_shutdown(void)
{
    HAL_GPIO_WritePin(GPIOB, GPIO_PIN_2, 1);
}
