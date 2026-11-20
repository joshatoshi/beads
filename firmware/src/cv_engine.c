#include "cv_engine.h"
#include "hal.h"
#include <string.h>

/* 256-entry exact half-step symmetric signed Q15 Sine LUT:
 * LUT[k] == -LUT[255 - k], LUT[k] == LUT[127 - k] (k < 64), sum(LUT) == 0 exact! */
const int16_t BEADS_SINE_LUT_256[256] = {
       402,   1206,   2009,   2811,   3612,   4410,   5205,   5998,   6786,   7571,   8351,   9126,   9896,  10659,  11417,  12167,
     12910,  13645,  14372,  15090,  15800,  16499,  17189,  17869,  18537,  19195,  19841,  20475,  21096,  21705,  22301,  22884,
     23452,  24007,  24547,  25072,  25582,  26077,  26556,  27019,  27466,  27896,  28310,  28706,  29085,  29447,  29791,  30117,
     30424,  30714,  30985,  31237,  31470,  31685,  31880,  32057,  32213,  32351,  32469,  32567,  32646,  32705,  32745,  32765,
     32765,  32745,  32705,  32646,  32567,  32469,  32351,  32213,  32057,  31880,  31685,  31470,  31237,  30985,  30714,  30424,
     30117,  29791,  29447,  29085,  28706,  28310,  27896,  27466,  27019,  26556,  26077,  25582,  25072,  24547,  24007,  23452,
     22884,  22301,  21705,  21096,  20475,  19841,  19195,  18537,  17869,  17189,  16499,  15800,  15090,  14372,  13645,  12910,
     12167,  11417,  10659,   9896,   9126,   8351,   7571,   6786,   5998,   5205,   4410,   3612,   2811,   2009,   1206,    402,
      -402,  -1206,  -2009,  -2811,  -3612,  -4410,  -5205,  -5998,  -6786,  -7571,  -8351,  -9126,  -9896, -10659, -11417, -12167,
    -12910, -13645, -14372, -15090, -15800, -16499, -17189, -17869, -18537, -19195, -19841, -20475, -21096, -21705, -22301, -22884,
    -23452, -24007, -24547, -25072, -25582, -26077, -26556, -27019, -27466, -27896, -28310, -28706, -29085, -29447, -29791, -30117,
    -30424, -30714, -30985, -31237, -31470, -31685, -31880, -32057, -32213, -32351, -32469, -32567, -32646, -32705, -32745, -32765,
    -32765, -32745, -32705, -32646, -32567, -32469, -32351, -32213, -32057, -31880, -31685, -31470, -31237, -30985, -30714, -30424,
    -30117, -29791, -29447, -29085, -28706, -28310, -27896, -27466, -27019, -26556, -26077, -25582, -25072, -24547, -24007, -23452,
    -22884, -22301, -21705, -21096, -20475, -19841, -19195, -18537, -17869, -17189, -16499, -15800, -15090, -14372, -13645, -12910,
    -12167, -11417, -10659,  -9896,  -9126,  -8351,  -7571,  -6786,  -5998,  -5205,  -4410,  -3612,  -2811,  -2009,  -1206,   -402,
};

/* Exponential Rate LUT: param_a [0..127] -> 0.005 Hz .. 20.0 Hz phase increment at 2.0 kHz */
static const uint32_t RATE_INC_Q32_2KHZ[128] = {
        10737u,     11462u,     12236u,     13061u,     13943u,     14884u,     15888u,     16960u,
        18105u,     19327u,     20631u,     22024u,     23510u,     25097u,     26790u,     28598u,
        30528u,     32589u,     34788u,     37136u,     39642u,     42317u,     45173u,     48222u,
        51476u,     54950u,     58658u,     62617u,     66843u,     71354u,     76169u,     81310u,
        86797u,     92655u,     98908u,    105583u,    112708u,    120315u,    128434u,    137102u,
       146355u,    156232u,    166776u,    178031u,    190046u,    202871u,    216562u,    231178u,
       246779u,    263434u,    281212u,    300190u,    320449u,    342075u,    365161u,    389805u,
       416112u,    444194u,    474171u,    506172u,    540332u,    576797u,    615724u,    657277u,
       701635u,    748986u,    799533u,    853492u,    911091u,    972578u,   1038215u,   1108281u,
      1183076u,   1262918u,   1348149u,   1439132u,   1536255u,   1639933u,   1750607u,   1868751u,
      1994867u,   2129495u,   2273209u,   2426622u,   2590388u,   2765206u,   2951822u,   3151032u,
      3363686u,   3590692u,   3833018u,   4091697u,   4367834u,   4662607u,   4977274u,   5313176u,
      5671747u,   6054518u,   6463120u,   6899298u,   7364912u,   7861950u,   8392531u,   8958919u,
      9563531u,  10208947u,  10897921u,  11633391u,  12418496u,  13256585u,  14151235u,  15106263u,
     16125742u,  17214023u,  18375749u,  19615877u,  20939698u,  22352860u,  23861392u,  25471730u,
     27190746u,  29025773u,  30984642u,  33075708u,  35307895u,  37690726u,  40234368u,  42949673u,
};

