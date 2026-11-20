#include "bypass_sequencer.h"
#include "board_pins.h"
#include "hal.h"

void bypass_seq_init(bypass_seq_t *seq, bool startup_active) {
    seq->state = BYP_STATE_POR_BLANK;
    seq->state_ticks = 0u;
    seq->por_blank_ticks = BYP_POR_BLANK_TICKS;
    seq->current_active = false;          /* Fail-safe passive true bypass at boot */
    seq->target_active = startup_active;
    seq->photomos_mute = true;            /* Hold PhotoMOS muted across 250 ms POR */
    seq->por_cleared_once = false;
    seq->snap_cv_now = false;
    seq->fs1_debounced = false;
    seq->fs1_debounce_cnt = 0u;
    seq->fs1_hold_ticks = 0u;
    seq->fs1_pre_press_active = false;

    hal_gpio_write(PIN_RELAY_BYPASS_EN, false);
    hal_gpio_write(PIN_PHOTOMOS_MUTE_EN, true);
    hal_gpio_write(PIN_LED_FS1_BYPASS, false);
}

void bypass_seq_set_target(bypass_seq_t *seq, bool active) {
    seq->target_active = active;
}

bool bypass_seq_is_idle(const bypass_seq_t *seq) {
    return (seq->state == BYP_STATE_IDLE) &&
           !seq->photomos_mute &&
           seq->por_cleared_once &&
           (seq->target_active == seq->current_active);
}

static void update_fs1_flexi_switch(bypass_seq_t *seq, bool fs1_pressed_raw) {
    if (fs1_pressed_raw != seq->fs1_debounced) {
        seq->fs1_debounce_cnt++;
        if (seq->fs1_debounce_cnt >= BYP_FS_DEBOUNCE_TICKS) {
            seq->fs1_debounce_cnt = 0u;
            seq->fs1_debounced = fs1_pressed_raw;
            if (seq->fs1_debounced) {
                /* Rising press edge: immediately toggle target (instant foot response) */
                seq->fs1_pre_press_active = seq->target_active;
                seq->target_active = !seq->target_active;
                seq->fs1_hold_ticks = 0u;
            } else {
                /* Release edge: EQD Flexi-Switch auto-momentary if held >= 350 ms! */
                if (seq->fs1_hold_ticks >= BYP_FLEXI_HOLD_TICKS) {
                    seq->target_active = seq->fs1_pre_press_active;
                }
                seq->fs1_hold_ticks = 0u;
            }
        }
    } else {
        seq->fs1_debounce_cnt = 0u;
        if (seq->fs1_debounced && seq->fs1_hold_ticks < 0xFFFFFFFEu) {
            seq->fs1_hold_ticks++;
        }
    }
}

void bypass_seq_tick_2khz(bypass_seq_t *seq, bool pedal_pwr_good, bool fs1_pressed_raw) {
    seq->snap_cv_now = false;

    /* 1. HIGHEST PRIORITY: Power-On & Brownout Thump Blanking.
     * Hold por_blank_ticks latched at full 500 ticks (250.0 ms) throughout sustained
     * undervoltage / USB-C bench-only mode (never decrementing during brownout!). */
    if (!pedal_pwr_good) {
        seq->state = BYP_STATE_POR_BLANK;
        seq->state_ticks = 0u;
        seq->por_blank_ticks = BYP_POR_BLANK_TICKS;
        seq->current_active = false;
        seq->photomos_mute = true;
        seq->por_cleared_once = false;
        seq->fs1_debounced = false;
        seq->fs1_debounce_cnt = 0u;
        seq->fs1_hold_ticks = 0u;
        hal_gpio_write(PIN_RELAY_BYPASS_EN, false);
        hal_gpio_write(PIN_PHOTOMOS_MUTE_EN, true);
        hal_gpio_write(PIN_LED_FS1_BYPASS, false);
        return;
    }

    /* Update FS1 debouncer & EQD Flexi-Switch (only once pedal power is present) */
    update_fs1_flexi_switch(seq, fs1_pressed_raw);

    switch (seq->state) {
        case BYP_STATE_POR_BLANK:
            seq->photomos_mute = true;
            hal_gpio_write(PIN_PHOTOMOS_MUTE_EN, true);
            if (seq->por_blank_ticks > 0u) {
                seq->por_blank_ticks--;
            }
            /* At 240.0 ms (20 ticks = 10.0 ms before unmute), enable DACs & engage startup relay while STILL MUTED! */
            if (seq->por_blank_ticks == BYP_POR_RELAY_LEAD_TICKS) {
                seq->por_cleared_once = true;
                seq->current_active = seq->target_active;
                hal_gpio_write(PIN_RELAY_BYPASS_EN, seq->current_active);
                hal_gpio_write(PIN_LED_FS1_BYPASS, seq->current_active);
                seq->snap_cv_now = true;
            }
            if (seq->por_blank_ticks == 0u) {
                seq->photomos_mute = false;
                seq->por_cleared_once = true;
                seq->state = BYP_STATE_IDLE;
                seq->state_ticks = 0u;
                hal_gpio_write(PIN_PHOTOMOS_MUTE_EN, false);
            }
            break;

        case BYP_STATE_IDLE:
            if (seq->target_active != seq->current_active) {
                /* Begin 15.0 ms popless/clickless sequence (t = 0.0 ms) */
                seq->state = BYP_STATE_MUTING;
                seq->state_ticks = 1u;
                seq->photomos_mute = true;
                hal_gpio_write(PIN_PHOTOMOS_MUTE_EN, true);
            }
            break;

        case BYP_STATE_MUTING:
            /* 3.5 ms (7 ticks): TLP172AM glides from >1 GOhm to 1.0 Ohm (>46 dB mute) */
            if (seq->state_ticks >= BYP_MUTE_LEAD_TICKS) {
                seq->state = BYP_STATE_SWITCHING;
                seq->state_ticks = 1u;
                seq->current_active = seq->target_active;
                hal_gpio_write(PIN_RELAY_BYPASS_EN, seq->current_active);
                hal_gpio_write(PIN_LED_FS1_BYPASS, seq->current_active);
                seq->snap_cv_now = true;
            } else {
                seq->state_ticks++;
            }
            break;

        case BYP_STATE_SWITCHING:
            /* 8.0 ms (16 ticks): holds muted across G6K-2F-Y flight (<=3 ms) + bounce (<=3 ms) */
            if (seq->state_ticks >= BYP_SWITCH_HOLD_TICKS) {
                seq->state = BYP_STATE_UNMUTING;
                seq->state_ticks = 1u;
                seq->photomos_mute = false;
                hal_gpio_write(PIN_PHOTOMOS_MUTE_EN, false);
            } else {
                seq->state_ticks++;
            }
            break;

        case BYP_STATE_UNMUTING:
            /* 3.5 ms (7 ticks): TLP172AM soft-knee release -> IDLE at t = 15.0 ms exact! */
            if (seq->state_ticks >= BYP_UNMUTE_TAIL_TICKS) {
                seq->state = BYP_STATE_IDLE;
                seq->state_ticks = 0u;
            } else {
                seq->state_ticks++;
            }
            break;
    }
}
