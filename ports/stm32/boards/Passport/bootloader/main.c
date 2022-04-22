// SPDX-FileCopyrightText: 2020 Foundation Devices, Inc. <hello@foundationdevices.com>
// SPDX-License-Identifier: GPL-3.0-or-later
//
// SPDX-FileCopyrightText: 2018 Coinkite, Inc. <coldcardwallet.com>
// SPDX-License-Identifier: GPL-3.0-only
//
#include <string.h>
#include <errno.h>

#include "../stm32h7xx_hal_conf.h"

#include "delay.h"
#include "fwheader.h"
#include "pprng.h"
#include "secrets.h"
#include "se.h"
#include "se-atecc608a.h"
#include "utils.h"

#include "flash.h"
#include "verify.h"
#include "update.h"

#include "backlight.h"
#include "display.h"
#include "lcd-sharp-ls018B7dh02.h"
#ifndef DEBUG
#include "keypad-adp-5587.h"
#endif /* DEBUG */
#include "splash.h"
#include "ui.h"
#include "gpio.h"
#include "version_info.h"
#include "hash.h"
#include "secresult.h"

/*
 * This is an empty function to satisfy the linker requirement for init
 * when the startup_stm32h753xx.s file was pulled into the bootloader
 * build to define the full vector table.
 */
void _init(void)
{
}

