// SPDX-FileCopyrightText: 2020 Foundation Devices, Inc. <hello@foundationdevices.com>
// SPDX-License-Identifier: GPL-3.0-or-later
//
// MP C foundation module, supports LCD, backlight, keypad and other devices as they are added

#include "py/builtin.h"
#include "py/obj.h"
#include "py/runtime.h"
#include <stdlib.h>
#include <string.h>
#include <math.h>

#include "bufhelper.h"

/* ADC related includes */
#include "adc.h"

// LCD related includes
#include "backlight.h"
#include "lcd-sharp-ls018B7dh02.h"
#include "spi.h"

// Keypad related includes
#include "keypad-adp-5587.h"
#include "py/objstr.h"
#include "ring_buffer.h"

// Camera related includes
#include "camera-ovm7690.h"
#include "image_conversion.h"

// QR related incldues
#include "quirc_internal.h"

// Main module includes
#include "modfoundation.h"

// BIP39 includes
#include "bip39_utils.h"

// QRCode includes
#include "qrcode.h"

#include "adc.h"
#include "busy_bar.h"
#include "dispatch.h"
#include "display.h"
#include "flash.h"
#include "frequency.h"
#include "fwheader.h"
#include "firmware-keys.h"
#include "gpio.h"
#include "pprng.h"
#include "se.h"
#include "stm32h7xx_hal.h"
#include "utils.h"
#include "sha256.h"
#include "se-config.h"
#include "pins.h"
#include "uECC.h"
#include "hash.h"

/* lcd class object, expand as needed with instance related details */
typedef struct _mp_obj_lcd_t
{
    mp_obj_base_t base;
    const spi_t* spi;

} mp_obj_lcd_t;

/* Backlight class object */
typedef struct _mp_obj_backlight_t
{
    mp_obj_base_t base;
} mp_obj_backlight_t;

/* keypad class object */
typedef struct _mp_obj_keypad_t
{
    mp_obj_base_t base;
} mp_obj_keypad_t;

/* Camera class object */
typedef struct _mp_obj_camera_t
{
    mp_obj_base_t base;
} mp_obj_camera_t;

/* Board Revision object */
typedef struct _mp_obj_boardrev_t
{
    mp_obj_base_t base;
} mp_obj_boardrev_t;

/* Power Monitor object */
typedef struct _mp_obj_powermon_t
{
    mp_obj_base_t base;
    uint16_t current;
    uint16_t voltage;
} mp_obj_powermon_t;

/* Noise Output object */
typedef struct _mp_obj_noise_t
{
    mp_obj_base_t base;
} mp_obj_noise_t;

/* QR decoder class object */
typedef struct _mp_obj_QR_t
{
    mp_obj_base_t base;
    struct quirc quirc;
    unsigned int width;
    unsigned int height;
} mp_obj_QR_t;

/* Internal flash class object */
typedef struct _mp_obj_SettingsFlash_t
{
    mp_obj_base_t base;
} mp_obj_SettingsFlash_t;

/* System class object */
typedef struct _mp_obj_System_t
{
    mp_obj_base_t base;
} mp_obj_System_t;

/* bip39 class object */
typedef struct _mp_obj_bip39_t
{
    mp_obj_base_t base;
} mp_obj_bip39_t;

/* QRCode class object */
typedef struct _mp_obj_QRCode_t
{
    mp_obj_base_t base;
    QRCode code;
} mp_obj_QRCode_t;

// Defines
#define QR_IMAGE_SIZE (396 * 330)
#define VIEWFINDER_IMAGE_SIZE ((240 * 240) / 8)

#define SETTINGS_FLASH_START 0x81E0000
#define SETTINGS_FLASH_SIZE 0x20000
#define SETTINGS_FLASH_END (SETTINGS_FLASH_START + SETTINGS_FLASH_SIZE - 1)

// Forward prototypes
void
turbo(bool enable);

/*=============================================================================
 * Start of keypad class
 *=============================================================================*/
STATIC mp_obj_t
keypad_make_new(const mp_obj_type_t* type, size_t n_args, size_t n_kw, const mp_obj_t* args)
{
    mp_obj_keypad_t* keypad = m_new_obj(mp_obj_keypad_t);
    keypad->base.type = type;

    keypad_init();
    return MP_OBJ_FROM_PTR(keypad);
}

STATIC mp_obj_t
keypad_get_keycode(mp_obj_t self)
{
    uint8_t buf[1];

    if (ring_buffer_dequeue(&buf[0]) == 0) {
        return mp_const_none;
    }
    // printf("keypad.get_keycode() 2: %d\n", buf[0]);
    return mp_obj_new_int_from_uint(buf[0]);
}
STATIC MP_DEFINE_CONST_FUN_OBJ_1(keypad_get_keycode_obj, keypad_get_keycode);

STATIC mp_obj_t
keypad___del__(mp_obj_t self)
{
    return mp_const_none;
}

STATIC MP_DEFINE_CONST_FUN_OBJ_1(keypad___del___obj, keypad___del__);

STATIC const mp_rom_map_elem_t keypad_locals_dict_table[] = {
    { MP_ROM_QSTR(MP_QSTR___name__), MP_ROM_QSTR(MP_QSTR_foundation) },
    { MP_ROM_QSTR(MP_QSTR_get_keycode), MP_ROM_PTR(&keypad_get_keycode_obj) },
    { MP_ROM_QSTR(MP_QSTR___del__), MP_ROM_PTR(&keypad___del___obj) },
};
STATIC MP_DEFINE_CONST_DICT(keypad_locals_dict, keypad_locals_dict_table);

const mp_obj_type_t keypad_type = {
    { &mp_type_type },
    .name = MP_QSTR_Keypad,
    .make_new = keypad_make_new,
    .locals_dict = (void*)&keypad_locals_dict,
};

/* End of Keypad class code */

/*=============================================================================
 * Start of LCD class
 *=============================================================================*/
void
lcd_obj_print(const mp_print_t* print, mp_obj_t self_in, mp_print_kind_t kind)
{
    mp_printf(print, "foundation obj print");
}

/* Instantiation */

/// def __init__(self, mode: int, key: bytes, iv: bytes = None) -> None:
///     '''
///     Initialize LCD object context. Return a MP LCD object
///     '''
STATIC mp_obj_t
lcd_obj_make_new(const mp_obj_type_t* type, size_t n_args, size_t n_kw, const mp_obj_t* args)
{
    mp_obj_lcd_t* lcd = m_new_obj(mp_obj_lcd_t);
    lcd->base.type = &lcd_type;
    lcd->spi = &spi_obj[0];
    // lcd_init(false);
    return MP_OBJ_FROM_PTR(lcd);
}

/* LCD object methods follow */
STATIC mp_obj_t
m_lcd_clear(mp_obj_t self_in, mp_obj_t invert_obj)
{
    uint8_t invert = mp_obj_get_int(invert_obj);
    lcd_clear(invert);
    return mp_const_none;
}
STATIC MP_DEFINE_CONST_FUN_OBJ_2(m_lcd_clear_obj, m_lcd_clear);

STATIC mp_obj_t
m_lcd_update(mp_obj_t self_in, mp_obj_t lcd_data)
{
    mp_uint_t interrupt_state;
    mp_buffer_info_t data_info;
    // Get the buffer info from the passed in object
    mp_get_buffer_raise(lcd_data, &data_info, MP_BUFFER_READ);

    interrupt_state = PASSPORT_KEYPAD_BEGIN_ATOMIC_SECTION();
    lcd_update(data_info.buf, true);
    PASSPORT_KEYPAD_END_ATOMIC_SECTION(interrupt_state);

    return mp_const_none;
}
STATIC MP_DEFINE_CONST_FUN_OBJ_2(m_lcd_update_obj, m_lcd_update);

STATIC mp_obj_t
foundation___del__(mp_obj_t self)
{
    lcd_deinit();
    return mp_const_none;
}
STATIC MP_DEFINE_CONST_FUN_OBJ_1(foundation___del___obj, foundation___del__);

/* End of LCD object methods */

/*
 * Class Locals Dictionary table for LCD class
 */
STATIC const mp_rom_map_elem_t lcd_locals_dict_table[] = {
    { MP_ROM_QSTR(MP_QSTR_clear), MP_ROM_PTR(&m_lcd_clear_obj) },
    { MP_ROM_QSTR(MP_QSTR_update), MP_ROM_PTR(&m_lcd_update_obj) },
};
STATIC MP_DEFINE_CONST_DICT(lcd_locals_dict, lcd_locals_dict_table);

const mp_obj_type_t lcd_type = {
    { &mp_type_type },
    .name = MP_QSTR_LCD,
    .print = lcd_obj_print,
    .make_new = lcd_obj_make_new,
    .locals_dict = (mp_obj_dict_t*)&lcd_locals_dict,
};
/* End of setup for LCD class */

/*=============================================================================
 * Start of backlight class
 *=============================================================================*/
STATIC mp_obj_t
backlight_obj_make_new(const mp_obj_type_t* type, size_t n_args, size_t n_kw, const mp_obj_t* args)
{
    mp_obj_backlight_t* backlight = m_new_obj(mp_obj_backlight_t);
    backlight->base.type = &backlight_type;
    backlight_minimal_init();
    return MP_OBJ_FROM_PTR(backlight);
}

/* LCD object methods follow */
STATIC mp_obj_t
m_backlight_intensity(mp_obj_t self_in, mp_obj_t intensity_obj)
{
    uint16_t intensity = mp_obj_get_int(intensity_obj);
    backlight_intensity(intensity);

    return mp_const_none;
}
STATIC MP_DEFINE_CONST_FUN_OBJ_2(m_backlight_intensity_obj, m_backlight_intensity);

