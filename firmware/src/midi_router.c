#include "midi_router.h"
#include "hal.h"
#include <string.h>

#if defined(__ARM_ARCH)
#define BEADS_SMP_MB() __asm__ volatile("dmb" ::: "memory")
#else
#define BEADS_SMP_MB() __asm__ volatile("" ::: "memory")
#endif

static uint8_t expected_data_bytes(uint8_t status) {
    uint8_t hi = status & 0xF0u;
    if (hi == 0xC0u || hi == 0xD0u) return 1u;
    if (hi >= 0x80u && hi <= 0xE0u) return 2u;
    if (status == 0xF1u || status == 0xF3u) return 1u;
    if (status == 0xF2u) return 2u;
    return 0u;
}

void midi_router_init(midi_router_t *mr, uint8_t rx_channel) {
    memset(mr, 0, sizeof(*mr));
    mr->uart_parser.rx_channel = rx_channel;
    mr->active_note = 60u;          /* Middle C */
    mr->clock_period_us = 20833u;   /* 120 BPM @ 24 PPQN */
}

void midi_router_set_channel(midi_router_t *mr, uint8_t rx_channel) {
    /* Reset Running Status on runtime MIDI channel change (HARDWARE_LESSONS.md!) */
    mr->uart_parser.rx_channel = (rx_channel <= 16u) ? rx_channel : 0u;
    mr->uart_parser.status = 0u;
    mr->uart_parser.idx = 0u;
    mr->uart_parser.expected = 0u;
}

static void dispatch_realtime(midi_router_t *mr, uint8_t rt, uint32_t now_us) {
    if (rt == 0xF8u) {
        /* 24 PPQN MIDI Clock */
        if (mr->last_clock_us != 0u) {
            uint32_t dt = now_us - mr->last_clock_us;
            if (dt >= 4000u && dt <= 250000u) {
                /* Smoothed clock period */
                mr->clock_period_us = (mr->clock_period_us * 3u + dt + 2u) >> 2u;
            }
        }
        mr->last_clock_us = now_us;
        mr->clock_pulse = true;
        mr->clock_tick_count++;
    } else if (rt == 0xFAu || rt == 0xFBu) {
        mr->transport_run = true;
        if (rt == 0xFAu) {
            mr->clock_tick_count = 0u;
        }
    } else if (rt == 0xFCu) {
        mr->transport_run = false;
    } else if (rt == 0xFFu) {
        /* 0xFF System Reset: MUST clear Running Status and release latched gates! */
        mr->uart_parser.status = 0u;
        mr->uart_parser.idx = 0u;
        mr->uart_parser.expected = 0u;
        mr->uart_parser.in_sysex = false;
        mr->gate_high = false;
        mr->transport_run = false;
    }
}

static void dispatch_channel_msg(midi_router_t *mr, uint8_t status, uint8_t d0, uint8_t d1) {
    uint8_t ch_1based = (uint8_t)((status & 0x0Fu) + 1u);
    if (mr->uart_parser.rx_channel != 0u && ch_1based != mr->uart_parser.rx_channel) {
        return;
    }
    uint8_t cmd = status & 0xF0u;
    switch (cmd) {
        case 0x90u: /* Note On (vel == 0 is Note Off) */
            if (d1 > 0u) {
                mr->active_note = d0 & 0x7Fu;
                mr->active_vel  = d1 & 0x7Fu;
                mr->gate_high   = true;
                mr->retrig_pulse = true;
            } else if ((d0 & 0x7Fu) == mr->active_note) {
                mr->gate_high = false;
            }
            break;
        case 0x80u: /* Note Off */
            if ((d0 & 0x7Fu) == mr->active_note) {
                mr->gate_high = false;
            }
            break;
        case 0xB0u: { /* Control Change */
            uint8_t cc_num = d0 & 0x7Fu;
            uint8_t cc_val = d1 & 0x7Fu;
            mr->cc[cc_num] = cc_val;
            if (cc_num == 102u) {
                /* CC #102: Popless Bypass Control (>=64 Active, <64 True Bypass) */
                mr->bypass_req_valid = true;
                mr->bypass_req_active = (cc_val >= 64u);
            } else if (cc_num == 120u || cc_num == 123u) {
                /* All Sound Off / All Notes Off */
                mr->gate_high = false;
            }
            break;
        }
        case 0xC0u: /* Program Change -> Recall Flash Preset 0..31 */
            mr->preset_req_valid = true;
            mr->preset_req_idx = (uint8_t)(d0 & 0x1Fu);
            break;
        case 0xD0u: /* Channel Aftertouch */
            mr->aftertouch = d0 & 0x7Fu;
            break;
        case 0xE0u: { /* Pitch Bend (14-bit centered at 8192) */
            int32_t raw14 = (int32_t)(d0 & 0x7Fu) | ((int32_t)(d1 & 0x7Fu) << 7);
            mr->pitch_bend = (int16_t)(raw14 - 8192);
            break;
        }
        default:
            break;
    }
}

