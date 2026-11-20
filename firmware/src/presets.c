#include "presets.h"
#include "hal.h"
#include <string.h>

/* IEEE 802.3 CRC-32 (bitwise, zero RAM table bloat, identical across ARM & x86_64) */
uint32_t beads_crc32(const void *data, size_t len) {
    const uint8_t *p = (const uint8_t *)data;
    uint32_t crc = 0xFFFFFFFFu;
    for (size_t i = 0u; i < len; i++) {
        crc ^= (uint32_t)p[i];
        for (uint8_t b = 0u; b < 8u; b++) {
            uint32_t mask = (uint32_t)(-(int32_t)(crc & 1u));
            crc = (crc >> 1u) ^ (0xEDB88320u & mask);
        }
    }
    return ~crc;
}

static uint32_t compute_block_crc(const beads_nvm_block_t *blk) {
    return beads_crc32(blk, offsetof(beads_nvm_block_t, crc32));
}

static bool validate_block(const beads_nvm_block_t *blk) {
    if (blk->magic != BEADS_NVM_MAGIC) return false;
    if (blk->version != BEADS_NVM_VERSION) return false;
    if (blk->active_preset >= BEADS_NUM_PRESETS) return false;
    return (compute_block_crc(blk) == blk->crc32);
}

void preset_mgr_load_factory_defaults(beads_nvm_block_t *blk) {
    /* Zero entire struct BEFORE populating so zero implicit/explicit pad bytes vary */
    memset(blk, 0, sizeof(*blk));
    blk->magic = BEADS_NVM_MAGIC;
    blk->version = BEADS_NVM_VERSION;
    blk->active_preset = 0u;
    blk->write_seq = 1u;

    /* Loaded 1V/Oct calibration LUT across 10 octaves accounting for 1 kOhm / 100 kOhm
     * Eurorack input load divider (100/101 = 0.990099x -> 250.898 LSB / Volt loaded):
     * C0 = -2.0V (code 1543), C2 = 0.00V (code 2045), C9 = +7.0V (code 3801). */
    for (uint8_t ch = 0u; ch < BEADS_NUM_CV_CHANNELS; ch++) {
        for (uint8_t oct = 0u; oct < BEADS_CAL_OCTAVES; oct++) {
            uint32_t code = 1543u + ((uint32_t)oct * 250898u + 500u) / 1000u;
            if (code > 4095u) code = 4095u;
            blk->cal.oct_dac[ch][oct] = (uint16_t)code;
        }
    }

    /* Populate 32 musical factory presets (Preset 0 = "DRIFT CLOUD" standalone Beads workstation!) */
    for (uint8_t i = 0u; i < BEADS_NUM_PRESETS; i++) {
        beads_preset_t *pr = &blk->presets[i];
        memcpy(pr->name, "DRIFT_00    ", 12u);
        pr->name[6] = (char)('0' + (i / 10u));
        pr->name[7] = (char)('0' + (i % 10u));
        pr->startup_active = 1u;
        pr->midi_channel = 0u; /* Omni */
        pr->tap_bpm_x10 = 1200u;

        /* Default 8-channel Beads mapping:
         * CV1=TIME (Bezier), CV2=DENSITY (Bezier), CV3=SIZE (LFO Sine), CV4=SHAPE (LFO Tri),
         * CV5=PITCH (MIDI 1V/Oct), CV6=ASSIGN (Guitar Env), CV7=SEED (Euclidean Trig), CV8=FREEZE (FS2) */
        pr->ch[0] = (cv_channel_cfg_t){ CV_MODE_BEZIER_DRIFT, 0u, CV_SPAN_BIP_5V, 24u, 96u,  0, 0u, 0u };
        pr->ch[1] = (cv_channel_cfg_t){ CV_MODE_BEZIER_DRIFT, 0u, CV_SPAN_BIP_5V, 18u, 110u, 0, 0u, 0u };
        pr->ch[2] = (cv_channel_cfg_t){ CV_MODE_LFO, LFO_WAVE_SINE, CV_SPAN_BIP_5V, 32u, 0u, 0, 0u, 0u };
        pr->ch[3] = (cv_channel_cfg_t){ CV_MODE_LFO, LFO_WAVE_TRI,  CV_SPAN_BIP_5V, 20u, 32u, 0, 0u, 0u };
        pr->ch[4] = (cv_channel_cfg_t){ CV_MODE_MIDI_NOTE_1VOCT, 0u, CV_SPAN_BIP_8V, 0u, 0u, 0, 0u, 0u };
        pr->ch[5] = (cv_channel_cfg_t){ CV_MODE_GUITAR_ENV, 0u, CV_SPAN_UNI_5V, 16u, 48u, 0, 0u, 0u };
        pr->ch[6] = (cv_channel_cfg_t){ CV_MODE_RANDOM_TRIG, 0u, CV_SPAN_UNI_5V, 16u, 5u, 0, 1u, 0u };
        pr->ch[7] = (cv_channel_cfg_t){ CV_MODE_FS2_ACTION, 2u, CV_SPAN_UNI_5V, 0u, 0u, 0, 0u, 0u };
    }
    memcpy(blk->presets[0].name, "DRIFT CLOUD ", 12u);
    memcpy(blk->presets[1].name, "MIDI 1V/OCT ", 12u);
    memcpy(blk->presets[2].name, "GTR DUCKER  ", 12u);
    memcpy(blk->presets[3].name, "TIME SCRUB  ", 12u);
    blk->presets[3].ch[0] = (cv_channel_cfg_t){ CV_MODE_LFO, LFO_WAVE_RAMP_UP, CV_SPAN_BIP_8V, 40u, 0u, 0, 1u, 0u };

    blk->reserved_pad = 0u;
    blk->crc32 = compute_block_crc(blk);
}