/*
 * Class Locals Dictionary table for Backlight class
 */
STATIC const mp_rom_map_elem_t backlight_locals_dict_table[] = {
    { MP_ROM_QSTR(MP_QSTR_intensity), MP_ROM_PTR(&m_backlight_intensity_obj) },
};
STATIC MP_DEFINE_CONST_DICT(backlight_locals_dict, backlight_locals_dict_table);

const mp_obj_type_t backlight_type = {
    { &mp_type_type },
    .name = MP_QSTR_Backlight,
    //        .print = lcd_obj_print,
    .make_new = backlight_obj_make_new,
    .locals_dict = (mp_obj_dict_t*)&backlight_locals_dict,
};
/* End of setup for Backlight class */

/*=============================================================================
 * Start of Camera class
 *=============================================================================*/
STATIC mp_obj_t
camera_make_new(const mp_obj_type_t* type, size_t n_args, size_t n_kw, const mp_obj_t* args)
{
    mp_obj_camera_t* o = m_new_obj(mp_obj_camera_t);
    o->base.type = type;

    return MP_OBJ_FROM_PTR(o);
}

/// def enable(self, data: buffer) -> None
///     '''
///     Turn on the camera in preparation for calling snapshot().
///     '''
STATIC mp_obj_t
camera_enable(mp_obj_t self)
{
    camera_on();
    return mp_const_none;
}

/// def disable(self, data: buffer) -> None
///     '''
///     Turn off the camera.
///     '''
STATIC mp_obj_t
camera_disable(mp_obj_t self)
{
    camera_off();
    return mp_const_none;
}

/// def snapshot(self, image: buffer) -> BoolG
///     '''
///     Start a snapshot and wait for it to finish, then convert and copy it into the provided image buffers.
///     '''
STATIC mp_obj_t
camera_snapshot_(size_t n_args, const mp_obj_t* args)
{
    mp_buffer_info_t qr_image_info;
    mp_get_buffer_raise(args[1], &qr_image_info, MP_BUFFER_WRITE);
    uint16_t qr_w = mp_obj_get_int(args[2]);
    uint16_t qr_h = mp_obj_get_int(args[3]);
    if (qr_image_info.len != qr_w * qr_h) {
        printf("ERROR: QR buffer w/h not consistent with buffer size!\n");
        return mp_const_false;
    }
    if (qr_image_info.len != QR_IMAGE_SIZE) {
        printf("ERROR: QR buffer is the wrong size!\n");
        return mp_const_false;
    }

    mp_buffer_info_t viewfinder_image_info;
    mp_get_buffer_raise(args[4], &viewfinder_image_info, MP_BUFFER_WRITE);
    uint16_t viewfinder_w = mp_obj_get_int(args[5]);
    uint16_t viewfinder_h = mp_obj_get_int(args[6]);
    if (viewfinder_image_info.len != viewfinder_w * viewfinder_h / 8) {
        printf("ERROR: Viewfinder buffer w/h not consistent with buffer size!\n");
        return mp_const_false;
    }
    if (viewfinder_w > qr_w || viewfinder_h > qr_h) {
        // Viewfinder can't be larger than base image
        printf("ERROR: Viewfinder buffer is larger than QR buffer!\n");
        return mp_const_false;
    }

    if (camera_snapshot() < 0) {
        return mp_const_false;
    }

    uint16_t* rgb565 = camera_get_frame_buffer();

    //uint32_t start = HAL_GetTick();
    convert_rgb565_to_grayscale_and_mono(
      rgb565, qr_image_info.buf, qr_w, qr_h, viewfinder_image_info.buf, viewfinder_w, viewfinder_h);
    //uint32_t end = HAL_GetTick();
    //printf("conversion: %lums\n", end - start);
    return mp_const_true;
}

STATIC mp_obj_t
camera_get_line_data(mp_obj_t self_in, mp_obj_t line, mp_obj_t _line_num)
{
    // Get the buffer info from the passed in object
    mp_buffer_info_t line_info;
    mp_get_buffer_raise(line, &line_info, MP_BUFFER_WRITE);

    int line_num = mp_obj_get_int(_line_num);
    if (line_num < 0 || line_num >= CAMERA_HEIGHT || line_info.len < CAMERA_WIDTH * 2) {
        printf("line_num = %d line_info.len = %u\n", line_num, line_info.len);
        return mp_const_false;
    }

    uint16_t* rgb565 = camera_get_frame_buffer();

    uint32_t pixels_per_line = CAMERA_WIDTH;

    memcpy(line_info.buf, rgb565 + (line_num * pixels_per_line), pixels_per_line * 2); // Two bytes per pixel

    return mp_const_true;
}

STATIC MP_DEFINE_CONST_FUN_OBJ_1(camera_enable_obj, camera_enable);
STATIC MP_DEFINE_CONST_FUN_OBJ_1(camera_disable_obj, camera_disable);
STATIC MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(camera_snapshot_obj, 7, 7, camera_snapshot_);
STATIC MP_DEFINE_CONST_FUN_OBJ_3(camera_get_line_data_obj, camera_get_line_data);

STATIC mp_obj_t
camera___del__(mp_obj_t self)
{
    // mp_obj_camera_t *o = MP_OBJ_TO_PTR(self);
    return mp_const_none;
}

STATIC MP_DEFINE_CONST_FUN_OBJ_1(camera___del___obj, camera___del__);

STATIC const mp_rom_map_elem_t camera_locals_dict_table[] = {
    { MP_ROM_QSTR(MP_QSTR___name__),
      MP_ROM_QSTR(MP_QSTR_foundation) },
    { MP_ROM_QSTR(MP_QSTR_enable), MP_ROM_PTR(&camera_enable_obj) },
    { MP_ROM_QSTR(MP_QSTR_disable), MP_ROM_PTR(&camera_disable_obj) },
    { MP_ROM_QSTR(MP_QSTR_snapshot), MP_ROM_PTR(&camera_snapshot_obj) },
    { MP_ROM_QSTR(MP_QSTR_get_line_data), MP_ROM_PTR(&camera_get_line_data_obj) },
    { MP_ROM_QSTR(MP_QSTR___del__), MP_ROM_PTR(&camera___del___obj) },
};
STATIC MP_DEFINE_CONST_DICT(camera_locals_dict, camera_locals_dict_table);

STATIC const mp_obj_type_t camera_type = {
    { &mp_type_type },
    .name = MP_QSTR_camera,
    .make_new = camera_make_new,
    .locals_dict = (void*)&camera_locals_dict,
};
/* End of setup for Camera class */

/*=============================================================================
 * Start of Power Monitor class
 *=============================================================================*/

STATIC mp_obj_t
mod_foundation_powermon_make_new(const mp_obj_type_t* type, size_t n_args, size_t n_kw, const mp_obj_t* args)
{
    mp_obj_powermon_t* powermon = m_new_obj(mp_obj_powermon_t);
    powermon->base.type = type;

    return MP_OBJ_FROM_PTR(powermon);
}

STATIC mp_obj_t
mod_foundation_powermon_read(mp_obj_t self)
{
    int ret;
    uint16_t current = 0;
    uint16_t voltage = 0;
    mp_obj_t tuple[2];

    mp_obj_powermon_t* pPowerMon = (mp_obj_powermon_t*)self;

    ret = adc_read_powermon(&current, &voltage);
    if (ret < 0) {
        tuple[0] = mp_const_none;
        tuple[1] = mp_const_none;
        return mp_obj_new_tuple(2, tuple);
    }
    pPowerMon->current = current;
    pPowerMon->voltage = voltage;

    tuple[0] = mp_obj_new_int_from_uint(current);
    tuple[1] = mp_obj_new_int_from_uint(voltage);
    return mp_obj_new_tuple(2, tuple);
}
STATIC MP_DEFINE_CONST_FUN_OBJ_1(mod_foundation_powermon_read_obj, mod_foundation_powermon_read);

STATIC mp_obj_t
mod_foundation_powermon___del__(mp_obj_t self)
{
    return mp_const_none;
}

STATIC MP_DEFINE_CONST_FUN_OBJ_1(mod_foundation_powermon___del___obj, mod_foundation_powermon___del__);

STATIC const mp_rom_map_elem_t mod_foundation_powermon_locals_dict_table[] = {
    { MP_ROM_QSTR(MP_QSTR___name__), MP_ROM_QSTR(MP_QSTR_foundation) },
    { MP_ROM_QSTR(MP_QSTR_read), MP_ROM_PTR(&mod_foundation_powermon_read_obj) },
    { MP_ROM_QSTR(MP_QSTR___del__), MP_ROM_PTR(&mod_foundation_powermon___del___obj) },
};
STATIC MP_DEFINE_CONST_DICT(mod_foundation_powermon_locals_dict, mod_foundation_powermon_locals_dict_table);

const mp_obj_type_t powermon_type = {
    { &mp_type_type },
    .name = MP_QSTR_PMon,
    .make_new = mod_foundation_powermon_make_new,
    .locals_dict = (void*)&mod_foundation_powermon_locals_dict,
};

/* End of power monitor class */

/*=============================================================================
 * Start of Board Revision class
 *=============================================================================*/
STATIC mp_obj_t
mod_foundation_boardrev_make_new(const mp_obj_type_t* type, size_t n_args, size_t n_kw, const mp_obj_t* args)
{
    mp_obj_boardrev_t* boardrev = m_new_obj(mp_obj_boardrev_t);
    boardrev->base.type = type;

    return MP_OBJ_FROM_PTR(boardrev);
}