void SysTick_Handler(void)
{
    HAL_IncTick();
}
#ifndef DEBUG
void EXTI15_10_IRQHandler(void)
{
    if (__HAL_GPIO_EXTI_GET_FLAG(1 << 12))
    {
        __HAL_GPIO_EXTI_CLEAR_FLAG(1 << 12);
        keypad_ISR();
    }
}
#endif /* DEBUG */
static void SystemClock_Config(void)
{
    HAL_StatusTypeDef rc;
    RCC_ClkInitTypeDef RCC_ClkInitStruct = {0};
    RCC_OscInitTypeDef RCC_OscInitStruct = {0};
    RCC_PeriphCLKInitTypeDef PeriphClkInitStruct = {0};

    /*!< Supply configuration update enable */
    rc = HAL_PWREx_ConfigSupply(PWR_LDO_SUPPLY);
    if (rc != HAL_OK)
        return;

    __HAL_PWR_VOLTAGESCALING_CONFIG(PWR_REGULATOR_VOLTAGE_SCALE1);

    while(!__HAL_PWR_GET_FLAG(PWR_FLAG_VOSRDY)) {}

    /* Enable HSE Oscillator and activate PLL with HSE as source */
    RCC_OscInitStruct.OscillatorType = RCC_OSCILLATORTYPE_HSE | RCC_OSCILLATORTYPE_HSI48;
    RCC_OscInitStruct.HSEState = RCC_HSE_ON;
    RCC_OscInitStruct.HSIState = RCC_HSI_OFF;
    RCC_OscInitStruct.CSIState = RCC_CSI_OFF;
    RCC_OscInitStruct.HSI48State = RCC_HSI48_ON;
    RCC_OscInitStruct.PLL.PLLState = RCC_PLL_ON;
    RCC_OscInitStruct.PLL.PLLSource = RCC_PLLSOURCE_HSE;

    RCC_OscInitStruct.PLL.PLLM = 1;
    RCC_OscInitStruct.PLL.PLLN = 120;
    RCC_OscInitStruct.PLL.PLLP = 2;
    RCC_OscInitStruct.PLL.PLLQ = 120;
    RCC_OscInitStruct.PLL.PLLR = 2;
    RCC_OscInitStruct.PLL.PLLFRACN = 0;

    RCC_OscInitStruct.PLL.PLLVCOSEL = RCC_PLL1VCOWIDE;
    RCC_OscInitStruct.PLL.PLLRGE = RCC_PLL1VCIRANGE_1;
    rc = HAL_RCC_OscConfig(&RCC_OscInitStruct);
    if (rc != HAL_OK)
    {
        while(1) { ; }
    }

    PeriphClkInitStruct.PeriphClockSelection =
        RCC_PERIPHCLK_RTC | RCC_PERIPHCLK_USART2  | RCC_PERIPHCLK_RNG;
    PeriphClkInitStruct.PLL2.PLL2M = 1;
    PeriphClkInitStruct.PLL2.PLL2N = 18;
    PeriphClkInitStruct.PLL2.PLL2P = 1;
    PeriphClkInitStruct.PLL2.PLL2Q = 2;
    PeriphClkInitStruct.PLL2.PLL2R = 2;
    PeriphClkInitStruct.PLL2.PLL2RGE = RCC_PLL2VCIRANGE_3;
    PeriphClkInitStruct.PLL2.PLL2VCOSEL = RCC_PLL2VCOMEDIUM;
    PeriphClkInitStruct.PLL2.PLL2FRACN = 6144;
    PeriphClkInitStruct.Usart234578ClockSelection = RCC_USART234578CLKSOURCE_D2PCLK1;
    PeriphClkInitStruct.RngClockSelection = RCC_RNGCLKSOURCE_HSI48;
    PeriphClkInitStruct.RTCClockSelection = RCC_RTCCLKSOURCE_LSI;
    rc = HAL_RCCEx_PeriphCLKConfig(&PeriphClkInitStruct);
    if (rc != HAL_OK)
    {
        while(1) { ; }
    }

    RCC_ClkInitStruct.ClockType = (RCC_CLOCKTYPE_SYSCLK | RCC_CLOCKTYPE_HCLK | RCC_CLOCKTYPE_D1PCLK1 | RCC_CLOCKTYPE_PCLK1 | \
                                 RCC_CLOCKTYPE_PCLK2  | RCC_CLOCKTYPE_D3PCLK1);
    RCC_ClkInitStruct.SYSCLKSource = RCC_SYSCLKSOURCE_PLLCLK;
    RCC_ClkInitStruct.SYSCLKDivider = RCC_SYSCLK_DIV1;
    RCC_ClkInitStruct.AHBCLKDivider = RCC_HCLK_DIV2;
    RCC_ClkInitStruct.APB3CLKDivider = RCC_APB3_DIV2;
    RCC_ClkInitStruct.APB1CLKDivider = RCC_APB1_DIV2;
    RCC_ClkInitStruct.APB2CLKDivider = RCC_APB2_DIV2;
    RCC_ClkInitStruct.APB4CLKDivider = RCC_APB4_DIV2;
    rc = HAL_RCC_ClockConfig(&RCC_ClkInitStruct, FLASH_LATENCY_4);
    if (rc != HAL_OK)
    {
        while(1) { ; }
    }

    __HAL_RCC_CSI_ENABLE() ;
    __HAL_RCC_SYSCFG_CLK_ENABLE() ;
    __HAL_RCC_GPIOA_CLK_ENABLE();
    __HAL_RCC_GPIOB_CLK_ENABLE();
    __HAL_RCC_GPIOC_CLK_ENABLE();
    __HAL_RCC_GPIOD_CLK_ENABLE();
    __HAL_RCC_GPIOE_CLK_ENABLE();
    __HAL_RCC_D2SRAM1_CLK_ENABLE();
    __HAL_RCC_D2SRAM2_CLK_ENABLE();
    __HAL_RCC_D2SRAM3_CLK_ENABLE();
}

// Recover from ECC errors during firmware updates
void HardFault_Handler(void)
{
    uint32_t cfsr = SCB->CFSR;

    if (cfsr & 0x8000) {
        uint32_t faultaddr = (uint32_t)SCB->BFAR;
        uint32_t fw_sector_start = FW_START;
        uint32_t fw_sector_end = FW_END;

        if ((faultaddr >= fw_sector_start) && (faultaddr < fw_sector_end)) {
            uint32_t faultsector = faultaddr & 0xFFF0000;

            flash_unlock();
            flash_sector_erase(faultsector);
            flash_lock();

            /* Reset the board */
            passport_reset();
        }
    }

    while (1);
}