/* Full 16-state Gray-code quadrature transition table
 * (Alps EC11E15244G1: 30 detents / 15 PPR = 2 quadrature edges per detent) */
static const int8_t ENC_QUAD_LUT[16] = {
     0, -1, +1,  0,
    +1,  0,  0, -1,
    -1,  0,  0, +1,
     0, +1, -1,  0,
};

/* Clock divider table (24 PPQN ticks per step: /1 .. /96) */
static const uint8_t CLOCK_DIV_TICKS[8] = { 1u, 3u, 6u, 12u, 24u, 48u, 72u, 96u };

/* Hardware bipolar transfer constants (derived from main_board.net:
 * code 0 = -8.233V, code 2045 = 0.000V, code 4095 = +8.251V -> 248.414 LSB/V):
 *   +5.0V = 2045 + 1242 = 3287
 *   -5.0V = 2045 - 1242 =  803
 *   +8.0V = 2045 + 1987 = 4032
 *   -8.0V = 2045 - 1987 =   58
 *   +2.5V = 2045 +  621 = 2666
 *   -2.5V = 2045 -  621 = 1424 */
#define DAC_CODE_ZERO_V  2045
#define DAC_SPAN_8V      1987
#define DAC_SPAN_5V      1242
#define DAC_SPAN_2V5      621
#define DAC_CODE_GATE_5V 3287u

int8_t cv_engine_decode_encoder_step(uint8_t *prev_ab, int8_t *sub_steps, uint8_t cur_ab) {
    uint8_t idx = (uint8_t)(((*prev_ab & 0x03u) << 2u) | (cur_ab & 0x03u));
    *prev_ab = cur_ab & 0x03u;
    int8_t d = ENC_QUAD_LUT[idx];
    if (d == 0) {
        return 0;
    }
    *sub_steps = (int8_t)(*sub_steps + d);
    /* Alps EC11E15244G1 (15 PPR / 30 detents): 2 quadrature edges per detent click */
    if (*sub_steps >= 2) {
        *sub_steps = 0;
        return +1;
    }
    if (*sub_steps <= -2) {
        *sub_steps = 0;
        return -1;
    }
    return 0;
}

/* Deadband-free rounded fixed-point EMA (HARDWARE_LESSONS.md: never stalls at 4080/4095!) */
int32_t cv_engine_ema_step_deadband_free(int32_t cur, int32_t target, uint8_t shift) {
    int32_t diff = target - cur;
    if (diff == 0) {
        return cur;
    }
    if (shift == 0u) {
        return target;
    }
    int32_t step = (diff >= 0) ? (diff >> shift) : -((-diff) >> shift);
    if (step == 0) {
        step = (diff > 0) ? 1 : -1;
    }
    return cur + step;
}

/* Pure integer Bjorklund/Bresenham Euclidean hit check (zero division!) */
bool cv_engine_euclidean_hit(uint8_t step, uint8_t steps, uint8_t hits) {
    if (steps == 0u) steps = 1u;
    if (hits == 0u) return false;
    if (hits >= steps) return true;
    uint16_t s = step;
    while (s >= steps) {
        s = (uint16_t)(s - steps);
    }
    uint16_t cur = (uint16_t)(s * hits);
    uint16_t prev = (uint16_t)((s == 0u ? (steps - 1u) : (s - 1u)) * hits);
    /* Count quotient crossings by repeated subtraction (steps <= 32, hits <= 32 -> fast!) */
    uint16_t q_cur = 0u;
    uint16_t rem = cur;
    while (rem >= steps) { rem = (uint16_t)(rem - steps); q_cur++; }
    if (s == 0u) {
        return true; /* Beat 0 always fires when hits > 0 */
    }
    uint16_t q_prev = 0u;
    rem = prev;
    while (rem >= steps) { rem = (uint16_t)(rem - steps); q_prev++; }
    return (q_cur != q_prev);
}