STATIC mp_obj_t
mod_foundation_boardrev_read(mp_obj_t self)
{
    HAL_StatusTypeDef ret;
    uint16_t board_rev = 0;

    ret = adc_read_boardrev(&board_rev);
    if (ret < 0) {
        return mp_const_none;
    }
    return mp_obj_new_int_from_uint(board_rev);
}
STATIC MP_DEFINE_CONST_FUN_OBJ_1(mod_foundation_boardrev_read_obj, mod_foundation_boardrev_read);

STATIC mp_obj_t
mod_foundation_boardrev___del__(mp_obj_t self)
{
    return mp_const_none;
}

STATIC MP_DEFINE_CONST_FUN_OBJ_1(mod_foundation_boardrev___del___obj, mod_foundation_boardrev___del__);

STATIC const mp_rom_map_elem_t mod_foundation_boardrev_locals_dict_table[] = {
    { MP_ROM_QSTR(MP_QSTR___name__), MP_ROM_QSTR(MP_QSTR_foundation) },
    { MP_ROM_QSTR(MP_QSTR_read), MP_ROM_PTR(&mod_foundation_boardrev_read_obj) },
    { MP_ROM_QSTR(MP_QSTR___del__), MP_ROM_PTR(&mod_foundation_boardrev___del___obj) },
};

STATIC MP_DEFINE_CONST_DICT(mod_foundation_boardrev_locals_dict, mod_foundation_boardrev_locals_dict_table);

const mp_obj_type_t boardrev_type = {
    { &mp_type_type },
    .name = MP_QSTR_Bdrev,
    .make_new = mod_foundation_boardrev_make_new,
    .locals_dict = (void*)&mod_foundation_boardrev_locals_dict,
};

/* End of board revision class */

/*=============================================================================
 * Start of Noise Output class
 *=============================================================================*/

STATIC mp_obj_t
mod_foundation_noise_make_new(const mp_obj_type_t* type, size_t n_args, size_t n_kw, const mp_obj_t* args)
{
    mp_obj_noise_t* noise = m_new_obj(mp_obj_noise_t);
    noise->base.type = type;
    /*
     * Need to enable the noise amp enables.
     */
    adc_enable_noise();

    return MP_OBJ_FROM_PTR(noise);
}

STATIC mp_obj_t
mod_foundation_noise_read(mp_obj_t self)
{
    HAL_StatusTypeDef ret;
    uint32_t noise1 = 0;
    uint32_t noise2 = 0;
    mp_obj_t tuple[2];

    ret = adc_read_noise_inputs(&noise1, &noise2);
    if (ret < 0) {
        tuple[0] = mp_const_none;
        tuple[1] = mp_const_none;
        return mp_obj_new_tuple(2, tuple);
    }

    tuple[0] = mp_obj_new_int_from_uint(noise1);
    tuple[1] = mp_obj_new_int_from_uint(noise2);
    return mp_obj_new_tuple(2, tuple);
}
STATIC MP_DEFINE_CONST_FUN_OBJ_1(mod_foundation_noise_read_obj, mod_foundation_noise_read);

bool
get_random_uint16(uint16_t* result)
{
    HAL_StatusTypeDef ret;
    uint32_t noise1 = 0;
    uint32_t noise2 = 0;
    uint16_t r = 0;

    for (int i = 0; i < 4; i++) {
        r = r << 4;

        HAL_Delay(1);

        ret = adc_read_noise_inputs(&noise1, &noise2);
        if (ret < 0) {
            return false;
        }

        r ^= noise1 ^ noise2;
    }
    *result = r;
    return true;
}

// Flags to select which entroy sources to combine
#define AVALANCHE_SOURCE 1
#define MCU_RNG_SOURCE 2
#define SE_RNG_SOURCE 4
#define ALS_SOURCE 8

// Function to combine multiple sources of randomness together
STATIC mp_obj_t
mod_foundation_noise_random_bytes(mp_obj_t self, const mp_obj_t buf, mp_obj_t _sources)
{
    mp_buffer_info_t buf_info;
    mp_get_buffer_raise(buf, &buf_info, MP_BUFFER_WRITE);

    // Buffer must be at least 4 bytes - if less is needed, caller can extract 1-3 bytes from a 4-byte buffer.
    if (buf_info.len < 4) {
        return false;
    }

    // Need to be fast for this
    turbo(true);

    int sources = mp_obj_get_int(_sources);
    // printf("sources = 0x%02x  buf_info.len=%d\n", sources, buf_info.len);
    if (!(sources & AVALANCHE_SOURCE) && !(sources & MCU_RNG_SOURCE) && !(sources & SE_RNG_SOURCE)) {
        // printf("Bad sources, so picking Avalanche!\n");
        // Ensure we always use at least one high entropy source even if caller made a mistake.
        // If you just want als value, you can read it separately.
        sources |= AVALANCHE_SOURCE;
    }

    if (sources & AVALANCHE_SOURCE) {
        uint8_t* pbuf8 = (uint8_t*)buf_info.buf;
        for (int i = 0; i < buf_info.len;) {
            uint8_t sample[2];
            bool result = get_random_uint16((uint16_t*)sample);
            if (!result) {
                turbo(false);
                // printf("failed to get Avalanche sample!\n");
                return mp_const_false;
            }

            // printf("AVALANCHE SAMPLE: 0x%02x%02x\n", sample[0], sample[1]);
            if (i < buf_info.len) {
                pbuf8[i] = sample[0];
                i++;
            }
            if (i < buf_info.len) {
                pbuf8[i] = sample[1];
                i++;
            }
        }
    }

    // MCU RNG
    if (sources & MCU_RNG_SOURCE) {
        // printf("Using MCU source\n");
        uint32_t* pbuf32 = (uint32_t*)buf_info.buf;

        // NOTE: We don't sample and mixin additional entropy into the final 1-3 bytes if buffer size
        //       is not a multiple of 4 bytes.
        for (int i = 0; i < buf_info.len / 4; i++) {
            uint32_t sample = rng_sample();
            // printf("MCU SAMPLE: 0x%08lx\n", sample);
            // XOR in the sample
            *(pbuf32 + i) ^= sample;
        }
    }

    // Secure Element RNG
    if (sources & SE_RNG_SOURCE) {
        uint8_t* pbuf8 = (uint8_t*)buf_info.buf;
        uint8_t* pbuf8_end = pbuf8 + buf_info.len;
        uint8_t num_in[20], sample[32];
        memset(num_in, 0, 20);

        for (int i = 0; i < buf_info.len / 32; i++) {
            int rc = se_pick_nonce(num_in, sample);
            if (rc < 0) {
                se_show_error();
                turbo(false);
                return mp_const_false;
            }

            // uint32_t* s = (uint32_t*)sample;
            // printf("SE SAMPLE: 0x%08lx %08lx %08lx %08lx\n", *s, *(s+1), *(s+2), *(s+3));

            // Mixin the sample values - don't overflow output buffer
            xor_mixin(pbuf8, sample, MIN(pbuf8_end - pbuf8, 32));
            pbuf8 += 32;
        }
    }

    // printf("1 buf: ");
    // uint8_t* pbuf8 = (uint8_t*)buf_info.buf;
    // for (int i=0; i<buf_info.len; i++) {
    //    printf("%02x", pbuf8[i]);
    // }
    // printf("\n");

    // Ambient Light Sensor
    if (sources & ALS_SOURCE) {
        // printf("Using ALS source\n");
        uint16_t* pbuf16 = (uint16_t*)buf_info.buf;

        // Pick a random offset at which to insert the
        uint16_t rnd_offset = rng_sample() % (buf_info.len / 2 - 2);
        // printf("als rnd_offset=%d\n", rnd_offset);

        // Just mix in one sample since it's not likely to vary by much sampled close together in time
        uint16_t sample;
        adc_read_als(&sample);
        // printf("als sample=0x%04x\n", sample);
        *(pbuf16 + rnd_offset) ^= sample;
    }

    // TODO: check final result for basic randomness

    // print_hex_buf("Final buf: ", buf_info.buf, buf_info.len);

    turbo(false);
    return mp_const_true;
}
STATIC MP_DEFINE_CONST_FUN_OBJ_3(mod_foundation_noise_random_bytes_obj, mod_foundation_noise_random_bytes);

STATIC mp_obj_t
mod_foundation_noise___del__(mp_obj_t self)
{
    adc_disable_noise();
    return mp_const_none;
}

STATIC MP_DEFINE_CONST_FUN_OBJ_1(mod_foundation_noise___del___obj, mod_foundation_noise___del__);

STATIC const mp_rom_map_elem_t mod_foundation_noise_locals_dict_table[] = {
    { MP_ROM_QSTR(MP_QSTR___name__), MP_ROM_QSTR(MP_QSTR_foundation) },
    { MP_ROM_QSTR(MP_QSTR_read), MP_ROM_PTR(&mod_foundation_noise_read_obj) },
    { MP_ROM_QSTR(MP_QSTR_random_bytes), MP_ROM_PTR(&mod_foundation_noise_random_bytes_obj) },
    { MP_ROM_QSTR(MP_QSTR___del__), MP_ROM_PTR(&mod_foundation_noise___del___obj) },
};
STATIC MP_DEFINE_CONST_DICT(mod_foundation_noise_locals_dict, mod_foundation_noise_locals_dict_table);

const mp_obj_type_t noise_type = {
    { &mp_type_type },
    .name = MP_QSTR_PMon,
    .make_new = mod_foundation_noise_make_new,
    .locals_dict = (void*)&mod_foundation_noise_locals_dict,
};

/* End of Noise output class */

/*=============================================================================
 * Start of QR decoder class
 *=============================================================================*/

