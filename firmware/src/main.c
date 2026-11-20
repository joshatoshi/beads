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

static void beads_core1_pump_usb(void) {
    hal_usb_task_on_core1();
    uint8_t pkt4[4];
    while (hal_usb_midi_read_packet(pkt4)) {
        (void)midi_router_usb_push_packet(&g_midi, pkt4);
    }
}

void beads_core1_service_slice(uint32_t now_ms) {
    /* 1. Continuous USB EP0/MIDI service on Core 1 (< 500 us max latency << 2.0 ms t_DSETADDR!) */
    beads_core1_pump_usb();

    /* 2. Consume encoder / button events safely under critical section */
    int32_t enc_d = 0;
    bool enc_c = false;
    bool back_c = false;

    hal_crit_enter();
    enc_d = g_engine.enc_delta_accum;
    g_engine.enc_delta_accum = 0;
    enc_c = g_engine.enc_sw_click_ev;
    g_engine.enc_sw_click_ev = false;
    back_c = g_engine.back_click_ev;
    g_engine.back_click_ev = false;
    hal_crit_exit();

    bool input_ev = (enc_d != 0) || enc_c || back_c;
    if (input_ev) {
        oled_ui_handle_inputs(&g_ui, enc_d, enc_c, back_c, &g_engine, &g_bypass, &g_midi, &g_presets);
    }

    /* 3. Rate-gated UI render (>= 2000 us timer or input event) + EP0-deferred 16-byte chunked I2C flush:
     *    - Defers OLED I2C completely while any EP0 control transfer is active (SET_ADDRESS / GET_DESCRIPTOR / CDC)
     *    - Transmits at most ONE 16-byte SSD1306 chunk (~405 us @ 400 kHz) per slice, then immediately re-polls USB! */
    uint32_t now_us = hal_time_us_32();
    if (!g_ui.rendered_once || input_ev || ((uint32_t)(now_us - g_ui.last_render_us) >= UI_RENDER_PERIOD_US)) {
        bool vbus = hal_gpio_read(PIN_VBUS_DET);
        hal_crit_enter();
        oled_ui_render(&g_ui, &g_engine, &g_bypass, &g_presets, vbus);
        hal_crit_exit();
        g_ui.rendered_once = true;
        g_ui.last_render_us = now_us;
    }

    if (g_ui.dirty && !hal_usb_ep0_is_busy()) {
        (void)oled_ui_flush_step(&g_ui);
        beads_core1_pump_usb();
    }

    /* 4. Idle-deferred dual-slot A/B CRC32 QSPI Flash save:
     * Re-sample live bypass_seq_is_idle(&g_bypass), pending MIDI bypass/preset & ring flags,
     * fresh monotonic now_ms = (g_engine.tick_count >> 1u), and fresh g_midi.last_non_rt_ms
     * atomically inside hal_crit_enter() right before staging the frozen snapshot (zero TOCTOU!). */
    (void)now_ms;
    uint32_t flash_slot = 0u;
    bool should_commit_flash = false;
    hal_crit_enter();
    uint32_t fresh_now_ms = g_engine.tick_count >> 1u;
    bool midi_idle = !g_midi.bypass_req_valid &&
                     !g_midi.preset_req_valid &&
                     (g_midi.uart_ring.head == g_midi.uart_ring.tail) &&
                     (g_midi.usb_ring.head == g_midi.usb_ring.tail);
    bool byp_idle_now = bypass_seq_is_idle(&g_bypass) && midi_idle;
    uint32_t fresh_last_non_rt = g_midi.last_non_rt_ms;
    should_commit_flash = preset_mgr_try_stage_locked(
        &g_presets, byp_idle_now, fresh_now_ms, fresh_last_non_rt, &flash_slot
    );
    hal_crit_exit();
    if (should_commit_flash) {
        (void)preset_mgr_commit_staged(&g_presets, flash_slot);
    }
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

#ifdef BEADS_HOST_UNIT_TEST
cv_engine_t   *beads_test_get_engine(void)  { return &g_engine; }
bypass_seq_t  *beads_test_get_bypass(void)  { return &g_bypass; }
midi_router_t *beads_test_get_midi(void)    { return &g_midi; }
preset_mgr_t  *beads_test_get_presets(void) { return &g_presets; }
oled_ui_t     *beads_test_get_ui(void)      { return &g_ui; }
#endif

#ifndef BEADS_HOST_UNIT_TEST
/* Target RP2040 entrypoint (also supports Pico SDK multicore_launch_core1 when built with PICO_SDK) */
extern void rp2040_launch_core1(void (*entry)(void));
extern void rp2040_core0_service_lockout(void);

static void core1_entry(void) {
    hal_usb_init_on_core1();
    oled_ui_init(&g_ui);
    for (;;) {
        /* Continuous non-blocking Core 1 USB + chunked-OLED loop (zero blocking delay_us,
         * guaranteeing < 500 us worst-case USB SET_ADDRESS recovery << 2.0 ms USB 2.0 §9.2.6.3!) */
        hal_crit_enter();
        uint32_t shared_now_ms = g_engine.tick_count >> 1u;
        hal_crit_exit();
        beads_core1_service_slice(shared_now_ms);
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