/* 9-octave 1V/Oct Calibration LUT interpolation (explicit signed diff cast, zero divide!) */
uint16_t cv_engine_note_to_dac_1voct(const beads_cal_lut_t *cal, uint8_t ch, uint8_t midi_note, int16_t pitch_bend) {
    if (ch >= BEADS_NUM_CV_CHANNELS) ch = 0u;
    uint8_t note = (midi_note > 108u) ? 108u : midi_note; /* C0 (0) .. C9 (108) */
    uint8_t oct = 0u;
    while (note >= 12u) {
        note = (uint8_t)(note - 12u);
        oct++;
    }
    if (oct >= BEADS_CAL_OCTAVES - 1u) {
        oct = BEADS_CAL_OCTAVES - 2u;
        note = 12u;
    }
    int32_t d0 = (int32_t)cal->oct_dac[ch][oct];
    int32_t d1 = (int32_t)cal->oct_dac[ch][oct + 1u];
    int32_t oct_span = d1 - d0; /* Explicit signed difference cast! */
    /* Semitone interpolation: round(oct_span * note / 12) via multiply-shift (5461/65536 = 1/12.0007) */
    int32_t semi_delta = (oct_span * (int32_t)note * 5461 + 32768) >> 16;
    /* Pitch bend: +-2 semitones = +-oct_span/6 -> single rounded Q6*Q13 >> 19 (zero double truncation!) */
    int32_t pb_q6 = (oct_span * 10923 + 512) >> 10; /* (oct_span / 6) * 64 */
    int32_t pb_delta = (pb_q6 * (int32_t)pitch_bend + 262144) >> 19;
    int32_t code = d0 + semi_delta + pb_delta;
    if (code < 0) code = 0;
    if (code > 4095) code = 4095;
    return (uint16_t)code;
}

int32_t cv_engine_eval_lfo_q15(lfo_wave_t wave, uint32_t phase_q32, int32_t slew_sh_q15) {
    uint8_t idx = (uint8_t)(phase_q32 >> 24u);
    uint8_t frac = (uint8_t)((phase_q32 >> 16u) & 0xFFu);
    switch (wave) {
        case LFO_WAVE_SINE: {
            int32_t s0 = BEADS_SINE_LUT_256[idx];
            int32_t s1 = BEADS_SINE_LUT_256[(uint8_t)(idx + 1u)];
            return s0 + (((s1 - s0) * (int32_t)frac) >> 8);
        }
        case LFO_WAVE_TRI: {
            /* Symmetric triangle: 0..0x3FFFFFFF -> 0..+32767, 0x40000000..0xBFFFFFFF -> +32767..-32767 */
            uint32_t p = phase_q32 >> 16u; /* 0..65535 */
            if (p < 16384u) {
                return (int32_t)(p << 1u);
            } else if (p < 49152u) {
                return (int32_t)(32767 - (int32_t)((p - 16384u) << 1u));
            } else {
                return (int32_t)(-32767 + (int32_t)((p - 49152u) << 1u));
            }
        }
        case LFO_WAVE_RAMP_UP:
            return (int32_t)(phase_q32 >> 16u) - 32768;
        case LFO_WAVE_RAMP_DN:
            return 32767 - (int32_t)(phase_q32 >> 16u);
        case LFO_WAVE_SQUARE:
            return (phase_q32 < 0x80000000u) ? 32767 : -32767;
        case LFO_WAVE_SLEW_SH:
        default:
            return slew_sh_q15;
    }
}