/// def __init__(self, mode: int, key: bytes, iv: bytes = None) -> None:
///     '''
///     Initialize QR context.
///     '''
STATIC mp_obj_t
QR_make_new(const mp_obj_type_t* type, size_t n_args, size_t n_kw, const mp_obj_t* args)
{
    mp_obj_QR_t* o = m_new_obj(mp_obj_QR_t);
    o->base.type = type;
    if (n_args != 3) {
        printf("ERROR: QR called with wrong number of arguments!");
        return mp_const_none;
    }

    o->width = mp_obj_get_int(args[0]);
    o->height = mp_obj_get_int(args[1]);
    mp_buffer_info_t image_info;
    mp_get_buffer_raise(args[2], &image_info, MP_BUFFER_READ);

    unsigned int expected_image_len = o->width * o->height;
    if (image_info.len != expected_image_len) {
        printf("ERROR: Invalid buffer size for this decoder. Expected %u\n", expected_image_len);
        return mp_const_none;
    }

    if (quirc_init(&o->quirc, o->width, o->height, image_info.buf) < 0) {
        printf("ERROR: Unable to initialize quirc!\n");
        return mp_const_none;
    }

    return MP_OBJ_FROM_PTR(o);
}

struct quirc_code code;
struct quirc_data data;

//#define QR_DEBUG
/// def find_qr_codes(self, image: image) -> array of strings:
///     '''
///     Find QR codes in image.
///     '''
STATIC mp_obj_t
QR_find_qr_codes(mp_obj_t self)
{
    mp_obj_QR_t* o = MP_OBJ_TO_PTR(self);

#ifdef QR_DEBUG
    printf("find_qr_codes: %u, %u\n", o->width, o->height);
#endif

    // Prepare to decode
    quirc_begin(&o->quirc, NULL, NULL);
#ifdef QR_DEBUG
    printf("w=%u, h=%u\n", o->width, o->height);
#endif

    // This triggers the decoding of the image we just gave quirc
    quirc_end(&o->quirc);

    // Let's see if we got any results
    int num_codes = quirc_count(&o->quirc);
#ifdef QR_DEBUG
    printf("num_codes=%d\n", num_codes);
#endif

    if (num_codes == 0) {
#ifdef QR_DEBUG
        printf("No codes found\n");
#endif
        return mp_const_none;
    }

    // Extract the first code found only, even if multiple were found
    quirc_extract(&o->quirc, 0, &code);
#ifdef QR_DEBUG
    printf("quirc_extract() done\n");
#endif

    // Decoding stage
    quirc_decode_error_t err = quirc_decode(&code, &data);
    if (err) {
        printf("ERROR: Decode failed: %s\n", quirc_strerror(err));
        return mp_const_none;
    } else {
#ifdef QR_DEBUG
        printf("Data: %s\n", data.payload);
#endif
    }

    // Return the payload as the function result
    // const char* payload = mp_obj_str_get_str(data.payload);
    // printf("Data: %s\n", payload);

    vstr_t vstr;
    int code_len = strlen((const char*)data.payload);

    vstr_init(&vstr, code_len + 1);
    vstr_add_strn(&vstr, (const char*)data.payload, code_len); // Can append to vstr if necessary

    return mp_obj_new_str_from_vstr(&mp_type_str, &vstr);
}
STATIC MP_DEFINE_CONST_FUN_OBJ_1(QR_find_qr_codes_obj, QR_find_qr_codes);

STATIC mp_obj_t
QR___del__(mp_obj_t self)
{
    mp_obj_QR_t* o = MP_OBJ_TO_PTR(self);
    quirc_destroy(&o->quirc);
    return mp_const_none;
}

STATIC MP_DEFINE_CONST_FUN_OBJ_1(QR___del___obj, QR___del__);

STATIC const mp_rom_map_elem_t QR_locals_dict_table[] = {
    { MP_ROM_QSTR(MP_QSTR___name__), MP_ROM_QSTR(MP_QSTR_foundation) },
    { MP_ROM_QSTR(MP_QSTR_find_qr_codes), MP_ROM_PTR(&QR_find_qr_codes_obj) },
    { MP_ROM_QSTR(MP_QSTR___del__), MP_ROM_PTR(&QR___del___obj) },
};
STATIC MP_DEFINE_CONST_DICT(QR_locals_dict, QR_locals_dict_table);

STATIC const mp_obj_type_t QR_type = {
    { &mp_type_type },
    .name = MP_QSTR_QR,
    .make_new = QR_make_new,
    .locals_dict = (void*)&QR_locals_dict,
};
/* End of setup for QR decoder class */

/*=============================================================================
 * Start of SettingsFlash class
 *=============================================================================*/

/// def __init__(self, mode: int, key: bytes, iv: bytes = None) -> boolean:
///     '''
///     Initialize SettingsFlash context.
///     '''
STATIC mp_obj_t
SettingsFlash_make_new(const mp_obj_type_t* type, size_t n_args, size_t n_kw, const mp_obj_t* args)
{
    mp_obj_SettingsFlash_t* o = m_new_obj(mp_obj_SettingsFlash_t);
    o->base.type = type;
    return MP_OBJ_FROM_PTR(o);
}

// #define FLASH_DEBUG
/// def write(self, dest_addr, data) -> boolean
///     '''
///     Write data to internal flash
///     '''
STATIC mp_obj_t
SettingsFlash_write(mp_obj_t self, mp_obj_t dest_addr, mp_obj_t data)
{
    uint32_t flash_addr = mp_obj_get_int(dest_addr);
    mp_buffer_info_t data_info;
    mp_get_buffer_raise(data, &data_info, MP_BUFFER_READ);

    if (flash_addr < SETTINGS_FLASH_START || flash_addr + data_info.len - 1 > SETTINGS_FLASH_END ||
        data_info.len % 4 != 0) {
#ifdef FLASH_DEBUG
        printf("ERROR: SettingsFlash_write: bad parameters: flash_addr=0x%08lx\nSETTINGS_FLASH_START=0x%08x\nSETTINGS_FLASH_END=0x%08x\ndata_info.len=0x%04x\n",
            flash_addr,
            SETTINGS_FLASH_START,
            SETTINGS_FLASH_END,
            data_info.len);
#endif
        return mp_const_false;
    }

#ifdef FLASH_DEBUG
    printf("SettingsFlash_write: %u bytes to 0x%08lx\n", data_info.len, flash_addr);

    // for (uint32_t i=0; i<data_info.len;) {
    //     printf("%02x ", ((uint8_t*)data_info.buf)[i]);
    //     i++;
    //     if (i % 32 == 0) {
    //         printf("\n");
    //     }
    // }
#endif

    // NOTE: This function doesn't return any error/success info
    flash_write(flash_addr, data_info.buf, data_info.len / 4);

#ifdef FLASH_DEBUG
    printf("write: DONE\n");
#endif

    return mp_const_true;
}

/// def erase(self, buf) -> boolean
///     '''
///     Erase all of flash (H7 doesn't provide facility to erase less than the whole 128K)
///     '''
STATIC mp_obj_t
SettingsFlash_erase(mp_obj_t self)
{
#ifdef FLASH_DEBUG
    printf("SettingsFlash_erase()\n");
#endif

    // NOTE: This function doesn't return any error/success info
    flash_erase(SETTINGS_FLASH_START, SETTINGS_FLASH_SIZE / 4);

    return mp_const_true;
}

STATIC MP_DEFINE_CONST_FUN_OBJ_3(SettingsFlash_write_obj, SettingsFlash_write);
STATIC MP_DEFINE_CONST_FUN_OBJ_1(SettingsFlash_erase_obj, SettingsFlash_erase);

STATIC mp_obj_t
SettingsFlash___del__(mp_obj_t self)
{
    return mp_const_none;
}

STATIC MP_DEFINE_CONST_FUN_OBJ_1(SettingsFlash___del___obj, SettingsFlash___del__);

STATIC const mp_rom_map_elem_t SettingsFlash_locals_dict_table[] = {
    { MP_ROM_QSTR(MP_QSTR___name__), MP_ROM_QSTR(MP_QSTR_foundation) },
    { MP_ROM_QSTR(MP_QSTR_write), MP_ROM_PTR(&SettingsFlash_write_obj) },
    { MP_ROM_QSTR(MP_QSTR_erase), MP_ROM_PTR(&SettingsFlash_erase_obj) },
    { MP_ROM_QSTR(MP_QSTR___del__), MP_ROM_PTR(&SettingsFlash___del___obj) },
};
STATIC MP_DEFINE_CONST_DICT(SettingsFlash_locals_dict, SettingsFlash_locals_dict_table);

STATIC const mp_obj_type_t SettingsFlash_type = {
    { &mp_type_type },
    .name = MP_QSTR_SettingsFlash,
    .make_new = SettingsFlash_make_new,
    .locals_dict = (void*)&SettingsFlash_locals_dict,
};
/* End of setup for internal flash class */

/*=============================================================================
 * Start of System class
 *=============================================================================*/

/// def __init__(self, mode: int, key: bytes, iv: bytes = None) -> boolean:
///     '''
///     Initialize System context.
///     '''
STATIC mp_obj_t
System_make_new(const mp_obj_type_t* type, size_t n_args, size_t n_kw, const mp_obj_t* args)
{
    mp_obj_System_t* o = m_new_obj(mp_obj_System_t);
    o->base.type = type;
    return MP_OBJ_FROM_PTR(o);
}

#define SYSTEM_DEBUG
/// def reset(self) -> None
///     '''
///     Perform a warm reset of the system (should be mostly the same as turning it off and then on)
///     '''
STATIC mp_obj_t
System_reset(mp_obj_t self)
{
    passport_reset();
    return mp_const_none;
}

/// def shutdown(self) -> None
///     '''
///    Shutdown power to the Passport
///     '''
STATIC mp_obj_t
System_shutdown(mp_obj_t self)
{
    // We clear the memory display and then shutdown
    display_clean_shutdown();
    return mp_const_none;
}

