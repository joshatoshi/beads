#ifndef BEADS_OLED_UI_H
#define BEADS_OLED_UI_H

#include <stdbool.h>
#include <stdint.h>
#include "cv_engine.h"
#include "presets.h"

#define OLED_I2C_ADDR        0x3Cu
#define OLED_WIDTH           128u
#define OLED_HEIGHT          64u
#define OLED_PAGES           8u
#define OLED_FB_BYTES        (OLED_WIDTH * OLED_PAGES)
#define OLED_I2C_CHUNK_BYTES 16u
#define OLED_CHUNKS_PER_PAGE (OLED_WIDTH / OLED_I2C_CHUNK_BYTES)
#define UI_RENDER_PERIOD_US  2000u

#define UI_CH_PARAM_COUNT 7u /* MODE, SUB, PARAM_A, PARAM_B, SPAN, OFFSET, SYNC */

typedef enum {
    UI_PAGE_SCOPE    = 0,  /* Live 8-ch oscilloscope + active channel bar */
    UI_PAGE_CHANNEL  = 1,  /* Edit selected CV1..8 mode/sub/param_a/param_b/span/offset/sync */
    UI_PAGE_PRESET   = 2,  /* Browse & recall Presets 0..31 */
    UI_PAGE_SYSTEM   = 3   /* MIDI Ch, 1V/Oct Cal, USB FIRMWARE UPDATE */
} ui_page_t;

typedef struct {
    ui_page_t page;
    uint8_t   selected_ch;     /* 0..7 */
    uint8_t   cursor;
    bool      editing;
    uint8_t   cal_ch;          /* 0..7 channel under 1V/Oct calibration */
    uint8_t   cal_oct;         /* 0..9 octave knot under 1V/Oct calibration */
    bool      usb_cdc_1200_armed;
    uint8_t   scope_hist[OLED_WIDTH];
    uint8_t   scope_head;
    uint8_t   flush_page;      /* Current SSD1306 page 0..7 */
    uint8_t   flush_substep;   /* 0 = 4B page/col cmd, 1..8 = 16B pixel chunks (<450 us!) */
    uint8_t   page_dirty_mask; /* Per-page dirty bitmask (1 bit per 128B page) */
    uint8_t   page_sent_mask;  /* Per-page valid bitmask once written to sent_fb */
    bool      rendered_once;
    uint32_t  last_render_us;
    bool      dirty;
    uint8_t   fb[OLED_FB_BYTES];
    uint8_t   sent_fb[OLED_FB_BYTES];
} oled_ui_t;

void oled_ui_init(oled_ui_t *ui);
void oled_ui_handle_inputs(oled_ui_t *ui, int32_t enc_delta, bool enc_click, bool back_click,
                           cv_engine_t *eng, bypass_seq_t *byp, midi_router_t *midi, preset_mgr_t *pm);
void oled_ui_handle_usb_cdc_line_coding(oled_ui_t *ui, uint32_t bit_rate);
void oled_ui_render(oled_ui_t *ui, const cv_engine_t *eng, const bypass_seq_t *byp,
                    const preset_mgr_t *pm, bool usb_connected);
bool oled_ui_flush_step(oled_ui_t *ui);
bool oled_ui_flush_one_page(oled_ui_t *ui);

#endif /* BEADS_OLED_UI_H */
