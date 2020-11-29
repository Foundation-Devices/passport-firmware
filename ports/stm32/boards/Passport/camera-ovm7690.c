// SPDX-FileCopyrightText: 2020 Foundation Devices, Inc.
// <hello@foundationdevices.com> SPDX-License-Identifier: BSD-3-Clause
//

/*-----------------------------------------------------------------------------
 * Copyright (c) 2013 - 2018 Arm Limited (or its affiliates). All
 * rights reserved.
 *
 * SPDX-License-Identifier: BSD-3-Clause
 *
 * Redistribution and use in source and binary forms, with or without
 * modification, are permitted provided that the following conditions are met:
 *   1.Redistributions of source code must retain the above copyright
 *     notice, this list of conditions and the following disclaimer.
 *   2.Redistributions in binary form must reproduce the above copyright
 *     notice, this list of conditions and the following disclaimer in the
 *     documentation and/or other materials provided with the distribution.
 *   3.Neither the name of Arm nor the names of its contributors may be used
 *     to endorse or promote products derived from this softwarwe without
 *     specific prior written permission.
 *
 * THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
 * AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
 * IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
 * ARE DISCLAIMED. IN NO EVENT SHALL COPYRIGHT HOLDERS AND CONTRIBUTORS BE
 * LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
 * CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
 * SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
 * INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
 * CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
 * ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
 * POSSIBILITY OF SUCH DAMAGE.
 *-----------------------------------------------------------------------------
 * Name:    Camera_OVM7690.c
 * Purpose: Digital camera OVM7690 interface
 * Rev.:    1.0.0
 *----------------------------------------------------------------------------*/

#include <stdio.h>
#include <string.h>

#include "stm32h7xx_hal.h"

#include "dma.h"
#include "camera-ovm7690.h"

#define CAMERA_I2C_ADDR (0x21 << 1) // Use 8-bit address

typedef struct
{
    uint8_t addr;
    uint8_t val;
} CAMERA_REG;

