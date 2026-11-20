#include <assert.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "board_pins.h"
#include "hal.h"
#include "bezier_drift.h"
#include "bypass_sequencer.h"
#include "cv_engine.h"
#include "dac_mcp4822.h"
#include "midi_router.h"
#include "oled_ui.h"
#include "presets.h"
#include "usb_ep0.h"

/* ============================================================================
 * Silicon-Honest Host HAL Mock (no masked bugs, models Flash sectors, GPIO,
 * SPI0 MCP4822 words, PL011 UART0 FIFO + error flags, SAR ADC, I2C0 OLED,
 * and RP2040 USB ROM reset_usb_boot!)
 * ============================================================================ */
static uint32_t g_now_us = 0u;
static bool     g_gpio_in[32];
static bool     g_gpio_out[32];
static uint16_t g_last_spi_word[4];
static uint32_t g_spi_writes = 0u;
static uint16_t g_adc_val[4];
static uint32_t g_uart_rsr_clears = 0u;
static uint16_t g_uart_hw_fifo[64];
static uint32_t g_uart_hw_head = 0u;
static uint32_t g_uart_hw_tail = 0u;
static uint8_t  g_flash_slots[2][4096];
static uint32_t g_flash_writes = 0u;
static uint32_t g_i2c_writes = 0u;
static bool     g_usb_boot_called = false;
static bool     g_spi_pwr_safe_enabled = false;
static int      g_crit_depth = 0;

void hal_init(void) {
    memset(g_gpio_in, 0, sizeof(g_gpio_in));
    memset(g_gpio_out, 0, sizeof(g_gpio_out));
    memset(g_last_spi_word, 0, sizeof(g_last_spi_word));
    g_spi_writes = 0u;
    g_uart_rsr_clears = 0u;
    g_uart_hw_head = g_uart_hw_tail = 0u;
    g_i2c_writes = 0u;
    g_usb_boot_called = false;
    /* Active-low switches rest HIGH when released */
    g_gpio_in[PIN_ENC_A] = true;
    g_gpio_in[PIN_ENC_B] = true;
    g_gpio_in[PIN_ENC_SW] = true;
    g_gpio_in[PIN_BTN_BACK] = true;
    g_gpio_in[PIN_FS1_BYPASS_SW] = true;
    g_gpio_in[PIN_FS2_ACTION_SW] = true;
    g_gpio_in[PIN_PEDAL_PWR_GOOD] = true;
    g_gpio_in[PIN_VBUS_DET] = false;
}

uint32_t hal_time_us_32(void) { return g_now_us; }
void hal_gpio_write(uint32_t pin, bool level) { assert(pin < 32u); g_gpio_out[pin] = level; }
bool hal_gpio_read(uint32_t pin) { assert(pin < 32u); return g_gpio_in[pin]; }

void hal_spi_dac_write16(uint8_t dac_idx, uint16_t word) {
    assert(dac_idx < 4u);
    g_last_spi_word[dac_idx] = word;
    g_spi_writes++;
}

void hal_spi_dac_set_power_safe(bool pedal_pwr_good) {
    g_spi_pwr_safe_enabled = pedal_pwr_good;
}

uint16_t hal_adc_read_ch(uint8_t adc_ch) {
    assert(adc_ch < 4u);
    return g_adc_val[adc_ch];
}

bool hal_uart0_try_read_dr(uint16_t *out_dr) {
    if (g_uart_hw_tail == g_uart_hw_head) return false;
    *out_dr = g_uart_hw_fifo[g_uart_hw_tail];
    g_uart_hw_tail = (g_uart_hw_tail + 1u) & 63u;
    return true;
}

void hal_uart0_clear_rsr(void) { g_uart_rsr_clears++; }

bool hal_i2c0_write_timeout(uint8_t addr7, const uint8_t *buf, size_t len, uint32_t timeout_us) {
    assert(addr7 == OLED_I2C_ADDR);
    assert(buf != NULL && len > 0u && timeout_us > 0u);
    g_i2c_writes++;
    return true;
}

bool hal_flash_read(uint32_t slot_idx, void *dst, size_t len) {
    assert(slot_idx < 2u && len <= 4096u);
    memcpy(dst, g_flash_slots[slot_idx], len);
    return true;
}

bool hal_flash_erase_and_program(uint32_t slot_idx, const void *src, size_t len) {
    assert(slot_idx < 2u && len <= 4096u);
    memset(g_flash_slots[slot_idx], 0xFF, 4096u);
    memcpy(g_flash_slots[slot_idx], src, len);
    g_flash_writes++;
    return true;
}

void hal_crit_enter(void) {
    /* Non-recursive spinlock assertion! Catches re-entrant lock bugs immediately! */
    assert(g_crit_depth == 0);
    g_crit_depth++;
}

void hal_crit_exit(void) {
    assert(g_crit_depth == 1);
    g_crit_depth--;
}

void hal_reset_usb_boot(uint32_t m1, uint32_t m2) {
    (void)m1; (void)m2;
    g_usb_boot_called = true;
}

void hal_usb_init_on_core1(void) {}
void hal_usb_task_on_core1(void) {}
bool hal_usb_midi_read_packet(uint8_t pkt4[4]) { (void)pkt4; return false; }

/* ============================================================================
 * TEST 1: 250 ms POR Blanking + Brownout Latch-Hold + 15.0 ms PhotoMOS Popless
 * Bypass + EQD Flexi-Switch Auto-Momentary
 * ============================================================================ */
