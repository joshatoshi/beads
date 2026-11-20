#include "oled_ui.h"
#include "hal.h"
#include <string.h>

/* Compact 5x7 uppercase ASCII glyph subset for clean zero-dependency SSD1306 rendering */
static const uint8_t OLED_INIT_SEQ[] = {
    0x00u, /* Command stream */
    0xAEu, /* Display OFF */
    0xD5u, 0x80u,
    0xA8u, 0x3Fu, /* 64 mux */
    0xD3u, 0x00u,
    0x40u,
    0x8Du, 0x14u, /* Charge pump ON */
    0x20u, 0x02u, /* Page addressing mode (clean 1-page <1ms slices!) */
    0xA1u, 0xC8u,
    0xDAu, 0x12u,
    0x81u, 0xCFu,
    0xD9u, 0xF1u,
    0xDBu, 0x40u,
    0xA4u, 0xA6u,
    0xAFu  /* Display ON */
};

static void fb_set_pixel(oled_ui_t *ui, uint8_t x, uint8_t y) {
    if (x >= OLED_WIDTH || y >= OLED_HEIGHT) return;
    ui->fb[(uint16_t)(y >> 3u) * OLED_WIDTH + x] |= (uint8_t)(1u << (y & 7u));
}

/* Compact 5x7 uppercase/digit ASCII font (0x20..0x5A) for readable SSD1306 menu text */
static const uint8_t FONT5X7[59][5] = {
    {0x00,0x00,0x00,0x00,0x00}, {0x00,0x00,0x5F,0x00,0x00}, {0x00,0x07,0x00,0x07,0x00},
    {0x14,0x7F,0x14,0x7F,0x14}, {0x24,0x2A,0x7F,0x2A,0x12}, {0x23,0x13,0x08,0x64,0x62},
    {0x36,0x49,0x55,0x22,0x50}, {0x00,0x05,0x03,0x00,0x00}, {0x00,0x1C,0x22,0x41,0x00},
    {0x00,0x41,0x22,0x1C,0x00}, {0x08,0x2A,0x1C,0x2A,0x08}, {0x08,0x08,0x3E,0x08,0x08},
    {0x00,0x50,0x30,0x00,0x00}, {0x08,0x08,0x08,0x08,0x08}, {0x00,0x60,0x60,0x00,0x00},
    {0x20,0x10,0x08,0x04,0x02}, {0x3E,0x51,0x49,0x45,0x3E}, {0x00,0x42,0x7F,0x40,0x00},
    {0x42,0x61,0x51,0x49,0x46}, {0x21,0x41,0x45,0x4B,0x31}, {0x18,0x14,0x12,0x7F,0x10},
    {0x27,0x45,0x45,0x45,0x39}, {0x3C,0x4A,0x49,0x49,0x30}, {0x01,0x71,0x09,0x05,0x03},
    {0x36,0x49,0x49,0x49,0x36}, {0x06,0x49,0x49,0x29,0x1E}, {0x00,0x36,0x36,0x00,0x00},
    {0x00,0x56,0x36,0x00,0x00}, {0x00,0x08,0x14,0x22,0x41}, {0x14,0x14,0x14,0x14,0x14},
    {0x41,0x22,0x14,0x08,0x00}, {0x02,0x01,0x51,0x09,0x06}, {0x32,0x49,0x79,0x41,0x3E},
    {0x7E,0x11,0x11,0x11,0x7E}, {0x7F,0x49,0x49,0x49,0x36}, {0x3E,0x41,0x41,0x41,0x22},
    {0x7F,0x41,0x41,0x22,0x1C}, {0x7F,0x49,0x49,0x49,0x41}, {0x7F,0x09,0x09,0x09,0x01},
    {0x3E,0x41,0x41,0x51,0x32}, {0x7F,0x08,0x08,0x08,0x7F}, {0x00,0x41,0x7F,0x41,0x00},
    {0x20,0x40,0x41,0x3F,0x01}, {0x7F,0x08,0x14,0x22,0x41}, {0x7F,0x40,0x40,0x40,0x40},
    {0x7F,0x02,0x04,0x02,0x7F}, {0x7F,0x04,0x08,0x10,0x7F}, {0x3E,0x41,0x41,0x41,0x3E},
    {0x7F,0x09,0x09,0x09,0x06}, {0x3E,0x41,0x51,0x21,0x5E}, {0x7F,0x09,0x19,0x29,0x46},
    {0x46,0x49,0x49,0x49,0x31}, {0x01,0x01,0x7F,0x01,0x01}, {0x3F,0x40,0x40,0x40,0x3F},
    {0x1F,0x20,0x40,0x20,0x1F}, {0x7F,0x20,0x18,0x20,0x7F}, {0x63,0x14,0x08,0x14,0x63},
    {0x03,0x04,0x78,0x04,0x03}, {0x61,0x51,0x49,0x45,0x43}
};