/// def dispatch(self, command: int, buf: bytes, len: int, arg2: int, ) -> array of strings:
///     '''
///     Dispatch system function by command number. This is a carry-over from the old firewall
///     code. We can probably switch this to direct function calls instead. The only benefit is
///     that this gives us a nice single point to handle RDP level 2 checks and other security checks.
///     '''
STATIC mp_obj_t
System_dispatch(size_t n_args, const mp_obj_t* args)
{
    int8_t command = mp_obj_get_int(args[1]);
    uint16_t arg2 = mp_obj_get_int(args[3]);
    int result;

    turbo(true);

    if (args[2] == mp_const_none) {
        result = se_dispatch(command, NULL, 0, arg2, 0, 0);
    } else {
        mp_buffer_info_t buf_info; // Use MP_BUFFER_WRITE below so any updates are copied back up
        mp_get_buffer_raise(args[2], &buf_info, MP_BUFFER_WRITE);

        result = se_dispatch(command, buf_info.buf, buf_info.len, arg2, 0, 0);
    }

    turbo(false);

    return mp_obj_new_int(result);
}

/// def show_busy_bar(self) -> None
///     '''
///    Start displaying the busy bar animation for long-running processes
///    Also, enable turbo mode since if we need to wait, speed it almost certainly helpful.
///     '''
STATIC mp_obj_t
System_show_busy_bar(mp_obj_t self)
{
    turbo(true);
    busy_bar_start();
    return mp_const_none;
}

/// def hide_busy_bar(self) -> None
///     '''
///    Stop showing the busy bar and disable turbo mode
///     '''
STATIC mp_obj_t
System_hide_busy_bar(mp_obj_t self)
{
    busy_bar_stop();
    turbo(false);
    return mp_const_none;
}

#define SECRETS_FLASH_START 0x81C0000
#define SECRETS_FLASH_SIZE 0x20000



/// def System_get_software_info(self) -> None
///     '''
///    Get version, timestamp & hash of the firmware and bootloader as a tuple
///     '''
STATIC mp_obj_t
System_get_software_info(mp_obj_t self)
{
    passport_firmware_header_t* fwhdr = (passport_firmware_header_t*)FW_HDR;

    mp_obj_t tuple[4];

    // Firmware version
    tuple[0] = mp_obj_new_str_copy(
      &mp_type_str, (const uint8_t*)fwhdr->info.fwversion, strlen((const char*)fwhdr->info.fwversion));

    // Firmware date
    tuple[1] = mp_obj_new_int_from_uint(fwhdr->info.timestamp);

    uint32_t boot_counter = 0;
    se_get_counter(&boot_counter, 1);
    tuple[2] = mp_obj_new_int_from_uint(boot_counter);

    // User-signed firmware?
    tuple[3] = (fwhdr->signature.pubkey1 == FW_USER_KEY) ? mp_const_true : mp_const_false;

    return mp_obj_new_tuple(4, tuple);
}

/// def System_progress_bar(self, progress) -> None
///     '''
///    Draw a progress bar to the specified amount (0-1.0)
///     '''
STATIC mp_obj_t
System_progress_bar(mp_obj_t self, mp_obj_t _progress)
{
    int8_t progress = mp_obj_get_int(_progress);
    display_progress_bar(
      PROGRESS_BAR_MARGIN, PROGRESS_BAR_Y, SCREEN_WIDTH - (PROGRESS_BAR_MARGIN * 2), PROGRESS_BAR_HEIGHT, progress);

    // Showing just the lines that changed is much faster and avoids full-screen flicker
    display_show_lines(PROGRESS_BAR_Y, PROGRESS_BAR_Y + PROGRESS_BAR_HEIGHT);

    return mp_const_none;
}

/// def System_read_ambient(self) -> None
///     '''
///    Read the ambient light sensor and bucket it to a level from  0-100
///     '''
STATIC mp_obj_t
System_read_ambient(mp_obj_t self)
{
    uint16_t millivolts;
    adc_read_als(&millivolts);
    millivolts = MIN(millivolts, 3200);
    // printf("millivolts = %u\n", millivolts);
    int level = millivolts / 32;

    return mp_obj_new_int(level);
}

uint8_t turbo_count = 0;
void
turbo(bool enable)
{
    if (enable) {
        if (turbo_count == 0) {
            frequency_turbo(true);
        }
        turbo_count++;
    } else {
        if (turbo_count == 0) {
            // printf("ERROR: Tried to disable turbo mode when it was not already enabled!\n");
            return;
        }
        if (turbo_count == 1) {
            frequency_turbo(false);
        }
        turbo_count--;
    }
}

/// def System_turbo(self, progress) -> None
///     '''
///    Enable or disable turbo mode (fastest MCU frequency)
///     '''
STATIC mp_obj_t
System_turbo(mp_obj_t self, mp_obj_t _enable)
{
    bool enable = mp_obj_is_true(_enable);

    turbo(enable);
    // printf("%s: %lu, %lu, %lu, %lu, %lu\n", enable ? "enable" : "disabled", HAL_RCC_GetSysClockFreq(), SystemCoreClock, HAL_RCC_GetHCLKFreq(),
    //     HAL_RCC_GetPCLK1Freq(), HAL_RCC_GetPCLK2Freq());

    return mp_const_none;
}


/// def System_sha256(self, buffer, digest) -> None
///     '''
///    Perform a sha256 hash on the given data (bytearray)
///     '''
STATIC mp_obj_t
System_sha256(mp_obj_t self, mp_obj_t data, mp_obj_t digest)
{
    mp_buffer_info_t data_info;
    mp_get_buffer_raise(data, &data_info, MP_BUFFER_READ);

    mp_buffer_info_t digest_info;
    mp_get_buffer_raise(digest, &digest_info, MP_BUFFER_WRITE);

    SHA256_CTX ctx;
    sha256_init(&ctx);
    sha256_update(&ctx, (void *)data_info.buf, data_info.len);
    sha256_final(&ctx, digest_info.buf);

    return mp_const_none;
}

// Simple header verification
bool verify_header(passport_firmware_header_t *hdr)
{
    if (hdr->info.magic != FW_HEADER_MAGIC) goto fail;
    if (hdr->info.timestamp == 0) goto fail;
    if (hdr->info.fwversion[0] == 0x0) goto fail;
    if (hdr->info.fwlength < FW_HEADER_SIZE) goto fail;

    if ((hdr->signature.pubkey1 != FW_USER_KEY) && (hdr->signature.pubkey1 > FW_MAX_PUB_KEYS)) goto fail;
    if (hdr->signature.pubkey1 != FW_USER_KEY)
    {
        if (hdr->signature.pubkey2 > FW_MAX_PUB_KEYS) goto fail;
    }

    return true;

fail:
    return false;
}

/// def System_validate_firmware_header(self, header) -> None
///     '''
///    Validate the given firmware header bytes as a potential candidate to be installed.
///     '''
STATIC mp_obj_t
System_validate_firmware_header(mp_obj_t self, mp_obj_t header)
{
    mp_buffer_info_t header_info;
    mp_get_buffer_raise(header, &header_info, MP_BUFFER_READ);

    // Existing header
    passport_firmware_header_t* fwhdr = (passport_firmware_header_t*)FW_HDR;

    // New header
    passport_firmware_header_t* new_fwhdr = (passport_firmware_header_t*)header_info.buf;

    mp_obj_t tuple[4];

    bool is_valid = verify_header(header_info.buf);

    if (is_valid) {
        // Ensure they are not trying to install an older version of firmware, but allow
        // a reinstall of the same version. Also allow installation of user firmware regardless of
        // timestamp and then allow installing a Foundation-signed build.
        if ((new_fwhdr->signature.pubkey1 != FW_USER_KEY && fwhdr->signature.pubkey1 != FW_USER_KEY ) &&
            (new_fwhdr->info.timestamp < fwhdr->info.timestamp)) {
            tuple[0] = mp_const_false;
            tuple[1] = mp_obj_new_str_copy(&mp_type_str, (const uint8_t*)new_fwhdr->info.fwversion, strlen((const char*)new_fwhdr->info.fwversion));

            // Include an error string
            vstr_t vstr;
            vstr_init(&vstr, 80);
            char* msg = "The selected firmware is older than the currently installed firmware and cannot be installed.\n\nCurrent Version:\n  ";
            vstr_add_strn(&vstr, (const char*)msg, strlen(msg));

            vstr_add_strn(&vstr, (const char*)fwhdr->info.fwdate, strlen((const char*)new_fwhdr->info.fwdate));

            msg = "\n\nSelected Version:\n  ";
            vstr_add_strn(&vstr, (const char*)msg, strlen(msg));

            vstr_add_strn(&vstr, (const char*)new_fwhdr->info.fwdate, strlen((const char*)new_fwhdr->info.fwdate));
            tuple[2] = mp_obj_new_str_from_vstr(&mp_type_str, &vstr);

            // Is this user-signed firmware?
            tuple[3] = mp_const_false;

            return mp_obj_new_tuple(4, tuple);
        }
    } else {
        // Invalid header
        tuple[0] = mp_const_false;
        tuple[1] = mp_obj_new_str_copy(&mp_type_str, (const uint8_t*)new_fwhdr->info.fwversion, strlen((const char*)new_fwhdr->info.fwversion));

        // Include an error string
        vstr_t vstr;
        vstr_init(&vstr, 80);
        char* msg = "The selected firmware header is invalid and cannot be installed.";
        vstr_add_strn(&vstr, (const char*)msg, strlen(msg));
        tuple[2] = mp_obj_new_str_from_vstr(&mp_type_str, &vstr);

        // No header = no user signed firmware
        tuple[3] = mp_const_false;

        return mp_obj_new_tuple(4, tuple);
    }

    // is_valid
    tuple[0] = mp_const_true;

    // Firmware version
    tuple[1] = mp_obj_new_str_copy(&mp_type_str, (const uint8_t*)new_fwhdr->info.fwversion, strlen((const char*)new_fwhdr->info.fwversion));

    // No error message
    tuple[2] = mp_const_none;

    // Is this user-signed firmware?
    tuple[3] = (new_fwhdr->signature.pubkey1 == FW_USER_KEY) ? mp_const_true : mp_const_false;

    return mp_obj_new_tuple(4, tuple);
}