/* OmniVision recommended settings based on OVM7690 Setting V2.2              */
/* Modified for RGB QVGA settings                                             */
static CAMERA_REG Camera_RegInit[] = {
    {0x0E, 0x00}, /* No sleep and full range (default)  */
    {0x0C, 0x06}, /* External sync */
    {0x81, 0xFF}, /* SDE, UV, vscale, hscale, uvavg, color matrix */
    {0x21, 0x44}, /* AECGM banding max */
    {0x16, 0x03}, /* Setting reserved bits?? */
    {0x39, 0x80}, /* Setting reserved bits?? */
    {0x1E, 0xB1}, /* Setting reserved bits?? */

    /* Format */
    {0x12, 0x06}, /* Output format control: RGB565      */
    {0x82, 0x03}, /* YUV422? */
    {0xD0, 0x48}, /* voffset/hoffset (default) */
    {0x80, 0x7F}, /* color interp, bp corr, wp corr, gamma, awb gain, awb, lens corr */
    {0x3E, 0x30}, /* reserved bit?? and PLCK YUV */
    {0x22, 0x00}, /* optical black output disable (default) */

    /* Resolution */
    {0x17, 0x69}, /* Horizontal window start point      */
    {0x18, 0xA4}, /* Horizontal senzor size             */
    {0x19, 0x0C}, /* Vertical Window start line         */
    {0x1A, 0xF6}, /* Vertical sensor size               */

    {0xC8, 0x02}, /* H input size MSBs (default) */
    {0xC9, 0x80}, /* H input size LSBs (default) */
    {0xCA, 0x01}, /* V input size MSBs (default) */
    {0xCB, 0xE0}, /* V input size LSBs (default) */
    {0xCC, 0x02}, /* H output size MSBs (default) */
    {0xCD, 0x80}, /* H output size LSBs (default) */
    {0xCE, 0x01}, /* V output size MSBs (default) */
    {0xCF, 0xE0}, /* V output size LSBs (default) */

    /* Lens Correction */
    {0x85, 0x90}, /* reserved bit?? and LENC bias enable */
    {0x86, 0x00}, /* no compensation radius (default) */
    {0x87, 0x00}, /* LENSC X coord (default) */
    {0x88, 0x10}, /* LENSC Y coord */
    {0x89, 0x30}, /* R compensation coefficient */
    {0x8A, 0x29}, /* G compensation coefficient */
    {0x8B, 0x26}, /* B compensation coefficient */

    /* Color Matrix */
    {0xBB, 0x80}, /* color matrix coefficient 1 */
    {0xBC, 0x62}, /* color matrix coefficient 2 */
    {0xBD, 0x1E}, /* color matrix coefficient 3 */
    {0xBE, 0x26}, /* color matrix coefficient 4 */
    {0xBF, 0x7B}, /* color matrix coefficient 5 */
    {0xC0, 0xAC}, /* color matrix coefficient 6 */
    {0xC1, 0x1E}, /* M sign (default) */

    /* Edge + Denoise */
    {0xB7, 0x05}, /* offset */
    {0xB8, 0x09}, /* base 1 */
    {0xB9, 0x00}, /* base 2 */
    {0xBA, 0x18}, /* gain 4x limited to 16 and DNS_th_sel */

    /* UVAdjust */
    {0x5A, 0x4A}, /* slope of UV curve */
    {0x5B, 0x9F}, /* UV adjust */
    {0x5C, 0x48}, /* UV adjust */
    {0x5D, 0x32}, /* UV adjust */

    /* AEC/AGC target */
    {0x24, 0x78}, /* stable operation up limit (default) */
    {0x25, 0x68}, /* stable operation lower limit (default) */
    {0x26, 0xB3}, /* fast mode operating region */

    /* Gamma */
    {0xA3, 0x0B}, /* gamma curve 1st segment */
    {0xA4, 0x15}, /* gamma curve 2nd segment */
    {0xA5, 0x2A}, /* gamma curve 3rd segment */
    {0xA6, 0x51}, /* gamma curve 4th segment */
    {0xA7, 0x63}, /* gamma curve 5th segment */
    {0xA8, 0x74}, /* gamma curve 6th segment */
    {0xA9, 0x83}, /* gamma curve 7th segment */
    {0xAA, 0x91}, /* gamma curve 8th segment */
    {0xAB, 0x9E}, /* gamma curve 9th segment */
    {0xAC, 0xAA}, /* gamma curve 10th segment */
    {0xAD, 0xBE}, /* gamma curve 11th segment */
    {0xAE, 0xCE}, /* gamma curve 12th segment */
    {0xAF, 0xE5}, /* gamma curve 13th segment */
    {0xB0, 0xF3}, /* gamma curve 14th segment */
    {0xB1, 0xFB}, /* gamma curve 15th segment */
    {0xB2, 0x06}, /* gamma curve highest segment slope */

    /* Advance (AWB Control Registers) */
    {0x8C, 0x5D},
    {0x8D, 0x11},
    {0x8E, 0x12},
    {0x8F, 0x11},
    {0x90, 0x50},
    {0x91, 0x22},
    {0x92, 0xD1},
    {0x93, 0xA7},
    {0x94, 0x23},
    {0x95, 0x3B},
    {0x96, 0xFF},
    {0x97, 0x00},
    {0x98, 0x4A},
    {0x99, 0x46},
    {0x9A, 0x3D},
    {0x9B, 0x3A},
    {0x9C, 0xF0},
    {0x9D, 0xF0},
    {0x9E, 0xF0},
    {0x9F, 0xFF},
    {0xA0, 0x56},
    {0xA1, 0x55},
    {0xA2, 0x13},

    /* General Control */
    {0x50, 0x9A}, /* 50 Hz banding AEC (default) */
    {0x51, 0x80}, /* 60 Hz banding AEC (default) */
    {0x21, 0x23}, /* AECGM banding max (overrides above) */

    {0x14, 0x29}, /* Max AGC 8x */
    {0x13, 0xE7}, /* fast AGC/AEC, AEC step unlimited, banding filter, AEC below banding, AGC auto, AWB auto, exp auto */
    {0x11, 0x00}, /* external clock or internal clock prescalar */

    {0x0E, 0x03}, /* already specified above */

    {0xC8, 0x02},
    {0xC9, 0x40}, /* Input Horiz 576 */
    {0xCA, 0x01},
    {0xCB, 0xE0}, /* Input Vert 480 */
    {0xCC, 0x01},
    {0xCD, 0x8C}, /* Output Horiz 396 */
    {0xCE, 0x01},
    {0xCF, 0x4A} /* Output Vert 330 */
};

