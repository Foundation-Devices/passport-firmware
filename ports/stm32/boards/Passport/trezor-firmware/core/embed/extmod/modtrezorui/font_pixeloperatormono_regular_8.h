#include <stdint.h>

#if TREZOR_FONT_BPP != 1
#error Wrong TREZOR_FONT_BPP (expected 1)
#endif
extern const uint8_t* const Font_PixelOperatorMono_Regular_8[126 + 1 - 32];
extern const uint8_t Font_PixelOperatorMono_Regular_8_glyph_nonprintable[];
