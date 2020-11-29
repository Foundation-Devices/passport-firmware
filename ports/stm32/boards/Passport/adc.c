// SPDX-FileCopyrightText: 2020 Foundation Devices, Inc.  <hello@foundationdevices.com>
// SPDX-License-Identifier: GPL-3.0-or-later
//
// Copyright 2020 - Foundation Devices Inc.
//

/*
 * Contains support for ADC3 - Board Revision
 * and ADC2 for Power Monitor
 * Init functions are called by board_init()
 * read_boardrev() is called as needed, currently
 * used by LCD display processing to determine active high/low for
 * SPI1 NSS pin.
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "stm32h7xx_hal.h"

#include "adc.h"

#define MAX_ADC_16BIT 65535
#define REF_VOLTAGE_MV 3000
#define MAX_SAMPLES_CNT 0xFFFF

#define MILLIVOLTS_PER_REVISION 500
#define PWRMON_I_SENSE_RESISTOR 5

/*
 * When doing single samples you cannot rely on
 * the value being exact, so adding a small offset
 * to the computed milli-volts resolves that issue.
 */
#define BOARD_REV_MV_OFFSET 20

/*
 * The number of samples to collect for the average
 * Current bounces around a lot so take more samples
 * and use an average.
 * Voltage may not be as bad so take fewer samples
 */
#define MAX_I_SAMPLES 20
#define MAX_V_SAMPLES 4

static ADC_HandleTypeDef hadc3;
static ADC_HandleTypeDef hadc2;

/*
 * adc2_init() - Sets up ADC2 which is used for Power Monitor and Noise inputs.
 */
HAL_StatusTypeDef adc2_init(void)
{
    GPIO_InitTypeDef GPIO_InitStruct = {0};
    HAL_StatusTypeDef ret = HAL_OK;

    hadc2.Instance = ADC2;
    ret = HAL_ADC_DeInit(&hadc2);
    if(ret != HAL_OK) {
        printf("Failed to DeInit ADC2\r\n");
        return ret;
    }

    __HAL_RCC_ADC12_CLK_ENABLE();
    /* ADC Periph interface clock configuration */
    __HAL_RCC_ADC_CONFIG(RCC_ADCCLKSOURCE_CLKP);

    /**ADC2 GPIO Configuration
    PC0     ------> ADC2_INP10 - NOISE_OUT2
    PC1     ------> ADC2_INP11 - NOISE_OUT1
    PC4     ------> ADC2_INP4  - PWRMON_V
    PC5     ------> ADC2_INP8  - PWRMON_I
    */

    GPIO_InitStruct.Pin = GPIO_PIN_0 | GPIO_PIN_1 | GPIO_PIN_4| GPIO_PIN_5; //
    GPIO_InitStruct.Mode = GPIO_MODE_ANALOG;
    GPIO_InitStruct.Pull = GPIO_NOPULL;
    HAL_GPIO_Init(GPIOC, &GPIO_InitStruct);

    /** Common config
    */
    // The ClockPrescaler can only be modified if ALL ADC instances are disabled!!!
    hadc2.Init.ClockPrescaler = ADC_CLOCK_ASYNC_DIV4; // ADC_CLOCK_ASYNC_DIV1

    hadc2.Init.Resolution = ADC_RESOLUTION_16B;
    hadc2.Init.ScanConvMode = ADC_SCAN_DISABLE;  // Needs to be ENABLE it processing more than 1 channel
    hadc2.Init.EOCSelection = ADC_EOC_SINGLE_CONV; // ADC_EOC_SEQ_CONV If doing more than one channel
    hadc2.Init.LowPowerAutoWait = ENABLE; // Says to use this with Polling was DISABLE;
    hadc2.Init.ContinuousConvMode = ENABLE;
    hadc2.Init.NbrOfConversion = 1; // Number of ranks to be converted within regular group sequencer
    hadc2.Init.DiscontinuousConvMode = DISABLE;  // Cannot be used if continuous mode is enabled.
    hadc2.Init.NbrOfDiscConversion = 1;
    hadc2.Init.ExternalTrigConv = ADC_SOFTWARE_START; // NOTE: This is common to ALL ADC instances..
    hadc2.Init.ExternalTrigConvEdge = ADC_EXTERNALTRIGCONVEDGE_NONE;
    hadc2.Init.ConversionDataManagement = ADC_CONVERSIONDATA_DR; // Can specify DMA for management of converted data
    hadc2.Init.Overrun = ADC_OVR_DATA_OVERWRITTEN; // ADC_OVR_DATA_PRESERVED
    hadc2.Init.LeftBitShift = ADC_LEFTBITSHIFT_NONE;

    /*
     * Perform oversampling to read multiple samples
     * and compute the average in HW.
     */
    hadc3.Init.OversamplingMode = ENABLE;
    hadc3.Init.Oversampling.Ratio = 0x20; /* Bit for 32x oversampling */
    hadc3.Init.Oversampling.RightBitShift = ADC_RIGHTBITSHIFT_5;
    hadc3.Init.Oversampling.TriggeredMode = ADC_TRIGGEREDMODE_SINGLE_TRIGGER;
    hadc3.Init.Oversampling.OversamplingStopReset = ADC_REGOVERSAMPLING_CONTINUED_MODE;

    ret = HAL_ADC_Init(&hadc2);
    if (ret != HAL_OK)
    {
        printf("Failed to init ADC2\r\n");;
        return ret;
    }

    /* Run the ADC calibration in single-ended mode */
    ret = HAL_ADCEx_Calibration_Start(&hadc2, ADC_CALIB_OFFSET, ADC_SINGLE_ENDED);
    if (ret != HAL_OK)
    {
        printf("ADC3 calibration failed\r\n");
        return ret;
    }

    return ret;
}

