#ifndef BEADS_PRESETS_H
#define BEADS_PRESETS_H

#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include "board_pins.h"

#define BEADS_NVM_MAGIC   0x42454144u /* 'BEAD' */
#define BEADS_NVM_VERSION 1u

typedef enum {
    CV_MODE_BEZIER_DRIFT    = 0,
    CV_MODE_LFO             = 1,
    CV_MODE_RANDOM_TRIG     = 2,
    CV_MODE_MIDI_NOTE_1VOCT = 3,
    CV_MODE_MIDI_GATE_TRIG  = 4,
    CV_MODE_MIDI_CLOCK_DIV  = 5,
    CV_MODE_MIDI_CC         = 6,
    CV_MODE_GUITAR_ENV      = 7,
    CV_MODE_GUITAR_PLUCK    = 8,
    CV_MODE_FS2_ACTION      = 9
} cv_mode_t;

typedef enum {
    LFO_WAVE_SINE    = 0,
    LFO_WAVE_TRI     = 1,
    LFO_WAVE_RAMP_UP = 2,
    LFO_WAVE_RAMP_DN = 3,
    LFO_WAVE_SQUARE  = 4,
    LFO_WAVE_SLEW_SH = 5
} lfo_wave_t;

typedef enum {
    CV_SPAN_BIP_8V  = 0, /* -8.0V .. +8.0V */
    CV_SPAN_BIP_5V  = 1, /* -5.0V .. +5.0V */
    CV_SPAN_BIP_2V5 = 2, /* -2.5V .. +2.5V */
    CV_SPAN_UNI_5V  = 3, /*  0.0V .. +5.0V */
    CV_SPAN_UNI_8V  = 4  /*  0.0V .. +8.0V */
} cv_span_t;

/* Explicit fixed-size ABI struct — zero implicit padding! */
typedef struct {
    uint8_t  mode;          /* cv_mode_t */
    uint8_t  sub_mode;      /* lfo_wave_t / clock div / MIDI CC # / FS2 mode */
    uint8_t  span;          /* cv_span_t */
    uint8_t  param_a;       /* Rate / Euclidean steps / Attack / Glide (0..127) */
    uint8_t  param_b;       /* Tension / Euclidean hits / Release / Phase (0..127) */
    int8_t   offset_pct;    /* Center offset (-100 .. +100) */
    uint8_t  clock_sync;    /* 0 = Free, 1 = Sync to MIDI/Tap Clock */
    uint8_t  reserved_pad;  /* Explicit zero padding */
} cv_channel_cfg_t;

typedef struct {
    char             name[12];
    uint8_t          startup_active; /* 0 = Bypass, 1 = Active */
    uint8_t          midi_channel;   /* 0 = Omni, 1..16 */
    uint16_t         tap_bpm_x10;    /* e.g. 1200 = 120.0 BPM */
    cv_channel_cfg_t ch[BEADS_NUM_CV_CHANNELS];
} beads_preset_t;

/* Calibration table: 10 octave knots (C0..C9, 0V..9V mapped into +-8.2V -> C0=-4V .. C8=+4V or 0V..8V!)
 * Stored as exact 12-bit MCP4822 DAC codes per octave knot for all 8 CV channels. */
typedef struct {
    uint16_t oct_dac[BEADS_NUM_CV_CHANNELS][BEADS_CAL_OCTAVES];
} beads_cal_lut_t;

/* Full dual-slot A/B persisted NVM image (fits cleanly inside one 4096-byte QSPI Flash sector!) */
typedef struct {
    uint32_t        magic;
    uint16_t        version;
    uint16_t        active_preset;
    uint32_t        write_seq;
    beads_cal_lut_t cal;
    beads_preset_t  presets[BEADS_NUM_PRESETS];
    uint32_t        reserved_pad;
    uint32_t        crc32;
} beads_nvm_block_t;

_Static_assert(sizeof(cv_channel_cfg_t) == 8u, "cv_channel_cfg_t size mismatch");
_Static_assert(sizeof(beads_preset_t) == 80u, "beads_preset_t size mismatch");
_Static_assert(sizeof(beads_cal_lut_t) == 160u, "beads_cal_lut_t size mismatch");
_Static_assert(sizeof(beads_nvm_block_t) == 2740u, "beads_nvm_block_t ABI padding mismatch");
_Static_assert(offsetof(beads_nvm_block_t, crc32) == sizeof(beads_nvm_block_t) - 4u, "crc32 must be tail");
_Static_assert(sizeof(beads_nvm_block_t) <= 4096u, "NVM block must fit inside 4KB QSPI sector");

typedef struct {
    beads_nvm_block_t live;
    uint32_t          last_write_seq;
    uint32_t          next_slot;
    bool              dirty;
} preset_mgr_t;

uint32_t beads_crc32(const void *data, size_t len);
void     preset_mgr_load_factory_defaults(beads_nvm_block_t *blk);
void     preset_mgr_init(preset_mgr_t *pm);
bool     preset_mgr_try_stage_locked(preset_mgr_t *pm, bool bypass_idle, uint32_t now_ms,
                                     uint32_t last_non_rt_midi_ms, uint32_t *out_slot);
bool     preset_mgr_commit_staged(preset_mgr_t *pm, uint32_t slot);
bool     preset_mgr_save_if_safe(preset_mgr_t *pm, bool bypass_idle, uint32_t now_ms, uint32_t last_non_rt_midi_ms);
void     preset_mgr_mark_dirty(preset_mgr_t *pm);
const beads_preset_t *preset_mgr_get(const preset_mgr_t *pm, uint8_t idx);

#endif /* BEADS_PRESETS_H */
