// SPDX-FileCopyrightText: 2020 Foundation Devices, Inc.  <hello@foundationdevices.com>
// SPDX-License-Identifier: GPL-3.0-or-later
//

#include <stdio.h>
#include <string.h>

#include "stm32h7xx_hal.h"
#include "stm32h7xx_hal_i2c_ex.h"

#include "extint.h"
#include "delay.h"
#include "keypad-adp-5587.h"
#include "modfoundation.h"

static I2C_HandleTypeDef hi2c;

static void keypad_reset(void)
{
    int i;

    // Toggle reset pin of keypad controller (pin PE2 on schematic)
    HAL_GPIO_WritePin(GPIOE, GPIO_PIN_2, 0);
    for (i = 0; i < 10; ++i)
        delay_us(1000);
    HAL_GPIO_WritePin(GPIOE, GPIO_PIN_2, 1);
    for (i = 0; i < 10; ++i)
        delay_us(1000);
}

static int keypad_setup(void)
{
    int rc;

    // Enable GPIO interrupt
    rc = keypad_write(KBD_ADDR, KBD_REG_GPIO_INT_EN1, 0xFF);
    if (rc < 0)
        return -1;

    rc = keypad_write(KBD_ADDR, KBD_REG_GPIO_INT_EN2, 0xFF);
    if (rc < 0)
        return -1;

    rc = keypad_write(KBD_ADDR, KBD_REG_GPIO_INT_EN3, 0x03);
    if (rc < 0)
        return -1;

    // Setup the configuration register
    rc = keypad_write(KBD_ADDR, KBD_REG_CFG,
                      KBD_REG_CFG_INT_CFG |
                      KBD_REG_CFG_GPI_IEN |
                      KBD_REG_CFG_KE_IEN
                      );
    if (rc < 0)
        return -1;

    // Enable GPI part of event FIFO (R0 to R7, C0 to C7, C8 to C9)
    rc = keypad_write(KBD_ADDR, KBD_REG_GPI_EM_REG1, 0xFF);
    if (rc < 0)
        return -1;

    rc = keypad_write(KBD_ADDR, KBD_REG_GPI_EM_REG2, 0xFF);
    if (rc < 0)
        return -1;

    rc = keypad_write(KBD_ADDR, KBD_REG_GPI_EM_REG3, 0x03);
    if (rc < 0)
        return -1;
    return 0;
}

void keypad_ISR()
{
    int rc;
    uint8_t key = 0;
    uint8_t key_count = 0;
 
    printf("keypad_ISR() 1\n");
    uint8_t loop_count = 0;
    while (loop_count < 10)
    {
        rc = keypad_read(KBD_ADDR, KBD_REG_KEY_EVENTA, &key, 1);
        if (rc < 0) {
            printf("keypad_ISR() read error\n");
            break;
        }

        if (key == 0) {
            printf("keypad_ISR() no key in queue\n");
            break;
        }

        ring_buffer_enqueue(&keybuf, key);
        printf("key=%d\n", key);
        key_count++;
        loop_count++;
    }

    if (key_count)
    {
        /* Clear the interrrupt on the keypad controller */
        rc = keypad_write(KBD_ADDR, KBD_REG_INT_STAT, 0xFF);
        if (rc < 0) {
            printf("[%s] I2C problem\n", __func__);
        }
    printf("keypad_ISR() 5\n");
    }
    else
    {
        /*
         * We're getting interrupts but no key codes...the keypad
         * controller is in a strange state. We'll reset it and reconfigure
         * it to get it working again.
         */
    printf("keypad_ISR() 2\n");
        keypad_reset();
    printf("keypad_ISR() 3\n");
        keypad_setup();
    printf("keypad_ISR() 4\n");
    }
    printf("keypad_ISR() 6======\n");
}