uint16_t cv_engine_q15_to_dac_code(int32_t val_q15, cv_span_t span, int8_t offset_pct) {
    if (val_q15 > 32767) val_q15 = 32767;
    if (val_q15 < -32767) val_q15 = -32767;
    int32_t code = DAC_CODE_ZERO_V;
    switch (span) {
        case CV_SPAN_BIP_8V:
            code = DAC_CODE_ZERO_V + ((val_q15 * DAC_SPAN_8V) >> 15);
            break;
        case CV_SPAN_BIP_5V:
            code = DAC_CODE_ZERO_V + ((val_q15 * DAC_SPAN_5V) >> 15);
            break;
        case CV_SPAN_BIP_2V5:
            code = DAC_CODE_ZERO_V + ((val_q15 * DAC_SPAN_2V5) >> 15);
            break;
        case CV_SPAN_UNI_5V: {
            int32_t u = (val_q15 + 32768) >> 1; /* 0..32767 */
            code = DAC_CODE_ZERO_V + ((u * DAC_SPAN_5V) >> 15);
            break;
        }
        case CV_SPAN_UNI_8V: {
            int32_t u = (val_q15 + 32768) >> 1;
            code = DAC_CODE_ZERO_V + ((u * DAC_SPAN_8V) >> 15);
            break;
        }
    }
    /* Apply offset_pct (-100..+100 -> +-5V shift) via multiply-shift (1242/100 ~= 12.42) */
    int32_t off_lsb = ((int32_t)offset_pct * 3180) >> 8;
    code += off_lsb;
    if (code < 0) code = 0;
    if (code > 4095) code = 4095;
    return (uint16_t)code;
}

void cv_engine_init(cv_engine_t *eng, const beads_preset_t *preset, uint8_t preset_idx, const beads_cal_lut_t *cal) {
    memset(eng, 0, sizeof(*eng));
    eng->cal = *cal;
    eng->tap_period_us = 500000u; /* 120 BPM */
    for (uint8_t i = 0u; i < BEADS_NUM_CV_CHANNELS; i++) {
        bezier_drift_init(&eng->ch[i].bezier, 0x13579BDFu ^ ((uint32_t)(i + 1u) * 0x2468ACE1u), 24576u);
        eng->ch[i].ema_code_q12 = DAC_CODE_ZERO_V;
        eng->ch[i].last_out_code = (uint16_t)DAC_CODE_ZERO_V;
    }
    cv_engine_load_preset(eng, preset, preset_idx);
}

void cv_engine_load_preset(cv_engine_t *eng, const beads_preset_t *preset, uint8_t preset_idx) {
    eng->active_preset = *preset;
    eng->active_preset_idx = preset_idx;
    for (uint8_t i = 0u; i < BEADS_NUM_CV_CHANNELS; i++) {
        uint16_t tens = (uint16_t)(4096u + ((uint32_t)preset->ch[i].param_b * 224u));
        eng->ch[i].bezier.tension_q15 = (tens > 32767u) ? 32767u : tens;
        eng->ch[i].euc_step = 0u;
        eng->ch[i].clock_div_cnt = 0u;
    }
}

static uint32_t scale_inc_by_dt(uint32_t inc_500us, uint32_t dt_us) {
    /* Exact 32-bit scaling for dt_us in [250..2000] around 500 us nominal (zero 64-bit ops!):
     * At dt_us == 500 -> returns exact inc_500us (0.00% drift even at lowest rates!). */
    if (dt_us == 500u) {
        return inc_500us;
    }
    uint32_t hi = inc_500us >> 10u;
    uint32_t lo = inc_500us & 0x3FFu;
    /* 2097 / 1048576 ~= 1 / 500.036: split hi/lo avoids 32-bit overflow up to inc=0x40000000 */
    uint32_t mult_q10 = (dt_us * 2097u) >> 10u; /* 1024 at dt_us=500 */
    return hi * mult_q10 + ((lo * mult_q10) >> 10u);
}