static void fb_draw_str(oled_ui_t *ui, uint8_t x, uint8_t y, const char *s) {
    while (*s != '\0' && x + 5u < OLED_WIDTH) {
        char c = *s++;
        if (c >= 'a' && c <= 'z') c = (char)(c - 32);
        if (c < 0x20 || c > 'Z') c = ' ';
        const uint8_t *glyph = FONT5X7[(uint8_t)(c - 0x20)];
        for (uint8_t col = 0u; col < 5u; col++) {
            uint8_t bits = glyph[col];
            for (uint8_t row = 0u; row < 7u; row++) {
                if ((bits & (1u << row)) != 0u) {
                    fb_set_pixel(ui, (uint8_t)(x + col), (uint8_t)(y + row));
                }
            }
        }
        x = (uint8_t)(x + 6u);
    }
}

void oled_ui_init(oled_ui_t *ui) {
    memset(ui, 0, sizeof(*ui));
    ui->page = UI_PAGE_SCOPE;
    ui->dirty = true;
    /* Bounded I2C timeout (2 ms) so absent/unplugged OLED never hangs Core 1! */
    (void)hal_i2c0_write_timeout(OLED_I2C_ADDR, OLED_INIT_SEQ, sizeof(OLED_INIT_SEQ), 2000u);
}

void oled_ui_handle_usb_cdc_line_coding(oled_ui_t *ui, uint32_t bit_rate) {
    /* Standard RP2040 1200-baud touch triggers headerless USB-C UF2 bootloader! */
    if (bit_rate == 1200u) {
        ui->usb_cdc_1200_armed = true;
        hal_reset_usb_boot(0u, 0u);
    }
}