void enable_noise(void) {
    GPIO_InitTypeDef GPIO_InitStruct = {0};

    /*
     * PD8 Amp2_enable
     * PD9 Amp1_enable
     * PD10 Noise Bias enable
     */
    GPIO_InitStruct.Pin = GPIO_PIN_8 | GPIO_PIN_9 | GPIO_PIN_10;
    GPIO_InitStruct.Mode = GPIO_MODE_OUTPUT_PP;
    GPIO_InitStruct.Pull = GPIO_NOPULL;
    HAL_GPIO_Init(GPIOD, &GPIO_InitStruct);

    HAL_GPIO_WritePin(GPIOD, GPIO_PIN_8, 1);
    HAL_GPIO_WritePin(GPIOD, GPIO_PIN_9, 1);
    HAL_GPIO_WritePin(GPIOD, GPIO_PIN_10, 1);
}

void disable_noise(void) {
    /*
     * PD8 Amp2_enable
     * PD9 Amp1_enable
     * PD10 Noise Bias enable
     */

    HAL_GPIO_WritePin(GPIOD, GPIO_PIN_8, 0);
    HAL_GPIO_WritePin(GPIOD, GPIO_PIN_9, 0);
    HAL_GPIO_WritePin(GPIOD, GPIO_PIN_10, 0);
}


/*
 * read_noise_inputs() - Reads the two noise output channels and returns
 * the count values read.
 */
HAL_StatusTypeDef read_noise_inputs(uint32_t * noise1, uint32_t * noise2) {
    HAL_StatusTypeDef ret = HAL_OK;
    ADC_ChannelConfTypeDef sConfig = {0};

    /* Configure Noiseout 1 input Channel */
    sConfig.Channel = ADC_CHANNEL_11;  // Noise 1 channel 11 PC1 INP11
    sConfig.Rank = ADC_REGULAR_RANK_1;

    sConfig.SamplingTime =  ADC_SAMPLETIME_8CYCLES_5;
    sConfig.SingleDiff = ADC_SINGLE_ENDED;
    sConfig.OffsetNumber = ADC_OFFSET_NONE;
    sConfig.Offset = 0;
    sConfig.OffsetRightShift = DISABLE; /* No Right Offset Shift */
    sConfig.OffsetSignedSaturation = DISABLE; /* No Signed Saturation */
    ret = HAL_ADC_ConfigChannel(&hadc2, &sConfig);
    if (ret != HAL_OK)
    {
        printf("Failed to config ADC2 channel 8\r\n");;
        return ret;
    }

    /* Start processing for current (I) values */
    ret = HAL_ADC_Start(&hadc2);
    if (ret != HAL_OK)
    {
        printf("ADC2 start failed\r\n");
        return ret;
    }

    ret = HAL_ADC_PollForConversion(&hadc2, HAL_MAX_DELAY);
    if (ret != HAL_OK)
    {
        printf("ADC2 poll for conversion failed\r\n");
        return ret;
    }

    *noise1 = HAL_ADC_GetValue(&hadc2);

    ret = HAL_ADC_Stop(&hadc2);
    if (ret != HAL_OK)
    {
        printf("ADC2 start failed\r\n");
        return ret;
    }

    /* Configure Noiseout 2 input Channel */
    /* Noise 2 channel 10 PC0 INP10 */
    sConfig.Channel = ADC_CHANNEL_10;
    sConfig.Rank = ADC_REGULAR_RANK_1;
    sConfig.SamplingTime =  ADC_SAMPLETIME_8CYCLES_5;
    ret = HAL_ADC_ConfigChannel(&hadc2, &sConfig);
    if (ret != HAL_OK)
    {
        printf("Failed to config ADC2 channel 4\r\n");;
        return ret;
    }

    /* Now sample for Noise output 2 */
    ret = HAL_ADC_Start(&hadc2);
    if (ret != HAL_OK)
    {
        printf("ADC2 start failed\r\n");
        return ret;
    }

    ret = HAL_ADC_PollForConversion(&hadc2, HAL_MAX_DELAY);
    if (ret != HAL_OK)
    {
        printf("ADC2 poll for conversion failed\r\n");
        return ret;
    }

    *noise2 = HAL_ADC_GetValue(&hadc2);

    ret = HAL_ADC_Stop(&hadc2);
    if (ret != HAL_OK)
    {
        printf("ADC2 start failed\r\n");
        return ret;
    }

    return ret;
}