static void update_ui_buttons_and_fs2(cv_engine_t *eng, uint32_t now_us) {
    /* 1. Quadrature Encoder 16-state Gray-code LUT */
    uint8_t cur_ab = (uint8_t)((hal_gpio_read(PIN_ENC_A) ? 1u : 0u) |
                               (hal_gpio_read(PIN_ENC_B) ? 2u : 0u));
    int8_t step = cv_engine_decode_encoder_step(&eng->enc_prev_ab, &eng->enc_sub_steps, cur_ab);
    if (step != 0) {
        eng->enc_delta_accum += step;
    }

    /* 2. ENC_SW & BTN_BACK debouncing (active-low) */
    bool sw_raw = !hal_gpio_read(PIN_ENC_SW);
    if (sw_raw != eng->enc_sw_debounced) {
        if (++eng->enc_sw_cnt >= BYP_FS_DEBOUNCE_TICKS) {
            eng->enc_sw_cnt = 0u;
            eng->enc_sw_debounced = sw_raw;
            if (sw_raw) eng->enc_sw_click_ev = true;
        }
    } else {
        eng->enc_sw_cnt = 0u;
    }

    bool bk_raw = !hal_gpio_read(PIN_BTN_BACK);
    if (bk_raw != eng->back_debounced) {
        if (++eng->back_cnt >= BYP_FS_DEBOUNCE_TICKS) {
            eng->back_cnt = 0u;
            eng->back_debounced = bk_raw;
            if (bk_raw) eng->back_click_ev = true;
        }
    } else {
        eng->back_cnt = 0u;
    }

    /* 3. FS2 Dual-Action: Short Tap (<350 ms) = Tap-Tempo & Seed Pulse; Hold (>=350 ms) = Freeze Toggle */
    bool fs2_raw = !hal_gpio_read(PIN_FS2_ACTION_SW);
    if (eng->fs2_seed_ticks > 0u) {
        eng->fs2_seed_ticks--;
        if (eng->fs2_seed_ticks == 0u) {
            eng->fs2_seed_pulse = false;
        }
    }
    if (fs2_raw != eng->fs2_debounced) {
        if (++eng->fs2_debounce_cnt >= BYP_FS_DEBOUNCE_TICKS) {
            eng->fs2_debounce_cnt = 0u;
            eng->fs2_debounced = fs2_raw;
            if (fs2_raw) {
                eng->fs2_hold_ticks = 0u;
            } else {
                if (eng->fs2_hold_ticks < BYP_FLEXI_HOLD_TICKS) {
                    /* Short tap: update tap tempo & emit 10 ms SEED trigger pulse */
                    if (eng->last_tap_us != 0u) {
                        uint32_t dt_tap = now_us - eng->last_tap_us;
                        if (dt_tap >= 150000u && dt_tap <= 2000000u) {
                            eng->tap_period_us = dt_tap;
                        }
                    }
                    eng->last_tap_us = now_us;
                    eng->fs2_seed_pulse = true;
                    eng->fs2_seed_ticks = 20u; /* 10 ms pulse */
                }
                eng->fs2_hold_ticks = 0u;
            }
        }
    } else {
        eng->fs2_debounce_cnt = 0u;
        if (eng->fs2_debounced) {
            eng->fs2_hold_ticks++;
            if (eng->fs2_hold_ticks == BYP_FLEXI_HOLD_TICKS) {
                /* Crossing 350 ms hold toggles FREEZE latch immediately */
                eng->fs2_freeze_latched = !eng->fs2_freeze_latched;
            }
        }
    }
    hal_gpio_write(PIN_LED_FS2_STATUS, eng->fs2_freeze_latched || eng->fs2_seed_pulse);
}

static void update_guitar_envelope(cv_engine_t *eng) {
    uint16_t raw = hal_adc_read_ch(ADC_CH_GTR_ENV);
    if (raw > 4095u) raw = 4095u;
    eng->env_prev_q12 = eng->env_level_q12;
    /* Fast attack, smooth musical envelope release (~32 ms -> bridges 82.4 Hz low-E guitar cycles!) */
    if (raw > eng->env_level_q12) {
        eng->env_level_q12 = (uint16_t)cv_engine_ema_step_deadband_free((int32_t)eng->env_level_q12, (int32_t)raw, 1u);
    } else {
        eng->env_level_q12 = (uint16_t)cv_engine_ema_step_deadband_free((int32_t)eng->env_level_q12, (int32_t)raw, 6u);
    }
    /* dE/dt Pluck Trigger detection */
    int32_t slope = (int32_t)eng->env_level_q12 - (int32_t)eng->env_prev_q12;
    if (slope > 220 && eng->env_level_q12 > 500u && eng->pluck_hold_ticks == 0u) {
        eng->pluck_trig_active = true;
        eng->pluck_hold_ticks = 60u; /* 30 ms retrigger holdoff + pulse */
    }
    if (eng->pluck_hold_ticks > 0u) {
        eng->pluck_hold_ticks--;
        if (eng->pluck_hold_ticks <= 40u) {
            eng->pluck_trig_active = false;
        }
    }
    /* Faceplate PEAK/CLIP LED illuminates above ~2.10V on ADC0 (reachable below 2.79V diode ceiling!) */
    eng->audio_clip_led = (raw > 2600u);
    hal_gpio_write(PIN_LED_AUDIO_PEAK, eng->audio_clip_led);
}