void oled_ui_handle_inputs(oled_ui_t *ui, int32_t enc_delta, bool enc_click, bool back_click,
                           cv_engine_t *eng, preset_mgr_t *pm) {
    if (enc_delta == 0 && !enc_click && !back_click) {
        return;
    }
    ui->dirty = true;

    if (back_click) {
        if (ui->editing) {
            ui->editing = false;
        } else {
            ui->page = (ui->page == UI_PAGE_SCOPE) ? UI_PAGE_SYSTEM : (ui_page_t)(ui->page - 1u);
            ui->cursor = 0u;
        }
        return;
    }

    switch (ui->page) {
        case UI_PAGE_SCOPE:
            if (enc_delta != 0) {
                int32_t ch = (int32_t)ui->selected_ch + enc_delta;
                if (ch < 0) ch = 0;
                if (ch >= (int32_t)BEADS_NUM_CV_CHANNELS) ch = (int32_t)BEADS_NUM_CV_CHANNELS - 1;
                ui->selected_ch = (uint8_t)ch;
            }
            if (enc_click) {
                ui->page = UI_PAGE_CHANNEL;
                ui->cursor = 0u;
            }
            break;

        case UI_PAGE_CHANNEL:
            if (!ui->editing) {
                if (enc_delta != 0) {
                    int32_t cur = (int32_t)ui->cursor + enc_delta;
                    if (cur < 0) cur = 0;
                    if (cur > 3) cur = 3;
                    ui->cursor = (uint8_t)cur;
                }
                if (enc_click) {
                    ui->editing = true;
                }
            } else {
                if (enc_delta != 0) {
                    hal_crit_enter();
                    cv_channel_cfg_t *c = &eng->active_preset.ch[ui->selected_ch];
                    if (ui->cursor == 0u) {
                        int32_t m = (int32_t)c->mode + enc_delta;
                        if (m < 0) m = 0;
                        if (m > (int32_t)CV_MODE_FS2_ACTION) m = (int32_t)CV_MODE_FS2_ACTION;
                        c->mode = (uint8_t)m;
                    } else if (ui->cursor == 1u) {
                        /* Saturate strictly to [0, 127], never & 0x7F wraparound! */
                        int32_t v = (int32_t)c->param_a + enc_delta;
                        if (v < 0) v = 0;
                        if (v > 127) v = 127;
                        c->param_a = (uint8_t)v;
                    } else if (ui->cursor == 2u) {
                        int32_t s = (int32_t)c->span + enc_delta;
                        if (s < 0) s = 0;
                        if (s > (int32_t)CV_SPAN_UNI_8V) s = (int32_t)CV_SPAN_UNI_8V;
                        c->span = (uint8_t)s;
                    } else {
                        int32_t o = (int32_t)c->offset_pct + enc_delta * 5;
                        if (o < -100) o = -100;
                        if (o > 100) o = 100;
                        c->offset_pct = (int8_t)o;
                    }
                    pm->live.presets[eng->active_preset_idx] = eng->active_preset;
                    preset_mgr_mark_dirty(pm);
                    hal_crit_exit();
                }
                if (enc_click) {
                    ui->editing = false;
                }
            }
            break;

        case UI_PAGE_PRESET:
            if (enc_delta != 0) {
                int32_t p = (int32_t)ui->cursor + enc_delta;
                if (p < 0) p = 0;
                if (p >= (int32_t)BEADS_NUM_PRESETS) p = (int32_t)BEADS_NUM_PRESETS - 1;
                ui->cursor = (uint8_t)p;
            }
            if (enc_click) {
                hal_crit_enter();
                const beads_preset_t *pr = preset_mgr_get(pm, ui->cursor);
                cv_engine_load_preset(eng, pr, ui->cursor);
                pm->live.active_preset = ui->cursor;
                preset_mgr_mark_dirty(pm);
                hal_crit_exit();
            }
            break;

        case UI_PAGE_SYSTEM:
            if (enc_delta != 0) {
                int32_t c = (int32_t)ui->cursor + enc_delta;
                if (c < 0) c = 0;
                if (c > 2) c = 2; /* 0=MIDI CH, 1=1V/OCT CAL, 2=USB FIRMWARE UPDATE */
                ui->cursor = (uint8_t)c;
            }
            if (enc_click && ui->cursor == 2u) {
                /* SYSTEM -> USB FIRMWARE UPDATE: enters RP2040 ROM UF2 Mass Storage! */
                hal_reset_usb_boot(0u, 0u);
            }
            break;
    }
}

