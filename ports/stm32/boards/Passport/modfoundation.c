// SPDX-FileCopyrightText: 2020 Foundation Devices, Inc.  <hello@foundationdevices.com>
// SPDX-License-Identifier: GPL-3.0-or-later
//
// MP C foundation module, supports LCD, backlight, keypad and other devices as they are added

#include "py/builtin.h"
#include "py/obj.h"
#include "py/runtime.h"
#include <stdlib.h>
#include <string.h>

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

#include "stm32h7xx_hal.h"
#include "flash.h"
#include "gpio.h"
#include "dispatch.h"

/* lcd class object, expand as needed with instance related details */
typedef struct _mp_obj_lcd_t
{
    mp_obj_base_t base;
    const spi_t *spi;

} mp_obj_lcd_t;

/* Backlight class object */
typedef struct _mp_obj_backlight_t
{
    mp_obj_base_t base;
} mp_obj_backlight_t;

/* Backlight class object and globals */
ring_buffer_t keybuf;

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
typedef struct _mp_obj_boardrev_t {
    mp_obj_base_t base;
} mp_obj_boardrev_t;

/* Power Monitor object */
typedef struct _mp_obj_powermon_t {
    mp_obj_base_t base;
    uint16_t current;
    uint16_t voltage;
} mp_obj_powermon_t;

/* Noise Output object */
typedef struct _mp_obj_noise_t {
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
#define SETTINGS_FLASH_SIZE  0x20000
#define SETTINGS_FLASH_END   (SETTINGS_FLASH_START + SETTINGS_FLASH_SIZE - 1)

/*=============================================================================
 * Start of keypad class
 *=============================================================================*/
STATIC mp_obj_t keypad_make_new(const mp_obj_type_t *type, size_t n_args, size_t n_kw, const mp_obj_t *args)
{
    mp_obj_keypad_t *keypad = m_new_obj(mp_obj_keypad_t);
    keypad->base.type = type;

    // uint32_t reg = *(uint32_t*)(0x580244d0);
    // printf("======================================================\nREG = 0x%08lx\n======================================================\n", reg);

    keypad_init();
    return MP_OBJ_FROM_PTR(keypad);
}

STATIC mp_obj_t keypad_get_keycode(mp_obj_t self)
{
    uint8_t buf[1];

    if (ring_buffer_dequeue(&keybuf, &buf[0]) == 0)
    {
        return mp_const_none;
    }
    // printf("keypad.get_keycode() 2: %d\n", buf[0]);
    return mp_obj_new_int_from_uint(buf[0]);
}
STATIC MP_DEFINE_CONST_FUN_OBJ_1(keypad_get_keycode_obj, keypad_get_keycode);

STATIC mp_obj_t keypad___del__(mp_obj_t self)
{
    return mp_const_none;
}

STATIC MP_DEFINE_CONST_FUN_OBJ_1(keypad___del___obj, keypad___del__);

STATIC const mp_rom_map_elem_t keypad_locals_dict_table[] = {
    {MP_ROM_QSTR(MP_QSTR___name__), MP_ROM_QSTR(MP_QSTR_foundation)},
    {MP_ROM_QSTR(MP_QSTR_get_keycode), MP_ROM_PTR(&keypad_get_keycode_obj)},
    {MP_ROM_QSTR(MP_QSTR___del__), MP_ROM_PTR(&keypad___del___obj)},
};
STATIC MP_DEFINE_CONST_DICT(keypad_locals_dict, keypad_locals_dict_table);

const mp_obj_type_t keypad_type = {
    {&mp_type_type},
    .name = MP_QSTR_Keypad,
    .make_new = keypad_make_new,
    .locals_dict = (void *)&keypad_locals_dict,
};

/* End of Keypad class code */

/*=============================================================================
 * Start of LCD class
 *=============================================================================*/
void lcd_obj_print(const mp_print_t *print, mp_obj_t self_in, mp_print_kind_t kind)
{
    mp_printf(print, "foundation obj print");
}

/* Instantiation */

/// def __init__(self, mode: int, key: bytes, iv: bytes = None) -> None:
///     '''
///     Initialize LCD object context.  Return a MP LCD object
///     '''
STATIC mp_obj_t lcd_obj_make_new(const mp_obj_type_t *type, size_t n_args, size_t n_kw, const mp_obj_t *args)
{
    mp_obj_lcd_t *lcd = m_new_obj(mp_obj_lcd_t);
    lcd->base.type = &lcd_type;
    lcd->spi = &spi_obj[0];
    lcd_init();
    return MP_OBJ_FROM_PTR(lcd);
}

/* LCD object methods follow */
STATIC mp_obj_t m_lcd_clear(mp_obj_t self_in, mp_obj_t invert_obj)
{
    uint8_t invert = mp_obj_get_int(invert_obj);
    lcd_clear(invert);
    return mp_const_none;
}

STATIC MP_DEFINE_CONST_FUN_OBJ_2(m_lcd_clear_obj, m_lcd_clear);

STATIC mp_obj_t m_lcd_update(mp_obj_t self_in, mp_obj_t lcd_data)
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

STATIC mp_obj_t foundation___del__(mp_obj_t self)
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
    {MP_ROM_QSTR(MP_QSTR_clear), MP_ROM_PTR(&m_lcd_clear_obj)},
    {MP_ROM_QSTR(MP_QSTR_update), MP_ROM_PTR(&m_lcd_update_obj)},
};
STATIC MP_DEFINE_CONST_DICT(lcd_locals_dict, lcd_locals_dict_table);

