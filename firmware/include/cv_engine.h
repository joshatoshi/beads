#ifndef BEADS_CV_ENGINE_H
#define BEADS_CV_ENGINE_H

#include <stdbool.h>
#include <stdint.h>
#include "board_pins.h"
#include "bezier_drift.h"
#include "bypass_sequencer.h"
#include "dac_mcp4822.h"
#include "midi_router.h"
#include "presets.h"

/* LFO 256-entry symmetric signed Q15 sine LUT (extern for full-table symmetry tests) */
extern const int16_t BEADS_SINE_LUT_256[256];

typedef struct {
    bezier_drift_t bezier;
    uint32_t       lfo_phase_q32;
    int32_t        sh_current_q15;
    int32_t        sh_target_q15;
    uint8_t        euc_step;
    uint16_t       trig_ticks_left;
    int32_t        ema_code_q12;      /* Smoothed 12-bit code (0..4095) */
    uint16_t       last_out_code;     /* Current 12-bit MCP4822 code */
    int16_t        scope_val_q15;     /* Snapshot for Core 1 SSD1306 oscilloscope */
    uint32_t       clock_div_cnt;
    bool           prev_clock_phase;
} cv_channel_rt_t;

typedef struct {
    cv_channel_rt_t ch[BEADS_NUM_CV_CHANNELS];
    beads_preset_t  active_preset;
    beads_cal_lut_t cal;
    uint8_t         active_preset_idx;

    /* Guitar peak envelope & dE/dt pluck detector (ADC0) */
    uint16_t        env_level_q12;    /* 0..4095 */
    uint16_t        env_prev_q12;
    bool            pluck_trig_active;
    uint16_t        pluck_hold_ticks;
    bool            audio_clip_led;

    /* FS2 dual-action (Short Tap = Tap Tempo / Seed; Hold >= 350ms = Freeze) */
    bool            fs2_debounced;
    uint16_t        fs2_debounce_cnt;
    uint32_t        fs2_hold_ticks;
    bool            fs2_freeze_latched;
    bool            fs2_seed_pulse;
    uint16_t        fs2_seed_ticks;
    uint32_t        last_tap_us;
    uint32_t        tap_period_us;    /* Quarter-note period (default 500,000 us = 120 BPM) */
    uint32_t        internal_clk_acc_us;
    bool            master_clk_pulse;

    /* Rotary encoder 16-state Gray-code LUT decoder */
    uint8_t         enc_prev_ab;
    int8_t          enc_sub_steps;
    int32_t         enc_delta_accum;
    bool            enc_sw_debounced;
    uint16_t        enc_sw_cnt;
    bool            enc_sw_click_ev;
    bool            back_debounced;
    uint16_t        back_cnt;
    bool            back_click_ev;

    /* Clamped dt_us tracking for positive repeating timer */
    uint32_t        prev_tick_us;
    uint32_t        tick_count;
} cv_engine_t;

void     cv_engine_init(cv_engine_t *eng, const beads_preset_t *preset, uint8_t preset_idx, const beads_cal_lut_t *cal);
void     cv_engine_load_preset(cv_engine_t *eng, const beads_preset_t *preset, uint8_t preset_idx);
uint16_t cv_engine_note_to_dac_1voct(const beads_cal_lut_t *cal, uint8_t ch, uint8_t midi_note, int16_t pitch_bend);
int32_t  cv_engine_eval_lfo_q15(lfo_wave_t wave, uint32_t phase_q32, int32_t slew_sh_q15);
bool     cv_engine_euclidean_hit(uint8_t step, uint8_t steps, uint8_t hits);
int32_t  cv_engine_ema_step_deadband_free(int32_t cur, int32_t target, uint8_t shift);
int8_t   cv_engine_decode_encoder_step(uint8_t *prev_ab, int8_t *sub_steps, uint8_t cur_ab);
uint16_t cv_engine_q15_to_dac_code(int32_t val_q15, cv_span_t span, int8_t offset_pct);

/* Main deterministic Core 0 2.0 kHz tick (zero float / zero 64-bit div!) */
void     cv_engine_tick_2khz(cv_engine_t *eng, bypass_seq_t *byp, dac_bank_t *dacs,
                             midi_router_t *midi, preset_mgr_t *pm, uint32_t now_us);

#endif /* BEADS_CV_ENGINE_H */
