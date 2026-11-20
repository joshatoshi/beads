#ifndef BEADS_BYPASS_SEQUENCER_H
#define BEADS_BYPASS_SEQUENCER_H

#include <stdbool.h>
#include <stdint.h>

/* Timing constants at 2.0 kHz (500 us/tick) */
#define BYP_POR_BLANK_TICKS      500u  /* 250.0 ms POR & brownout thump blanking */
#define BYP_POR_RELAY_LEAD_TICKS  20u  /* Engage relay at 240.0 ms (10 ms before unmute) */
#define BYP_MUTE_LEAD_TICKS        7u  /* 3.5 ms (> 2.0 ms TLP172AM max t_ON + soft-knee) */
#define BYP_SWITCH_HOLD_TICKS     16u  /* 8.0 ms (> 3.0 ms operate + 3.0 ms bounce G6K-2F-Y) */
#define BYP_UNMUTE_TAIL_TICKS      7u  /* 3.5 ms (> 1.0 ms max t_OFF + soft release) */
/* Total runtime clickless window = 7 + 16 + 7 = 30 ticks = 15.0 ms exact! */

#define BYP_FS_DEBOUNCE_TICKS     20u  /* 10.0 ms contact debounce */
#define BYP_FLEXI_HOLD_TICKS     700u  /* 350.0 ms EQD Flexi-Switch auto-momentary threshold */

typedef enum {
    BYP_STATE_POR_BLANK = 0,
    BYP_STATE_IDLE      = 1,
    BYP_STATE_MUTING    = 2,
    BYP_STATE_SWITCHING = 3,
    BYP_STATE_UNMUTING  = 4
} bypass_state_t;

typedef struct {
    bypass_state_t state;
    uint16_t       state_ticks;
    uint16_t       por_blank_ticks;
    bool           current_active;   /* Physical K1/K2 relay coil state (1=Active, 0=Bypass) */
    bool           target_active;    /* Requested state */
    bool           photomos_mute;    /* Physical GPIO23 TLP172AM state (1=Muted) */
    bool           por_cleared_once; /* True after initial 250 ms POR settle completes */
    bool           snap_cv_now;      /* 1-tick pulse during SWITCHING while output is muted */
    /* FS1 debouncer & EQD Flexi-Switch state */
    bool           fs1_debounced;    /* True when FS1 held down */
    uint16_t       fs1_debounce_cnt;
    uint32_t       fs1_hold_ticks;
    bool           fs1_pre_press_active;
} bypass_seq_t;

void bypass_seq_init(bypass_seq_t *seq, bool startup_active);
void bypass_seq_set_target(bypass_seq_t *seq, bool active);
void bypass_seq_tick_2khz(bypass_seq_t *seq, bool pedal_pwr_good, bool fs1_pressed_raw);
bool bypass_seq_is_idle(const bypass_seq_t *seq);

#endif /* BEADS_BYPASS_SEQUENCER_H */
