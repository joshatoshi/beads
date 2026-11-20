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
    0x20u, 0x02u, /* Page addressing mode (clean 1-page slices!) */
    0xA1u, 0xC8u,
    0xDAu, 0x12u,
    0x81u, 0xCFu,
    0xD9u, 0xF1u,
    0xDBu, 0x40u,
    0xA4u, 0xA6u,
    0xAFu  /* Display ON */
};

static const char *const MODE_NAMES[10] = {
    "BEZIER", "LFO", "EUCLID", "1V/OCT", "GATE",
    "CLKDIV", "MIDICC", "GTRENV", "PLUCK", "FS2"
};

static const char *const LFO_NAMES[6] = {
    "SINE", "TRI", "RAMP+", "RAMP-", "SQR", "S&H"
};

static const char *const SPAN_NAMES[5] = {
    "+-8V", "+-5V", "+-2.5", "0..5V", "0..8V"
};

static const char *const CLK_DIV_NAMES[8] = {
    "/1", "/3", "/6", "/12", "/24", "/48", "/72", "/96"
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

/* Zero-division integer decimal formatter (0..9999) */
static void fmt_u16(char *buf, uint16_t val, uint8_t min_digits) {
    static const uint16_t POW10[4] = { 1000u, 100u, 10u, 1u };
    uint8_t pos = 0u;
    bool started = false;
    for (uint8_t i = 0u; i < 4u; i++) {
        uint8_t d = 0u;
        while (val >= POW10[i]) {
            val = (uint16_t)(val - POW10[i]);
            d++;
        }
        uint8_t rem_digits = (uint8_t)(4u - i);
        if (d > 0u || started || rem_digits <= min_digits) {
            buf[pos++] = (char)('0' + d);
            started = true;
        }
    }
    buf[pos] = '\0';
}

static void fmt_i8_pct(char *buf, int8_t val) {
    uint8_t pos = 0u;
    uint16_t mag = 0u;
    if (val < 0) {
        buf[pos++] = '-';
        mag = (uint16_t)(-(int16_t)val);
    } else {
        buf[pos++] = '+';
        mag = (uint16_t)val;
    }
    fmt_u16(&buf[pos], mag, 1u);
    size_t len = strlen(buf);
    buf[len] = '%';
    buf[len + 1u] = '\0';
}

static void fmt_sub_mode(char *buf, const cv_channel_cfg_t *c) {
    if (c->mode == CV_MODE_LFO) {
        uint8_t w = (c->sub_mode < 6u) ? c->sub_mode : 0u;
        strcpy(buf, LFO_NAMES[w]);
    } else if (c->mode == CV_MODE_MIDI_CLOCK_DIV) {
        strcpy(buf, CLK_DIV_NAMES[c->sub_mode & 0x07u]);
    } else if (c->mode == CV_MODE_MIDI_CC) {
        buf[0] = 'C'; buf[1] = 'C';
        fmt_u16(&buf[2], (uint16_t)(c->sub_mode & 0x7Fu), 1u);
    } else if (c->mode == CV_MODE_GUITAR_ENV) {
        strcpy(buf, (c->sub_mode != 0u) ? "DUCK" : "NORM");
    } else if (c->mode == CV_MODE_MIDI_GATE_TRIG) {
        strcpy(buf, (c->sub_mode != 0u) ? "TRIG" : "GATE");
    } else if (c->mode == CV_MODE_FS2_ACTION) {
        strcpy(buf, (c->sub_mode == 1u) ? "SEED" : "FREEZE");
    } else {
        fmt_u16(buf, c->sub_mode, 1u);
    }
}

void oled_ui_init(oled_ui_t *ui) {
    memset(ui, 0, sizeof(*ui));
    memset(ui->scope_hist, 38u, sizeof(ui->scope_hist)); /* Centerline Y=38 (0.00V) on boot */
    ui->page = UI_PAGE_SCOPE;
    ui->page_dirty_mask = 0xFFu;
    ui->dirty = true;
    /* Bounded I2C timeout (1.5 ms) so absent/unplugged OLED never hangs Core 1! */
    (void)hal_i2c0_write_timeout(OLED_I2C_ADDR, OLED_INIT_SEQ, sizeof(OLED_INIT_SEQ), 1500u);
}

void oled_ui_handle_usb_cdc_line_coding(oled_ui_t *ui, uint32_t bit_rate) {
    /* Standard RP2040 1200-baud touch triggers headerless USB-C UF2 bootloader! */
    if (bit_rate == 1200u) {
        ui->usb_cdc_1200_armed = true;
        hal_reset_usb_boot(0u, 0u);
    }
}

static uint8_t sub_mode_max_for(uint8_t mode) {
    switch ((cv_mode_t)mode) {
        case CV_MODE_LFO:            return 5u;
        case CV_MODE_MIDI_CLOCK_DIV: return 7u;
        case CV_MODE_MIDI_CC:        return 127u;
        case CV_MODE_MIDI_GATE_TRIG:
        case CV_MODE_GUITAR_ENV:     return 1u;
        case CV_MODE_FS2_ACTION:     return 2u;
        default:                     return 7u;
    }
}

void oled_ui_handle_inputs(oled_ui_t *ui, int32_t enc_delta, bool enc_click, bool back_click,
                           cv_engine_t *eng, bypass_seq_t *byp, midi_router_t *midi, preset_mgr_t *pm) {
    if (enc_delta == 0 && !enc_click && !back_click) {
        return;
    }
    ui->dirty = true;

    if (back_click) {
        if (ui->editing) {
            ui->editing = false;
            if (ui->page == UI_PAGE_SYSTEM && ui->cursor == 1u) {
                hal_crit_enter();
                eng->cal_override_active = false;
                hal_crit_exit();
            }
        } else {
            ui->page = (ui->page == UI_PAGE_SCOPE) ? UI_PAGE_SYSTEM : (ui_page_t)(ui->page - 1u);
            ui->cursor = (ui->page == UI_PAGE_PRESET) ? eng->active_preset_idx : 0u;
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
                ui->editing = false;
            }
            break;

        case UI_PAGE_CHANNEL:
            if (!ui->editing) {
                if (enc_delta != 0) {
                    int32_t cur = (int32_t)ui->cursor + enc_delta;
                    if (cur < 0) cur = 0;
                    if (cur >= (int32_t)UI_CH_PARAM_COUNT) cur = (int32_t)UI_CH_PARAM_COUNT - 1;
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
                        uint8_t smax = sub_mode_max_for(c->mode);
                        if (c->sub_mode > smax) c->sub_mode = smax;
                    } else if (ui->cursor == 1u) {
                        int32_t smax = (int32_t)sub_mode_max_for(c->mode);
                        int32_t s = (int32_t)c->sub_mode + enc_delta;
                        if (s < 0) s = 0;
                        if (s > smax) s = smax;
                        c->sub_mode = (uint8_t)s;
                    } else if (ui->cursor == 2u) {
                        /* Saturate strictly to [0, 127], never & 0x7F wraparound! */
                        int32_t v = (int32_t)c->param_a + enc_delta;
                        if (v < 0) v = 0;
                        if (v > 127) v = 127;
                        c->param_a = (uint8_t)v;
                    } else if (ui->cursor == 3u) {
                        int32_t v = (int32_t)c->param_b + enc_delta;
                        if (v < 0) v = 0;
                        if (v > 127) v = 127;
                        c->param_b = (uint8_t)v;
                        uint16_t tens = (uint16_t)(4096u + ((uint32_t)c->param_b * 224u));
                        eng->ch[ui->selected_ch].bezier.tension_q15 = (tens > 32767u) ? 32767u : tens;
                    } else if (ui->cursor == 4u) {
                        int32_t s = (int32_t)c->span + enc_delta;
                        if (s < 0) s = 0;
                        if (s > (int32_t)CV_SPAN_UNI_8V) s = (int32_t)CV_SPAN_UNI_8V;
                        c->span = (uint8_t)s;
                    } else if (ui->cursor == 5u) {
                        int32_t o = (int32_t)c->offset_pct + enc_delta * 5;
                        if (o < -100) o = -100;
                        if (o > 100) o = 100;
                        c->offset_pct = (int8_t)o;
                    } else {
                        c->clock_sync = (enc_delta > 0) ? 1u : 0u;
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
                if (byp != NULL) {
                    bypass_seq_set_target(byp, pr->startup_active != 0u);
                }
                if (midi != NULL) {
                    midi_router_set_channel(midi, pr->midi_channel);
                }
                pm->live.active_preset = ui->cursor;
                preset_mgr_mark_dirty(pm);
                hal_crit_exit();
            }
            break;

        case UI_PAGE_SYSTEM:
            if (!ui->editing) {
                if (enc_delta != 0) {
                    int32_t c = (int32_t)ui->cursor + enc_delta;
                    if (c < 0) c = 0;
                    if (c > 2) c = 2; /* 0=MIDI CH, 1=1V/OCT CAL, 2=USB FIRMWARE UPDATE */
                    ui->cursor = (uint8_t)c;
                }
                if (enc_click) {
                    if (ui->cursor == 0u) {
                        ui->editing = true;
                    } else if (ui->cursor == 1u) {
                        ui->editing = true;
                        ui->cal_ch = ui->selected_ch;
                        ui->cal_oct = 2u; /* Start on C2 (0.00V) */
                        hal_crit_enter();
                        eng->cal_override_active = true;
                        eng->cal_override_ch = ui->cal_ch;
                        eng->cal_override_code = eng->cal.oct_dac[ui->cal_ch][ui->cal_oct];
                        hal_crit_exit();
                    } else if (ui->cursor == 2u) {
                        /* SYSTEM -> USB FIRMWARE UPDATE: enters RP2040 ROM UF2 Mass Storage! */
                        hal_reset_usb_boot(0u, 0u);
                    }
                }
            } else if (ui->cursor == 0u) {
                /* Interactive MIDI CHANNEL editor (0=OMNI, 1..16) */
                if (enc_delta != 0) {
                    hal_crit_enter();
                    int32_t mch = (int32_t)eng->active_preset.midi_channel + enc_delta;
                    if (mch < 0) mch = 0;
                    if (mch > 16) mch = 16;
                    eng->active_preset.midi_channel = (uint8_t)mch;
                    pm->live.presets[eng->active_preset_idx].midi_channel = (uint8_t)mch;
                    if (midi != NULL) {
                        midi_router_set_channel(midi, (uint8_t)mch);
                    }
                    preset_mgr_mark_dirty(pm);
                    hal_crit_exit();
                }
                if (enc_click) {
                    ui->editing = false;
                }
            } else if (ui->cursor == 1u) {
                /* Interactive 1V/OCT CALIB knot trimmer (click advances octave/ch, BACK exits) */
                if (enc_delta != 0) {
                    hal_crit_enter();
                    int32_t code = (int32_t)eng->cal.oct_dac[ui->cal_ch][ui->cal_oct] + enc_delta;
                    if (code < 0) code = 0;
                    if (code > 4095) code = 4095;
                    eng->cal.oct_dac[ui->cal_ch][ui->cal_oct] = (uint16_t)code;
                    pm->live.cal.oct_dac[ui->cal_ch][ui->cal_oct] = (uint16_t)code;
                    eng->cal_override_active = true;
                    eng->cal_override_ch = ui->cal_ch;
                    eng->cal_override_code = (uint16_t)code;
                    preset_mgr_mark_dirty(pm);
                    hal_crit_exit();
                }
                if (enc_click) {
                    ui->cal_oct++;
                    if (ui->cal_oct >= BEADS_CAL_OCTAVES) {
                        ui->cal_oct = 0u;
                        ui->cal_ch++;
                        if (ui->cal_ch >= BEADS_NUM_CV_CHANNELS) {
                            ui->cal_ch = 0u;
                        }
                    }
                    hal_crit_enter();
                    eng->cal_override_active = true;
                    eng->cal_override_ch = ui->cal_ch;
                    eng->cal_override_code = eng->cal.oct_dac[ui->cal_ch][ui->cal_oct];
                    hal_crit_exit();
                }
            }
            break;
    }
}

void oled_ui_render(oled_ui_t *ui, const cv_engine_t *eng, const bypass_seq_t *byp,
                    const preset_mgr_t *pm, bool usb_connected) {
    memset(ui->fb, 0, sizeof(ui->fb));

    /* Top status bar (Y = 0..11): Active/Bypass indicator + USB badge */
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
    int32_t py = 38 - ((q15 * 22) >> 15);
    if (py < 14) py = 14;
    if (py > 61) py = 61;
    ui->scope_hist[ui->scope_head] = (uint8_t)py;
    ui->scope_head = (uint8_t)((ui->scope_head + 1u) & (OLED_WIDTH - 1u));

    char buf[16];
    if (ui->page == UI_PAGE_SCOPE) {
        const cv_channel_cfg_t *c = &eng->active_preset.ch[ui->selected_ch];
        char hdr[18] = "CV1 ";
        hdr[2] = (char)('1' + ui->selected_ch);
        strcpy(&hdr[4], (c->mode < 10u) ? MODE_NAMES[c->mode] : "CV");
        fb_draw_str(ui, 16u, 2u, hdr);

        for (uint8_t x = 0u; x < OLED_WIDTH; x += 4u) {
            fb_set_pixel(ui, x, 38u);
        }
        for (uint8_t x = 0u; x < OLED_WIDTH; x++) {
            uint8_t idx = (uint8_t)((ui->scope_head + x) & (OLED_WIDTH - 1u));
            fb_set_pixel(ui, x, ui->scope_hist[idx]);
        }
        for (uint8_t ch = 0u; ch < BEADS_NUM_CV_CHANNELS; ch++) {
            uint8_t bx = (uint8_t)(ch * 16u + 1u);
            uint8_t bw = (uint8_t)((eng->ch[ch].last_out_code >> 8u) & 0x0Fu);
            for (uint8_t dx = 0u; dx < bw; dx++) {
                fb_set_pixel(ui, (uint8_t)(bx + dx), 63u);
            }
        }
    } else if (ui->page == UI_PAGE_CHANNEL) {
        const cv_channel_cfg_t *c = &eng->active_preset.ch[ui->selected_ch];
        char hdr[16] = "CH1 EDIT";
        hdr[2] = (char)('1' + ui->selected_ch);
        if (ui->editing) strcpy(&hdr[8], " *");
        fb_draw_str(ui, 16u, 2u, hdr);

        /* Scrollable 4-row window over 7 channel parameters (0..6) */
        uint8_t first_row = (ui->cursor >= 4u) ? (uint8_t)(ui->cursor - 3u) : 0u;
        for (uint8_t vis = 0u; vis < 4u; vis++) {
            uint8_t r = (uint8_t)(first_row + vis);
            if (r >= UI_CH_PARAM_COUNT) break;
            uint8_t y = (uint8_t)(17u + vis * 12u);
            const char *lbl = "";
            buf[0] = '\0';
            switch (r) {
                case 0u:
                    lbl = "MODE";
                    strcpy(buf, (c->mode < 10u) ? MODE_NAMES[c->mode] : "?");
                    break;
                case 1u:
                    lbl = "SUB";
                    fmt_sub_mode(buf, c);
                    break;
                case 2u:
                    lbl = "PAR A";
                    fmt_u16(buf, c->param_a, 1u);
                    break;
                case 3u:
                    lbl = "PAR B";
                    fmt_u16(buf, c->param_b, 1u);
                    break;
                case 4u:
                    lbl = "SPAN";
                    strcpy(buf, (c->span < 5u) ? SPAN_NAMES[c->span] : "?");
                    break;
                case 5u:
                    lbl = "OFFS";
                    fmt_i8_pct(buf, c->offset_pct);
                    break;
                default:
                    lbl = "SYNC";
                    strcpy(buf, (c->clock_sync != 0u) ? "CLK" : "FREE");
                    break;
            }
            fb_draw_str(ui, 6u, y, lbl);
            fb_draw_str(ui, 56u, y, buf);
            if (r == ui->cursor) {
                uint8_t box_y = (uint8_t)(y - 2u);
                for (uint8_t x = 2u; x < 126u; x++) {
                    fb_set_pixel(ui, x, box_y);
                    fb_set_pixel(ui, x, (uint8_t)(box_y + 9u));
                }
            }
        }
    } else if (ui->page == UI_PAGE_PRESET) {
        fb_draw_str(ui, 16u, 2u, "PRESET RECALL");
        /* Display HOVERED preset (ui->cursor) rather than active_preset! */
        const beads_preset_t *hov = (pm != NULL) ? preset_mgr_get(pm, ui->cursor) : &eng->active_preset;
        char slot_str[16];
        slot_str[0] = 'P';
        fmt_u16(&slot_str[1], ui->cursor, 2u);
        slot_str[3] = (ui->cursor == eng->active_preset_idx) ? '*' : ' ';
        slot_str[4] = '\0';
        fb_draw_str(ui, 8u, 18u, slot_str);

        char name_z[13];
        memcpy(name_z, hov->name, 12u);
        name_z[12] = '\0';
        fb_draw_str(ui, 36u, 18u, name_z);

        fb_draw_str(ui, 8u, 36u, (hov->startup_active != 0u) ? "BOOT: ACTIVE" : "BOOT: BYPASS");
        for (uint8_t x = 2u; x < 126u; x++) {
            fb_set_pixel(ui, x, 15u);
            fb_set_pixel(ui, x, 27u);
        }
    } else {
        fb_draw_str(ui, 16u, 2u, ui->editing ? "SYSTEM EDIT *" : "SYSTEM MENU");
        /* Row 0: MIDI CHANNEL + live value */
        fb_draw_str(ui, 6u, 17u, "MIDI CH");
        if (eng->active_preset.midi_channel == 0u) {
            strcpy(buf, "OMNI");
        } else {
            fmt_u16(buf, eng->active_preset.midi_channel, 2u);
        }
        fb_draw_str(ui, 72u, 17u, buf);

        /* Row 1: 1V/OCT CALIB + live channel/octave/DAC code */
        fb_draw_str(ui, 6u, 29u, "1V/OCT");
        if (ui->editing && ui->cursor == 1u) {
            buf[0] = 'C'; buf[1] = (char)('1' + ui->cal_ch);
            buf[2] = 'O'; buf[3] = (char)('0' + ui->cal_oct);
            buf[4] = ':';
            fmt_u16(&buf[5], eng->cal.oct_dac[ui->cal_ch][ui->cal_oct], 4u);
            fb_draw_str(ui, 54u, 29u, buf);
        } else {
            fb_draw_str(ui, 54u, 29u, "CALIB");
        }

        /* Row 2: USB FIRMWARE UPDATE */
        fb_draw_str(ui, 6u, 41u, "USB FW UPDATE");

        uint8_t row_y = (uint8_t)(15u + ui->cursor * 12u);
        for (uint8_t x = 2u; x < 126u; x++) {
            fb_set_pixel(ui, x, row_y);
            fb_set_pixel(ui, x, (uint8_t)(row_y + 9u));
        }
    }

    /* Compute real per-page dirty bitmask against last transmitted SSD1306 bytes (0 stack allocation!) */
    for (uint8_t p = 0u; p < OLED_PAGES; p++) {
        uint8_t bit = (uint8_t)(1u << p);
        const uint8_t *cur_p = &ui->fb[(uint16_t)p * OLED_WIDTH];
        const uint8_t *old_p = &ui->sent_fb[(uint16_t)p * OLED_WIDTH];
        if ((ui->page_sent_mask & bit) == 0u || memcmp(cur_p, old_p, OLED_WIDTH) != 0) {
            ui->page_dirty_mask |= bit;
        }
    }
    ui->dirty = (ui->page_dirty_mask != 0u);
}

bool oled_ui_flush_step(oled_ui_t *ui) {
    /* Sends AT MOST ONE <=16-pixel-byte I2C burst (~405 us @ 400 kHz, << 2.0 ms USB t_DSETADDR!) */
    if (ui->page_dirty_mask == 0u) {
        ui->dirty = false;
        ui->flush_substep = 0u;
        return true;
    }

    if (ui->flush_substep == 0u) {
        /* Advance flush_page to the next actually dirty page */
        for (uint8_t i = 0u; i < OLED_PAGES; i++) {
            uint8_t cand = (uint8_t)((ui->flush_page + i) & 0x07u);
            if ((ui->page_dirty_mask & (uint8_t)(1u << cand)) != 0u) {
                ui->flush_page = cand;
                break;
            }
        }
        uint8_t p = ui->flush_page & 0x07u;
        uint8_t cmd[4] = { 0x00u, (uint8_t)(0xB0u | p), 0x00u, 0x10u };
        if (!hal_i2c0_write_timeout(OLED_I2C_ADDR, cmd, sizeof(cmd), 600u)) {
            return false;
        }
        ui->flush_substep = 1u;
        return true;
    }

    uint8_t p = ui->flush_page & 0x07u;
    uint8_t chunk_idx = (uint8_t)(ui->flush_substep - 1u);
    if (chunk_idx >= OLED_CHUNKS_PER_PAGE) {
        ui->flush_substep = 0u;
        return true;
    }

    uint16_t off = (uint16_t)p * OLED_WIDTH + (uint16_t)chunk_idx * OLED_I2C_CHUNK_BYTES;
    uint8_t pkt[1u + OLED_I2C_CHUNK_BYTES];
    pkt[0] = 0x40u;
    memcpy(&pkt[1], &ui->fb[off], OLED_I2C_CHUNK_BYTES);
    bool ok = hal_i2c0_write_timeout(OLED_I2C_ADDR, pkt, sizeof(pkt), 700u);
    if (ok) {
        memcpy(&ui->sent_fb[off], &pkt[1], OLED_I2C_CHUNK_BYTES);
    }
    ui->flush_substep++;
    if (ui->flush_substep > OLED_CHUNKS_PER_PAGE) {
        ui->flush_substep = 0u;
        uint8_t bit = (uint8_t)(1u << p);
        if (ok) {
            ui->page_sent_mask |= bit;
            /* Re-verify whether ui->fb[p] mutated again mid-page before clearing dirty bit */
            if (memcmp(&ui->fb[(uint16_t)p * OLED_WIDTH], &ui->sent_fb[(uint16_t)p * OLED_WIDTH], OLED_WIDTH) == 0) {
                ui->page_dirty_mask &= (uint8_t)~bit;
            }
        }
        ui->flush_page = (uint8_t)((p + 1u) & 0x07u);
        if (ui->page_dirty_mask == 0u) {
            ui->dirty = false;
        }
    }
    return ok;
}

bool oled_ui_flush_one_page(oled_ui_t *ui) {
    /* Convenience wrapper that flushes 1 dirty page in <=16-byte chunks while servicing USB between chunks */
    if (ui->page_dirty_mask == 0u) {
        ui->dirty = false;
        return true;
    }
    bool all_ok = true;
    for (uint8_t step = 0u; step < (1u + OLED_CHUNKS_PER_PAGE); step++) {
        if (hal_usb_ep0_is_busy()) {
            break;
        }
        if (!oled_ui_flush_step(ui)) {
            all_ok = false;
            break;
        }
        hal_usb_task_on_core1();
        if (ui->flush_substep == 0u) {
            break;
        }
    }
    return all_ok;
}