/// def System_set_user_firmware_pubkey(self, pubkey) -> None
///     '''
///    Set the user firmware public key so the user can install custom firmware
///     '''
STATIC mp_obj_t
System_set_user_firmware_pubkey(mp_obj_t self, mp_obj_t pubkey)
{
    uint8_t pin_hash[32];

    mp_buffer_info_t pubkey_info;
    mp_get_buffer_raise(pubkey, &pubkey_info, MP_BUFFER_READ);
    // uint8_t* p = (uint8_t*)pubkey_info.buf;
    // printf("WRITE: len=%d pubkey=%02x%02x%02x%02x...\n",pubkey_info.len, p[0],  p[1],  p[2], p[3]);

    pinAttempt_t pa_args;
    pa_args.magic_value = PA_MAGIC_V1;
    memcpy(&pa_args.cached_main_pin, g_cached_main_pin, sizeof(g_cached_main_pin));

    // Get the hash that proves user knows the PIN
    int rv = pin_cache_restore(&pa_args, pin_hash);
    if (rv) {
        return mp_const_false;
    }

    // printf("pin hash=%02x%02x%02x%02x...", pin_hash[0], pin_hash[1], pin_hash[2],pin_hash[3]);

    rv = se_encrypted_write(KEYNUM_user_fw_pubkey, KEYNUM_pin_hash, pin_hash, pubkey_info.buf, pubkey_info.len);
    // printf("rv=%d\n", rv);
    return rv == 0 ? mp_const_true : mp_const_false;
}

/// def System_get_user_firmware_pubkey(self, pubkey) -> None
///     '''
///    Get the user firmware public key
///     '''
STATIC mp_obj_t
System_get_user_firmware_pubkey(mp_obj_t self, mp_obj_t pubkey)
{
    uint8_t buf[72];

    mp_buffer_info_t pubkey_info;
    mp_get_buffer_raise(pubkey, &pubkey_info, MP_BUFFER_READ);

    if (pubkey_info.len < 64) {
        return mp_const_false;
    }

    se_pair_unlock();
    int rv = se_read_data_slot(KEYNUM_user_fw_pubkey, buf, sizeof(buf));
    if (rv == 0) {
        memcpy(pubkey_info.buf, buf, 64);
        return mp_const_true;
    }
    return mp_const_false;
}

/// def is_user_firmware_installed(self) -> None
///     '''
///     Check if user firmware is installed or not
///     '''
STATIC mp_obj_t
System_is_user_firmware_installed(mp_obj_t self)
{
    passport_firmware_header_t* fwhdr = (passport_firmware_header_t*)FW_HDR;

    return (fwhdr->signature.pubkey1 == FW_USER_KEY && fwhdr->signature.pubkey2 == 0) ? mp_const_true : mp_const_false;
}

/// def System_supply_chain_challenge(self, challenge, response) -> None
///     '''
///    Perform the supply chain challenge (HMAC)
///     '''
STATIC mp_obj_t
System_supply_chain_challenge(mp_obj_t self, mp_obj_t challenge, mp_obj_t response)
{
    mp_buffer_info_t challenge_info;
    mp_get_buffer_raise(challenge, &challenge_info, MP_BUFFER_READ);

    mp_buffer_info_t response_info;
    mp_get_buffer_raise(response, &response_info, MP_BUFFER_WRITE);

    se_pair_unlock();
    int rc = se_hmac32(KEYNUM_supply_chain, challenge_info.buf, response_info.buf);
    if (rc == 0) {
        return mp_const_true;
    }
    return mp_const_false;
}


uint8_t supply_chain_validation_server_pubkey[64] = {
    0x75, 0xF6, 0xCD, 0xDB, 0x93, 0x49, 0x59, 0x9D, 0x4B, 0xB2, 0xDF, 0x82, 0xBC, 0xF9, 0x8E, 0x85,
    0x45, 0x6C, 0xFB, 0xE2, 0x87, 0x57, 0xFF, 0x77, 0x5D, 0xB0, 0x4C, 0xAE, 0x70, 0x1B, 0xDC, 0x00,
    0x53, 0x4E, 0x0C, 0x70, 0x01, 0x90, 0x6C, 0x6F, 0xFB, 0xA6, 0x15, 0xAF, 0xDB, 0x67, 0xDE, 0xF9,
    0x46, 0x96, 0x4B, 0xB4, 0x39, 0xD0, 0x02, 0x3E, 0xF6, 0x59, 0xF5, 0x80, 0xBB, 0x31, 0x11, 0x3E
};

/// def System_verify_supply_chain_server_signature(self, hash, signature) -> None
///     '''
///    Verify server signature
///     '''
STATIC mp_obj_t
System_verify_supply_chain_server_signature(mp_obj_t self, mp_obj_t hash, mp_obj_t signature)
{
    mp_buffer_info_t hash_info;
    mp_get_buffer_raise(hash, &hash_info, MP_BUFFER_READ);

    mp_buffer_info_t signature_info;
    mp_get_buffer_raise(signature, &signature_info, MP_BUFFER_READ);

    int rc = uECC_verify(supply_chain_validation_server_pubkey,
                         hash_info.buf, hash_info.len,
                         signature_info.buf, uECC_secp256k1());

    return rc == 0 ? mp_const_false : mp_const_true;
}

#define SHA256_BLOCK_LENGTH  64
#define SHA256_DIGEST_LENGTH 32

void _hmac_sha256(uint8_t* key, uint32_t key_len, uint8_t* msg, uint32_t msg_len, uint8_t* hmac) {
    uint8_t i_key_pad[SHA256_BLOCK_LENGTH];
    memset(i_key_pad, 0, SHA256_BLOCK_LENGTH);
    memcpy(i_key_pad, key, key_len);

    uint8_t o_key_pad[SHA256_BLOCK_LENGTH];
    for (int i = 0; i < SHA256_BLOCK_LENGTH; i++) {
        o_key_pad[i] = i_key_pad[i] ^ 0x5c;
        i_key_pad[i] ^= 0x36;
    }

    // First hash
    SHA256_CTX ctx;
    sha256_init(&ctx);
    sha256_update(&ctx, i_key_pad, SHA256_BLOCK_LENGTH);
    memset(i_key_pad, 0, SHA256_BLOCK_LENGTH);

    // Add the data
    sha256_update(&ctx, msg, msg_len);

    // Hash
    sha256_final(&ctx, hmac);

    // Second hash
    sha256_init(&ctx);
    sha256_update(&ctx, o_key_pad, SHA256_BLOCK_LENGTH);
    sha256_update(&ctx, hmac, SHA256_DIGEST_LENGTH);
    sha256_final(&ctx, hmac);
}

/// def System_hmac_sha256(self, key, msg, hmac) -> None
///     '''
///    Calculate an hmac using the given key and data
///     '''
STATIC mp_obj_t
System_hmac_sha256(size_t n_args, const mp_obj_t* args)
{
    mp_buffer_info_t key_info;
    mp_get_buffer_raise(args[1], &key_info, MP_BUFFER_READ);
    // uint8_t* pkey = (uint8_t*)key_info.buf;
    // printf("key: 0x%02x 0x%02x 0x%02x 0x%02x (len=%d)\n", pkey[0], pkey[1], pkey[2], pkey[3], key_info.len);

    mp_buffer_info_t msg_info;
    mp_get_buffer_raise(args[2], &msg_info, MP_BUFFER_READ);
    // uint8_t* pmsg = (uint8_t*)msg_info.buf;
    // printf("msg: 0x%02x 0x%02x 0x%02x 0x%02x (len=%d)\n", pmsg[0], pmsg[1], pmsg[2], pmsg[3], msg_info.len);

    mp_buffer_info_t hmac_info;
    mp_get_buffer_raise(args[3], &hmac_info, MP_BUFFER_WRITE);
    // printf("hmac:(len=%d)\n", hmac_info.len);

    _hmac_sha256(key_info.buf, key_info.len, msg_info.buf, msg_info.len, hmac_info.buf);

    return mp_const_none;
}

#define MAX_SERIAL_NUMBER_LEN 20
/// def System_get_serial_number(self) -> None
///     '''
///    Get the serial number
///     '''
STATIC mp_obj_t
System_get_serial_number(mp_obj_t self)
{
    char serial[MAX_SERIAL_NUMBER_LEN];

    get_serial_number(serial, MAX_SERIAL_NUMBER_LEN);

    return mp_obj_new_str_copy(&mp_type_str, (const uint8_t*)serial, strlen(serial));
}

/// def System_get_device_hash(self, hash) -> None
///     '''
///    Get the device hash
///     '''
STATIC mp_obj_t
System_get_device_hash(mp_obj_t self, mp_obj_t hash)
{
    mp_buffer_info_t hash_info;
    mp_get_buffer_raise(hash, &hash_info, MP_BUFFER_WRITE);

    get_device_hash(hash_info.buf);

    return mp_const_none;
}