static void test_bypass_por_photomos_and_flexi(void) {
    hal_init();
    bypass_seq_t seq;
    bypass_seq_init(&seq, true);

    /* Initial boot state: relay OFF, PhotoMOS MUTED, por_blank_ticks == 500 */
    assert(seq.state == BYP_STATE_POR_BLANK);
    assert(!g_gpio_out[PIN_RELAY_BYPASS_EN]);
    assert(g_gpio_out[PIN_PHOTOMOS_MUTE_EN]);

    /* Sustained undervoltage / USB-C bench mode: por_blank_ticks MUST stay latched at 500! */
    for (int i = 0; i < 100; i++) {
        bypass_seq_tick_2khz(&seq, false, false);
        assert(seq.por_blank_ticks == BYP_POR_BLANK_TICKS);
        assert(!g_gpio_out[PIN_RELAY_BYPASS_EN]);
        assert(g_gpio_out[PIN_PHOTOMOS_MUTE_EN]);
    }

    /* Power stabilizes: ticks 1..479 must stay muted & bypassed */
    for (int t = 1; t < 480; t++) {
        bypass_seq_tick_2khz(&seq, true, false);
        assert(g_gpio_out[PIN_PHOTOMOS_MUTE_EN]);
        assert(!g_gpio_out[PIN_RELAY_BYPASS_EN]);
    }
    /* Tick 480 (240.0 ms): relay switches to startup_active=true WHILE STILL MUTED! */
    bypass_seq_tick_2khz(&seq, true, false);
    assert(g_gpio_out[PIN_RELAY_BYPASS_EN]);
    assert(g_gpio_out[PIN_PHOTOMOS_MUTE_EN]);
    assert(seq.snap_cv_now);

    /* Ticks 481..499: stay muted while relay settles */
    for (int t = 481; t < 500; t++) {
        bypass_seq_tick_2khz(&seq, true, false);
        assert(g_gpio_out[PIN_PHOTOMOS_MUTE_EN]);
    }
    /* Tick 500 (250.0 ms exact): PhotoMOS unmutes, IDLE reached! */
    bypass_seq_tick_2khz(&seq, true, false);
    assert(!g_gpio_out[PIN_PHOTOMOS_MUTE_EN]);
    assert(bypass_seq_is_idle(&seq));

    /* Exact 15.0 ms (30-tick) Runtime Popless Bypass Transition (Active -> Bypass) */
    bypass_seq_set_target(&seq, false);
    /* Tick 1..7 (3.5 ms): BYP_STATE_MUTING, relay still ON, PhotoMOS ON */
    for (int t = 1; t <= 7; t++) {
        bypass_seq_tick_2khz(&seq, true, false);
        assert(seq.state == BYP_STATE_MUTING);
        assert(g_gpio_out[PIN_PHOTOMOS_MUTE_EN]);
        assert(g_gpio_out[PIN_RELAY_BYPASS_EN]);
    }
    /* Tick 8..23 (8.0 ms): BYP_STATE_SWITCHING, relay flips OFF at tick 8 while muted! */
    for (int t = 8; t <= 23; t++) {
        bypass_seq_tick_2khz(&seq, true, false);
        assert(seq.state == BYP_STATE_SWITCHING);
        assert(g_gpio_out[PIN_PHOTOMOS_MUTE_EN]);
        assert(!g_gpio_out[PIN_RELAY_BYPASS_EN]);
        if (t == 8) assert(seq.snap_cv_now);
    }
    /* Tick 24..30 (3.5 ms): BYP_STATE_UNMUTING, PhotoMOS OFF */
    for (int t = 24; t <= 30; t++) {
        bypass_seq_tick_2khz(&seq, true, false);
        assert(seq.state == BYP_STATE_UNMUTING);
        assert(!g_gpio_out[PIN_PHOTOMOS_MUTE_EN]);
    }
    /* Tick 31: returns cleanly to BYP_STATE_IDLE! */
    bypass_seq_tick_2khz(&seq, true, false);
    assert(bypass_seq_is_idle(&seq));

    /* EQD Flexi-Switch Test A: Short tap (< 300 ms = 200 ticks) -> LATCHES ON */
    assert(!seq.target_active);
    for (int t = 0; t < 200; t++) bypass_seq_tick_2khz(&seq, true, true);
    assert(seq.target_active);
    for (int t = 0; t < 60; t++) bypass_seq_tick_2khz(&seq, true, false);
    assert(seq.target_active && seq.current_active && bypass_seq_is_idle(&seq));

    /* EQD Flexi-Switch Test B: Long hold (>= 350 ms = 800 ticks) -> AUTO-MOMENTARY reverts on release! */
    for (int t = 0; t < 800; t++) bypass_seq_tick_2khz(&seq, true, true);
    assert(!seq.target_active && !seq.current_active); /* Bypassed while held */
    for (int t = 0; t < 80; t++) bypass_seq_tick_2khz(&seq, true, false);
    assert(seq.target_active && seq.current_active && bypass_seq_is_idle(&seq)); /* Reverted back Active! */

    /* Mid-operation brownout immediately forces passive bypass & re-arms 250 ms blanking */
    bypass_seq_tick_2khz(&seq, false, false);
    assert(!g_gpio_out[PIN_RELAY_BYPASS_EN]);
    assert(g_gpio_out[PIN_PHOTOMOS_MUTE_EN]);
    assert(seq.por_blank_ticks == BYP_POR_BLANK_TICKS);
    printf("[PASS] Test 1: 250ms POR/brownout blanking + 15.0ms PhotoMOS mute + EQD Flexi-Switch\n");
}

/* ============================================================================
 * TEST 2: C1-Continuous Cubic Bezier Drift Continuity Across 20 Segment Wraps
 * ============================================================================ */