void cv_engine_tick_2khz(cv_engine_t *eng, bypass_seq_t *byp, dac_bank_t *dacs,
                         midi_router_t *midi, preset_mgr_t *pm, uint32_t now_us) {
    /* 1. Compute clamped dt_us (handles post-lockout positive repeating timer stretch!) */
    uint32_t dt_us = CORE0_TICK_US;
    if (eng->prev_tick_us != 0u) {
        uint32_t raw_dt = now_us - eng->prev_tick_us;
        if (raw_dt < 250u) raw_dt = 250u;
        if (raw_dt > 2000u) raw_dt = 2000u;
        dt_us = raw_dt;
    }
    eng->prev_tick_us = now_us;
    eng->tick_count++;
    uint32_t now_ms = eng->tick_count >> 1u; /* 2 kHz -> exact 0.5 ms/tick, zero divide! */

    /* 2. Popless PhotoMOS True-Bypass & 250ms POR/Brownout Blanking (highest priority!) */
    bool pwr_good = hal_gpio_read(PIN_PEDAL_PWR_GOOD);
    bool fs1_raw  = !hal_gpio_read(PIN_FS1_BYPASS_SW);
    bypass_seq_tick_2khz(byp, pwr_good, fs1_raw);

    /* Keep SPI0 & ~CS GPIOs strictly LOW when +5V_BUCK is off (USB-only / brownout defense-in-depth),
     * and enable MCP4822 DAC bank only once analog +5V/+-12V rails clear POR */
    hal_spi_dac_set_power_safe(pwr_good);
    dac_bank_set_enabled(dacs, pwr_good && byp->por_cleared_once);

    /* 3. Drain UART0 + USB-MIDI rings */
    midi->clock_pulse = false;
    midi->retrig_pulse = false;
    midi_router_poll_core0(midi, now_us, now_ms);

    if (midi->bypass_req_valid) {
        midi->bypass_req_valid = false;
        bypass_seq_set_target(byp, midi->bypass_req_active);
    }
    if (midi->preset_req_valid) {
        midi->preset_req_valid = false;
        uint8_t idx = (midi->preset_req_idx < BEADS_NUM_PRESETS) ? midi->preset_req_idx : 0u;
        const beads_preset_t *pr = preset_mgr_get(pm, idx);
        cv_engine_load_preset(eng, pr, idx);
        bypass_seq_set_target(byp, pr->startup_active != 0u);
        midi_router_set_channel(midi, pr->midi_channel);
        pm->live.active_preset = idx;
    }

    /* 4. Encoder, UI buttons, FS2 Tap-Tempo/Freeze & ADC0 Guitar Envelope */
    update_ui_buttons_and_fs2(eng, now_us);
    update_guitar_envelope(eng);

    /* Master 16th-note clock pulse: uses external 24 PPQN MIDI clock (/6 via wrap counter, zero div!)
     * when active (<500ms), falling back cleanly to internal FS2 Tap-Tempo clock ONLY when absent! */
    bool ext_clk_active = (midi->last_clock_us != 0u) && ((uint32_t)(now_us - midi->last_clock_us) < 500000u);
    eng->master_clk_pulse = false;
    if (ext_clk_active) {
        eng->internal_clk_acc_us = 0u;
        if (midi->clock_pulse) {
            if (midi->clock_tick_count == 1u) {
                eng->ext_clk_div6_cnt = 0u;
            }
            if (eng->ext_clk_div6_cnt == 0u) {
                eng->master_clk_pulse = true;
            }
            eng->ext_clk_div6_cnt++;
            if (eng->ext_clk_div6_cnt >= 6u) {
                eng->ext_clk_div6_cnt = 0u;
            }
        }
    } else {
        eng->ext_clk_div6_cnt = 0u;
        eng->internal_clk_acc_us += dt_us;
        uint32_t step_us = eng->tap_period_us >> 2u; /* 16th-note pulse */
        if (step_us < 20000u) step_us = 20000u;
        if (eng->internal_clk_acc_us >= step_us) {
            eng->internal_clk_acc_us -= step_us;
            eng->master_clk_pulse = true;
        }
    }

    /* 5. Evaluate all 8 universal bipolar CV/Gate channels & delta-gate SPI0 MCP4822 */
    for (uint8_t i = 0u; i < BEADS_NUM_CV_CHANNELS; i++) {
        const cv_channel_cfg_t *cfg = &eng->active_preset.ch[i];
        cv_channel_rt_t *rt = &eng->ch[i];
        uint16_t out_code = (uint16_t)DAC_CODE_ZERO_V;
        int32_t  scope_q15 = 0;

        switch ((cv_mode_t)cfg->mode) {
            case CV_MODE_BEZIER_DRIFT: {
                uint32_t inc = scale_inc_by_dt(RATE_INC_Q32_2KHZ[cfg->param_a & 0x7Fu], dt_us);
                scope_q15 = bezier_drift_step(&rt->bezier, inc);
                out_code = cv_engine_q15_to_dac_code(scope_q15, (cv_span_t)cfg->span, cfg->offset_pct);
                break;
            }
            case CV_MODE_LFO: {
                uint32_t base_inc = RATE_INC_Q32_2KHZ[cfg->param_a & 0x7Fu];
                if (cfg->clock_sync != 0u && eng->master_clk_pulse) {
                    /* Quantized clock-synced phase step on 16th-note master pulses */
                    uint8_t shift = (uint8_t)(2u + ((cfg->param_a >> 5u) & 0x03u));
                    base_inc = 0x40000000u >> shift;
                }
                uint32_t inc = (cfg->clock_sync != 0u)
                    ? (eng->master_clk_pulse ? base_inc : 0u)
                    : scale_inc_by_dt(base_inc, dt_us);
                uint32_t prev = rt->lfo_phase_q32;
                rt->lfo_phase_q32 += inc;
                if (rt->lfo_phase_q32 < prev) {
                    /* Trigger new S&H sample on phase wrap */
                    rt->sh_target_q15 = bezier_drift_step(&rt->bezier, 0x40000000u);
                }
                rt->sh_current_q15 = cv_engine_ema_step_deadband_free(rt->sh_current_q15, rt->sh_target_q15, 3u);
                uint32_t ph_off = ((uint32_t)(cfg->param_b & 0x7Fu)) << 25u;
                scope_q15 = cv_engine_eval_lfo_q15((lfo_wave_t)cfg->sub_mode, rt->lfo_phase_q32 + ph_off, rt->sh_current_q15);
                out_code = cv_engine_q15_to_dac_code(scope_q15, (cv_span_t)cfg->span, cfg->offset_pct);
                break;
            }
            case CV_MODE_RANDOM_TRIG: {
                if (eng->master_clk_pulse) {
                    uint8_t steps = (cfg->param_a == 0u) ? 16u : (cfg->param_a > 32u ? 32u : cfg->param_a);
                    uint8_t hits  = (cfg->param_b > steps) ? steps : cfg->param_b;
                    if (cv_engine_euclidean_hit(rt->euc_step, steps, hits)) {
                        rt->trig_ticks_left = 12u; /* 6.0 ms +5V trigger */
                    }
                    rt->euc_step = (uint8_t)(rt->euc_step + 1u);
                    if (rt->euc_step >= steps) rt->euc_step = 0u;
                }
                if (rt->trig_ticks_left > 0u) {
                    rt->trig_ticks_left--;
                    out_code = DAC_CODE_GATE_5V;
                    scope_q15 = 32767;
                } else {
                    out_code = (uint16_t)DAC_CODE_ZERO_V;
                    scope_q15 = 0;
                }
                break;
            }
            case CV_MODE_MIDI_NOTE_1VOCT: {
                uint16_t target = cv_engine_note_to_dac_1voct(&eng->cal, i, midi->active_note, midi->pitch_bend);
                uint8_t glide_shift = (uint8_t)(cfg->param_a >> 4u); /* 0..7 */
                if (byp->snap_cv_now || glide_shift == 0u) {
                    rt->ema_code_q12 = (int32_t)target;
                } else {
                    rt->ema_code_q12 = cv_engine_ema_step_deadband_free(rt->ema_code_q12, (int32_t)target, glide_shift);
                }
                out_code = (uint16_t)rt->ema_code_q12;
                scope_q15 = ((int32_t)out_code - DAC_CODE_ZERO_V) << 4;
                break;
            }
            case CV_MODE_MIDI_GATE_TRIG: {
                if (midi->retrig_pulse) {
                    rt->trig_ticks_left = 10u; /* 5.0 ms retrig */
                }
                bool high = (cfg->sub_mode == 1u) ? (rt->trig_ticks_left > 0u) : midi->gate_high;
                if (rt->trig_ticks_left > 0u) rt->trig_ticks_left--;
                out_code = high ? DAC_CODE_GATE_5V : (uint16_t)DAC_CODE_ZERO_V;
                scope_q15 = high ? 32767 : 0;
                break;
            }
            case CV_MODE_MIDI_CLOCK_DIV: {
                uint8_t div = CLOCK_DIV_TICKS[cfg->sub_mode & 0x07u];
                if (midi->clock_pulse) {
                    if (midi->clock_tick_count == 1u) {
                        rt->clock_div_cnt = 0u; /* Reset divider phase on 0xFA MIDI Start! */
                    }
                    if (rt->clock_div_cnt == 0u) {
                        rt->trig_ticks_left = 10u; /* 5.0 ms clock pulse */
                    }
                    rt->clock_div_cnt++;
                    if (rt->clock_div_cnt >= div) rt->clock_div_cnt = 0u;
                }
                bool high = (rt->trig_ticks_left > 0u);
                if (rt->trig_ticks_left > 0u) rt->trig_ticks_left--;
                out_code = high ? DAC_CODE_GATE_5V : (uint16_t)DAC_CODE_ZERO_V;
                scope_q15 = high ? 32767 : 0;
                break;
            }
            case CV_MODE_MIDI_CC: {
                uint8_t cc_val = midi->cc[cfg->sub_mode & 0x7Fu];
                int32_t val_q15 = ((int32_t)cc_val * 516) - 32767; /* 0..127 -> -32767..+32765 */
                uint16_t target = cv_engine_q15_to_dac_code(val_q15, (cv_span_t)cfg->span, cfg->offset_pct);
                if (byp->snap_cv_now) {
                    rt->ema_code_q12 = (int32_t)target;
                } else {
                    rt->ema_code_q12 = cv_engine_ema_step_deadband_free(rt->ema_code_q12, (int32_t)target, 2u);
                }
                out_code = (uint16_t)rt->ema_code_q12;
                scope_q15 = ((int32_t)out_code - DAC_CODE_ZERO_V) << 4;
                break;
            }
            case CV_MODE_GUITAR_ENV: {
                /* 0..4095 -> 0..+32760 (or inverted ducking if sub_mode == 1) */
                int32_t env_u = (int32_t)eng->env_level_q12 << 3;
                int32_t q15 = (cfg->sub_mode == 1u) ? (32767 - (env_u << 1)) : ((env_u << 1) - 32767);
                scope_q15 = q15;
                out_code = cv_engine_q15_to_dac_code(q15, (cv_span_t)cfg->span, cfg->offset_pct);
                break;
            }
            case CV_MODE_GUITAR_PLUCK: {
                out_code = eng->pluck_trig_active ? DAC_CODE_GATE_5V : (uint16_t)DAC_CODE_ZERO_V;
                scope_q15 = eng->pluck_trig_active ? 32767 : 0;
                break;
            }
            case CV_MODE_FS2_ACTION: {
                bool high = (cfg->sub_mode == 1u) ? eng->fs2_seed_pulse : eng->fs2_freeze_latched;
                out_code = high ? DAC_CODE_GATE_5V : (uint16_t)DAC_CODE_ZERO_V;
                scope_q15 = high ? 32767 : 0;
                break;
            }
        }

        if (eng->cal_override_active && i == eng->cal_override_ch) {
            out_code = eng->cal_override_code & 0x0FFFu;
            scope_q15 = ((int32_t)out_code - DAC_CODE_ZERO_V) << 4;
        }

        rt->last_out_code = out_code;
        rt->scope_val_q15 = (int16_t)(scope_q15 > 32767 ? 32767 : (scope_q15 < -32767 ? -32767 : scope_q15));
        dac_bank_write_ch(dacs, i, out_code);
    }
}