void midi_router_uart_push_dr(midi_router_t *mr, uint16_t uart_dr) {
    /* Inspect PL011 UARTDR error bits [11:8] (OE=11, BE=10, PE=9, FE=8) */
    bool hw_err = ((uart_dr & 0x0F00u) != 0u);
    if (hw_err) {
        hal_uart0_clear_rsr();
        mr->uart_ring.overflow_latched = true;
        return;
    }
    uint32_t head = mr->uart_ring.head;
    uint32_t next = (head + 1u) & (MIDI_RING_SIZE - 1u);
    if (next == mr->uart_ring.tail) {
        /* Ring overflow: latch in-band overflow marker for the next accepted byte! */
        mr->uart_ring.overflow_latched = true;
        return;
    }
    uint16_t entry = (uint16_t)(uart_dr & 0x00FFu);
    if (mr->uart_ring.overflow_latched) {
        entry |= MIDI_ENTRY_OVERFLOW_BIT;
        mr->uart_ring.overflow_latched = false;
    }
    mr->uart_ring.buf[head] = entry;
    BEADS_SMP_MB();
    mr->uart_ring.head = next;
}

bool midi_router_usb_push_packet(midi_router_t *mr, const uint8_t pkt4[4]) {
    uint32_t head = mr->usb_ring.head;
    uint32_t next = (head + 1u) & (MIDI_RING_SIZE - 1u);
    if (next == mr->usb_ring.tail) {
        return false;
    }
    uint32_t packed = ((uint32_t)pkt4[0]) |
                      ((uint32_t)pkt4[1] << 8u) |
                      ((uint32_t)pkt4[2] << 16u) |
                      ((uint32_t)pkt4[3] << 24u);
    mr->usb_ring.buf[head] = packed;
    BEADS_SMP_MB();
    mr->usb_ring.head = next;
    return true;
}

void midi_router_feed_uart_byte(midi_router_t *mr, uint8_t byte, bool err_or_ovf,
                                uint32_t now_us, uint32_t now_ms) {
    midi_parser_t *p = &mr->uart_parser;
    if (err_or_ovf) {
        /* Reset Running Status immediately on in-band UART error / ring overflow! */
        p->status = 0u;
        p->idx = 0u;
        p->expected = 0u;
        p->in_sysex = false;
        p->err_count++;
    }

    /* Real-time messages (>= 0xF8) do NOT alter Running Status and do NOT refresh Flash silence guard! */
    if (byte >= 0xF8u) {
        dispatch_realtime(mr, byte, now_us);
        return;
    }

    /* Non-realtime byte: refresh Flash-save idle guard timestamp */
    mr->last_non_rt_ms = now_ms;
    p->non_rt_last_ms = now_ms;

    if (byte == 0xF0u) {
        p->in_sysex = true;
        p->status = 0u;
        p->idx = 0u;
        p->expected = 0u;
        return;
    }
    if (byte == 0xF7u) {
        p->in_sysex = false;
        return;
    }
    if ((byte & 0x80u) != 0u) {
        /* Status byte 0x80..0xF6 */
        p->in_sysex = false;
        if (byte >= 0xF0u) {
            /* System Common clears Running Status per MIDI 1.0 spec */
            p->status = 0u;
            p->expected = expected_data_bytes(byte);
            p->idx = 0u;
        } else {
            p->status = byte;
            p->expected = expected_data_bytes(byte);
            p->idx = 0u;
        }
        return;
    }

    /* Data byte 0x00..0x7F */
    if (p->in_sysex || p->status == 0u || p->expected == 0u) {
        return;
    }
    p->data[p->idx++] = byte;
    if (p->idx >= p->expected) {
        uint8_t d0 = p->data[0];
        uint8_t d1 = (p->expected >= 2u) ? p->data[1] : 0u;
        p->idx = 0u; /* Retain p->status for valid Running Status */
        dispatch_channel_msg(mr, p->status, d0, d1);
    }
}