static void test_bezier_c1_continuity(void) {
    bezier_drift_t b;
    bezier_drift_init(&b, 0xDEADBEEFu, 24576u);
    const uint32_t inc = 0x01000000u; /* 256 steps per segment */
    int32_t prev_y = bezier_drift_eval_q15(&b, 0u);
    int32_t prev_dy = 0;
    int32_t min_y = 32767, max_y = -32767;
    int wraps = 0;

    for (int step = 0; step < 256 * 20; step++) {
        uint32_t p_before = b.phase_q32;
        int32_t y = bezier_drift_step(&b, inc);
        assert(y >= -32767 && y <= 32767);
        if (y < min_y) min_y = y;
        if (y > max_y) max_y = y;
        int32_t dy = y - prev_y;
        if (b.phase_q32 < p_before) {
            /* Segment boundary crossed: verify C0 (small jump) & C1 (smooth slope match)! */
            assert(abs(dy) < 500);          /* Smooth C0 position continuity */
            assert(abs(dy - prev_dy) < 120); /* Smooth C1 derivative continuity across boundary! */
            wraps++;
        }
        prev_y = y;
        prev_dy = dy;
    }
    assert(wraps >= 19);
    assert(max_y > 10000 && min_y < -10000);
    printf("[PASS] Test 2: Cubic Bezier C0/C1 continuity verified across %d wraps (range [%d, %d])\n", wraps, min_y, max_y);
}

/* ============================================================================
 * TEST 3: Full-Table 256-Entry LFO Symmetry + Euclidean Rhythm + Deadband-Free EMA
 * ============================================================================ */
static void test_lfo_euclidean_and_ema(void) {
    int32_t sum = 0;
    for (int k = 0; k < 256; k++) {
        assert(BEADS_SINE_LUT_256[k] == -BEADS_SINE_LUT_256[255 - k]);
        if (k < 64) {
            assert(BEADS_SINE_LUT_256[k] == BEADS_SINE_LUT_256[127 - k]);
        }
        sum += BEADS_SINE_LUT_256[k];
    }
    assert(sum == 0); /* Exact zero DC bias */

    /* Triangle symmetry */
    assert(cv_engine_eval_lfo_q15(LFO_WAVE_TRI, 0x00000000u, 0) == 0);
    assert(cv_engine_eval_lfo_q15(LFO_WAVE_TRI, 0x40000000u, 0) == 32767);
    assert(cv_engine_eval_lfo_q15(LFO_WAVE_TRI, 0xC0000000u, 0) == -32767);

    /* Euclidean (16 steps, 5 hits) must produce exactly 5 evenly distributed hits! */
    int hits = 0;
    for (uint8_t s = 0u; s < 16u; s++) {
        if (cv_engine_euclidean_hit(s, 16u, 5u)) hits++;
    }
    assert(hits == 5);

    /* Deadband-free fixed-point EMA MUST reach exact 4095 and exact 0 (never stall at 4080!) */
    int32_t cur = 0;
    for (int i = 0; i < 400; i++) cur = cv_engine_ema_step_deadband_free(cur, 4095, 4u);
    assert(cur == 4095);
    for (int i = 0; i < 400; i++) cur = cv_engine_ema_step_deadband_free(cur, 0, 4u);
    assert(cur == 0);
    printf("[PASS] Test 3: Full-table 256-pt LFO symmetry (sum=0), Euclidean(16,5)=5 hits, deadband-free EMA\n");
}

/* ============================================================================
 * TEST 4: 9-Octave 1V/Oct Calibration LUT Accuracy + Delta-Gated 0xFFFF DAC
 * ============================================================================ */
static void test_1voct_lut_and_dac(void) {
    hal_init();
    beads_nvm_block_t blk;
    preset_mgr_load_factory_defaults(&blk);

    /* Exact knot round-trip across all 9 octaves on all 8 channels + strict monotonicity */
    for (uint8_t ch = 0u; ch < BEADS_NUM_CV_CHANNELS; ch++) {
        uint16_t prev = 0u;
        for (uint8_t note = 0u; note <= 108u; note++) {
            uint16_t code = cv_engine_note_to_dac_1voct(&blk.cal, ch, note, 0);
            if (note > 0u) assert(code > prev);
            if ((note % 12u) == 0u) {
                uint8_t oct = note / 12u;
                assert(code == blk.cal.oct_dac[ch][oct]);
            }
            prev = code;
        }
        /* Check +-2 semitone pitch bend symmetry around C4 (note 48) */
        uint16_t c4   = cv_engine_note_to_dac_1voct(&blk.cal, ch, 48u, 0);
        uint16_t d4   = cv_engine_note_to_dac_1voct(&blk.cal, ch, 50u, 0);
        uint16_t c4up = cv_engine_note_to_dac_1voct(&blk.cal, ch, 48u, 8191);
        assert(abs((int)c4up - (int)d4) <= 1);
        uint16_t bb3  = cv_engine_note_to_dac_1voct(&blk.cal, ch, 46u, 0);
        uint16_t c4dn = cv_engine_note_to_dac_1voct(&blk.cal, ch, 48u, -8192);
        assert(abs((int)c4dn - (int)bb3) <= 1);
        (void)c4;
    }

    /* Delta-gated 0xFFFF MCP4822 driver: code 255 MUST NOT collide with sentinel; steady-state skips SPI! */
    dac_bank_t d;
    dac_bank_init(&d);
    assert(!dac_bank_write_ch(&d, 0u, 255u)); /* Disabled during POR */
    dac_bank_set_enabled(&d, true);
    assert(dac_bank_write_ch(&d, 0u, 255u));  /* Must write 255! */
    assert(d.spi_write_count == 1u);
    assert(!dac_bank_write_ch(&d, 0u, 255u)); /* Steady-state delta gate skips SPI! */
    assert(d.spi_write_count == 1u);
    assert(dac_bank_write_ch(&d, 1u, 4095u));
    assert(g_last_spi_word[0] == ((1u << 15u) | (1u << 12u) | 4095u)); /* Ch B, 2x gain, active */
    printf("[PASS] Test 4: 9-octave 1V/Oct LUT (<=1 LSB pitch-bend) + 0xFFFF delta-gated MCP4822 SPI\n");
}