void oled_ui_render(oled_ui_t *ui, const cv_engine_t *eng, const bypass_seq_t *byp, bool usb_connected) {
    memset(ui->fb, 0, sizeof(ui->fb));

    /* Top status bar (Y = 0..11): Active/Bypass indicator + USB badge + selected channel marker */
    for (uint8_t x = 0u; x < OLED_WIDTH; x++) {
        fb_set_pixel(ui, x, 11u);
    }
    if (byp->current_active) {
        for (uint8_t x = 2u; x < 10u; x++)
            for (uint8_t y = 2u; y < 9u; y++)
                fb_set_pixel(ui, x, y);
    }
    if (usb_connected) {
        for (uint8_t x = 116u; x < 124u; x++)
            for (uint8_t y = 3u; y < 8u; y++)
                fb_set_pixel(ui, x, y);
    }

    /* Record oscilloscope trace for selected CV channel */
    int32_t q15 = eng->ch[ui->selected_ch].scope_val_q15;
    /* Map [-32767..+32767] -> Y in [60..16] */
    int32_t py = 38 - ((q15 * 22) >> 15);
    if (py < 14) py = 14;
    if (py > 61) py = 61;
    ui->scope_hist[ui->scope_head] = (uint8_t)py;
    ui->scope_head = (uint8_t)((ui->scope_head + 1u) & (OLED_WIDTH - 1u));

    if (ui->page == UI_PAGE_SCOPE) {
        /* Center 0V dashed horizon at Y=38 */
        for (uint8_t x = 0u; x < OLED_WIDTH; x += 4u) {
            fb_set_pixel(ui, x, 38u);
        }
        /* Draw scrolling waveform */
        for (uint8_t x = 0u; x < OLED_WIDTH; x++) {
            uint8_t idx = (uint8_t)((ui->scope_head + x) & (OLED_WIDTH - 1u));
            fb_set_pixel(ui, x, ui->scope_hist[idx]);
        }
        /* Draw 8-channel mini bar meters along bottom 3 pixels */
        for (uint8_t ch = 0u; ch < BEADS_NUM_CV_CHANNELS; ch++) {
            uint8_t bx = (uint8_t)(ch * 16u + 1u);
            uint8_t bw = (uint8_t)((eng->ch[ch].last_out_code >> 8u) & 0x0Fu);
            for (uint8_t dx = 0u; dx < bw; dx++) {
                fb_set_pixel(ui, (uint8_t)(bx + dx), 63u);
            }
        }
    } else if (ui->page == UI_PAGE_CHANNEL) {
        fb_draw_str(ui, 16u, 2u, "CH EDIT");
        fb_draw_str(ui, 8u, 17u, "MODE");
        fb_draw_str(ui, 8u, 29u, "RATE/CC");
        fb_draw_str(ui, 8u, 41u, "SPAN");
        fb_draw_str(ui, 8u, 53u, "OFFSET");
        uint8_t row_y = (uint8_t)(15u + ui->cursor * 12u);
        for (uint8_t x = 2u; x < 126u; x++) {
            fb_set_pixel(ui, x, row_y);
            fb_set_pixel(ui, x, (uint8_t)(row_y + 9u));
        }
    } else if (ui->page == UI_PAGE_PRESET) {
        fb_draw_str(ui, 16u, 2u, "PRESET RECALL");
        fb_draw_str(ui, 8u, 22u, eng->active_preset.name);
        for (uint8_t x = 2u; x < 126u; x++) {
            fb_set_pixel(ui, x, 19u);
            fb_set_pixel(ui, x, 31u);
        }
    } else {
        fb_draw_str(ui, 16u, 2u, "SYSTEM MENU");
        fb_draw_str(ui, 8u, 17u, "MIDI CHANNEL");
        fb_draw_str(ui, 8u, 29u, "1V/OCT CALIB");
        fb_draw_str(ui, 8u, 41u, "USB FIRMWARE UPD");
        uint8_t row_y = (uint8_t)(15u + ui->cursor * 12u);
        for (uint8_t x = 2u; x < 126u; x++) {
            fb_set_pixel(ui, x, row_y);
            fb_set_pixel(ui, x, (uint8_t)(row_y + 9u));
        }
    }
    ui->dirty = true;
}

bool oled_ui_flush_one_page(oled_ui_t *ui) {
    /* Sends exactly ONE 128-byte OLED page per call (< 3.5 ms @ 400 kHz I2C, bounded timeout!) */
    uint8_t p = ui->flush_page & 0x07u;
    uint8_t cmd[4] = { 0x00u, (uint8_t)(0xB0u | p), 0x00u, 0x10u };
    if (!hal_i2c0_write_timeout(OLED_I2C_ADDR, cmd, sizeof(cmd), 1500u)) {
        return false;
    }
    uint8_t data_pkt[1u + OLED_WIDTH];
    data_pkt[0] = 0x40u;
    memcpy(&data_pkt[1], &ui->fb[(uint16_t)p * OLED_WIDTH], OLED_WIDTH);
    bool ok = hal_i2c0_write_timeout(OLED_I2C_ADDR, data_pkt, sizeof(data_pkt), 4000u);
    ui->flush_page = (uint8_t)((p + 1u) & 0x07u);
    if (ui->flush_page == 0u) {
        ui->dirty = false;
    }
    return ok;
}