/// def System_get_backup_pw_hash(self, hash) -> None
///     '''
///    Get the hash to use as the "entropy" for the backup password.
///    It's based on the device hash plus the seed.
///     '''
STATIC mp_obj_t
System_get_backup_pw_hash(mp_obj_t self, mp_obj_t hash)
{
    uint8_t device_hash[32];

    mp_buffer_info_t hash_info;
    mp_get_buffer_raise(hash, &hash_info, MP_BUFFER_WRITE);

    get_device_hash(device_hash);
    pinAttempt_t pin_attempt;
    memset(&pin_attempt, 0, sizeof(pinAttempt_t));
    pin_fetch_secret(&pin_attempt);

    SHA256_CTX ctx;
    sha256_init(&ctx);
    sha256_update(&ctx, (void *)device_hash, 32);
    sha256_update(&ctx, (void *)pin_attempt.secret, SE_SECRET_LEN);
    sha256_final(&ctx, hash_info.buf);

    // Double SHA
    sha256_init(&ctx);
    sha256_update(&ctx, (void *)hash_info.buf, 32);
    sha256_final(&ctx, hash_info.buf);

    return mp_const_none;
}


STATIC MP_DEFINE_CONST_FUN_OBJ_1(System_reset_obj, System_reset);
STATIC MP_DEFINE_CONST_FUN_OBJ_1(System_shutdown_obj, System_shutdown);
STATIC MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(System_dispatch_obj, 4, 4, System_dispatch);
STATIC MP_DEFINE_CONST_FUN_OBJ_1(System_show_busy_bar_obj, System_show_busy_bar);
STATIC MP_DEFINE_CONST_FUN_OBJ_1(System_hide_busy_bar_obj, System_hide_busy_bar);
STATIC MP_DEFINE_CONST_FUN_OBJ_1(System_get_software_info_obj, System_get_software_info);
STATIC MP_DEFINE_CONST_FUN_OBJ_2(System_progress_bar_obj, System_progress_bar);
STATIC MP_DEFINE_CONST_FUN_OBJ_1(System_read_ambient_obj, System_read_ambient);
STATIC MP_DEFINE_CONST_FUN_OBJ_2(System_turbo_obj, System_turbo);
STATIC MP_DEFINE_CONST_FUN_OBJ_3(System_sha256_obj, System_sha256);
STATIC MP_DEFINE_CONST_FUN_OBJ_2(System_validate_firmware_header_obj, System_validate_firmware_header);
STATIC MP_DEFINE_CONST_FUN_OBJ_2(System_set_user_firmware_pubkey_obj, System_set_user_firmware_pubkey);
STATIC MP_DEFINE_CONST_FUN_OBJ_2(System_get_user_firmware_pubkey_obj, System_get_user_firmware_pubkey);
STATIC MP_DEFINE_CONST_FUN_OBJ_1(System_is_user_firmware_installed_obj, System_is_user_firmware_installed);
STATIC MP_DEFINE_CONST_FUN_OBJ_3(System_supply_chain_challenge_obj, System_supply_chain_challenge);
STATIC MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(System_hmac_sha256_obj, 4, 4, System_hmac_sha256);
STATIC MP_DEFINE_CONST_FUN_OBJ_3(System_verify_supply_chain_server_signature_obj, System_verify_supply_chain_server_signature);
STATIC MP_DEFINE_CONST_FUN_OBJ_1(System_get_serial_number_obj, System_get_serial_number);
STATIC MP_DEFINE_CONST_FUN_OBJ_2(System_get_device_hash_obj, System_get_device_hash);
STATIC MP_DEFINE_CONST_FUN_OBJ_2(System_get_backup_pw_hash_obj, System_get_backup_pw_hash);


STATIC mp_obj_t
System___del__(mp_obj_t self)
{
    return mp_const_none;
}

STATIC MP_DEFINE_CONST_FUN_OBJ_1(System___del___obj, System___del__);

STATIC const mp_rom_map_elem_t System_locals_dict_table[] = {
    { MP_ROM_QSTR(MP_QSTR___name__), MP_ROM_QSTR(MP_QSTR_foundation) },
    { MP_ROM_QSTR(MP_QSTR_reset), MP_ROM_PTR(&System_reset_obj) },
    { MP_ROM_QSTR(MP_QSTR_shutdown), MP_ROM_PTR(&System_shutdown_obj) },
    { MP_ROM_QSTR(MP_QSTR_dispatch), MP_ROM_PTR(&System_dispatch_obj) },
    { MP_ROM_QSTR(MP_QSTR_show_busy_bar), MP_ROM_PTR(&System_show_busy_bar_obj) },
    { MP_ROM_QSTR(MP_QSTR_hide_busy_bar), MP_ROM_PTR(&System_hide_busy_bar_obj) },
    { MP_ROM_QSTR(MP_QSTR_get_software_info), MP_ROM_PTR(&System_get_software_info_obj) },
    { MP_ROM_QSTR(MP_QSTR_progress_bar), MP_ROM_PTR(&System_progress_bar_obj) },
    { MP_ROM_QSTR(MP_QSTR_read_ambient), MP_ROM_PTR(&System_read_ambient_obj) },
    { MP_ROM_QSTR(MP_QSTR_turbo), MP_ROM_PTR(&System_turbo_obj) },
    { MP_ROM_QSTR(MP_QSTR_sha256), MP_ROM_PTR(&System_sha256_obj) },
    { MP_ROM_QSTR(MP_QSTR_validate_firmware_header), MP_ROM_PTR(&System_validate_firmware_header_obj) },
    { MP_ROM_QSTR(MP_QSTR_set_user_firmware_pubkey), MP_ROM_PTR(&System_set_user_firmware_pubkey_obj) },
    { MP_ROM_QSTR(MP_QSTR_get_user_firmware_pubkey), MP_ROM_PTR(&System_get_user_firmware_pubkey_obj) },
    { MP_ROM_QSTR(MP_QSTR_is_user_firmware_installed), MP_ROM_PTR(&System_is_user_firmware_installed_obj) },
    { MP_ROM_QSTR(MP_QSTR_supply_chain_challenge), MP_ROM_PTR(&System_supply_chain_challenge_obj) },
    { MP_ROM_QSTR(MP_QSTR_verify_supply_chain_server_signature), MP_ROM_PTR(&System_verify_supply_chain_server_signature_obj) },
    { MP_ROM_QSTR(MP_QSTR_hmac_sha256), MP_ROM_PTR(&System_hmac_sha256_obj) },
    { MP_ROM_QSTR(MP_QSTR_get_serial_number), MP_ROM_PTR(&System_get_serial_number_obj) },
    { MP_ROM_QSTR(MP_QSTR_get_device_hash), MP_ROM_PTR(&System_get_device_hash_obj) },
    { MP_ROM_QSTR(MP_QSTR_get_backup_pw_hash), MP_ROM_PTR(&System_get_backup_pw_hash_obj) },
    { MP_ROM_QSTR(MP_QSTR___del__), MP_ROM_PTR(&System___del___obj) },
};
STATIC MP_DEFINE_CONST_DICT(System_locals_dict, System_locals_dict_table);

STATIC const mp_obj_type_t System_type = {
    { &mp_type_type },
    .name = MP_QSTR_System,
    .make_new = System_make_new,
    .locals_dict = (void*)&System_locals_dict,
};
/* End of setup for System class */

/*=============================================================================
 * Start of bip39 class
 *=============================================================================*/

extern word_info_t bip39_word_info[];
extern word_info_t bytewords_word_info[]; // TODO: Restructure this so bip39 and bytewords are separate

/// def __init__(self, mode: int, key: bytes, iv: bytes = None) -> boolean:
///     '''
///     Initialize System context.
///     '''
STATIC mp_obj_t
bip39_make_new(const mp_obj_type_t* type, size_t n_args, size_t n_kw, const mp_obj_t* args)
{
    mp_obj_bip39_t* o = m_new_obj(mp_obj_bip39_t);
    o->base.type = type;
    return MP_OBJ_FROM_PTR(o);
}

#define MATCHES_LEN 80

/// def get_words_matching_prefix(self, prefix, max_matches, word_list) -> None
///     '''
///     Return a comma-separated list of BIP39 seed words that match the given keypad
///     digits prefix (e.g., '222').
///     '''
STATIC mp_obj_t
bip39_get_words_matching_prefix(size_t n_args, const mp_obj_t* args)
{
    mp_check_self(mp_obj_is_str_or_bytes(args[1]));
    GET_STR_DATA_LEN(args[1], prefix_str, prefix_len);

    int max_matches = mp_obj_get_int(args[2]);

    // Must be "bip39" or "bytewords"
    mp_check_self(mp_obj_is_str_or_bytes(args[3]));
    GET_STR_DATA_LEN(args[3], word_list_str, word_list_len);

    const word_info_t* word_info = NULL;
    uint32_t num_words = 0;
    if (strcmp("bip39", (char*)word_list_str) == 0) {
        word_info = bip39_word_info;
        num_words = 2048;
    } else if (strcmp("bytewords", (char*)word_list_str) == 0) {
        word_info = bytewords_word_info;
        num_words = 256;
    } else {
        return mp_const_none;
    }

    char matches[MATCHES_LEN];

    get_words_matching_prefix((char*)prefix_str, matches, MATCHES_LEN, max_matches, word_info, num_words);

    // Return the string
    vstr_t vstr;
    int matches_len = strlen((const char*)matches);

    vstr_init(&vstr, matches_len + 1);
    vstr_add_strn(&vstr, (const char*)matches, matches_len);

    return mp_obj_new_str_from_vstr(&mp_type_str, &vstr);
}
STATIC MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(bip39_get_words_matching_prefix_obj, 4, 4, bip39_get_words_matching_prefix);

#include "bip39.h"