const mp_obj_type_t lcd_type = {
    {&mp_type_type},
    .name = MP_QSTR_LCD,
    .print = lcd_obj_print,
    .make_new = lcd_obj_make_new,
    .locals_dict = (mp_obj_dict_t *)&lcd_locals_dict,
};
/* End of setup for LCD class */

/*=============================================================================
 * Start of backlight class
 *=============================================================================*/
STATIC mp_obj_t backlight_obj_make_new(const mp_obj_type_t *type, size_t n_args, size_t n_kw, const mp_obj_t *args)
{
    mp_obj_backlight_t *backlight = m_new_obj(mp_obj_backlight_t);
    backlight->base.type = &backlight_type;
    backlight_init();
    return MP_OBJ_FROM_PTR(backlight);
}

/* LCD object methods follow */
STATIC mp_obj_t m_backlight_intensity(mp_obj_t self_in, mp_obj_t intensity_obj)
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
    {MP_ROM_QSTR(MP_QSTR_intensity), MP_ROM_PTR(&m_backlight_intensity_obj)},
};
STATIC MP_DEFINE_CONST_DICT(backlight_locals_dict, backlight_locals_dict_table);

const mp_obj_type_t backlight_type = {
    {&mp_type_type},
    .name = MP_QSTR_Backlight,
    //        .print = lcd_obj_print,
    .make_new = backlight_obj_make_new,
    .locals_dict = (mp_obj_dict_t *)&backlight_locals_dict,
};
/* End of setup for Backlight class */

/*=============================================================================
 * Start of Camera class
 *=============================================================================*/
STATIC mp_obj_t camera_make_new(const mp_obj_type_t *type, size_t n_args, size_t n_kw, const mp_obj_t *args)
{
    mp_obj_camera_t *o = m_new_obj(mp_obj_camera_t);
    o->base.type = type;

    // printf("new Camera()!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!\n");
    // #camera_init();

    return MP_OBJ_FROM_PTR(o);
}

/// def enable(self, data: buffer) -> None
///     '''
///     Turn on the camera in preparation for calling snapshot().
///     '''
STATIC mp_obj_t camera_enable(mp_obj_t self)
{
    camera_on();
    return mp_const_none;
}

/// def disable(self, data: buffer) -> None
///     '''
///     Turn off the camera.
///     '''
STATIC mp_obj_t camera_disable(mp_obj_t self)
{
    camera_off();
    return mp_const_none;
}

/// def snapshot(self, image: buffer) -> BoolG
///     '''
///     Start a snapshot and wait for it to finish, then convert and copy it into the provided image buffers.
///     '''
STATIC mp_obj_t camera_snapshot_(size_t n_args, const mp_obj_t *args)
{
    mp_buffer_info_t qr_image_info;
    mp_get_buffer_raise(args[1], &qr_image_info, MP_BUFFER_WRITE);
    uint16_t qr_w = mp_obj_get_int(args[2]);
    uint16_t qr_h = mp_obj_get_int(args[3]);
    if (qr_image_info.len != qr_w * qr_h)
    {
        printf("ERROR: QR buffer w/h not consistent with buffer size!\n");
        return mp_const_false;
    }
    if (qr_image_info.len != QR_IMAGE_SIZE)
    {
        printf("ERROR: QR buffer is the wrong size!\n");
        return mp_const_false;
    }

    mp_buffer_info_t viewfinder_image_info;
    mp_get_buffer_raise(args[4], &viewfinder_image_info, MP_BUFFER_WRITE);
    uint16_t viewfinder_w = mp_obj_get_int(args[5]);
    uint16_t viewfinder_h = mp_obj_get_int(args[6]);
    if (viewfinder_image_info.len != viewfinder_w * viewfinder_h / 8)
    {
        printf("ERROR: Viewfinder buffer w/h not consistent with buffer size!\n");
        return mp_const_false;
    }
    if (viewfinder_w > qr_w || viewfinder_h > qr_h)
    {
        // Viewfinder can't be larger than base image
        printf("ERROR: Viewfinder buffer is larger than QR buffer!\n");
        return mp_const_false;
    }

    if (camera_snapshot() < 0) {
        return mp_const_false;
    }

    uint16_t *rgb565 = camera_get_frame_buffer();

    uint32_t start = HAL_GetTick();
    convert_rgb565_to_grayscale_and_mono(rgb565, qr_image_info.buf, qr_w, qr_h, viewfinder_image_info.buf, viewfinder_w, viewfinder_h);
    uint32_t end = HAL_GetTick();
    printf("conversion: %lums\n", end - start);
    return mp_const_true;
}