/* ============================================================================
 * TEST 5: MIDI Parser, PL011 Error/Overflow Recovery, 0xFF Reset & USB CIN=0x0F
 * ============================================================================ */
static void test_midi_router_and_recovery(void) {
    hal_init();
    midi_router_t mr;
    midi_router_init(&mr, 0u);

    /* Running Status Note On -> Note On */
    midi_router_feed_uart_byte(&mr, 0x90u, false, 1000u, 1u);
    midi_router_feed_uart_byte(&mr, 64u, false, 1100u, 1u);
    midi_router_feed_uart_byte(&mr, 100u, false, 1200u, 1u);
    assert(mr.active_note == 64u && mr.gate_high);

    /* Running Status second note without status byte */
    midi_router_feed_uart_byte(&mr, 67u, false, 1300u, 2u);
    midi_router_feed_uart_byte(&mr, 110u, false, 1400u, 2u);
    assert(mr.active_note == 67u && mr.active_vel == 110u);

    /* USB-MIDI single-byte CIN=0x0F (<0xF8) MUST NOT clobber UART Running Status! */
    uint8_t usb_cin_f[4] = { 0x0Fu, 0x55u, 0x00u, 0x00u };
    midi_router_feed_usb_packet(&mr, usb_cin_f, 1500u, 2u);
    assert(mr.uart_parser.status == 0x90u);

    /* Real-time MIDI Clock (0xF8) MUST NOT refresh last_non_rt_ms (Flash silence guard!) */
    uint32_t saved_non_rt = mr.last_non_rt_ms;
    midi_router_feed_uart_byte(&mr, 0xF8u, false, 20000u, 500u);
    assert(mr.clock_pulse && mr.last_non_rt_ms == saved_non_rt);

    /* 0xFF System Reset MUST clear Running Status & release gate! */
    midi_router_feed_uart_byte(&mr, 0xFFu, false, 21000u, 501u);
    assert(mr.uart_parser.status == 0u && !mr.gate_high);

    /* PL011 UARTDR[11:8] framing/overrun error clears UARTRSR & marks next byte with in-band overflow! */
    midi_router_feed_uart_byte(&mr, 0x90u, false, 22000u, 502u); /* Prime running status */
    assert(mr.uart_parser.status == 0x90u);
    midi_router_uart_push_dr(&mr, 0x0100u | 0x40u); /* FE bit set! */
    assert(g_uart_rsr_clears == 1u);
    midi_router_uart_push_dr(&mr, 72u);             /* Next data byte arrives with in-band OVF flag */
    midi_router_poll_core0(&mr, 23000u, 503u);
    assert(mr.uart_parser.status == 0u);            /* Running Status reset! */
    assert(mr.active_note == 67u);                  /* Orphaned data byte ignored safely! */

    /* USB-MIDI CC #102 Bypass & PC #3 Preset Recall */
    uint8_t usb_cc[4] = { 0x0Bu, 0xB0u, 102u, 127u };
    midi_router_feed_usb_packet(&mr, usb_cc, 24000u, 504u);
    assert(mr.bypass_req_valid && mr.bypass_req_active);
    uint8_t usb_pc[4] = { 0x0Cu, 0xC0u, 3u, 0u };
    midi_router_feed_usb_packet(&mr, usb_pc, 25000u, 505u);
    assert(mr.preset_req_valid && mr.preset_req_idx == 3u);
    printf("[PASS] Test 5: MIDI Running-Status, PL011 error/OVF, 0xFF reset, USB CIN=0x0F, CC102/PC\n");
}

/* ============================================================================
 * TEST 6: Dual-Slot A/B CRC32 + write_seq QSPI Flash Persistence + OLED UF2 Boot
 * ============================================================================ */