static uint32_t FrameBufAddr;
static DMA_HandleTypeDef hdma;
static DCMI_HandleTypeDef hdcmi;
static I2C_HandleTypeDef hi2c1;
static TIM_HandleTypeDef tim3;

uint16_t *camera_frame_buffer = (uint16_t *)D2_AHBSRAM_BASE;

static int
camera_read(uint8_t reg, uint8_t *data)
{
    HAL_StatusTypeDef ret;
    ret = HAL_I2C_Master_Transmit(&hi2c1, CAMERA_I2C_ADDR, &reg, 1, 100);
    if (ret != HAL_OK)
    {
        printf("[%s] HAL_I2C_Master_Transmit() failed\n", __func__);
        return -1;
    }

    ret = HAL_I2C_Master_Receive(&hi2c1, CAMERA_I2C_ADDR, data, 1, 100);
    if (ret != HAL_OK)
    {
        printf("[%s] HAL_I2C_Master_Receive() failed\n", __func__);
        return -1;
    }

    return 0;
}

static int
camera_write(uint8_t reg, uint8_t data)
{
    HAL_StatusTypeDef ret;
    ret = HAL_I2C_Mem_Write(
        &hi2c1, CAMERA_I2C_ADDR, reg, I2C_MEMADD_SIZE_8BIT, &data, 1, 100);
    if (ret != HAL_OK)
    {
        printf("[%s] HAL_I2C_Mem_Write() failed\n", __func__);
        return -1;
    }
    return 0;
}

static int
camera_setQVGA(void)
{
    int i;
    int rc;

    for (i = 0; i < (sizeof(Camera_RegInit) / sizeof(CAMERA_REG)); i++)
    {
        rc = camera_write(Camera_RegInit[i].addr, Camera_RegInit[i].val);
        if (rc < 0)
        {
            printf("[%s] camera_write() failed on index %d\n", __func__, i);
            return -1;
        }
    }
    return 0;
}

int
camera_on(void)
{
    int rc;
    uint8_t val;

    printf("DRIVER: camera_on()\n");
    rc = camera_read(0x0E, &val);
    if (rc < 0)
    {
        printf("[%s] camera_read() failed\n", __func__);
        return -1;
    }

    val &= ~(1 << 3);
    rc = camera_write(0x0E, val);
    if (rc < 0)
    {
        printf("[%s] camera_write() failed\n", __func__);
        return -1;
    }

    return 0;
}

int
camera_off(void)
{
    int rval = 0;
    int irc;
    uint8_t val;
    HAL_StatusTypeDef rc;

printf("DRIVER: camera_off() 1\n");
    rc = HAL_DCMI_Stop(&hdcmi);
printf("DRIVER: camera_off() 1\n");
    if (rc != HAL_OK)
    {
        printf("[%s] HAL_DCMI_Stop() failed\n", __func__);
        rval = -1;
    }

    irc = camera_read(0x0E, &val);
printf("DRIVER: camera_off() 2\n");
    if (irc < 0)
    {
        printf("[%s] camera_read() failed\n", __func__);
        rval = -1;
        goto out;
    }

    /* Put camera into sleep mode */
    irc = camera_write(0x0E, val | (1 << 3));
printf("DRIVER: camera_off() 3\n");
    if (irc < 0)
    {
        printf("[%s] camera_write() failed\n", __func__);
        rval = -1;
    }
out:
printf("DRIVER: camera_off() - DONE\n");
    return rval;
}

int camera_stop_dcmi(void) {
    int rval = 0;
    HAL_StatusTypeDef rc = HAL_DCMI_Stop(&hdcmi);
    if (rc != HAL_OK)
    {
        printf("[%s] HAL_DCMI_Stop() failed\n", __func__);
        rval = -1;
    }
    return rval;
}

uint16_t *
camera_get_frame_buffer()
{
    return camera_frame_buffer;
}

