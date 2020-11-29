/*
 * Code generated from Atmel Start.
 *
 * This file will be overwritten when reconfiguring your Atmel Start project.
 * Please copy examples or other code you want to keep to a separate file
 * to avoid losing it when reconfiguring.
 */
#ifndef DRIVER_INIT_INCLUDED
#define DRIVER_INIT_INCLUDED

#include "atmel_start_pins.h"

#ifdef __cplusplus
extern "C" {
#endif

#include <hal_atomic.h>
#include <hal_delay.h>
#include <hal_gpio.h>
#include <hal_init.h>
#include <hal_io.h>
#include <hal_sleep.h>

#include <hal_adc_sync.h>

#include <hal_flash.h>

#include <hal_spi_m_sync.h>

#include <hal_i2c_m_sync.h>
#include <hal_usart_async.h>

#include <hal_spi_m_dma.h>

#include <hal_delay.h>
#include <hal_timer.h>
#include <hal_pwm.h>
#include <hpl_tc_base.h>

#include <hal_dac_sync.h>

#include "hal_usb_device.h"

extern struct adc_sync_descriptor ADC_0;

extern struct flash_descriptor      FLASH_0;
extern struct spi_m_sync_descriptor SPI_M_SERCOM0;

extern struct i2c_m_sync_desc        I2C_M_SYNC_SERCOM1;
extern struct usart_async_descriptor USART_ASYNC_SERCOM2;

extern struct spi_m_dma_descriptor SPI_M_DMA_SERCOM3;

extern struct timer_descriptor TIMER_0;

extern struct pwm_descriptor PWM_0;

extern struct dac_sync_descriptor DAC_0;

void ADC_0_PORT_init(void);
void ADC_0_CLOCK_init(void);
void ADC_0_init(void);

void FLASH_0_init(void);
void FLASH_0_CLOCK_init(void);

void SPI_M_SERCOM0_PORT_init(void);
void SPI_M_SERCOM0_CLOCK_init(void);
void SPI_M_SERCOM0_init(void);

void I2C_M_SYNC_SERCOM1_CLOCK_init(void);
void I2C_M_SYNC_SERCOM1_init(void);
void I2C_M_SYNC_SERCOM1_PORT_init(void);

void USART_ASYNC_SERCOM2_PORT_init(void);
void USART_ASYNC_SERCOM2_CLOCK_init(void);
void USART_ASYNC_SERCOM2_init(void);

void SPI_M_DMA_SERCOM3_PORT_init(void);
void SPI_M_DMA_SERCOM3_CLOCK_init(void);
void SPI_M_DMA_SERCOM3_init(void);

void delay_driver_init(void);

void PWM_0_PORT_init(void);
void PWM_0_CLOCK_init(void);
void PWM_0_init(void);

void DAC_0_PORT_init(void);
void DAC_0_CLOCK_init(void);
void DAC_0_init(void);

void USB_0_CLOCK_init(void);
void USB_0_init(void);

/**
 * \brief Perform system initialization, initialize pins and clocks for
 * peripherals
 */
void system_init(void);

#ifdef __cplusplus
}
#endif
#endif // DRIVER_INIT_INCLUDED