static void test_flash_ab_crc32_and_oled_uf2(void) {
    hal_init();
    memset(g_flash_slots, 0xFF, sizeof(g_flash_slots));
    g_flash_writes = 0u;

    preset_mgr_t pm;
    preset_mgr_init(&pm);
    assert(pm.last_write_seq == 1u);

    /* Mutate preset 0 and mark dirty */
    pm.live.presets[0].ch[0].param_a = 77u;
    preset_mgr_mark_dirty(&pm);

    /* Must REFUSE flash write during active bypass transition or < 300 ms MIDI silence! */
    assert(!preset_mgr_save_if_safe(&pm, false, 1000u, 0u));   /* Bypass NOT idle */
    assert(!preset_mgr_save_if_safe(&pm, true,  1000u, 800u)); /* Only 200 ms MIDI silence */
    assert(g_flash_writes == 0u && pm.dirty);

    /* Succeeds once BYP_STATE_IDLE & >= 300 ms silence -> writes Slot 0 (write_seq=2) */
    assert(preset_mgr_save_if_safe(&pm, true, 1000u, 600u));
    assert(g_flash_writes == 1u && pm.last_write_seq == 2u && !pm.dirty);

    /* Second save -> writes Slot 1 (write_seq=3) */
    pm.live.presets[0].ch[0].param_a = 99u;
    preset_mgr_mark_dirty(&pm);
    assert(preset_mgr_save_if_safe(&pm, true, 2000u, 600u));
    assert(g_flash_writes == 2u && pm.last_write_seq == 3u);

    /* Reboot test A: Both slots valid -> MUST pick newer Slot 1 (param_a=99) & restore write_seq=3! */
    preset_mgr_t pm2;
    preset_mgr_init(&pm2);
    assert(pm2.live.presets[0].ch[0].param_a == 99u);
    assert(pm2.last_write_seq == 3u);

    /* Reboot test B: Corrupt 1 bit in Slot 1 -> MUST fail CRC32 and fall back cleanly to Slot 0 (param_a=77, seq=2)! */
    g_flash_slots[1][100] ^= 0x04u;
    preset_mgr_t pm3;
    preset_mgr_init(&pm3);
    assert(pm3.live.presets[0].ch[0].param_a == 77u);
    assert(pm3.last_write_seq == 2u);

    /* 16-state Gray-code Encoder LUT test (Alps EC11E15244G1: 30 detents / 15 PPR = 2 edges/detent!) */
    uint8_t prev_ab = 0u;
    int8_t sub = 0;
    const uint8_t cw_seq[4] = { 2u, 3u, 1u, 0u };
    int sum_cw = 0;
    for (int i = 0; i < 2; i++) sum_cw += cv_engine_decode_encoder_step(&prev_ab, &sub, cw_seq[i]);
    assert(sum_cw == 1); /* 1 detent = 2 quadrature edges */
    for (int i = 2; i < 4; i++) sum_cw += cv_engine_decode_encoder_step(&prev_ab, &sub, cw_seq[i]);
    assert(sum_cw == 2); /* Full 4-edge electrical cycle = 2 mechanical detents on 15 PPR / 30 detent EC11E! */
    const uint8_t ccw_seq[2] = { 1u, 3u };
    int sum_ccw = 0;
    for (int i = 0; i < 2; i++) sum_ccw += cv_engine_decode_encoder_step(&prev_ab, &sub, ccw_seq[i]);
    assert(sum_ccw == -1);

    /* OLED SYSTEM -> USB FIRMWARE UPDATE & 1200-baud CDC UF2 Boot Trigger */
    oled_ui_t ui;
    oled_ui_init(&ui);
    cv_engine_t eng;
    bypass_seq_t byp;
    midi_router_t mr;
    bypass_seq_init(&byp, true);
    midi_router_init(&mr, 0u);
    cv_engine_init(&eng, preset_mgr_get(&pm3, 0u), 0u, &pm3.live.cal);
    assert(!g_usb_boot_called);
    oled_ui_handle_inputs(&ui, 0, false, true, &eng, &byp, &mr, &pm3); /* BACK from SCOPE -> SYSTEM */
    assert(ui.page == UI_PAGE_SYSTEM);
    oled_ui_handle_inputs(&ui, 2, true, false, &eng, &byp, &mr, &pm3); /* Cursor=2 (USB FIRMWARE UPDATE) + click */
    assert(g_usb_boot_called);

    g_usb_boot_called = false;
    oled_ui_handle_usb_cdc_line_coding(&ui, 1200u);
    assert(g_usb_boot_called);
    printf("[PASS] Test 6: Dual-slot A/B CRC32+write_seq Flash, 16-state EC11E +-2 detent LUT, OLED & 1200-baud UF2 boot\n");
}

/* Forward declarations of integrated dual-core entry hooks in main.c */
extern void beads_app_init(void);
extern void beads_core0_tick_handler(void);
extern void beads_core1_service_slice(uint32_t now_ms);

/* ============================================================================
 * TEST 7: Full Integrated Core 0 (2kHz) + Core 1 Loop (FS2 Freeze/Tap, ADC0
 * Guitar Envelope & dE/dt Pluck, PEAK LED, SSD1306 8-page flush, Non-Recursive Lock)
 * ============================================================================ */
static void test_integrated_dual_core_engine(void) {
    memset(g_flash_slots, 0xFF, sizeof(g_flash_slots));
    g_now_us = 1000u;
    beads_app_init();

    /* Run 510 ticks @ 500 us (255 ms) -> clears 250 ms POR, enables DACs, enters Active */
    for (int t = 0; t < 510; t++) {
        g_now_us += CORE0_TICK_US;
        beads_core0_tick_handler();
    }
    assert(g_gpio_out[PIN_RELAY_BYPASS_EN]);
    assert(!g_gpio_out[PIN_PHOTOMOS_MUTE_EN]);
    assert(g_spi_writes >= BEADS_NUM_CV_CHANNELS);

    /* Guitar pluck spike on ADC0: triggers PEAK LED (>3680) & pluck detector! */
    g_adc_val[ADC_CH_GTR_ENV] = 3900u;
    g_now_us += CORE0_TICK_US;
    beads_core0_tick_handler();
    assert(g_gpio_out[PIN_LED_AUDIO_PEAK]);
    g_adc_val[ADC_CH_GTR_ENV] = 0u;
    g_now_us += CORE0_TICK_US;
    beads_core0_tick_handler();
    assert(!g_gpio_out[PIN_LED_AUDIO_PEAK]);

    /* FS2 Long Hold (>=350ms = 750 ticks): latches FREEZE LED ON */
    g_gpio_in[PIN_FS2_ACTION_SW] = false; /* Active-low pressed */
    for (int t = 0; t < 750; t++) {
        g_now_us += CORE0_TICK_US;
        beads_core0_tick_handler();
    }
    assert(g_gpio_out[PIN_LED_FS2_STATUS]);
    g_gpio_in[PIN_FS2_ACTION_SW] = true;
    for (int t = 0; t < 40; t++) {
        g_now_us += CORE0_TICK_US;
        beads_core0_tick_handler();
    }
    assert(g_gpio_out[PIN_LED_FS2_STATUS]); /* Stays latched after release! */

    /* Exercise Core 1 OLED 8-page flush + USB task + idle Flash poll */
    uint32_t i2c_before = g_i2c_writes;
    for (uint32_t page = 0u; page < OLED_PAGES; page++) {
        beads_core1_service_slice(1000u + page * 10u);
    }
    assert(g_i2c_writes >= i2c_before + OLED_PAGES * 2u);
    assert(g_spi_pwr_safe_enabled);
    printf("[PASS] Test 7: Integrated Dual-Core Core0(2kHz)+Core1 loop (POR, ADC0 pluck/PEAK, FS2 Freeze, OLED)\n");
}

/* ============================================================================
 * TEST 8: Composite USB-MIDI + CDC-ACM Descriptor Audit & Multi-Packet EP0 IN
 * ============================================================================ */