void keypad_init(void)
{
    int rcc;
    HAL_StatusTypeDef rc;
    GPIO_InitTypeDef GPIO_InitStruct = { 0 };

printf("keypad_init(): 1\n");
    // Need to specify the size of the ring buffer 128 for a test
    ring_buffer_init(&keybuf);

printf("keypad_init(): 2\n");
    __HAL_RCC_GPIOE_CLK_ENABLE();
printf("keypad_init(): 3\n");

    GPIO_InitStruct.Pin = GPIO_PIN_2;
    GPIO_InitStruct.Mode = GPIO_MODE_OUTPUT_PP;
    GPIO_InitStruct.Pull = GPIO_NOPULL;
    GPIO_InitStruct.Speed = GPIO_SPEED_FREQ_LOW;
printf("keypad_init(): 4\n");
    HAL_GPIO_Init(GPIOE, &GPIO_InitStruct);
printf("keypad_init(): 5\n");

    __HAL_RCC_I2C2_CLK_ENABLE();
printf("keypad_init(): 6\n");

    memset(&GPIO_InitStruct, 0, sizeof(GPIO_InitStruct));
    GPIO_InitStruct.Pin = GPIO_PIN_10 | GPIO_PIN_11;
    GPIO_InitStruct.Mode = GPIO_MODE_AF_OD;
    GPIO_InitStruct.Pull = GPIO_NOPULL;
    GPIO_InitStruct.Speed = GPIO_SPEED_FREQ_LOW;
    GPIO_InitStruct.Alternate = GPIO_AF4_I2C2;
printf("keypad_init(): 7\n");
    HAL_GPIO_Init(GPIOB, &GPIO_InitStruct);
printf("keypad_init(): 8\n");

    /* Configure GPIO pin : PB12 */
    memset(&GPIO_InitStruct, 0, sizeof(GPIO_InitStruct));
    GPIO_InitStruct.Pin = GPIO_PIN_12;
    GPIO_InitStruct.Mode = GPIO_MODE_IT_FALLING;
    GPIO_InitStruct.Pull = GPIO_NOPULL;
printf("keypad_init(): 9\n");
    HAL_GPIO_Init(GPIOB, &GPIO_InitStruct);
printf("keypad_init(): 10\n");

    hi2c.Instance = I2C2;
    hi2c.Init.Timing = 0x109095DF;
    hi2c.Init.OwnAddress1 = 0;
    hi2c.Init.AddressingMode = I2C_ADDRESSINGMODE_7BIT;
    hi2c.Init.DualAddressMode = I2C_DUALADDRESS_DISABLE;
    hi2c.Init.OwnAddress2 = 0;
    hi2c.Init.OwnAddress2Masks = I2C_OA2_NOMASK;
    hi2c.Init.GeneralCallMode = I2C_GENERALCALL_DISABLE;
    hi2c.Init.NoStretchMode = I2C_NOSTRETCH_DISABLE;
printf("keypad_init(): 11\n");
    rc = HAL_I2C_Init(&hi2c);
    if (rc != HAL_OK)
        printf("[%s-%d] HAL_I2C_Init failed\n", __func__, __LINE__);
printf("keypad_init(): 12\n");

    keypad_reset();
printf("keypad_init(): 13\n");
    rcc = keypad_setup();
    if (rcc < 0)
        printf("[%s-%d] keypad_setup() failed\n", __func__, __LINE__);

    /* EXTI interrupt init*/
printf("keypad_init(): 14\n");
    mp_uint_t irq_state = disable_irq();
printf("keypad_init(): 15\n");
    HAL_NVIC_SetPriority(EXTI15_10_IRQn, 0, 0);
printf("keypad_init(): 16\n");
    HAL_NVIC_EnableIRQ(EXTI15_10_IRQn);
printf("keypad_init(): 17\n");
    enable_irq(irq_state);
printf("keypad_init(): 18\n");
}

int keypad_write(
    uint8_t address,
    uint8_t reg,
    uint8_t data
)
{
    HAL_StatusTypeDef rc;
    rc = HAL_I2C_Mem_Write(&hi2c, address, reg, I2C_MEMADD_SIZE_8BIT, &data, 1, 100);
    if (rc != HAL_OK)
        return -1;
    return 0;
}

int keypad_read(
    uint8_t address,
    uint8_t reg,
    uint8_t* data,
    uint8_t len
)
{
    HAL_StatusTypeDef rc;
    rc = HAL_I2C_Master_Transmit(&hi2c, address, &reg, 1, 100);
    if (rc != HAL_OK)
        return -1;
    else
    {
        rc = HAL_I2C_Master_Receive(&hi2c, address, data, len, 100);
        if (rc != HAL_OK)
            return -1;
    }
    return 0;
}