static void MPU_Config(void)
{
    MPU_Region_InitTypeDef MPU_InitStruct;

    /* Disable MPU */
    HAL_MPU_Disable();

    /* Configure AXI SRAM region as non-executable */
    memset(&MPU_InitStruct, 0, sizeof(MPU_InitStruct));
    MPU_InitStruct.Enable = MPU_REGION_ENABLE;
    MPU_InitStruct.BaseAddress = 0x24000000;
    MPU_InitStruct.Size = MPU_REGION_SIZE_512KB;
    MPU_InitStruct.AccessPermission = MPU_REGION_FULL_ACCESS;
    MPU_InitStruct.IsBufferable = MPU_ACCESS_NOT_BUFFERABLE;
    MPU_InitStruct.IsCacheable = MPU_ACCESS_CACHEABLE;
    MPU_InitStruct.IsShareable = MPU_ACCESS_SHAREABLE;
    MPU_InitStruct.Number = MPU_REGION_NUMBER0;
    MPU_InitStruct.TypeExtField = MPU_TEX_LEVEL0;
    MPU_InitStruct.SubRegionDisable = 0x00;
    MPU_InitStruct.DisableExec = MPU_INSTRUCTION_ACCESS_DISABLE;
    HAL_MPU_ConfigRegion(&MPU_InitStruct);

    /* Configure SRAM1 region as non-executable */
    memset(&MPU_InitStruct, 0, sizeof(MPU_InitStruct));
    MPU_InitStruct.Enable = MPU_REGION_ENABLE;
    MPU_InitStruct.BaseAddress = 0x30000000;
    MPU_InitStruct.Size = MPU_REGION_SIZE_128KB;
    MPU_InitStruct.AccessPermission = MPU_REGION_FULL_ACCESS;
    MPU_InitStruct.IsBufferable = MPU_ACCESS_NOT_BUFFERABLE;
    MPU_InitStruct.IsCacheable = MPU_ACCESS_CACHEABLE;
    MPU_InitStruct.IsShareable = MPU_ACCESS_SHAREABLE;
    MPU_InitStruct.Number = MPU_REGION_NUMBER1;
    MPU_InitStruct.TypeExtField = MPU_TEX_LEVEL0;
    MPU_InitStruct.SubRegionDisable = 0x00;
    MPU_InitStruct.DisableExec = MPU_INSTRUCTION_ACCESS_DISABLE;
    HAL_MPU_ConfigRegion(&MPU_InitStruct);

    /* Configure SRAM2 region as non-executable */
    memset(&MPU_InitStruct, 0, sizeof(MPU_InitStruct));
    MPU_InitStruct.Enable = MPU_REGION_ENABLE;
    MPU_InitStruct.BaseAddress = 0x30020000;
    MPU_InitStruct.Size = MPU_REGION_SIZE_128KB;
    MPU_InitStruct.AccessPermission = MPU_REGION_FULL_ACCESS;
    MPU_InitStruct.IsBufferable = MPU_ACCESS_NOT_BUFFERABLE;
    MPU_InitStruct.IsCacheable = MPU_ACCESS_CACHEABLE;
    MPU_InitStruct.IsShareable = MPU_ACCESS_SHAREABLE;
    MPU_InitStruct.Number = MPU_REGION_NUMBER2;
    MPU_InitStruct.TypeExtField = MPU_TEX_LEVEL0;
    MPU_InitStruct.SubRegionDisable = 0x00;
    MPU_InitStruct.DisableExec = MPU_INSTRUCTION_ACCESS_DISABLE;
    HAL_MPU_ConfigRegion(&MPU_InitStruct);

    /* Configure SRAM3 region as non-executable */
    memset(&MPU_InitStruct, 0, sizeof(MPU_InitStruct));
    MPU_InitStruct.Enable = MPU_REGION_ENABLE;
    MPU_InitStruct.BaseAddress = 0x30040000;
    MPU_InitStruct.Size = MPU_REGION_SIZE_32KB;
    MPU_InitStruct.AccessPermission = MPU_REGION_FULL_ACCESS;
    MPU_InitStruct.IsBufferable = MPU_ACCESS_NOT_BUFFERABLE;
    MPU_InitStruct.IsCacheable = MPU_ACCESS_CACHEABLE;
    MPU_InitStruct.IsShareable = MPU_ACCESS_SHAREABLE;
    MPU_InitStruct.Number = MPU_REGION_NUMBER3;
    MPU_InitStruct.TypeExtField = MPU_TEX_LEVEL0;
    MPU_InitStruct.SubRegionDisable = 0x00;
    MPU_InitStruct.DisableExec = MPU_INSTRUCTION_ACCESS_DISABLE;
    HAL_MPU_ConfigRegion(&MPU_InitStruct);

    /* Configure SRAM4 region as non-executable */
    memset(&MPU_InitStruct, 0, sizeof(MPU_InitStruct));
    MPU_InitStruct.Enable = MPU_REGION_ENABLE;
    MPU_InitStruct.BaseAddress = 0x38000000;
    MPU_InitStruct.Size = MPU_REGION_SIZE_64KB;
    MPU_InitStruct.AccessPermission = MPU_REGION_FULL_ACCESS;
    MPU_InitStruct.IsBufferable = MPU_ACCESS_NOT_BUFFERABLE;
    MPU_InitStruct.IsCacheable = MPU_ACCESS_CACHEABLE;
    MPU_InitStruct.IsShareable = MPU_ACCESS_SHAREABLE;
    MPU_InitStruct.Number = MPU_REGION_NUMBER4;
    MPU_InitStruct.TypeExtField = MPU_TEX_LEVEL0;
    MPU_InitStruct.SubRegionDisable = 0x00;
    MPU_InitStruct.DisableExec = MPU_INSTRUCTION_ACCESS_DISABLE;
    HAL_MPU_ConfigRegion(&MPU_InitStruct);

    /* Configure ITCM region as non-executable */
    memset(&MPU_InitStruct, 0, sizeof(MPU_InitStruct));
    MPU_InitStruct.Enable = MPU_REGION_ENABLE;
    MPU_InitStruct.BaseAddress = 0x00000000;
    MPU_InitStruct.Size = MPU_REGION_SIZE_64KB;
    MPU_InitStruct.AccessPermission = MPU_REGION_FULL_ACCESS;
    MPU_InitStruct.IsBufferable = MPU_ACCESS_NOT_BUFFERABLE;
    MPU_InitStruct.IsCacheable = MPU_ACCESS_CACHEABLE;
    MPU_InitStruct.IsShareable = MPU_ACCESS_SHAREABLE;
    MPU_InitStruct.Number = MPU_REGION_NUMBER5;
    MPU_InitStruct.TypeExtField = MPU_TEX_LEVEL0;
    MPU_InitStruct.SubRegionDisable = 0x00;
    MPU_InitStruct.DisableExec = MPU_INSTRUCTION_ACCESS_DISABLE;
    HAL_MPU_ConfigRegion(&MPU_InitStruct);

    /* Configure DTCM region as non-executable */
    memset(&MPU_InitStruct, 0, sizeof(MPU_InitStruct));
    MPU_InitStruct.Enable = MPU_REGION_ENABLE;
    MPU_InitStruct.BaseAddress = 0x20000000;
    MPU_InitStruct.Size = MPU_REGION_SIZE_128KB;
    MPU_InitStruct.AccessPermission = MPU_REGION_FULL_ACCESS;
    MPU_InitStruct.IsBufferable = MPU_ACCESS_NOT_BUFFERABLE;
    MPU_InitStruct.IsCacheable = MPU_ACCESS_CACHEABLE;
    MPU_InitStruct.IsShareable = MPU_ACCESS_SHAREABLE;
    MPU_InitStruct.Number = MPU_REGION_NUMBER5;
    MPU_InitStruct.TypeExtField = MPU_TEX_LEVEL0;
    MPU_InitStruct.SubRegionDisable = 0x00;
    MPU_InitStruct.DisableExec = MPU_INSTRUCTION_ACCESS_DISABLE;
    HAL_MPU_ConfigRegion(&MPU_InitStruct);

    /* Configure Backup region as non-executable */
    memset(&MPU_InitStruct, 0, sizeof(MPU_InitStruct));
    MPU_InitStruct.Enable = MPU_REGION_ENABLE;
    MPU_InitStruct.BaseAddress = 0x38800000;
    MPU_InitStruct.Size = MPU_REGION_SIZE_4KB;
    MPU_InitStruct.AccessPermission = MPU_REGION_FULL_ACCESS;
    MPU_InitStruct.IsBufferable = MPU_ACCESS_NOT_BUFFERABLE;
    MPU_InitStruct.IsCacheable = MPU_ACCESS_CACHEABLE;
    MPU_InitStruct.IsShareable = MPU_ACCESS_SHAREABLE;
    MPU_InitStruct.Number = MPU_REGION_NUMBER5;
    MPU_InitStruct.TypeExtField = MPU_TEX_LEVEL0;
    MPU_InitStruct.SubRegionDisable = 0x00;
    MPU_InitStruct.DisableExec = MPU_INSTRUCTION_ACCESS_DISABLE;
    HAL_MPU_ConfigRegion(&MPU_InitStruct);

    /* Enable MPU */
    HAL_MPU_Enable(MPU_PRIVILEGED_DEFAULT);
}