typedef struct {
    uint8_t  rx_stream[256];
    uint16_t rx_total;
    uint8_t  pkt_lens[8];
    uint8_t  pkt_pids[8];
    uint8_t  pkt_count;
    bool     rx_armed;
    uint16_t rx_arm_len;
    bool     stalled;
    uint8_t  addr;
    uint8_t  cfg;
    bool     reset_1200_fired;
} mock_usb_hw_t;

static void m_ep0_tx(void *ctx, const uint8_t *data, uint16_t len, uint8_t pid) {
    mock_usb_hw_t *m = (mock_usb_hw_t *)ctx;
    assert(len <= BEADS_USB_EP0_MAX_PKT);
    assert(m->pkt_count < 8u);
    m->pkt_lens[m->pkt_count] = (uint8_t)len;
    m->pkt_pids[m->pkt_count] = pid;
    m->pkt_count++;
    if (data != NULL && len > 0u) {
        assert((uint32_t)m->rx_total + len <= sizeof(m->rx_stream));
        memcpy(&m->rx_stream[m->rx_total], data, len);
        m->rx_total = (uint16_t)(m->rx_total + len);
    }
}
static void m_ep0_rx_arm(void *ctx, uint16_t max_len, uint8_t pid) {
    mock_usb_hw_t *m = (mock_usb_hw_t *)ctx;
    (void)pid;
    m->rx_armed = true;
    m->rx_arm_len = max_len;
}
static void m_ep0_stall(void *ctx) { ((mock_usb_hw_t *)ctx)->stalled = true; }
static void m_set_addr(void *ctx, uint8_t a) { ((mock_usb_hw_t *)ctx)->addr = a; }
static void m_on_cfg(void *ctx, uint8_t c) { ((mock_usb_hw_t *)ctx)->cfg = c; }
static void m_on_1200(void *ctx) { ((mock_usb_hw_t *)ctx)->reset_1200_fired = true; }

static void test_usb_descriptors_and_multipacket_ep0(void) {
    /* 1. Structural byte-walk of BEADS_USB_CFG_DESC: verify exact wTotalLength, IADs, MIDI & CDC IF0..IF3 */
    uint16_t wTotal = (uint16_t)BEADS_USB_CFG_DESC[2] | ((uint16_t)BEADS_USB_CFG_DESC[3] << 8u);
    assert(wTotal == sizeof(BEADS_USB_CFG_DESC));
    assert(BEADS_USB_CFG_DESC[4] == 4u); /* 4 interfaces: IF0 AC, IF1 MS, IF2 CDC Comm, IF3 CDC Data */

    size_t off = 0u;
    int iad_count = 0, if_count = 0, ep_count = 0;
    bool saw_cdc_union_5b = false, saw_ms_hdr = false, saw_cdc_data_if3 = false;
    while (off < sizeof(BEADS_USB_CFG_DESC)) {
        uint8_t blen = BEADS_USB_CFG_DESC[off];
        uint8_t btype = BEADS_USB_CFG_DESC[off + 1u];
        assert(blen >= 2u && (off + blen) <= sizeof(BEADS_USB_CFG_DESC));
        if (btype == 0x0Bu) {
            assert(blen == 8u);
            iad_count++;
        } else if (btype == 0x04u) {
            assert(blen == 9u);
            if_count++;
            if (BEADS_USB_CFG_DESC[off + 2u] == 3u && BEADS_USB_CFG_DESC[off + 5u] == 0x0Au) {
                saw_cdc_data_if3 = true;
            }
        } else if (btype == 0x05u) {
            ep_count++;
        } else if (btype == 0x24u && blen == 7u && BEADS_USB_CFG_DESC[off + 2u] == 0x01u) {
            /* CS MS Header wTotalLength must equal 7+6+9+9+5 = 36 */
            uint16_t ms_tot = (uint16_t)BEADS_USB_CFG_DESC[off + 5u] | ((uint16_t)BEADS_USB_CFG_DESC[off + 6u] << 8u);
            assert(ms_tot == 36u);
            saw_ms_hdr = true;
        } else if (btype == 0x24u && BEADS_USB_CFG_DESC[off + 2u] == 0x06u) {
            /* CDC Union MUST be 5 bytes (Master=2, Slave=3) */
            assert(blen == 5u && BEADS_USB_CFG_DESC[off + 3u] == 2u && BEADS_USB_CFG_DESC[off + 4u] == 3u);
            saw_cdc_union_5b = true;
        }
        off += blen;
    }
    assert(off == sizeof(BEADS_USB_CFG_DESC));
    assert(iad_count == 2 && if_count == 4 && ep_count == 4);
    assert(saw_ms_hdr && saw_cdc_union_5b && saw_cdc_data_if3);

    /* 2. Multi-packet EP0 IN continuation for full 146-byte GET_DESCRIPTOR(Config, wLength=255) */
    usb_ep0_state_t st;
    usb_ep0_init(&st);
    mock_usb_hw_t m;
    memset(&m, 0, sizeof(m));
    usb_ep0_hw_t hw = { m_ep0_tx, m_ep0_rx_arm, m_ep0_stall, m_set_addr, m_on_cfg, m_on_1200, &m };

    uint8_t setup_cfg[8] = { 0x80u, 0x06u, 0x00u, 0x02u, 0x00u, 0x00u, 0xFFu, 0x00u };
    usb_ep0_handle_setup(&st, setup_cfg, &hw);
    assert(m.pkt_count == 1u && m.pkt_lens[0] == 64u && m.pkt_pids[0] == 1u);
    assert(st.tx_active);
    usb_ep0_on_in_complete(&st, &hw); /* Chunk 2: 64 B, DATA0 */
    assert(m.pkt_count == 2u && m.pkt_lens[1] == 64u && m.pkt_pids[1] == 0u);
    assert(st.tx_active);
    usb_ep0_on_in_complete(&st, &hw); /* Chunk 3: 18 B, DATA1 -> arms OUT status ZLP */
    assert(m.pkt_count == 3u && m.pkt_lens[2] == 18u && m.pkt_pids[2] == 1u);
    assert(!st.tx_active && m.rx_armed);
    assert(m.rx_total == sizeof(BEADS_USB_CFG_DESC));
    assert(memcmp(m.rx_stream, BEADS_USB_CFG_DESC, sizeof(BEADS_USB_CFG_DESC)) == 0);

    /* 3. Exact 64-byte request (wLength=64): NO spurious trailing ZLP when transfer == wLength */
    memset(&m, 0, sizeof(m));
    uint8_t setup_64[8] = { 0x80u, 0x06u, 0x00u, 0x02u, 0x00u, 0x00u, 64u, 0x00u };
    usb_ep0_handle_setup(&st, setup_64, &hw);
    assert(m.pkt_count == 1u && m.pkt_lens[0] == 64u && !st.tx_active);

    /* 4. SET_ADDRESS latched strictly on IN status completion */
    memset(&m, 0, sizeof(m));
    uint8_t setup_addr[8] = { 0x00u, 0x05u, 7u, 0x00u, 0x00u, 0x00u, 0x00u, 0x00u };
    usb_ep0_handle_setup(&st, setup_addr, &hw);
    assert(m.addr == 0u && m.pkt_count == 1u && m.pkt_lens[0] == 0u);
    usb_ep0_on_in_complete(&st, &hw);
    assert(m.addr == 7u);

    /* 5. CDC SET_LINE_CODING (1200 baud) -> ACKs status ZLP and fires UF2 boot reset! */
    memset(&m, 0, sizeof(m));
    uint8_t setup_lc[8] = { 0x21u, 0x20u, 0x00u, 0x00u, 0x02u, 0x00u, 0x07u, 0x00u };
    usb_ep0_handle_setup(&st, setup_lc, &hw);
    assert(m.rx_armed && st.expect_line_coding);
    uint8_t lc_1200[7] = { 0xB0u, 0x04u, 0x00u, 0x00u, 0u, 0u, 8u }; /* 1200 bps LE */
    usb_ep0_on_out_complete(&st, lc_1200, 7u, &hw);
    assert(m.pkt_count == 1u && m.pkt_lens[0] == 0u); /* Status IN ZLP sent */
    assert(m.reset_1200_fired);
    printf("[PASS] Test 8: Composite 146B USB-MIDI+CDC descriptors, multi-packet EP0 IN (64+64+18) & 1200-baud UF2 reset\n");
}

