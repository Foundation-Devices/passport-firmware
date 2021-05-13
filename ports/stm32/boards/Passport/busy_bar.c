// SPDX-FileCopyrightText: 2020 Foundation Devices, Inc.
// <hello@foundationdevices.com> SPDX-License-Identifier: GPL-3.0-or-later
//
// busy_bar.c - Timer and rendering code for busy bar
#include <string.h>
#include <math.h>
#include "display.h"
#include "firmware_graphics.h"

#define BUSY_BAR_HEIGHT 34

static TIM_HandleTypeDef htim7;

#ifdef SINE_WAVE_BUSY_BAR
#define NUM_BUSY_BAR_FRAMES 24
#define NUM_BUSY_BAR_FRAMES_TO_RENDER 20
static int busy_bar_frames[NUM_BUSY_BAR_FRAMES] = {6,5,4,3,2,1,0,1,2,3,4,5,6,5,4,3,2,1,0,1,2,3,4,5};

#define NUM_BUSY_BAR_IMAGES 7
static Image* busy_bar_images[NUM_BUSY_BAR_IMAGES] = {
  &busybar1_img,
  &busybar2_img,
  &busybar3_img,
  &busybar4_img,
  &busybar5_img,
  &busybar6_img,
  &busybar7_img,
};

#define X_OFFSET_PER_IMAGE 20
#define DIRECTION_RIGHT_TO_LEFT 1
#define DIRECTION_LEFT_TO_RIGHT 2

static float sin_offset = 0.0;
static void busy_bar(void)
{
    int16_t start_y = SCREEN_HEIGHT - BUSY_BAR_HEIGHT;
    uint16_t direction = DIRECTION_LEFT_TO_RIGHT;

    // Draw white area for the background since we only draw black pixels below
    display_fill_rect(0, start_y, SCREEN_WIDTH, BUSY_BAR_HEIGHT, 0);

    for (int16_t i=0; i<NUM_BUSY_BAR_FRAMES_TO_RENDER; i++) {
      int16_t x = (X_OFFSET_PER_IMAGE * i) - 10;
      uint16_t image_index = 1; //busy_bar_frames[i];
      float v = (float)x + sin_offset;  // Offset for animation
      float s = sin(v);
      int16_t scaled = (int16_t)(s * 7.0f);
      int16_t y = (int16_t)(scaled + start_y + 8);

      display_image(x + ((int16_t)(sin_offset * 2.0) % X_OFFSET_PER_IMAGE), y, busy_bar_images[image_index]->width, busy_bar_images[image_index]->height, busy_bar_images[image_index]->data, DRAW_MODE_WHITE_ONLY);
    }

    display_show_lines(start_y, start_y + SCREEN_HEIGHT - 1);
    sin_offset += 1.0;

    // Rotate frame indexes
    if (direction == DIRECTION_RIGHT_TO_LEFT) {
      int first = busy_bar_frames[0];
      for (int16_t i=0; i<NUM_BUSY_BAR_FRAMES - 1; i++) {
        busy_bar_frames[i] = busy_bar_frames[i+1];
      }
      busy_bar_frames[NUM_BUSY_BAR_FRAMES-1] =  first;
    } else {
      int last = busy_bar_frames[NUM_BUSY_BAR_FRAMES-1];
      for (int16_t i=NUM_BUSY_BAR_FRAMES - 1; i>0; i--) {
        busy_bar_frames[i] = busy_bar_frames[i-1];
      }
      busy_bar_frames[0] =  last;
    }
}
#endif

#define KNIGHT_RIDER_BUSY_BAR
#ifdef KNIGHT_RIDER_BUSY_BAR

#define NUM_BUSY_BAR_IMAGES 6
#define X_OFFSET_PER_IMAGE 23

typedef struct _bal_info_t {
  Image* image;
  int16_t x_pos;
  int8_t direction;
} ball_info_t;

ball_info_t ball_info[NUM_BUSY_BAR_IMAGES] = {
//  {&busybar7_img, 0, 1},
  {&busybar6_img, 0, 1},
  {&busybar5_img, 0, 1},
  {&busybar4_img, 0, 1},
  {&busybar3_img, 0, 1},
  {&busybar2_img, 0, 1},
  {&busybar1_img, 0, 1},
};

static bool first_activation = true;