void version(void)
{
    passport_firmware_header_t *fwhdr = (passport_firmware_header_t *)FW_HDR;
    char version[22] = {0};

    strcpy(version, "Version ");
    strcat(version, (char *)fwhdr->info.fwversion);

    show_splash(version);
}

#ifndef DEBUG

static void show_more_info(void)
{
    char message[80];

    // For the firmware header and hash
    uint8_t fw_hash[HASH_LEN];
    passport_firmware_header_t *fwhdr = (passport_firmware_header_t *)FW_HDR;

    uint8_t page = 0;
    while (true) {
        switch (page) {
            case 0:
                strcpy(message, "\nVersion:\n");
                strcat(message, build_version);
                strcat(message, "\n\nBuild Date:\n");
                strcat(message, build_date);

                if (ui_show_message("Bootloader Info", message, "SHUT DOWN", "NEXT", true)){
                    page++;
                } else {
                    display_clean_shutdown();
                }
                break;

            case 1:
                strcpy(message, "\nVersion:\n");
                strcat(message, (char*)fwhdr->info.fwversion);
                strcat(message, "\n\nBuild Date:\n");
                strcat(message, (char*)fwhdr->info.fwdate);
                if (ui_show_message("Firmware Info", message, "BACK", "NEXT", true)){
                    page++;
                } else {
                    page--;
                }
                break;

            case 2: {
                message[0] = '\n';
                message[1] = 0;
                hash_fw_user((uint8_t*)fwhdr, FW_HEADER_SIZE + fwhdr->info.fwlength, fw_hash, sizeof(fw_hash), false);

                bytes_to_hex_str(fw_hash, 32, &message[1], 8, '\n');

                if (ui_show_message("Download Hash", message, "BACK", "NEXT", true)){
                    page++;
                } else {
                    page--;
                }
                break;
            }

            case 3: {
                message[0] = '\n';
                message[1] = 0;
                hash_fw_user((uint8_t*)fwhdr, FW_HEADER_SIZE + fwhdr->info.fwlength, fw_hash, sizeof(fw_hash), true);

                bytes_to_hex_str(fw_hash, 32, &message[1], 8, '\n');

                if (ui_show_message("Build Hash", message, "BACK", "START", true)){
                    return;
                } else {
                    page--;
                }
                break;
            }
        }
    }
}
#endif /* DEBUG */