/* ============================================================================
 * TEST 9: Complete OLED UI Menu Handlers (CHANNEL all 7 fields, PRESET preview
 * + bypass/MIDI sync on recall, SYSTEM MIDI CH & 1V/OCT CALIB) + MIDI /6 Wrap
 * ============================================================================ */
static void test_oled_ui_complete_and_midi_div6(void) {
    hal_init();
    memset(g_flash_slots, 0xFF, sizeof(g_flash_slots));

    preset_mgr_t pm;
    preset_mgr_init(&pm);
    /* Configure Preset 2 with distinct startup_active=0 and midi_channel=5 for recall test */
    pm.live.presets[2].startup_active = 0u;
    pm.live.presets[2].midi_channel = 5u;

    bypass_seq_t byp;
    bypass_seq_init(&byp, true);
    dac_bank_t dacs;
    dac_bank_init(&dacs);
    midi_router_t mr;
    midi_router_init(&mr, 0u);
    cv_engine_t eng;
    cv_engine_init(&eng, preset_mgr_get(&pm, 0u), 0u, &pm.live.cal);
    oled_ui_t ui;
    oled_ui_init(&ui);

    /* 1. UI_PAGE_CHANNEL: test editing sub_mode (cursor 1), param_b (cursor 3), clock_sync (cursor 6) */
    oled_ui_handle_inputs(&ui, 0, true, false, &eng, &byp, &mr, &pm); /* SCOPE -> CHANNEL */
    assert(ui.page == UI_PAGE_CHANNEL && ui.selected_ch == 0u);
    /* Change MODE to LFO (1) */
    oled_ui_handle_inputs(&ui, 0, true, false, &eng, &byp, &mr, &pm);
    oled_ui_handle_inputs(&ui, +1, true, false, &eng, &byp, &mr, &pm);
    assert(eng.active_preset.ch[0].mode == CV_MODE_LFO);
    /* Move to cursor 1 (SUB_MODE) and set to LFO_WAVE_RAMP_UP (2) */
    oled_ui_handle_inputs(&ui, +1, true, false, &eng, &byp, &mr, &pm);
    oled_ui_handle_inputs(&ui, +2, true, false, &eng, &byp, &mr, &pm);
    assert(eng.active_preset.ch[0].sub_mode == LFO_WAVE_RAMP_UP);
    /* Move to cursor 3 (PARAM_B) and increment +5 */
    uint8_t old_pb = eng.active_preset.ch[0].param_b;
    oled_ui_handle_inputs(&ui, +2, true, false, &eng, &byp, &mr, &pm);
    oled_ui_handle_inputs(&ui, +5, true, false, &eng, &byp, &mr, &pm);
    assert(eng.active_preset.ch[0].param_b == old_pb + 5u);
    /* Move to cursor 6 (CLOCK_SYNC) and enable sync */
    oled_ui_handle_inputs(&ui, +3, true, false, &eng, &byp, &mr, &pm);
    oled_ui_handle_inputs(&ui, +1, true, false, &eng, &byp, &mr, &pm);
    assert(eng.active_preset.ch[0].clock_sync == 1u);
    oled_ui_render(&ui, &eng, &byp, &pm, true);
    /* Verify non-empty rendered pixels on value column (x >= 56) */
    int val_pixels = 0;
    for (uint8_t p = 2u; p < 8u; p++)
        for (uint8_t x = 56u; x < 120u; x++)
            if (ui.fb[p * OLED_WIDTH + x] != 0u) val_pixels++;
    assert(val_pixels > 20);

    /* 2. UI_PAGE_PRESET: preview hovered cursor name (differs from active_preset) & recall updates bypass + MIDI ch */
    ui.page = UI_PAGE_PRESET;
    ui.cursor = 0u;
    oled_ui_render(&ui, &eng, &byp, &pm, false);
    uint8_t fb_p0[OLED_FB_BYTES];
    memcpy(fb_p0, ui.fb, OLED_FB_BYTES);
    oled_ui_handle_inputs(&ui, +2, false, false, &eng, &byp, &mr, &pm); /* Hover preset 2 ("GTR DUCKER  ") */
    assert(ui.cursor == 2u && eng.active_preset_idx == 0u);
    oled_ui_render(&ui, &eng, &byp, &pm, false);
    assert(memcmp(fb_p0, ui.fb, OLED_FB_BYTES) != 0); /* Rendered hovered preset name changed! */
    /* Click to recall Preset 2 -> MUST update bypass target (0) and MIDI channel (5)! */
    oled_ui_handle_inputs(&ui, 0, true, false, &eng, &byp, &mr, &pm);
    assert(eng.active_preset_idx == 2u);
    assert(byp.target_active == false);
    assert(mr.uart_parser.rx_channel == 5u);

    /* 3. UI_PAGE_SYSTEM: interactive MIDI CHANNEL & 1V/OCT CALIB handlers */
    ui.page = UI_PAGE_SYSTEM;
    ui.cursor = 0u;
    ui.editing = false;
    oled_ui_handle_inputs(&ui, 0, true, false, &eng, &byp, &mr, &pm); /* Enter MIDI CH edit */
    assert(ui.editing);
    oled_ui_handle_inputs(&ui, +3, true, false, &eng, &byp, &mr, &pm); /* 5 + 3 = Ch 8, exit */
    assert(!ui.editing && mr.uart_parser.rx_channel == 8u && eng.active_preset.midi_channel == 8u);

    /* Enter 1V/OCT CALIB (cursor = 1), trim +7 LSB, verify live DAC override & cal LUT updated! */
    oled_ui_handle_inputs(&ui, +1, true, false, &eng, &byp, &mr, &pm);
    assert(ui.editing && ui.cursor == 1u && eng.cal_override_active);
    uint16_t orig_c2 = eng.cal.oct_dac[ui.cal_ch][ui.cal_oct];
    oled_ui_handle_inputs(&ui, +7, false, false, &eng, &byp, &mr, &pm);
    assert(eng.cal.oct_dac[ui.cal_ch][ui.cal_oct] == orig_c2 + 7u);
    assert(pm.live.cal.oct_dac[ui.cal_ch][ui.cal_oct] == orig_c2 + 7u);
    assert(eng.cal_override_code == orig_c2 + 7u);
    oled_ui_render(&ui, &eng, &byp, &pm, false);
    /* Click advances octave knot; BACK exits cal override cleanly */
    uint8_t prev_oct = ui.cal_oct;
    oled_ui_handle_inputs(&ui, 0, true, false, &eng, &byp, &mr, &pm);
    assert(ui.cal_oct == prev_oct + 1u);
    oled_ui_handle_inputs(&ui, 0, false, true, &eng, &byp, &mr, &pm);
    assert(!ui.editing && !eng.cal_override_active);

    /* 4. Zero-division external MIDI 24 PPQN /6 wrap counter check (24 pulses -> exactly 4 16th-note pulses) */
    midi_router_feed_uart_byte(&mr, 0xFAu, false, 1000u, 1u);
    int pulses_16th = 0;
    for (uint32_t k = 0u; k < 24u; k++) {
        uint32_t t_us = 2000u + k * 20000u;
        midi_router_uart_push_dr(&mr, 0xF8u);
        cv_engine_tick_2khz(&eng, &byp, &dacs, &mr, &pm, t_us);
        if (eng.master_clk_pulse) pulses_16th++;
    }
    assert(pulses_16th == 4);

    /* 5. MIDI Program Change recall via cv_engine_tick_2khz MUST sync midi_channel & pm.live.active_preset! */
    pm.live.presets[3].startup_active = 1u;
    pm.live.presets[3].midi_channel = 11u;
    midi_router_set_channel(&mr, 0u); /* Omni to receive PC #3 */
    uint8_t usb_pc3[4] = { 0x0Cu, 0xC0u, 3u, 0u };
    assert(midi_router_usb_push_packet(&mr, usb_pc3));
    cv_engine_tick_2khz(&eng, &byp, &dacs, &mr, &pm, 500000u);
    assert(eng.active_preset_idx == 3u);
    assert(pm.live.active_preset == 3u);
    assert(byp.target_active == true);
    assert(mr.uart_parser.rx_channel == 11u);
    printf("[PASS] Test 9: Complete OLED UI, MIDI /6 wrap & MIDI PC channel/active_preset sync\n");
}

int main(void) {
    test_bypass_por_photomos_and_flexi();
    test_bezier_c1_continuity();
    test_lfo_euclidean_and_ema();
    test_1voct_lut_and_dac();
    test_midi_router_and_recovery();
    test_flash_ab_crc32_and_oled_uf2();
    test_integrated_dual_core_engine();
    test_usb_descriptors_and_multipacket_ep0();
    test_oled_ui_complete_and_midi_div6();
    printf("ALL 9 FIRMWARE SILICON-MOCK UNIT TEST SUITES PASSED (100%% ASSERTIONS)!\n");
    return 0;
}