int camera_snapshot(void)
{
    int rval = 0;
    HAL_StatusTypeDef rc;

    // uint32_t total_start = HAL_GetTick();
    // uint32_t total_end = 0;

    /* Clear the buffer */
    memset(camera_frame_buffer, 0, (FRAMEBUF_SIZE * 2));

    /* Clear any current interrupts */
    hdcmi.Instance->ICR = DCMI_IT_FRAME | DCMI_IT_OVR | DCMI_IT_ERR | DCMI_IT_VSYNC | DCMI_IT_LINE;

    /* Take a snapshot */
    rc = HAL_DCMI_Start_DMA(
        &hdcmi, DCMI_MODE_SNAPSHOT, FrameBufAddr, (FRAMEBUF_SIZE * 2) / 4);
    if (rc != HAL_OK)
    {
        printf("[%s] HAL_DCMI_Start_DMA() failed\n", __func__);
        rval = -1;
    }
    else
    {
        uint16_t count = 0;

        /* Poll for frame completion */
        while (!(hdcmi.Instance->RISR & DCMI_IT_FRAME))
        {
           HAL_Delay(1);
            ++count;
            if (count > 1000)
            {
                printf("[%s] frame complete did not occur in 1 second\n", __func__);
                goto out;
            }
        }
        // printf("[%s] frame complete in %d milliseconds\n", __func__, count);
    }
out:
    // Need to call this after DMA completes
    camera_stop_dcmi();

    // total_end = HAL_GetTick();
    // printf("camera_snapshot(): took %lu ms\n", total_end - total_start);
    return rval;
}

int camera_continuous(void)
{
    int irc;
    int rval = 0;
    HAL_StatusTypeDef rc;

    irc = camera_on();
    if (irc < 0)
        return -1;

    /* Clear the buffer */
    memset(camera_frame_buffer, 0, (FRAMEBUF_SIZE * 2));

    /* Clear any current interrupts */
    hdcmi.Instance->ICR = DCMI_IT_FRAME | DCMI_IT_OVR | DCMI_IT_ERR | DCMI_IT_VSYNC | DCMI_IT_LINE;

    /* Run in continuous mode */
    rc = HAL_DCMI_Start_DMA(
        &hdcmi, DCMI_MODE_CONTINUOUS, FrameBufAddr, (FRAMEBUF_SIZE * 2) / 4);
    if (rc != HAL_OK)
    {
        printf("[%s] HAL_DCMI_Start_DMA() failed\n", __func__);
        rval = -1;
        goto out;
    }

    printf("[%s] camera in continous capture mode\n", __func__);
out:
    return rval;
}

void camera_stop(void)
{
    camera_off();
}