STATIC MP_DEFINE_CONST_FUN_OBJ_1(camera_enable_obj, camera_enable);
STATIC MP_DEFINE_CONST_FUN_OBJ_1(camera_disable_obj, camera_disable);
STATIC MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(camera_snapshot_obj, 7, 7, camera_snapshot_);

STATIC mp_obj_t camera___del__(mp_obj_t self)
{
    // mp_obj_camera_t *o = MP_OBJ_TO_PTR(self);
    return mp_const_none;
}

STATIC MP_DEFINE_CONST_FUN_OBJ_1(camera___del___obj, camera___del__);

STATIC const mp_rom_map_elem_t camera_locals_dict_table[] = {
    {MP_ROM_QSTR(MP_QSTR___name__), MP_ROM_QSTR(MP_QSTR_foundation)}, // TODO: Is this right?  Should it be "foundation_camera" or "camera"?
    {MP_ROM_QSTR(MP_QSTR_enable), MP_ROM_PTR(&camera_enable_obj)},
    {MP_ROM_QSTR(MP_QSTR_disable), MP_ROM_PTR(&camera_disable_obj)},
    {MP_ROM_QSTR(MP_QSTR_snapshot), MP_ROM_PTR(&camera_snapshot_obj)},
    {MP_ROM_QSTR(MP_QSTR___del__), MP_ROM_PTR(&camera___del___obj)},
};
STATIC MP_DEFINE_CONST_DICT(camera_locals_dict, camera_locals_dict_table);

STATIC const mp_obj_type_t camera_type = {
    {&mp_type_type},
    .name = MP_QSTR_camera,
    .make_new = camera_make_new,
    .locals_dict = (void *)&camera_locals_dict,
};
/* End of setup for Camera class */

/*=============================================================================
 * Start of Power Monitor class
 *=============================================================================*/

STATIC mp_obj_t mod_foundation_powermon_make_new(const mp_obj_type_t *type, size_t n_args, size_t n_kw, const mp_obj_t *args) {
    mp_obj_powermon_t *powermon = m_new_obj(mp_obj_powermon_t);
    powermon->base.type = type;

    return MP_OBJ_FROM_PTR(powermon);
}