static void busy_bar_reset_animation(void) {
  for (int16_t i=0; i<NUM_BUSY_BAR_IMAGES; i++) {
    ball_info[i].x_pos = -(X_OFFSET_PER_IMAGE*i);
    ball_info[i].direction = 1;
  }
}

static void busy_bar(void)
{
    int16_t start_y = SCREEN_HEIGHT - BUSY_BAR_HEIGHT;
    int16_t x_offset = (X_OFFSET_PER_IMAGE - ball_info[0].image->width) / 2;

    // Don't draw this the first time we show it on the splash screen -- looks better
    if (!first_activation) {
        // Draw a black separator line (should be exactly where the footer line is)
        display_fill_rect(0, start_y, SCREEN_WIDTH, 1, 1);
    }

    // Draw white area for the background since we only draw black pixels below
    display_fill_rect(0, start_y + 1, SCREEN_WIDTH, BUSY_BAR_HEIGHT - 1, 0);

    // Vertical offset to center busy bar
    int16_t voffset = (BUSY_BAR_HEIGHT / 2) - (ball_info[0].image->height/2);

    for (int16_t i=0; i<NUM_BUSY_BAR_IMAGES; i++) {
      display_image(ball_info[i].x_pos + x_offset, start_y + voffset, ball_info[i].image->width, ball_info[i].image->height, ball_info[i].image->data, DRAW_MODE_WHITE_ONLY);

      // Move this ball for next time
      ball_info[i].x_pos += X_OFFSET_PER_IMAGE * ball_info[i].direction;
      if ((ball_info[i].x_pos < 0 && ball_info[i].direction == -1) ||
          (ball_info[i].x_pos > SCREEN_WIDTH && ball_info[i].direction == 1)) {
        ball_info[i].direction = -ball_info[i].direction;
      }
    }

    int16_t end_y = start_y + BUSY_BAR_HEIGHT - 1;
    display_show_lines(start_y, end_y);
}
#endif

void TIM7_IRQHandler(void)
{
    if (__HAL_TIM_GET_FLAG(&htim7, TIM_FLAG_UPDATE) != RESET)
    {
        if (__HAL_TIM_GET_ITSTATUS(&htim7, TIM_IT_UPDATE) != RESET)
        {
            __HAL_TIM_CLEAR_FLAG(&htim7, TIM_FLAG_UPDATE);
            busy_bar();
        }
    }
    return;
}

void busy_bar_start(void)
{
    busy_bar_reset_animation();
    HAL_NVIC_EnableIRQ(TIM7_IRQn);
    HAL_TIM_Base_Start_IT(&htim7);
}

void busy_bar_stop(void)
{
    HAL_TIM_Base_Stop_IT(&htim7);
    HAL_NVIC_DisableIRQ(TIM7_IRQn);
    first_activation = false;
}

void busy_bar_init(void)
{
    TIM_ClockConfigTypeDef sClockSourceConfig = {0};
    TIM_MasterConfigTypeDef sMasterConfig = {0};
    uint16_t prescaler;
    uint32_t period;

    __TIM7_CLK_ENABLE();

    /* Fixed interrupt frequency of 1 Hz */
    prescaler = 24000 - 1;
    period = 1000 - 1;

    htim7.Instance = TIM7;
    htim7.Init.Prescaler = prescaler;
    htim7.Init.CounterMode = TIM_COUNTERMODE_UP;
    htim7.Init.Period = period;
    htim7.Init.ClockDivision = TIM_CLOCKDIVISION_DIV1;
    htim7.Init.AutoReloadPreload = TIM_AUTORELOAD_PRELOAD_DISABLE;
    HAL_TIM_Base_Init(&htim7);

    sClockSourceConfig.ClockSource = TIM_CLOCKSOURCE_INTERNAL;
    HAL_TIM_ConfigClockSource(&htim7, &sClockSourceConfig);

    sMasterConfig.MasterOutputTrigger = TIM_TRGO_RESET;
    sMasterConfig.MasterSlaveMode = TIM_MASTERSLAVEMODE_DISABLE;
    HAL_TIMEx_MasterConfigSynchronization(&htim7, &sMasterConfig);

    __HAL_TIM_CLEAR_FLAG(&htim7, TIM_SR_UIF);

    HAL_NVIC_SetPriority(TIM7_IRQn, 10, 0);
}
