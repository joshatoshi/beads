#include "board_pins.h"
#include "hal.h"
#include "bypass_sequencer.h"
#include "cv_engine.h"
#include "dac_mcp4822.h"
#include "midi_router.h"
#include "oled_ui.h"
#include "presets.h"

/* Global dual-core state (all shared cross-core accesses guarded by hal_crit_enter/exit!) */
static bypass_seq_t  g_bypass;
static dac_bank_t    g_dacs;
static midi_router_t g_midi;
static preset_mgr_t  g_presets;
static cv_engine_t   g_engine;
static oled_ui_t     g_ui;

/* Exposed hooks so Core 0 timer ISR and Core 1 main loop are testable on both RP2040 and host */
void beads_core0_tick_handler(void) {
    uint32_t now_us = hal_time_us_32();
    hal_crit_enter();
    cv_engine_tick_2khz(&g_engine, &g_bypass, &g_dacs, &g_midi, &g_presets, now_us);
    hal_crit_exit();
}

void beads_core1_service_slice(uint32_t now_ms) {
    /* 1. TinyUSB task & USB-MIDI RX pump on Core 1 (same core as hal_usb_init_on_core1!) */
    hal_usb_task_on_core1();
    uint8_t pkt4[4];
    while (hal_usb_midi_read_packet(pkt4)) {
        (void)midi_router_usb_push_packet(&g_midi, pkt4);
    }

    /* 2. Consume encoder / button events safely under critical section */
    int32_t enc_d = 0;
    bool enc_c = false;
    bool back_c = false;
    bool byp_idle = false;
    uint32_t last_non_rt = 0u;

    hal_crit_enter();
    enc_d = g_engine.enc_delta_accum;
    g_engine.enc_delta_accum = 0;
    enc_c = g_engine.enc_sw_click_ev;
    g_engine.enc_sw_click_ev = false;
    back_c = g_engine.back_click_ev;
    g_engine.back_click_ev = false;
    byp_idle = bypass_seq_is_idle(&g_bypass);
    last_non_rt = g_midi.last_non_rt_ms;
    hal_crit_exit();

    oled_ui_handle_inputs(&g_ui, enc_d, enc_c, back_c, &g_engine, &g_presets);

    /* 3. Render (under lock snapshot) & flush 1 page slice of SSD1306 (bounded I2C timeout) */
    bool vbus = hal_gpio_read(PIN_VBUS_DET);
    hal_crit_enter();
    oled_ui_render(&g_ui, &g_engine, &g_bypass, vbus);
    hal_crit_exit();
    (void)oled_ui_flush_one_page(&g_ui);

    /* 4. Idle-deferred dual-slot A/B CRC32 QSPI Flash save (only when BYP_STATE_IDLE & >=300ms silence!) */
    (void)preset_mgr_save_if_safe(&g_presets, byp_idle, now_ms, last_non_rt);
}

void beads_app_init(void) {
    hal_init();
    preset_mgr_init(&g_presets);
    uint8_t boot_idx = (uint8_t)g_presets.live.active_preset;
    const beads_preset_t *boot_preset = preset_mgr_get(&g_presets, boot_idx);

    bypass_seq_init(&g_bypass, boot_preset->startup_active != 0u);
    dac_bank_init(&g_dacs);
    midi_router_init(&g_midi, boot_preset->midi_channel);
    cv_engine_init(&g_engine, boot_preset, boot_idx, &g_presets.live.cal);
}

#ifndef BEADS_HOST_UNIT_TEST
/* Target RP2040 entrypoint (also supports Pico SDK multicore_launch_core1 when built with PICO_SDK) */
extern void rp2040_launch_core1(void (*entry)(void));
extern void rp2040_delay_us(uint32_t us);
extern void rp2040_core0_service_lockout(void);

static void core1_entry(void) {
    hal_usb_init_on_core1();
    oled_ui_init(&g_ui);
    for (;;) {
        /* Share exact Core 0 monotonic millisecond timebase -> zero drift or underflow! */
        hal_crit_enter();
        uint32_t shared_now_ms = g_engine.tick_count >> 1u;
        hal_crit_exit();
        beads_core1_service_slice(shared_now_ms);
        rp2040_delay_us(2000u);
    }
}

int main(void) {
    beads_app_init();
    rp2040_launch_core1(core1_entry);

    /* Core 0 positive-delay 2.0 kHz real-time scheduler (zero catchup bursts after flash lockouts!) */
    uint32_t next_us = hal_time_us_32() + CORE0_TICK_US;
    for (;;) {
        rp2040_core0_service_lockout();
        uint32_t now = hal_time_us_32();
        if ((int32_t)(now - next_us) >= 0) {
            beads_core0_tick_handler();
            next_us = hal_time_us_32() + CORE0_TICK_US; /* Positive post-execution delay! */
        }
    }
}
#endif