int camera_init(void)
{
    HAL_StatusTypeDef rc;
    GPIO_InitTypeDef GPIO_InitStruct = {0};
    TIM_MasterConfigTypeDef sMasterConfig = {0};
    TIM_OC_InitTypeDef sConfigOC = {0};
    uint16_t Period = (SystemCoreClock / 24000000); /* Need 24 MHz clock for the camera */

    uint8_t val;

    FrameBufAddr = (uint32_t)camera_frame_buffer;

    printf("****************************************************************************\n");

    /*
   * Per STM Appnote AN5020
   * Reset DCMI by setting bit in RCC_AHB2RSTR register
   *   to reset clock domains
   * Configure GPIOs
   * Configure timings and clocks (done at startup)
   * Configure DCMI
   * Configure DMA
   * Configure Camera module
   */

    /* PE7 DCMI_PWDN config set before pinmux */
    HAL_GPIO_WritePin(GPIOE, GPIO_PIN_7, GPIO_PIN_RESET);

    /* DCMI_PWDN pin PE7 PE8 PWR_EN */
    GPIO_InitStruct.Pin = GPIO_PIN_7 | GPIO_PIN_8;
    GPIO_InitStruct.Mode = GPIO_MODE_OUTPUT_PP;
    GPIO_InitStruct.Pull = GPIO_NOPULL;
    GPIO_InitStruct.Speed = GPIO_SPEED_FREQ_LOW;
    HAL_GPIO_Init(GPIOE, &GPIO_InitStruct);

    /* DCMI pin setup */
    GPIO_InitStruct.Pin = GPIO_PIN_4 | GPIO_PIN_6;
    GPIO_InitStruct.Mode = GPIO_MODE_AF_PP;
    GPIO_InitStruct.Pull = GPIO_PULLUP;
    GPIO_InitStruct.Speed = GPIO_SPEED_HIGH;
    GPIO_InitStruct.Alternate = GPIO_AF13_DCMI;
    HAL_GPIO_Init(GPIOA, &GPIO_InitStruct);

    GPIO_InitStruct.Pin = GPIO_PIN_7;
    GPIO_InitStruct.Mode = GPIO_MODE_AF_PP;
    GPIO_InitStruct.Pull = GPIO_NOPULL;
    GPIO_InitStruct.Speed = GPIO_SPEED_LOW;
    GPIO_InitStruct.Alternate = GPIO_AF13_DCMI;
    HAL_GPIO_Init(GPIOB, &GPIO_InitStruct);

    GPIO_InitStruct.Pin = GPIO_PIN_6 | GPIO_PIN_7;
    GPIO_InitStruct.Mode = GPIO_MODE_AF_PP;
    GPIO_InitStruct.Pull = GPIO_PULLUP;
    GPIO_InitStruct.Speed = GPIO_SPEED_HIGH;
    GPIO_InitStruct.Alternate = GPIO_AF13_DCMI;
    HAL_GPIO_Init(GPIOC, &GPIO_InitStruct);

    GPIO_InitStruct.Pin = GPIO_PIN_3;
    GPIO_InitStruct.Mode = GPIO_MODE_AF_PP;
    GPIO_InitStruct.Pull = GPIO_PULLUP;
    GPIO_InitStruct.Speed = GPIO_SPEED_HIGH;
    GPIO_InitStruct.Alternate = GPIO_AF13_DCMI;
    HAL_GPIO_Init(GPIOD, &GPIO_InitStruct);

    GPIO_InitStruct.Pin = GPIO_PIN_0 | GPIO_PIN_1 | GPIO_PIN_4 | GPIO_PIN_5 | GPIO_PIN_6;
    GPIO_InitStruct.Mode = GPIO_MODE_AF_PP;
    GPIO_InitStruct.Pull = GPIO_PULLUP;
    GPIO_InitStruct.Speed = GPIO_SPEED_HIGH;
    GPIO_InitStruct.Alternate = GPIO_AF13_DCMI;
    HAL_GPIO_Init(GPIOE, &GPIO_InitStruct);

    /* TIM3 GPIO Configuration: PB1 -> TIM3_CH4 */
    GPIO_InitStruct.Pin = GPIO_PIN_1;
    GPIO_InitStruct.Mode = GPIO_MODE_AF_PP;
    GPIO_InitStruct.Pull = GPIO_NOPULL;
    GPIO_InitStruct.Speed = GPIO_SPEED_FREQ_LOW;
    GPIO_InitStruct.Alternate = GPIO_AF2_TIM3;
    HAL_GPIO_Init(GPIOB, &GPIO_InitStruct);

    /* I2C1 Pin configuration */
    GPIO_InitStruct.Pin = GPIO_PIN_6 | GPIO_PIN_9;
    GPIO_InitStruct.Mode = GPIO_MODE_AF_OD;
    GPIO_InitStruct.Pull = GPIO_NOPULL;
    GPIO_InitStruct.Speed = GPIO_SPEED_FREQ_LOW;
    GPIO_InitStruct.Alternate = GPIO_AF4_I2C1;
    HAL_GPIO_Init(GPIOB, &GPIO_InitStruct);

    /* Configure Timer 3 channel 4 */
    __TIM3_CLK_ENABLE();

    tim3.Instance = TIM3;
    tim3.Init.Prescaler = 0;
    tim3.Init.CounterMode = TIM_COUNTERMODE_UP;
    tim3.Init.Period = Period - 1;
    tim3.Init.ClockDivision = 0;
    tim3.Init.RepetitionCounter = 0;
    tim3.Init.AutoReloadPreload = TIM_AUTORELOAD_PRELOAD_DISABLE;
    rc = HAL_TIM_PWM_Init(&tim3);
    if (rc != HAL_OK)
    {
        printf("[%s] HAL_TIM_PWM_Init() failed\n", __func__);
        return -1;
    }

    sMasterConfig.MasterOutputTrigger = TIM_TRGO_RESET;
    sMasterConfig.MasterSlaveMode = TIM_MASTERSLAVEMODE_DISABLE;
    rc = HAL_TIMEx_MasterConfigSynchronization(&tim3, &sMasterConfig);
    if (rc != HAL_OK)
    {
        printf("[%s] HAL_TIMEx_MasterConfigSynchronization() failed\n", __func__);
        return -1;
    }

    /* PWM configuration */
    sConfigOC.OCMode = TIM_OCMODE_PWM1;
    sConfigOC.Pulse = Period / 2;
    sConfigOC.OCPolarity = TIM_OCPOLARITY_HIGH;
    sConfigOC.OCFastMode = TIM_OCFAST_DISABLE;
    rc = HAL_TIM_PWM_ConfigChannel(&tim3, &sConfigOC, TIM_CHANNEL_4);
    if (rc != HAL_OK)
    {
        printf("[%s] HAL_TIM_PWM_ConfigChannel() failed\n", __func__);
        return -1;
    }
    HAL_TIM_PWM_Start(&tim3, TIM_CHANNEL_4);

    /* I2C1 config */
    __HAL_RCC_I2C1_CLK_ENABLE();

    hi2c1.Instance = I2C1;
    hi2c1.Init.Timing = 0x109095DF;
    hi2c1.Init.OwnAddress1 = 0;
    hi2c1.Init.AddressingMode = I2C_ADDRESSINGMODE_7BIT;
    hi2c1.Init.DualAddressMode = I2C_DUALADDRESS_DISABLE;
    hi2c1.Init.OwnAddress2 = 0;
    hi2c1.Init.OwnAddress2Masks = I2C_OA2_NOMASK;
    hi2c1.Init.GeneralCallMode = I2C_GENERALCALL_DISABLE;
    hi2c1.Init.NoStretchMode = I2C_NOSTRETCH_DISABLE;
    rc = HAL_I2C_Init(&hi2c1);
    if (rc != HAL_OK)
    {
        printf("[%s] HAL_I2C_Init() failed\n", __func__);
        return -1;
    }

    /* Reset DCMI */
    __DCMI_CLK_ENABLE();
    __HAL_RCC_DCMI_FORCE_RESET();
    HAL_Delay(20);
    __HAL_RCC_DCMI_RELEASE_RESET();

    /* Configure DCMI peripheral */
    hdcmi.Instance = DCMI;
    hdcmi.Init.SynchroMode = DCMI_SYNCHRO_HARDWARE;
    hdcmi.Init.PCKPolarity = DCMI_PCKPOLARITY_RISING;
    hdcmi.Init.VSPolarity = DCMI_VSPOLARITY_HIGH;
    hdcmi.Init.HSPolarity = DCMI_HSPOLARITY_LOW;
    hdcmi.Init.CaptureRate = DCMI_CR_ALL_FRAME;
    hdcmi.Init.ExtendedDataMode = DCMI_EXTEND_DATA_8B;
    hdcmi.Init.JPEGMode = DCMI_JPEG_DISABLE;
    rc = HAL_DCMI_Init(&hdcmi);
    if (rc != HAL_OK)
    {
        printf("[%s] HAL_DCMI_Init() failed\n", __func__);
        return -1;
    }

    /* DMA configuration */
    dma_init(&hdma, &dma_DCMI_0, DMA_PERIPH_TO_MEMORY, &hdcmi);
    __HAL_LINKDMA(&hdcmi, DMA_Handle, hdma);

    /* Reset camera, power down pin is active high */
    HAL_GPIO_WritePin(GPIOE, GPIO_PIN_7, GPIO_PIN_SET);
    HAL_Delay(20);
    HAL_GPIO_WritePin(GPIOE, GPIO_PIN_7, GPIO_PIN_RESET);

    /* Configure camera size */
    camera_setQVGA();

    /* Don't reset camera sensor timing when mode changes. */
    camera_read(0x6F, &val);
    val &= ~(1 << 7);
    camera_write(0x6F, val);

    printf("CAMERA INIT COMPLETE!\n");
    return 0;
}

void camera_uninit(void)
{
    HAL_GPIO_DeInit(GPIOA, GPIO_PIN_6 | GPIO_PIN_4);
    HAL_GPIO_DeInit(GPIOB, GPIO_PIN_7);
    HAL_GPIO_DeInit(GPIOC, GPIO_PIN_6 | GPIO_PIN_7);
    HAL_GPIO_DeInit(GPIOD, GPIO_PIN_3);
    HAL_GPIO_DeInit(
        GPIOE, GPIO_PIN_0 | GPIO_PIN_1 | GPIO_PIN_4 | GPIO_PIN_5 | GPIO_PIN_6);

    /* Disable DCMI clock */
    __DCMI_CLK_DISABLE();
}
