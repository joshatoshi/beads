#ifndef BEADS_OLED_UI_H
#define BEADS_OLED_UI_H

#include <stdbool.h>
#include <stdint.h>
#include "cv_engine.h"
#include "presets.h"

#define OLED_I2C_ADDR    0x3Cu
#define OLED_WIDTH       128u
#define OLED_HEIGHT      64u
#define OLED_PAGES       8u
#define OLED_FB_BYTES    (OLED_WIDTH * OLED_PAGES)

typedef enum {
    UI_PAGE_SCOPE    = 0,  /* Live 8-ch oscilloscope + active channel bar */
    UI_PAGE_CHANNEL  = 1,  /* Edit selected CV1..8 mode/rate/span/offset */
    UI_PAGE_PRESET   = 2,  /* Load/Save Presets 0..31 */
    UI_PAGE_SYSTEM   = 3   /* MIDI Ch, 1V/Oct Cal, USB FIRMWARE UPDATE */
} ui_page_t;

typedef struct {
    ui_page_t page;
    uint8_t   selected_ch;     /* 0..7 */
    uint8_t   cursor;
    bool      editing;
    bool      usb_cdc_1200_armed;
    uint8_t   scope_hist[OLED_WIDTH];
    uint8_t   scope_head;
    uint8_t   flush_page;      /* Page-sliced I2C flush 0..7 (< 1 ms per slice!) */
    bool      dirty;
    uint8_t   fb[OLED_FB_BYTES];
} oled_ui_t;

void oled_ui_init(oled_ui_t *ui);
void oled_ui_handle_inputs(oled_ui_t *ui, int32_t enc_delta, bool enc_click, bool back_click,
                           cv_engine_t *eng, preset_mgr_t *pm);
void oled_ui_handle_usb_cdc_line_coding(oled_ui_t *ui, uint32_t bit_rate);
void oled_ui_render(oled_ui_t *ui, const cv_engine_t *eng, const bypass_seq_t *byp, bool usb_connected);
bool oled_ui_flush_one_page(oled_ui_t *ui);

#endif /* BEADS_OLED_UI_H */