void random_boot_delay() {
    // Random delay to make cold-boot stepping attacks harder: 0 - 100ms
    uint32_t ms_to_delay = rng_sample() % 50;
    delay_ms(ms_to_delay);
}

int main(void)
{
    HAL_StatusTypeDef rc;
#ifndef DEBUG
    uint8_t keycount;
    uint8_t key;
#endif /* DEBUG */
    SystemInit();

    rc = HAL_Init();
    if (rc != HAL_OK)
        LOCKUP_FOREVER();

#if 0 /* This is interfering with firmware boot after an update. It
       * appears that the data cache is getting in the way of the
       * reset handler properly copying over the data section into SRAM.
       */
    SCB_EnableICache();
    SCB_EnableDCache();
#endif
    SystemClock_Config();

    // Set Brown-out level early on to reset on glitch attempts
    MODIFY_REG(FLASH->OPTSR_PRG, FLASH_OPTSR_BOR_LEV, (uint32_t)OB_BOR_LEVEL2);

#ifdef LOCKED
    // Ensure RDP level 2 on every boot in case of shenanigans
    if (!flash_is_security_level2()) {
        flash_lockdown_hard();
    }
#endif /* LOCKED */

    rng_setup();

    random_boot_delay();

    se_setup();

    // Force LED to red every time we restart for consistency
    se_set_gpio(0);

    // Initialize the LCD driver and clear the display
    backlight_init();
    backlight_intensity(100);
    display_init(true);

#ifndef DEBUG
    keypad_init();
    gpio_init();

#endif /* DEBUG */

    show_splash("");

    random_boot_delay();


    // Check for first-boot condition
    if (flash_is_programmed() == SEC_FALSE) {
        secresult result = flash_first_boot();
        switch (result) {
            case SEC_TRUE:
                // All good!
                break;

            case ERR_ROM_SECRETS_TOO_BIG:
                ui_show_fatal_error("ROM Secrets area is larger than 2048 bytes.");
                break;

            case ERR_INVALID_FIRMWARE_HEADER:
                ui_show_fatal_error("Invalid firmware header found during first boot.");
                break;

            case ERR_INVALID_FIRMWARE_SIGNATURE:
                ui_show_fatal_error("Invalid firmware signature found during first boot.");
                break;

            case ERR_UNABLE_TO_CONFIGURE_SE:
                ui_show_fatal_error("Unable to configure the Secure Element during first boot.");
                break;

            case ERR_UNABLE_TO_WRITE_ROM_SECRETS:
                ui_show_fatal_error("Unable to flash ROM secrets to end of bootloader flash block during first boot.");
                break;

            case ERR_UNABLE_TO_UPDATE_FIRMWARE_HASH_IN_SE:
                ui_show_fatal_error("Unable to program firmware hash into security chip during first boot.");
                break;

            default:
                ui_show_fatal_error("Unexpected error on first boot.");
                break;
        }
    }


    // Increment the boot counter
    uint32_t counter_result;
    if (se_add_counter(&counter_result, 1, 1) != 0) {
        ui_show_fatal_error("Unable to increment boot counter in the Secure Element. Device may have been tampered with.\n\nThis Passport is now permanently disabled.");
    }

    // Validate our pairing secret
    if (!se_valid_secret(rom_secrets->pairing_secret)) {
        ui_show_fatal_error("Unable to connect to the Secure Element.\n\nThis Passport is now permanently disabled.");
    }

    // Check for firmware update
    if (is_firmware_update_present() == SEC_TRUE) {
        update_firmware();
    }

    // Validate the internal firmware
    secresult result = verify_current_firmware(true);
    switch (result) {
        case SEC_TRUE:
            // All good!
            break;

        case ERR_INVALID_FIRMWARE_HEADER:
            ui_show_fatal_error("Invalid firmware header found.\n\nThis Passport is now permanently disabled.");
            break;

        case ERR_INVALID_FIRMWARE_SIGNATURE:
            ui_show_fatal_error("The installed firmware was not signed by a valid key.\n\nThis Passport is now permanently disabled.");
            break;

        case ERR_FIRMWARE_HASH_DOES_NOT_MATCH_SE:
            ui_show_fatal_error("The installed firmware hash does not match that expected by the Secure Element.\n\nThis Passport is now permanently disabled.");
            break;

        default:
            ui_show_fatal_error("Unexpected error when verifying current firmware.");
            break;
    }

    random_boot_delay();

    // Setup MPU
    MPU_Config();

    version();

#ifndef DEBUG
    /*
     * Delay for 3 seconds to allow the user to press a key indicating that
     * they would like to see board info or show the self test (in Python).
     */
    delay_ms(3000);

    // We use the first byte in sram4 to pass a parameter that we check for on the MicroPython side
    // to see if user wants to view the self-test.
    uint8_t* p_sram4 = (uint8_t*)0x38000000;
    *p_sram4 = 0;

    keycount = ring_buffer_dequeue(&key);
    if (keycount > 0)
    {
        // The '1' key
        if ((key & 0x7f) == 112)
        {
            show_more_info();
        }

        // The '7' key
        if ((key & 0x7f) == 107)
        {
            // Setting this byte to 1 signals main.py to show the self-test and serial number
            *p_sram4 = 1;
        }
    }
#endif

    // Show a warning message if non-Foundation firmware is loaded on the device
    if (is_user_signed_firmware_installed() == SEC_TRUE) {
        if (ui_show_message("Firmware Warning", "\nCustom, non-Foundation firmware is loaded on this Passport.\n\nOK to continue?", "NO", "YES", true)){
            // Continue booting
        } else {
            display_clean_shutdown();
        }
    }

    // From here we'll boot to Micropython: see stm32_main() in /ports/stm32/main.c
}