STATIC mp_obj_t mod_foundation_powermon_read(mp_obj_t self) {
    HAL_StatusTypeDef ret;
    uint16_t current = 0;
    uint16_t voltage = 0;
    mp_obj_t tuple[2];

    mp_obj_powermon_t *pPowerMon = (mp_obj_powermon_t *)self;

    ret = read_powermon(&current, &voltage);
    if (ret != HAL_OK) {
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

STATIC mp_obj_t mod_foundation_powermon___del__(mp_obj_t self) {
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
STATIC mp_obj_t mod_foundation_boardrev_make_new(const mp_obj_type_t *type, size_t n_args, size_t n_kw, const mp_obj_t *args) {
    mp_obj_boardrev_t *boardrev = m_new_obj(mp_obj_boardrev_t);
    boardrev->base.type = type;

    return MP_OBJ_FROM_PTR(boardrev);
}

STATIC mp_obj_t mod_foundation_boardrev_read(mp_obj_t self) {
    HAL_StatusTypeDef ret;
    uint16_t board_rev = 0;

    ret = read_boardrev(&board_rev);
    if (ret != HAL_OK) {
        return mp_const_none;
    }
    return mp_obj_new_int_from_uint(board_rev);
}
STATIC MP_DEFINE_CONST_FUN_OBJ_1(mod_foundation_boardrev_read_obj, mod_foundation_boardrev_read);

STATIC mp_obj_t mod_foundation_boardrev___del__(mp_obj_t self) {
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

STATIC mp_obj_t mod_foundation_noise_make_new(const mp_obj_type_t *type, size_t n_args, size_t n_kw, const mp_obj_t *args) {
    mp_obj_noise_t *noise = m_new_obj(mp_obj_noise_t);
    noise->base.type = type;
    /*
     * Need to enable the noise amp enables.
     */
    enable_noise();

    return MP_OBJ_FROM_PTR(noise);
}

STATIC mp_obj_t mod_foundation_noise_read(mp_obj_t self) {
    HAL_StatusTypeDef ret;
    uint32_t noise1 = 0;
    uint32_t noise2 = 0;
    mp_obj_t tuple[2];

    ret = read_noise_inputs(&noise1, &noise2);
    if (ret != HAL_OK) {
        tuple[0] = mp_const_none;
        tuple[1] = mp_const_none;
        return mp_obj_new_tuple(2, tuple);
    }

    tuple[0] = mp_obj_new_int_from_uint(noise1);
    tuple[1] = mp_obj_new_int_from_uint(noise2);
    return mp_obj_new_tuple(2, tuple);
}
STATIC MP_DEFINE_CONST_FUN_OBJ_1(mod_foundation_noise_read_obj, mod_foundation_noise_read);

bool get_random_uint16(uint16_t* result) {
    HAL_StatusTypeDef ret;
    uint32_t noise1 = 0;
    uint32_t noise2 = 0;
    uint16_t r = 0;

    for (int i=0; i<4; i++) {
        r = r << 4;

        HAL_Delay(1);  // TODO: How long should this be?

        ret = read_noise_inputs(&noise1, &noise2);
        if (ret != HAL_OK) {
            return false;
        }

        r ^= noise1 ^ noise2;
    }
    *result = r;
    return true;
}

STATIC mp_obj_t mod_foundation_noise_random_bytes(mp_obj_t self, const mp_obj_t buf) {
    mp_buffer_info_t buf_info;
    mp_get_buffer_raise(buf, &buf_info, MP_BUFFER_WRITE);
    uint8_t* pbuf = (uint8_t*)buf_info.buf;

    for (int i=0; i<buf_info.len;) {
        uint8_t r[2];
        bool result = get_random_uint16((uint16_t*)&r);
        if (!result) {
            return mp_const_false;
        }

        if (i<buf_info.len) {
            pbuf[i] = r[0];
            i++;
        }
        if (i<buf_info.len) {
            pbuf[i] = r[1];
            i++;
        }
    }
    return mp_const_true;
}
STATIC MP_DEFINE_CONST_FUN_OBJ_2(mod_foundation_noise_random_bytes_obj, mod_foundation_noise_random_bytes);

STATIC mp_obj_t mod_foundation_noise___del__(mp_obj_t self) {
    disable_noise();
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
STATIC mp_obj_t QR_make_new(const mp_obj_type_t *type, size_t n_args, size_t n_kw, const mp_obj_t *args)
{
    mp_obj_QR_t *o = m_new_obj(mp_obj_QR_t);
    o->base.type = type;
    if (n_args != 3)
    {
        printf("ERROR: QR called with wrong number of arguments!");
        return mp_const_none;
    }

    o->width = mp_obj_get_int(args[0]);
    o->height = mp_obj_get_int(args[1]);
    mp_buffer_info_t image_info;
    mp_get_buffer_raise(args[2], &image_info, MP_BUFFER_READ);

    unsigned int expected_image_len = o->width * o->height;
    if (image_info.len != expected_image_len)
    {
        printf("ERROR: Invalid buffer size for this decoder.  Expected %u\n", expected_image_len);
        return mp_const_none;
    }

    if (quirc_init(&o->quirc, o->width, o->height, image_info.buf) < 0)
    {
        printf("ERROR: Unable to initialize quirc!\n");
        return mp_const_none;
    }

    return MP_OBJ_FROM_PTR(o);
}

struct quirc_code code;
struct quirc_data data;

#define QR_DEBUG
/// def find_qr_codes(self, image: image) -> array of strings:
///     '''
///     Find QR codes in image.
///     '''
STATIC mp_obj_t QR_find_qr_codes(mp_obj_t self)
{
    mp_obj_QR_t *o = MP_OBJ_TO_PTR(self);

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


    if (num_codes == 0)
    {
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
    if (err)
    {
        printf("ERROR: Decode failed: %s\n", quirc_strerror(err));
        return mp_const_none;
    }
    else
    {
#ifdef QR_DEBUG
        printf("Data: %s\n", data.payload);
#endif
    }

    // Return the payload as the function result
    // const char* payload = mp_obj_str_get_str(data.payload);
    // printf("Data: %s\n", payload);

    vstr_t vstr;
    int code_len = strlen((const char *)data.payload);

    vstr_init(&vstr, code_len + 1);
    vstr_add_strn(&vstr, (const char *)data.payload, code_len); // Can append to vstr if necessary
    return mp_obj_new_str_from_vstr(&mp_type_str, &vstr);
}
STATIC MP_DEFINE_CONST_FUN_OBJ_1(QR_find_qr_codes_obj, QR_find_qr_codes);

STATIC mp_obj_t QR___del__(mp_obj_t self)
{
    mp_obj_QR_t *o = MP_OBJ_TO_PTR(self);
    quirc_destroy(&o->quirc);
    return mp_const_none;
}

STATIC MP_DEFINE_CONST_FUN_OBJ_1(QR___del___obj, QR___del__);

STATIC const mp_rom_map_elem_t QR_locals_dict_table[] = {
    {MP_ROM_QSTR(MP_QSTR___name__), MP_ROM_QSTR(MP_QSTR_foundation)},
    {MP_ROM_QSTR(MP_QSTR_find_qr_codes), MP_ROM_PTR(&QR_find_qr_codes_obj)},
    {MP_ROM_QSTR(MP_QSTR___del__), MP_ROM_PTR(&QR___del___obj)},
};
STATIC MP_DEFINE_CONST_DICT(QR_locals_dict, QR_locals_dict_table);

STATIC const mp_obj_type_t QR_type = {
    {&mp_type_type},
    .name = MP_QSTR_QR,
    .make_new = QR_make_new,
    .locals_dict = (void *)&QR_locals_dict,
};
/* End of setup for QR decoder class */


/*=============================================================================
 * Start of SettingsFlash class
 *=============================================================================*/

/// def __init__(self, mode: int, key: bytes, iv: bytes = None) -> boolean:
///     '''
///     Initialize SettingsFlash context.
///     '''
STATIC mp_obj_t SettingsFlash_make_new(const mp_obj_type_t *type, size_t n_args, size_t n_kw, const mp_obj_t *args)
{
    mp_obj_SettingsFlash_t *o = m_new_obj(mp_obj_SettingsFlash_t);
    o->base.type = type;
    return MP_OBJ_FROM_PTR(o);
}

#define FLASH_DEBUG
/// def write(self, dest_addr, data) -> boolean
///     '''
///     Write data to internal flash
///     '''
STATIC mp_obj_t SettingsFlash_write(mp_obj_t self, mp_obj_t dest_addr, mp_obj_t data)
{
    uint32_t flash_addr = mp_obj_get_int(dest_addr);
    mp_buffer_info_t data_info;
    mp_get_buffer_raise(data, &data_info, MP_BUFFER_READ);

    if (flash_addr < SETTINGS_FLASH_START ||
        flash_addr + data_info.len > SETTINGS_FLASH_END ||
        data_info.len % 4 != 0) {
#ifdef FLASH_DEBUG
    printf("ERROR: SettingsFlash_write: bad parameters\n");
#endif
        return mp_const_false;
    }

#ifdef FLASH_DEBUG
    printf("SettingsFlash_write: %u bytes to 0x%08lx\n",data_info.len, flash_addr);

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


    printf("write: DONE\n");

    return mp_const_true;
}

/// def erase(self, buf) -> boolean
///     '''
///     Erase all of flash (H7 doesn't provide facility to erase less than the whole 128K)
///     '''
STATIC mp_obj_t SettingsFlash_erase(mp_obj_t self)
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

STATIC mp_obj_t SettingsFlash___del__(mp_obj_t self)
{
    return mp_const_none;
}

STATIC MP_DEFINE_CONST_FUN_OBJ_1(SettingsFlash___del___obj, SettingsFlash___del__);

STATIC const mp_rom_map_elem_t SettingsFlash_locals_dict_table[] = {
    {MP_ROM_QSTR(MP_QSTR___name__), MP_ROM_QSTR(MP_QSTR_foundation)},
    {MP_ROM_QSTR(MP_QSTR_write), MP_ROM_PTR(&SettingsFlash_write_obj)},
    {MP_ROM_QSTR(MP_QSTR_erase), MP_ROM_PTR(&SettingsFlash_erase_obj)},
    {MP_ROM_QSTR(MP_QSTR___del__), MP_ROM_PTR(&SettingsFlash___del___obj)},
};
STATIC MP_DEFINE_CONST_DICT(SettingsFlash_locals_dict, SettingsFlash_locals_dict_table);

STATIC const mp_obj_type_t SettingsFlash_type = {
    {&mp_type_type},
    .name = MP_QSTR_SettingsFlash,
    .make_new = SettingsFlash_make_new,
    .locals_dict = (void *)&SettingsFlash_locals_dict,
};
/* End of setup for internal flash class */

/*=============================================================================
 * Start of System class
 *=============================================================================*/

/// def __init__(self, mode: int, key: bytes, iv: bytes = None) -> boolean:
///     '''
///     Initialize System context.
///     '''
STATIC mp_obj_t System_make_new(const mp_obj_type_t *type, size_t n_args, size_t n_kw, const mp_obj_t *args)
{
    mp_obj_System_t *o = m_new_obj(mp_obj_System_t);
    o->base.type = type;
    return MP_OBJ_FROM_PTR(o);
}

#define SYSTEM_DEBUG
/// def reset(self) -> None
///     '''
///     Perform a warm reset of the system (should be mostly the same as turning it off and then on)
///     '''
STATIC mp_obj_t System_reset(mp_obj_t self)
{
    passport_reset();
    return mp_const_none;
}

/// def shutdown(self) -> None
///     '''
///    Shutdown power to the Passport
///     '''
STATIC mp_obj_t System_shutdown(mp_obj_t self)
{
    passport_shutdown();
    return mp_const_none;
}

/// def dispatch(self, command: int, buf: bytes, len: int, arg2: int, ) -> array of strings:
///     '''
///     Dispatch system function by command number.  This is a carry-over from the old firewall
///     code.  We can probably switch this to direct function calls instead.  The only benefit is
///     that this gives us a nice single point to handle RDP level 2 checks and other security checks.
///     '''
STATIC mp_obj_t System_dispatch(size_t n_args, const mp_obj_t *args)
{
    int8_t command = mp_obj_get_int(args[1]);
    uint16_t arg2 = mp_obj_get_int(args[3]);
    int result;

    if (args[2] == mp_const_none) {
        result = se_dispatch(command, NULL, 0, arg2, 0, 0);
    } else {
        mp_buffer_info_t buf_info;  // Use MP_BUFFER_WRITE below so any updates are copied back up
        mp_get_buffer_raise(args[2], &buf_info, MP_BUFFER_WRITE);

        // TODO: What are the incoming_sp and incoming_lr for?
        result = se_dispatch(command, buf_info.buf, buf_info.len, arg2, 0, 0);
    }

    return mp_obj_new_int(result);
}


#define SECRETS_FLASH_START 0x81C0000
#define SECRETS_FLASH_SIZE  0x20000

/// def erase_rom_secrets(self) -> None
///     '''
///    Erase ROM secrets
///    TODO: This is a temporary function, since ROM secrets will be in the bootloader,
///    in this final bank of flash as they are here.
///     '''
STATIC mp_obj_t System_erase_rom_secrets(mp_obj_t self)
{
    // NOTE: This function doesn't return any error/success info
    flash_erase(SECRETS_FLASH_START, SECRETS_FLASH_SIZE / 4);
    return mp_const_none;
}

STATIC MP_DEFINE_CONST_FUN_OBJ_1(System_reset_obj, System_reset);
STATIC MP_DEFINE_CONST_FUN_OBJ_1(System_shutdown_obj, System_shutdown);
STATIC MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(System_dispatch_obj, 4, 4, System_dispatch);
STATIC MP_DEFINE_CONST_FUN_OBJ_1(System_erase_rom_secrets_obj, System_erase_rom_secrets);

STATIC mp_obj_t System___del__(mp_obj_t self)
{
    return mp_const_none;
}

STATIC MP_DEFINE_CONST_FUN_OBJ_1(System___del___obj, System___del__);

STATIC const mp_rom_map_elem_t System_locals_dict_table[] = {
    {MP_ROM_QSTR(MP_QSTR___name__), MP_ROM_QSTR(MP_QSTR_foundation)},
    {MP_ROM_QSTR(MP_QSTR_reset), MP_ROM_PTR(&System_reset_obj)},
    {MP_ROM_QSTR(MP_QSTR_shutdown), MP_ROM_PTR(&System_shutdown_obj)},
    {MP_ROM_QSTR(MP_QSTR_dispatch), MP_ROM_PTR(&System_dispatch_obj)},
    {MP_ROM_QSTR(MP_QSTR_erase_rom_secrets), MP_ROM_PTR(&System_erase_rom_secrets_obj)},
    {MP_ROM_QSTR(MP_QSTR___del__), MP_ROM_PTR(&System___del___obj)},
};
STATIC MP_DEFINE_CONST_DICT(System_locals_dict, System_locals_dict_table);

STATIC const mp_obj_type_t System_type = {
    {&mp_type_type},
    .name = MP_QSTR_System,
    .make_new = System_make_new,
    .locals_dict = (void *)&System_locals_dict,
};
/* End of setup for System class */

/*=============================================================================
 * Start of bip39 class
 *=============================================================================*/

/// def __init__(self, mode: int, key: bytes, iv: bytes = None) -> boolean:
///     '''
///     Initialize System context.
///     '''
STATIC mp_obj_t bip39_make_new(const mp_obj_type_t *type, size_t n_args, size_t n_kw, const mp_obj_t *args)
{
    mp_obj_bip39_t *o = m_new_obj(mp_obj_bip39_t);
    o->base.type = type;
    return MP_OBJ_FROM_PTR(o);
}

/// def get_words_matching_prefix(self) -> None
///     '''
///     Return a comma-separated list of BIP39 seed words that match the given keypad
///     digits prefix (e.g., '222').
///     '''
STATIC mp_obj_t bip39_get_words_matching_prefix(mp_obj_t self, mp_obj_t prefix, mp_obj_t _max_matches)
{
    uint32_t start = HAL_GetTick();

    mp_check_self(mp_obj_is_str_or_bytes(prefix));
    GET_STR_DATA_LEN(prefix, prefix_str, prefix_len);

    printf("bip39_get_words_matching_prefix: prefix_str=%s len=%d\n", prefix_str, prefix_len);

    int max_matches = mp_obj_get_int(_max_matches);
    // TODO: change this to calculate dynamically based on max_matches and max seed word length,including comma separators
    #define MATCHES_LEN 80
    char matches[MATCHES_LEN];

    get_words_matching_prefix((char*)prefix_str, matches, MATCHES_LEN, max_matches);

    // Return the string
    vstr_t vstr;
    int matches_len = strlen((const char *)matches);

    vstr_init(&vstr, matches_len + 1);
    vstr_add_strn(&vstr, (const char *)matches, matches_len);

    uint32_t end = HAL_GetTick();
    printf("bip39_get_words_matching_prefix: %lums\n", end - start);

    return mp_obj_new_str_from_vstr(&mp_type_str, &vstr);
}
STATIC MP_DEFINE_CONST_FUN_OBJ_3(bip39_get_words_matching_prefix_obj, bip39_get_words_matching_prefix);

#include "bip39.h"

/// def mnemonic_to_entropy(self) -> None
///     '''
///     Call trezorcrypto's mnemonic_to_entropy() C function since it's not exposed through their
///     Python interface.
///     '''
STATIC mp_obj_t bip39_mnemonic_to_entropy(mp_obj_t self, mp_obj_t mnemonic, mp_obj_t entropy)
{
    mp_check_self(mp_obj_is_str_or_bytes(mnemonic));
    GET_STR_DATA_LEN(mnemonic, mnemonic_str, mnemonic_len);
    mp_buffer_info_t entropy_info;
    mp_get_buffer_raise(entropy, &entropy_info, MP_BUFFER_WRITE);
 
    int len = mnemonic_to_entropy((const char*)mnemonic_str, entropy_info.buf);
    return mp_obj_new_int(len);
}
STATIC MP_DEFINE_CONST_FUN_OBJ_3(bip39_mnemonic_to_entropy_obj, bip39_mnemonic_to_entropy);


STATIC mp_obj_t bip39___del__(mp_obj_t self)
{
    return mp_const_none;
}

STATIC MP_DEFINE_CONST_FUN_OBJ_1(bip39___del___obj, bip39___del__);

STATIC const mp_rom_map_elem_t bip39_locals_dict_table[] = {
    {MP_ROM_QSTR(MP_QSTR___name__), MP_ROM_QSTR(MP_QSTR_foundation)},
    {MP_ROM_QSTR(MP_QSTR_get_words_matching_prefix), MP_ROM_PTR(&bip39_get_words_matching_prefix_obj)},
    {MP_ROM_QSTR(MP_QSTR_mnemonic_to_entropy), MP_ROM_PTR(&bip39_mnemonic_to_entropy_obj)},
    {MP_ROM_QSTR(MP_QSTR___del__), MP_ROM_PTR(&bip39___del___obj)},
};
STATIC MP_DEFINE_CONST_DICT(bip39_locals_dict, bip39_locals_dict_table);

STATIC const mp_obj_type_t bip39_type = {
    {&mp_type_type},
    .name = MP_QSTR_bip39,
    .make_new = bip39_make_new,
    .locals_dict = (void *)&bip39_locals_dict,
};
/* End of setup for bip39 class */

/*=============================================================================
 * Start of QRCode class - renders QR codes to a buffer passed down from MP
 *=============================================================================*/


// We only have versions here that can be rendered on a 
uint16_t version_capacity[] = {
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

/// def __init__(self, mode: int, key: bytes, iv: bytes = None) -> boolean:
///     '''
///     Initialize QRCode context.
///     '''
STATIC mp_obj_t QRCode_make_new(const mp_obj_type_t *type, size_t n_args, size_t n_kw, const mp_obj_t *args)
{
    mp_obj_QRCode_t *o = m_new_obj(mp_obj_QRCode_t);
    o->base.type = type;
    return MP_OBJ_FROM_PTR(o);
}

QRCode qrcode;
#define QRCODE_DEBUG

/// def render(self) -> None
///     '''
///     Render a QR code with the given data, version and ecc level
///     '''
STATIC mp_obj_t QRCode_render(size_t n_args, const mp_obj_t *args)
{
    mp_check_self(mp_obj_is_str_or_bytes(args[1]));
    GET_STR_DATA_LEN(args[1], text_str, text_len);

    uint8_t version = mp_obj_get_int(args[2]);
    uint8_t ecc = mp_obj_get_int(args[3]);

    mp_buffer_info_t output_info;
    mp_get_buffer_raise(args[4], &output_info, MP_BUFFER_WRITE);

    uint8_t result = qrcode_initBytes(&qrcode, (uint8_t *)output_info.buf, version, ecc, (uint8_t *)text_str, text_len);

    return result == 0 ? mp_const_false : mp_const_true;
}

/// def fit_to_version(self) -> None
///     '''
///    Return the QR code version that best fits this data (assumes ECC level 0 for now)
///     '''
STATIC mp_obj_t QRCode_fit_to_version(mp_obj_t self, mp_obj_t data_size)
{
    int num_entries = sizeof(version_capacity)/sizeof(uint16_t);

    uint16_t size = mp_obj_get_int(data_size);
    // printf("QRCode_fit_to_version: size=%u\n", size);

    for (int i=0; i<num_entries; i++) {
        if (version_capacity[i] >= size) {
            return mp_obj_new_int(i + 1);
        }
    }

    // Data is too big
    return mp_obj_new_int(0);
}

STATIC MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(QRCode_render_obj, 5, 5, QRCode_render);
STATIC MP_DEFINE_CONST_FUN_OBJ_2(QRCode_fit_to_version_obj, QRCode_fit_to_version);

STATIC mp_obj_t QRCode___del__(mp_obj_t self)
{
    return mp_const_none;
}

STATIC MP_DEFINE_CONST_FUN_OBJ_1(QRCode___del___obj, QRCode___del__);

STATIC const mp_rom_map_elem_t QRCode_locals_dict_table[] = {
    {MP_ROM_QSTR(MP_QSTR___name__), MP_ROM_QSTR(MP_QSTR_foundation)},
    {MP_ROM_QSTR(MP_QSTR_render), MP_ROM_PTR(&QRCode_render_obj)},
    {MP_ROM_QSTR(MP_QSTR_fit_to_version), MP_ROM_PTR(&QRCode_fit_to_version_obj)},
    {MP_ROM_QSTR(MP_QSTR___del__), MP_ROM_PTR(&QRCode___del___obj)},
};
STATIC MP_DEFINE_CONST_DICT(QRCode_locals_dict, QRCode_locals_dict_table);

STATIC const mp_obj_type_t QRCode_type = {
    {&mp_type_type},
    .name = MP_QSTR_QRCode,
    .make_new = QRCode_make_new,
    .locals_dict = (void *)&QRCode_locals_dict,
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
    {MP_ROM_QSTR(MP_QSTR___name__), MP_ROM_QSTR(MP_QSTR_foundation)},
    {MP_ROM_QSTR(MP_QSTR___del__), MP_ROM_PTR(&foundation___del___obj)},
    {MP_ROM_QSTR(MP_QSTR_Backlight), MP_ROM_PTR(&backlight_type)},
    {MP_ROM_QSTR(MP_QSTR_Keypad), MP_ROM_PTR(&keypad_type)},
    {MP_ROM_QSTR(MP_QSTR_LCD), MP_ROM_PTR(&lcd_type)},
    {MP_ROM_QSTR(MP_QSTR_Camera), MP_ROM_PTR(&camera_type)},
    {MP_ROM_QSTR(MP_QSTR_Boardrev), MP_ROM_PTR(&boardrev_type)},
    {MP_ROM_QSTR(MP_QSTR_Powermon), MP_ROM_PTR(&powermon_type)},
    {MP_ROM_QSTR(MP_QSTR_Noise), MP_ROM_PTR(&noise_type)},
    {MP_ROM_QSTR(MP_QSTR_QR), MP_ROM_PTR(&QR_type)},
    {MP_ROM_QSTR(MP_QSTR_SettingsFlash), MP_ROM_PTR(&SettingsFlash_type)},
    {MP_ROM_QSTR(MP_QSTR_System), MP_ROM_PTR(&System_type)},
    {MP_ROM_QSTR(MP_QSTR_bip39), MP_ROM_PTR(&bip39_type)},
    {MP_ROM_QSTR(MP_QSTR_QRCode), MP_ROM_PTR(&QRCode_type)},
};
STATIC MP_DEFINE_CONST_DICT(foundation_module_globals, foundation_module_globals_table);

/* Define module object. */
const mp_obj_module_t foundation_user_cmodule = {
    .base = {&mp_type_module},
    .globals = (mp_obj_dict_t *)&foundation_module_globals,
};

MP_REGISTER_MODULE(MP_QSTR_foundation, foundation_user_cmodule, PASSPORT_FOUNDATION_ENABLED);