/*
 * read_powermon() Reads the power monitor current and voltage channels
 */
HAL_StatusTypeDef read_powermon(uint16_t * current, uint16_t * voltage) {
    HAL_StatusTypeDef ret = HAL_OK;
    ADC_ChannelConfTypeDef sConfig = {0};

    uint32_t adc_value_i;
    uint32_t adc_value_v;

    /* Configure Regular Power Monitor Current Channel */
    sConfig.Channel = ADC_CHANNEL_8;  // PWRMON_I channel PC5 INP8
    sConfig.Rank = ADC_REGULAR_RANK_1;

    sConfig.SamplingTime =  ADC_SAMPLETIME_8CYCLES_5;
    sConfig.SingleDiff = ADC_SINGLE_ENDED;
    sConfig.OffsetNumber = ADC_OFFSET_NONE;
    sConfig.Offset = 0;
    sConfig.OffsetRightShift = DISABLE; /* No Right Offset Shift */
    sConfig.OffsetSignedSaturation = DISABLE; /* No Signed Saturation */
    ret = HAL_ADC_ConfigChannel(&hadc2, &sConfig);
    if (ret != HAL_OK)
    {
        printf("Failed to config ADC2 channel 8\r\n");;
        return ret;
    }

    // Start processing for current (I) values
    ret = HAL_ADC_Start(&hadc2);
    if (ret != HAL_OK)
    {
        printf("ADC2 start failed\r\n");
        return ret;
    }

    ret = HAL_ADC_PollForConversion(&hadc2, HAL_MAX_DELAY);
    if (ret != HAL_OK)
    {
        printf("ADC2 poll for conversion failed\r\n");
        return ret;
    }

    adc_value_i = HAL_ADC_GetValue(&hadc2);
    /*
    * Current is I sense voltage divided by
    * the sense resistor value which is 5 ohms
    */

    *current = ((adc_value_i * REF_VOLTAGE_MV) / MAX_SAMPLES_CNT) / PWRMON_I_SENSE_RESISTOR;

    ret = HAL_ADC_Stop(&hadc2);
    if (ret != HAL_OK)
    {
        printf("ADC2 start failed\r\n");
        return ret;
    }

    /* Switch to the voltage channel */
    /* PWRMON_V channel PC4 INP4 */
    sConfig.Channel = ADC_CHANNEL_4;
    sConfig.Rank = ADC_REGULAR_RANK_1;
    sConfig.SamplingTime =  ADC_SAMPLETIME_8CYCLES_5;
    ret = HAL_ADC_ConfigChannel(&hadc2, &sConfig);
    if (ret != HAL_OK)
    {
        printf("Failed to config ADC2 channel 4\r\n");;
        return ret;
    }

    /* Now sample for voltage (V) */
    ret = HAL_ADC_Start(&hadc2);
    if (ret != HAL_OK)
    {
        printf("ADC2 start failed\r\n");
        return ret;
    }

    ret = HAL_ADC_PollForConversion(&hadc2, HAL_MAX_DELAY);
    if (ret != HAL_OK)
    {
        printf("ADC2 poll for conversion failed\r\n");
        return ret;
    }

    adc_value_v = HAL_ADC_GetValue(&hadc2);

    *voltage = (adc_value_v * REF_VOLTAGE_MV) / MAX_SAMPLES_CNT;

    ret = HAL_ADC_Stop(&hadc2);
    if (ret != HAL_OK)
    {
        printf("ADC2 start failed\r\n");
        return ret;
    }

    return ret;
}

/*
 * adc3_init() - Set up ADC3 which is used for the board revision
 */
