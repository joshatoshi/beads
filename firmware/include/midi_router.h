#ifndef BEADS_MIDI_ROUTER_H
#define BEADS_MIDI_ROUTER_H

#include <stdbool.h>
#include <stdint.h>

#define MIDI_RING_SIZE 128u  /* Power of 2 for lock-free mask */

/* Bit 8 in UART SPSC ring entry flags an in-band overflow/error recovery boundary */
#define MIDI_ENTRY_OVERFLOW_BIT 0x0100u

typedef struct {
    volatile uint16_t buf[MIDI_RING_SIZE];
    volatile uint32_t head;
    volatile uint32_t tail;
    volatile bool     overflow_latched;
} midi_spsc_u16_t;

typedef struct {
    volatile uint32_t buf[MIDI_RING_SIZE];
    volatile uint32_t head;
    volatile uint32_t tail;
} midi_spsc_usb_t;

typedef struct {
    uint8_t  status;
    uint8_t  data[2];
    uint8_t  expected;
    uint8_t  idx;
    uint8_t  rx_channel;        /* 0 = Omni, 1..16 = specific channel */
    bool     in_sysex;
    uint32_t err_count;
    uint32_t non_rt_last_ms;    /* Timestamp of last NON-realtime (< 0xF8) MIDI byte */
} midi_parser_t;

typedef struct {
    uint8_t  active_note;
    uint8_t  active_vel;
    bool     gate_high;
    bool     retrig_pulse;
    int16_t  pitch_bend;        /* -8192 .. +8191 */
    uint8_t  aftertouch;        /* 0 .. 127 */
    uint8_t  cc[128];
    bool     bypass_req_valid;
    bool     bypass_req_active;
    bool     preset_req_valid;
    uint8_t  preset_req_idx;
    bool     clock_pulse;
    bool     transport_run;
    uint32_t clock_tick_count;
    uint32_t last_clock_us;
    uint32_t clock_period_us;   /* 24 PPQN tick period */
    uint32_t last_non_rt_ms;    /* For QSPI Flash idle-silence guard */
    midi_parser_t uart_parser;
    midi_spsc_u16_t uart_ring;
    midi_spsc_usb_t usb_ring;
} midi_router_t;

void midi_router_init(midi_router_t *mr, uint8_t rx_channel);
void midi_router_set_channel(midi_router_t *mr, uint8_t rx_channel);

/* Producer side (UART0 RX ISR / Core 1 USB-MIDI poll) */
void midi_router_uart_push_dr(midi_router_t *mr, uint16_t uart_dr);
bool midi_router_usb_push_packet(midi_router_t *mr, const uint8_t pkt4[4]);

/* Consumer side (Core 0 2 kHz tick) */
void midi_router_poll_core0(midi_router_t *mr, uint32_t now_us, uint32_t now_ms);
void midi_router_feed_uart_byte(midi_router_t *mr, uint8_t byte, bool err_or_ovf, uint32_t now_us, uint32_t now_ms);
void midi_router_feed_usb_packet(midi_router_t *mr, const uint8_t pkt4[4], uint32_t now_us, uint32_t now_ms);

#endif /* BEADS_MIDI_ROUTER_H */
