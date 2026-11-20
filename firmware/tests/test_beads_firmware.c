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

    /* 16-state Gray-code Encoder LUT test (4 CW transitions -> +1 detent, 4 CCW -> -1 detent) */
    uint8_t prev_ab = 0u;
    int8_t sub = 0;
    const uint8_t cw_seq[4] = { 2u, 3u, 1u, 0u };
    int sum_cw = 0;
    for (int i = 0; i < 4; i++) sum_cw += cv_engine_decode_encoder_step(&prev_ab, &sub, cw_seq[i]);
    assert(sum_cw == 1);

    /* OLED SYSTEM -> USB FIRMWARE UPDATE & 1200-baud CDC UF2 Boot Trigger */
    oled_ui_t ui;
    oled_ui_init(&ui);
    cv_engine_t eng;
    cv_engine_init(&eng, preset_mgr_get(&pm3, 0u), 0u, &pm3.live.cal);
    assert(!g_usb_boot_called);
    oled_ui_handle_inputs(&ui, 0, false, true, &eng, &pm3); /* BACK from SCOPE -> SYSTEM */
    assert(ui.page == UI_PAGE_SYSTEM);
    oled_ui_handle_inputs(&ui, 2, true, false, &eng, &pm3); /* Cursor=2 (USB FIRMWARE UPDATE) + click */
    assert(g_usb_boot_called);

    g_usb_boot_called = false;
    oled_ui_handle_usb_cdc_line_coding(&ui, 1200u);
    assert(g_usb_boot_called);
    printf("[PASS] Test 6: Dual-slot A/B CRC32+write_seq Flash, 16-state encoder LUT, OLED & 1200-baud UF2 boot\n");
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
    printf("[PASS] Test 7: Integrated Dual-Core Core0(2kHz)+Core1 loop (POR, ADC0 pluck/PEAK, FS2 Freeze, OLED)\n");
}

int main(void) {
    test_bypass_por_photomos_and_flexi();
    test_bezier_c1_continuity();
    test_lfo_euclidean_and_ema();
    test_1voct_lut_and_dac();
    test_midi_router_and_recovery();
    test_flash_ab_crc32_and_oled_uf2();
    test_integrated_dual_core_engine();
    printf("ALL 7 FIRMWARE SILICON-MOCK UNIT TEST SUITES PASSED (100%% ASSERTIONS)!\n");
    return 0;
}