HAL_StatusTypeDef adc3_init(void)
{
    HAL_StatusTypeDef ret = HAL_OK;

    ADC_ChannelConfTypeDef sConfig = {0};

    hadc3.Instance = ADC3;
    ret = HAL_ADC_DeInit(&hadc3);
    if (ret != HAL_OK)
    {
        printf("Failed to deinit ADC3\r\n");
        return ret;
    }

    /*
     * PC3 ----> ADC3 INP1
     */
    __HAL_RCC_ADC3_CLK_ENABLE();

    /**ADC3 GPIO Configuration
    PC3_C     ------> ADC3_INP1
    */
    HAL_SYSCFG_AnalogSwitchConfig(SYSCFG_SWITCH_PC3, SYSCFG_SWITCH_PC3_OPEN);

    hadc3.Instance = ADC3;
    hadc3.Init.ClockPrescaler = ADC_CLOCK_ASYNC_DIV2;  // 4
    hadc3.Init.Resolution = ADC_RESOLUTION_16B;
    hadc3.Init.ScanConvMode = ADC_SCAN_DISABLE;
    hadc3.Init.EOCSelection = ADC_EOC_SINGLE_CONV;
    hadc3.Init.LowPowerAutoWait = DISABLE;
    hadc3.Init.ContinuousConvMode = ENABLE;  // DIS
    hadc3.Init.NbrOfConversion = 1;
    hadc3.Init.DiscontinuousConvMode = DISABLE;
    hadc3.Init.ExternalTrigConv = ADC_SOFTWARE_START;
    hadc3.Init.ExternalTrigConvEdge = ADC_EXTERNALTRIGCONVEDGE_NONE;
    hadc3.Init.ConversionDataManagement = ADC_CONVERSIONDATA_DR;
    hadc3.Init.Overrun = ADC_OVR_DATA_OVERWRITTEN;
    hadc3.Init.LeftBitShift = ADC_LEFTBITSHIFT_NONE;

    /*
     * Perform oversampling to read multiple samples
     * and compute the average in HW.
     */
    hadc3.Init.OversamplingMode = ENABLE;
    hadc3.Init.Oversampling.Ratio = 0x20; /* Bit for 32x oversampling */
    hadc3.Init.Oversampling.RightBitShift = ADC_RIGHTBITSHIFT_5;
    hadc3.Init.Oversampling.TriggeredMode = ADC_TRIGGEREDMODE_SINGLE_TRIGGER;
    hadc3.Init.Oversampling.OversamplingStopReset = ADC_REGOVERSAMPLING_CONTINUED_MODE;

    ret = HAL_ADC_Init(&hadc3);
    if (ret != HAL_OK)
    {
        printf("ADC3 init failed\r\n");
        return ret;
    }
    /** Configure Regular Channel
    */
    sConfig.Channel = ADC_CHANNEL_1;
    sConfig.Rank = ADC_REGULAR_RANK_1;
    sConfig.SamplingTime = ADC_SAMPLETIME_8CYCLES_5;
    sConfig.SingleDiff = ADC_SINGLE_ENDED;
    sConfig.OffsetNumber = ADC_OFFSET_NONE;
    sConfig.Offset = 0;
    ret = HAL_ADC_ConfigChannel(&hadc3, &sConfig);
    if (ret != HAL_OK)
    {
        printf("Failed to config ADC3 channel\r\n");
    }

    /* Run the ADC calibration in single-ended mode */
    ret = HAL_ADCEx_Calibration_Start(&hadc3, ADC_CALIB_OFFSET, ADC_SINGLE_ENDED);
    if (ret != HAL_OK)
    {
        printf("ADC3 calibration failed\r\n");
    }

    return ret;
}

/*
 * read_boardrev() - Reads the board revision channel
 * and returns a numeric value based on the milli-volts
 * read divided by the number of milli-volts per revision.
 */
HAL_StatusTypeDef read_boardrev(uint16_t * board_rev)
{
    HAL_StatusTypeDef ret = HAL_OK;
    uint32_t adc_value;
    uint16_t millivolts;

    ret = HAL_ADC_Start(&hadc3);
    if (ret != HAL_OK)
    {
        printf("ADC3 start failed\r\n");
        return ret;
    }

    ret = HAL_ADC_PollForConversion(&hadc3, HAL_MAX_DELAY);
    if (ret != HAL_OK)
    {
        printf("ADC3 poll for conversion failed\r\n");
        return ret;
    }
    adc_value = HAL_ADC_GetValue(&hadc3);
    HAL_ADC_Stop(&hadc3);

    /*
     * The ADC consistently reads low when taking a single sample.
     * For now add an offset to make sure that we can properly compute the board rev number
     * TODO: This will need to be tested with the next board revision to make sure that it tracks properly.
     */

    millivolts = (((adc_value) * REF_VOLTAGE_MV) / MAX_SAMPLES_CNT); //  + BOARD_REV_MV_OFFSET;

    /*
     * Determine the board revision based on the milli-volts, probably will
     * need a tolerance for example if we are looking for 100 mv increments
     * then maybe have a +/- 6 mv window.
     *
     */

    *board_rev = millivolts / MILLIVOLTS_PER_REVISION;
    return ret;
}