void preset_mgr_init(preset_mgr_t *pm) {
    /* Static scratch avoids placing two 2740-byte structs on 4KB Core 1 stack! */
    static beads_nvm_block_t slot_a;
    static beads_nvm_block_t slot_b;

    memset(pm, 0, sizeof(*pm));
    bool ok_a = hal_flash_read(0u, &slot_a, sizeof(slot_a)) && validate_block(&slot_a);
    bool ok_b = hal_flash_read(1u, &slot_b, sizeof(slot_b)) && validate_block(&slot_b);

    if (ok_a && ok_b) {
        if ((int32_t)(slot_a.write_seq - slot_b.write_seq) >= 0) {
            pm->live = slot_a;
            pm->last_write_seq = slot_a.write_seq;
            pm->next_slot = 1u;
        } else {
            pm->live = slot_b;
            pm->last_write_seq = slot_b.write_seq;
            pm->next_slot = 0u;
        }
    } else if (ok_a) {
        pm->live = slot_a;
        pm->last_write_seq = slot_a.write_seq;
        pm->next_slot = 1u;
    } else if (ok_b) {
        pm->live = slot_b;
        pm->last_write_seq = slot_b.write_seq;
        pm->next_slot = 0u;
    } else {
        preset_mgr_load_factory_defaults(&pm->live);
        pm->last_write_seq = pm->live.write_seq;
        pm->next_slot = 0u;
    }
    pm->dirty = false;
}

void preset_mgr_mark_dirty(preset_mgr_t *pm) {
    pm->dirty = true;
}

const beads_preset_t *preset_mgr_get(const preset_mgr_t *pm, uint8_t idx) {
    if (idx >= BEADS_NUM_PRESETS) {
        idx = 0u;
    }
    return &pm->live.presets[idx];
}

/* Static frozen staging snapshot (avoids 2740 B stack allocation on Core 1!) */
static beads_nvm_block_t s_frozen_snap;

bool preset_mgr_try_stage_locked(preset_mgr_t *pm, bool bypass_idle, uint32_t now_ms,
                                 uint32_t last_non_rt_midi_ms, uint32_t *out_slot) {
    if (!pm->dirty) {
        return false;
    }
    /* Mandatory idle-deferred guard: ONLY stage QSPI Flash during BYP_STATE_IDLE
     * (with target_active == current_active) AND >= 300 ms of non-realtime MIDI silence!
     * Signed modular difference prevents unsigned wraparound bypass if now_ms < last_non_rt! */
    if (!bypass_idle) {
        return false;
    }
    if ((int32_t)(now_ms - last_non_rt_midi_ms) < 300) {
        return false;
    }

    memset(&s_frozen_snap, 0, sizeof(s_frozen_snap));
    s_frozen_snap = pm->live;
    pm->last_write_seq++;
    s_frozen_snap.magic = BEADS_NVM_MAGIC;
    s_frozen_snap.version = BEADS_NVM_VERSION;
    s_frozen_snap.write_seq = pm->last_write_seq;
    s_frozen_snap.reserved_pad = 0u;
    s_frozen_snap.crc32 = compute_block_crc(&s_frozen_snap);
    pm->live.write_seq = s_frozen_snap.write_seq;
    pm->live.crc32 = s_frozen_snap.crc32;
    pm->dirty = false;
    *out_slot = pm->next_slot & 1u;
    return true;
}

bool preset_mgr_commit_staged(preset_mgr_t *pm, uint32_t slot) {
    if (!hal_flash_erase_and_program(slot, &s_frozen_snap, sizeof(s_frozen_snap))) {
        hal_crit_enter();
        pm->dirty = true;
        hal_crit_exit();
        return false;
    }
    hal_crit_enter();
    pm->next_slot = slot ^ 1u;
    hal_crit_exit();
    return true;
}

bool preset_mgr_save_if_safe(preset_mgr_t *pm, bool bypass_idle, uint32_t now_ms, uint32_t last_non_rt_midi_ms) {
    uint32_t slot = 0u;
    hal_crit_enter();
    bool staged = preset_mgr_try_stage_locked(pm, bypass_idle, now_ms, last_non_rt_midi_ms, &slot);
    hal_crit_exit();
    if (!staged) {
        return false;
    }
    return preset_mgr_commit_staged(pm, slot);
}