/// def mnemonic_to_entropy(self) -> None
///     '''
///     Call trezorcrypto's mnemonic_to_entropy() C function since it's not exposed through their
///     Python interface.
///     '''
STATIC mp_obj_t
bip39_mnemonic_to_entropy(mp_obj_t self, mp_obj_t mnemonic, mp_obj_t entropy)
{
    mp_check_self(mp_obj_is_str_or_bytes(mnemonic));
    GET_STR_DATA_LEN(mnemonic, mnemonic_str, mnemonic_len);
    mp_buffer_info_t entropy_info;
    mp_get_buffer_raise(entropy, &entropy_info, MP_BUFFER_WRITE);

    int len = mnemonic_to_entropy((const char*)mnemonic_str, entropy_info.buf);
    return mp_obj_new_int(len);
}
STATIC MP_DEFINE_CONST_FUN_OBJ_3(bip39_mnemonic_to_entropy_obj, bip39_mnemonic_to_entropy);

STATIC mp_obj_t
bip39___del__(mp_obj_t self)
{
    return mp_const_none;
}

STATIC MP_DEFINE_CONST_FUN_OBJ_1(bip39___del___obj, bip39___del__);

STATIC const mp_rom_map_elem_t bip39_locals_dict_table[] = {
    { MP_ROM_QSTR(MP_QSTR___name__), MP_ROM_QSTR(MP_QSTR_foundation) },
    { MP_ROM_QSTR(MP_QSTR_get_words_matching_prefix), MP_ROM_PTR(&bip39_get_words_matching_prefix_obj) },
    { MP_ROM_QSTR(MP_QSTR_mnemonic_to_entropy), MP_ROM_PTR(&bip39_mnemonic_to_entropy_obj) },
    { MP_ROM_QSTR(MP_QSTR___del__), MP_ROM_PTR(&bip39___del___obj) },
};
STATIC MP_DEFINE_CONST_DICT(bip39_locals_dict, bip39_locals_dict_table);

STATIC const mp_obj_type_t bip39_type = {
    { &mp_type_type },
    .name = MP_QSTR_bip39,
    .make_new = bip39_make_new,
    .locals_dict = (void*)&bip39_locals_dict,
};
/* End of setup for bip39 class */

/*=============================================================================
 * Start of QRCode class - renders QR codes to a buffer passed down from MP
 *=============================================================================*/

// We only have versions here that can be rendered on Pasport's display
uint16_t version_capacity_alphanumeric[] = {
    25,   // 1
    47,   // 2
    77,   // 3
    114,  // 4
    154,  // 5
    195,  // 6
    224,  // 7
    279,  // 8
    335,  // 9
    395,  // 10
    468,  // 11
    535,  // 12
    619,  // 13
    667,  // 14
    758,  // 15
    854,  // 16
    938,  // 17
    1046, // 18
    1153, // 19
    1249, // 20
    1352, // 21
    1460, // 22
    1588, // 23
    1704  // 24
};

uint16_t version_capacity_binary[] = {
    17,   // 1
    32,   // 2
    53,   // 3
    78,   // 4
    106,  // 5
    134,  // 6
    154,  // 7
    192,  // 8
    230,  // 9
    271,  // 10
    321,  // 11
    367,  // 12
    425,  // 13
    458,  // 14
    520,  // 15
    586,  // 16
    644,  // 17
    718,  // 18
    792,  // 19
    858,  // 20
    929,  // 21
    1003, // 22
    1091, // 23
    1171  // 24
};

/// def __init__(self, mode: int, key: bytes, iv: bytes = None) -> boolean:
///     '''
///     Initialize QRCode context.
///     '''
STATIC mp_obj_t
QRCode_make_new(const mp_obj_type_t* type, size_t n_args, size_t n_kw, const mp_obj_t* args)
{
    mp_obj_QRCode_t* o = m_new_obj(mp_obj_QRCode_t);
    o->base.type = type;
    return MP_OBJ_FROM_PTR(o);
}

QRCode qrcode;
#define QRCODE_DEBUG

/// def render(self) -> None
///     '''
///     Render a QR code with the given data, version and ecc level
///     '''
STATIC mp_obj_t
QRCode_render(size_t n_args, const mp_obj_t* args)
{
    mp_check_self(mp_obj_is_str_or_bytes(args[1]));
    GET_STR_DATA_LEN(args[1], text_str, text_len);
    // printf("text_str=%s text_len=%d\n", text_str, text_len);

    uint8_t version = mp_obj_get_int(args[2]);
    uint8_t ecc = mp_obj_get_int(args[3]);

    mp_buffer_info_t output_info;
    mp_get_buffer_raise(args[4], &output_info, MP_BUFFER_WRITE);

    uint8_t result = qrcode_initBytes(&qrcode, (uint8_t*)output_info.buf, version, ecc, (uint8_t*)text_str, text_len);

    return result == 0 ? mp_const_false : mp_const_true;
}

/// def fit_to_version(self) -> None
///     '''
///    Return the QR code version that best fits this data (assumes ECC level 0 for now)
///     '''
STATIC mp_obj_t
QRCode_fit_to_version(mp_obj_t self, mp_obj_t data_size, mp_obj_t is_alphanumeric)
{
    uint16_t size = mp_obj_get_int(data_size);
    uint16_t is_alpha = mp_obj_get_int(is_alphanumeric);
    uint16_t *lookup_table = is_alpha ? version_capacity_alphanumeric : version_capacity_binary;

    int num_entries = sizeof(version_capacity_alphanumeric) / sizeof(uint16_t);

    for (int i = 0; i < num_entries; i++) {
        if (lookup_table[i] >= size) {
            return mp_obj_new_int(i + 1);
        }
    }

    // Data is too big
    return mp_obj_new_int(0);
}

STATIC MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(QRCode_render_obj, 5, 5, QRCode_render);
STATIC MP_DEFINE_CONST_FUN_OBJ_3(QRCode_fit_to_version_obj, QRCode_fit_to_version);

STATIC mp_obj_t
QRCode___del__(mp_obj_t self)
{
    return mp_const_none;
}

STATIC MP_DEFINE_CONST_FUN_OBJ_1(QRCode___del___obj, QRCode___del__);

STATIC const mp_rom_map_elem_t QRCode_locals_dict_table[] = {
    { MP_ROM_QSTR(MP_QSTR___name__), MP_ROM_QSTR(MP_QSTR_foundation) },
    { MP_ROM_QSTR(MP_QSTR_render), MP_ROM_PTR(&QRCode_render_obj) },
    { MP_ROM_QSTR(MP_QSTR_fit_to_version), MP_ROM_PTR(&QRCode_fit_to_version_obj) },
    { MP_ROM_QSTR(MP_QSTR___del__), MP_ROM_PTR(&QRCode___del___obj) },
};
STATIC MP_DEFINE_CONST_DICT(QRCode_locals_dict, QRCode_locals_dict_table);

STATIC const mp_obj_type_t QRCode_type = {
    { &mp_type_type },
    .name = MP_QSTR_QRCode,
    .make_new = QRCode_make_new,
    .locals_dict = (void*)&QRCode_locals_dict,
};
/* End of setup for QRCode class */

/*
 * Add additional class local dictionary table and data structure here
 * And add the Class name and MP_ROM_PTR() to the globals table
 * below
 */

/* Module Global configuration */
/* Define all properties of the module.
 * Table entries are key/value pairs of the attribute name (a string)
 * and the MicroPython object reference.
 * All identifiers and strings are written as MP_QSTR_xxx and will be
 * optimized to word-sized integers by the build system (interned strings).
 */
STATIC const mp_rom_map_elem_t foundation_module_globals_table[] = {
    { MP_ROM_QSTR(MP_QSTR___name__), MP_ROM_QSTR(MP_QSTR_foundation) },
    { MP_ROM_QSTR(MP_QSTR___del__), MP_ROM_PTR(&foundation___del___obj) },
    { MP_ROM_QSTR(MP_QSTR_Backlight), MP_ROM_PTR(&backlight_type) },
    { MP_ROM_QSTR(MP_QSTR_Keypad), MP_ROM_PTR(&keypad_type) },
    { MP_ROM_QSTR(MP_QSTR_LCD), MP_ROM_PTR(&lcd_type) },
    { MP_ROM_QSTR(MP_QSTR_Camera), MP_ROM_PTR(&camera_type) },
    { MP_ROM_QSTR(MP_QSTR_Boardrev), MP_ROM_PTR(&boardrev_type) },
    { MP_ROM_QSTR(MP_QSTR_Powermon), MP_ROM_PTR(&powermon_type) },
    { MP_ROM_QSTR(MP_QSTR_Noise), MP_ROM_PTR(&noise_type) },
    { MP_ROM_QSTR(MP_QSTR_QR), MP_ROM_PTR(&QR_type) },
    { MP_ROM_QSTR(MP_QSTR_SettingsFlash), MP_ROM_PTR(&SettingsFlash_type) },
    { MP_ROM_QSTR(MP_QSTR_System), MP_ROM_PTR(&System_type) },
    { MP_ROM_QSTR(MP_QSTR_bip39), MP_ROM_PTR(&bip39_type) },
    { MP_ROM_QSTR(MP_QSTR_QRCode), MP_ROM_PTR(&QRCode_type) },
};
STATIC MP_DEFINE_CONST_DICT(foundation_module_globals, foundation_module_globals_table);

/* Define module object. */
const mp_obj_module_t foundation_user_cmodule = {
    .base = { &mp_type_module },
    .globals = (mp_obj_dict_t*)&foundation_module_globals,
};

MP_REGISTER_MODULE(MP_QSTR_foundation, foundation_user_cmodule, PASSPORT_FOUNDATION_ENABLED);