void midi_router_feed_usb_packet(midi_router_t *mr, const uint8_t pkt4[4],
                                 uint32_t now_us, uint32_t now_ms) {
    /* USB-MIDI 4-byte Event Packet (CIN = pkt4[0] & 0x0F).
     * Strictly isolated from UART Running-Status state! */
    uint8_t cin = pkt4[0] & 0x0Fu;
    uint8_t b0 = pkt4[1];
    uint8_t b1 = pkt4[2];
    uint8_t b2 = pkt4[3];

    if (cin == 0x0Fu) {
        /* Single-byte packet: handle >=0xF8 real-time ONLY; ignore <0xF8 so shared UART RS stays isolated! */
        if (b0 >= 0xF8u) {
            dispatch_realtime(mr, b0, now_us);
        } else {
            mr->last_non_rt_ms = now_ms;
        }
        return;
    }
    if (cin == 0x05u && b0 >= 0xF8u) {
        dispatch_realtime(mr, b0, now_us);
        return;
    }

    mr->last_non_rt_ms = now_ms;
    switch (cin) {
        case 0x08u: /* Note Off */
        case 0x09u: /* Note On */
        case 0x0Bu: /* Control Change */
        case 0x0Eu: /* Pitch Bend */
            dispatch_channel_msg(mr, b0, b1, b2);
            break;
        case 0x0Cu: /* Program Change */
        case 0x0Du: /* Channel Aftertouch */
            dispatch_channel_msg(mr, b0, b1, 0u);
            break;
        default:
            break;
    }
}

void midi_router_poll_core0(midi_router_t *mr, uint32_t now_us, uint32_t now_ms) {
    /* First drain PL011 hardware RX FIFO into SPSC ring (if polled in addition to ISR) */
    uint16_t dr = 0u;
    uint8_t guard = 0u;
    while (guard < 32u && hal_uart0_try_read_dr(&dr)) {
        midi_router_uart_push_dr(mr, dr);
        guard++;
    }

    /* Drain UART SPSC ring */
    while (mr->uart_ring.tail != mr->uart_ring.head) {
        BEADS_SMP_MB();
        uint32_t tail = mr->uart_ring.tail;
        uint16_t entry = mr->uart_ring.buf[tail];
        BEADS_SMP_MB();
        mr->uart_ring.tail = (tail + 1u) & (MIDI_RING_SIZE - 1u);
        midi_router_feed_uart_byte(
            mr,
            (uint8_t)(entry & 0xFFu),
            (entry & MIDI_ENTRY_OVERFLOW_BIT) != 0u,
            now_us,
            now_ms
        );
    }

    /* Drain USB-MIDI SPSC ring */
    while (mr->usb_ring.tail != mr->usb_ring.head) {
        BEADS_SMP_MB();
        uint32_t tail = mr->usb_ring.tail;
        uint32_t packed = mr->usb_ring.buf[tail];
        BEADS_SMP_MB();
        mr->usb_ring.tail = (tail + 1u) & (MIDI_RING_SIZE - 1u);
        uint8_t pkt4[4] = {
            (uint8_t)(packed & 0xFFu),
            (uint8_t)((packed >> 8u) & 0xFFu),
            (uint8_t)((packed >> 16u) & 0xFFu),
            (uint8_t)((packed >> 24u) & 0xFFu),
        };
        midi_router_feed_usb_packet(mr, pkt4, now_us, now_ms);
    }
}
