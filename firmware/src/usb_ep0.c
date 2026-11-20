#include "usb_ep0.h"
#include <string.h>

/* Device Descriptor (18 B): Miscellaneous EF/02/01 for IAD Composite Device */
const uint8_t BEADS_USB_DEV_DESC[18] = {
    18u, 0x01u,             /* bLength=18, bDescriptorType=DEVICE */
    0x00u, 0x02u,           /* bcdUSB = 2.00 */
    0xEFu, 0x02u, 0x01u,    /* bDeviceClass=Misc, SubClass=Common, Protocol=IAD */
    BEADS_USB_EP0_MAX_PKT,  /* bMaxPacketSize0 = 64 */
    0x8Au, 0x2Eu,           /* idVendor  = 0x2E8A (Raspberry Pi) */
    0x0Au, 0x00u,           /* idProduct = 0x000A (Beads Composite MIDI + CDC) */
    0x00u, 0x01u,           /* bcdDevice = 1.00 */
    1u, 2u, 0u,             /* iManufacturer=1, iProduct=2, iSerialNumber=0 */
    1u                      /* bNumConfigurations = 1 */
};

/* Composite Configuration Descriptor (exact 146 B):
 *   - Config Header (9 B)
 *   - IAD #1 (8 B): Audio/MIDI Function (IF0 + IF1)
 *     - IF0: AudioControl (9 B) + CS AC Header (9 B)                     = 18 B
 *     - IF1: MIDIStreaming (9 B) + CS MS Header (7 B) + IN Jack (6 B)
 *            + OUT Jack (9 B) + EP1 OUT Bulk (9 B) + CS EP1 OUT (5 B)    = 45 B
 *   - IAD #2 (8 B): CDC-ACM Function (IF2 + IF3)
 *     - IF2: CDC Comm (9 B) + Header (5 B) + CallMgmt (5 B) + ACM (4 B)
 *            + Union (5 B) + EP2 IN Int (7 B)                            = 35 B
 *     - IF3: CDC Data (9 B) + EP3 OUT Bulk (7 B) + EP3 IN Bulk (7 B)     = 23 B
 *   Total = 9 + 8 + 18 + 45 + 8 + 35 + 23 = 146 bytes exact!
 */
const uint8_t BEADS_USB_CFG_DESC[BEADS_USB_CFG_DESC_LEN] = {
    /* Configuration Descriptor (9 B) */
    9u, 0x02u,
    (uint8_t)(BEADS_USB_CFG_DESC_LEN & 0xFFu), (uint8_t)(BEADS_USB_CFG_DESC_LEN >> 8u),
    4u,                     /* bNumInterfaces = 4 (IF0..IF3) */
    1u,                     /* bConfigurationValue = 1 */
    0u,                     /* iConfiguration = 0 */
    0x80u,                  /* bmAttributes = Bus Powered */
    100u,                   /* bMaxPower = 200 mA */

    /* IAD #1: AudioControl (IF0) + MIDIStreaming (IF1) (8 B) */
    8u, 0x0Bu, 0u, 2u, 0x01u, 0x03u, 0x00u, 0u,

    /* IF0: Standard AudioControl Interface Descriptor (9 B) */
    9u, 0x04u, 0u, 0u, 0u, 0x01u, 0x01u, 0x00u, 0u,
    /* Class-Specific AC Interface Header Descriptor (9 B, wTotalLength = 9) */
    9u, 0x24u, 0x01u, 0x00u, 0x01u, 9u, 0x00u, 1u, 1u,

    /* IF1: Standard MIDIStreaming Interface Descriptor (9 B, 1 EP) */
    9u, 0x04u, 1u, 0u, 1u, 0x01u, 0x03u, 0x00u, 0u,
    /* Class-Specific MS Interface Header (7 B, wTotalLength = 7+6+9+9+5 = 36) */
    7u, 0x24u, 0x01u, 0x00u, 0x01u, 36u, 0x00u,
    /* MIDI IN Jack Descriptor — Embedded, Jack ID = 1 (6 B) */
    6u, 0x24u, 0x02u, 0x01u, 1u, 0u,
    /* MIDI OUT Jack Descriptor — External, Jack ID = 2, Src=1 (9 B) */
    9u, 0x24u, 0x03u, 0x02u, 2u, 1u, 1u, 1u, 0u,
    /* Standard Bulk OUT Endpoint EP1 OUT (0x01, 64 B) (9 B) */
    9u, 0x05u, 0x01u, 0x02u, 64u, 0x00u, 0u, 0u, 0u,
    /* Class-Specific MS Bulk OUT Endpoint Descriptor (5 B, AssocJack = 1) */
    5u, 0x25u, 0x01u, 1u, 1u,

    /* IAD #2: CDC ACM Control (IF2) + CDC Data (IF3) (8 B) */
    8u, 0x0Bu, 2u, 2u, 0x02u, 0x02u, 0x00u, 0u,

    /* IF2: CDC ACM Communication Interface (9 B, 1 Int IN EP) */
    9u, 0x04u, 2u, 0u, 1u, 0x02u, 0x02u, 0x00u, 0u,
    /* CDC Header Functional Descriptor (5 B, bcdCDC = 1.10) */
    5u, 0x24u, 0x00u, 0x10u, 0x01u,
    /* CDC Call Management Functional Descriptor (5 B, bDataInterface = 3) */
    5u, 0x24u, 0x01u, 0x00u, 3u,
    /* CDC ACM Functional Descriptor (4 B, supports Line Coding & Control Line State) */
    4u, 0x24u, 0x02u, 0x02u,
    /* CDC Union Functional Descriptor (5 B, Master=IF2, Slave=IF3) */
    5u, 0x24u, 0x06u, 2u, 3u,
    /* Standard Interrupt IN Endpoint EP2 IN (0x82, 8 B, 16 ms) (7 B) */
    7u, 0x05u, 0x82u, 0x03u, 8u, 0x00u, 16u,

    /* IF3: CDC Data Interface (9 B, 2 Bulk EPs) */
    9u, 0x04u, 3u, 0u, 2u, 0x0Au, 0x00u, 0x00u, 0u,
    /* Standard Bulk OUT Endpoint EP3 OUT (0x03, 64 B) (7 B) */
    7u, 0x05u, 0x03u, 0x02u, 64u, 0x00u, 0u,
    /* Standard Bulk IN Endpoint EP3 IN (0x83, 64 B) (7 B) */
    7u, 0x05u, 0x83u, 0x02u, 64u, 0x00u, 0u
};

_Static_assert(sizeof(BEADS_USB_DEV_DESC) == 18u, "Device descriptor must be 18 bytes");
_Static_assert(sizeof(BEADS_USB_CFG_DESC) == BEADS_USB_CFG_DESC_LEN, "Config descriptor length mismatch");

const uint8_t BEADS_USB_STR_LANG[4] = { 4u, 0x03u, 0x09u, 0x04u };

/* UTF-16LE "Beads Skiff" (11 chars -> 2 + 22 = 24? Wait: "Beads Bridge" = 12 chars -> 2 + 24 = 26 B) */
const uint8_t BEADS_USB_STR_MFR[26] = {
    26u, 0x03u,
    'B',0, 'e',0, 'a',0, 'd',0, 's',0, ' ',0, 'B',0, 'r',0, 'i',0, 'd',0, 'g',0, 'e',0
};

/* UTF-16LE "Beads Drift Bridge" (18 chars -> 2 + 36 = 38 B) */
const uint8_t BEADS_USB_STR_PROD[38] = {
    38u, 0x03u,
    'B',0, 'e',0, 'a',0, 'd',0, 's',0, ' ',0, 'D',0, 'r',0, 'i',0, 'f',0, 't',0,
    ' ',0, 'B',0, 'r',0, 'i',0, 'd',0, 'g',0, 'e',0
};

static void ep0_send_next_chunk(usb_ep0_state_t *st, const usb_ep0_hw_t *hw) {
    if (st->tx_rem > 0u) {
        uint16_t chunk = (st->tx_rem > BEADS_USB_EP0_MAX_PKT) ? BEADS_USB_EP0_MAX_PKT : st->tx_rem;
        const uint8_t *p = st->tx_ptr;
        st->tx_ptr += chunk;
        st->tx_rem = (uint16_t)(st->tx_rem - chunk);
        uint8_t pid = st->tx_pid;
        st->tx_pid ^= 1u;
        hw->ep0_tx(hw->ctx, p, chunk, pid);
        /* Once final payload packet (and any needed ZLP) is queued, arm OUT status ZLP */
        if (st->tx_rem == 0u && !st->tx_need_zlp) {
            st->tx_active = false;
            hw->ep0_rx_arm(hw->ctx, 0u, 1u);
        }
    } else if (st->tx_need_zlp) {
        st->tx_need_zlp = false;
        st->tx_active = false;
        uint8_t pid = st->tx_pid;
        st->tx_pid ^= 1u;
        hw->ep0_tx(hw->ctx, NULL, 0u, pid);
        hw->ep0_rx_arm(hw->ctx, 0u, 1u);
    } else {
        st->tx_active = false;
    }
}

static void ep0_start_in_transfer(usb_ep0_state_t *st, const uint8_t *data, uint16_t data_len,
                                  uint16_t req_len, const usb_ep0_hw_t *hw) {
    uint16_t xfer_len = (req_len < data_len) ? req_len : data_len;
    st->tx_ptr = data;
    st->tx_rem = xfer_len;
    st->tx_pid = 1u; /* First DATA stage packet after SETUP is always DATA1 */
    /* USB 2.0 §8.5.3.2: send trailing ZLP if transfer is shorter than wLength AND exact multiple of 64 B */
    st->tx_need_zlp = (xfer_len < req_len) && (xfer_len > 0u) && ((xfer_len & (BEADS_USB_EP0_MAX_PKT - 1u)) == 0u);
    st->tx_active = true;
    ep0_send_next_chunk(st, hw);
}

void usb_ep0_init(usb_ep0_state_t *st) {
    memset(st, 0, sizeof(*st));
    /* Default CDC Line Coding: 115200 8N1 (0x0001C200 LE) */
    st->line_coding[0] = 0x00u;
    st->line_coding[1] = 0xC2u;
    st->line_coding[2] = 0x01u;
    st->line_coding[3] = 0x00u;
    st->line_coding[4] = 0x00u; /* 1 stop bit */
    st->line_coding[5] = 0x00u; /* No parity */
    st->line_coding[6] = 0x08u; /* 8 data bits */
}

void usb_ep0_bus_reset(usb_ep0_state_t *st) {
    st->tx_ptr = NULL;
    st->tx_rem = 0u;
    st->tx_pid = 1u;
    st->tx_need_zlp = false;
    st->tx_active = false;
    st->pending_addr = 0u;
    st->config_val = 0u;
    st->expect_line_coding = false;
}

bool usb_ep0_is_busy(const usb_ep0_state_t *st) {
    return (st->pending_addr != 0u) || st->tx_active || st->expect_line_coding;
}

void usb_ep0_handle_setup(usb_ep0_state_t *st, const uint8_t setup[8], const usb_ep0_hw_t *hw) {
    uint8_t  bmReq = setup[0];
    uint8_t  bReq  = setup[1];
    uint16_t wVal  = (uint16_t)setup[2] | ((uint16_t)setup[3] << 8u);
    uint16_t wLen  = (uint16_t)setup[6] | ((uint16_t)setup[7] << 8u);

    /* Any new SETUP aborts previous in-flight EP0 transfer */
    st->tx_active = false;
    st->tx_rem = 0u;
    st->tx_need_zlp = false;
    st->expect_line_coding = false;

    if (bmReq == 0x80u && bReq == 0x06u) {
        /* Standard GET_DESCRIPTOR */
        uint8_t dtype = (uint8_t)(wVal >> 8u);
        uint8_t didx  = (uint8_t)(wVal & 0xFFu);
        if (dtype == 0x01u) {
            ep0_start_in_transfer(st, BEADS_USB_DEV_DESC, (uint16_t)sizeof(BEADS_USB_DEV_DESC), wLen, hw);
        } else if (dtype == 0x02u) {
            ep0_start_in_transfer(st, BEADS_USB_CFG_DESC, (uint16_t)sizeof(BEADS_USB_CFG_DESC), wLen, hw);
        } else if (dtype == 0x03u) {
            if (didx == 0u) {
                ep0_start_in_transfer(st, BEADS_USB_STR_LANG, (uint16_t)sizeof(BEADS_USB_STR_LANG), wLen, hw);
            } else if (didx == 1u) {
                ep0_start_in_transfer(st, BEADS_USB_STR_MFR, (uint16_t)sizeof(BEADS_USB_STR_MFR), wLen, hw);
            } else if (didx == 2u) {
                ep0_start_in_transfer(st, BEADS_USB_STR_PROD, (uint16_t)sizeof(BEADS_USB_STR_PROD), wLen, hw);
            } else {
                hw->ep0_stall(hw->ctx);
            }
        } else {
            hw->ep0_stall(hw->ctx);
        }
    } else if (bmReq == 0x00u && bReq == 0x05u) {
        /* SET_ADDRESS: latch hardware address AFTER status IN ZLP completes */
        st->pending_addr = (uint8_t)(wVal & 0x7Fu);
        hw->ep0_tx(hw->ctx, NULL, 0u, 1u);
    } else if (bmReq == 0x00u && bReq == 0x09u) {
        /* SET_CONFIGURATION */
        st->config_val = (uint8_t)(wVal & 0xFFu);
        hw->on_configured(hw->ctx, st->config_val);
        hw->ep0_tx(hw->ctx, NULL, 0u, 1u);
    } else if (bmReq == 0x80u && bReq == 0x08u) {
        /* GET_CONFIGURATION */
        ep0_start_in_transfer(st, &st->config_val, 1u, wLen, hw);
    } else if (bmReq == 0x80u && bReq == 0x00u) {
        /* GET_STATUS (Device) */
        static const uint8_t status_zero[2] = { 0u, 0u };
        ep0_start_in_transfer(st, status_zero, 2u, wLen, hw);
    } else if (bmReq == 0x21u && bReq == 0x20u && wLen >= 7u) {
        /* CDC SET_LINE_CODING: receive 7-byte payload on EP0 OUT (DATA1) */
        st->expect_line_coding = true;
        hw->ep0_rx_arm(hw->ctx, 64u, 1u);
    } else if (bmReq == 0xA1u && bReq == 0x21u) {
        /* CDC GET_LINE_CODING: return current 7-byte line coding */
        ep0_start_in_transfer(st, st->line_coding, 7u, wLen, hw);
    } else if (bmReq == 0x21u && bReq == 0x22u) {
        /* CDC SET_CONTROL_LINE_STATE: ACK via status ZLP */
        hw->ep0_tx(hw->ctx, NULL, 0u, 1u);
    } else if ((bmReq & 0x80u) == 0u && wLen == 0u) {
        /* Benign zero-length OUT request: ACK cleanly */
        hw->ep0_tx(hw->ctx, NULL, 0u, 1u);
    } else {
        hw->ep0_stall(hw->ctx);
    }
}

void usb_ep0_on_in_complete(usb_ep0_state_t *st, const usb_ep0_hw_t *hw) {
    if (st->pending_addr != 0u) {
        uint8_t addr = st->pending_addr;
        st->pending_addr = 0u;
        hw->set_address(hw->ctx, addr);
        return;
    }
    if (st->tx_active) {
        ep0_send_next_chunk(st, hw);
    }
}

void usb_ep0_on_out_complete(usb_ep0_state_t *st, const uint8_t *rx_buf, uint16_t rx_len, const usb_ep0_hw_t *hw) {
    if (st->expect_line_coding) {
        st->expect_line_coding = false;
        if (rx_len >= 7u) {
            memcpy(st->line_coding, rx_buf, 7u);
        }
        uint32_t baud = (uint32_t)st->line_coding[0] |
                        ((uint32_t)st->line_coding[1] << 8u) |
                        ((uint32_t)st->line_coding[2] << 16u) |
                        ((uint32_t)st->line_coding[3] << 24u);
        /* Always ACK SET_LINE_CODING status stage first */
        hw->ep0_tx(hw->ctx, NULL, 0u, 1u);
        if (baud == 1200u) {
            hw->on_1200baud_reset(hw->ctx);
        }
    }
}

void usb_vbus_init(usb_vbus_state_t *vs) {
    vs->attached = false;
}

bool usb_vbus_sync(usb_vbus_state_t *vs, const usb_vbus_hw_t *hw) {
    bool vbus = hw->read_vbus_det(hw->ctx);

    if (!vs->attached) {
        if (vbus) {
            vs->attached = true;
            hw->on_attach(hw->ctx);
        } else {
            /* Keep PULLUP_EN strictly 0 whenever VBUS_DET is LOW (< 1 uA backfeed!) */
            hw->set_pullup(hw->ctx, false);
        }
        return vs->attached;
    }

    /* Currently attached: D_ESD_VP (1N4148W) reverse-isolates U_USB_ESD Pin 5 (ESD_VP)
     * from USB_VBUS, so VBUS_DET drops immediately to 0V on hot-unplug even with PULLUP_EN=1.
     * PULLUP_EN stays continuously asserted throughout USB Suspend (zero SE0 T_DDIS violation!). */
    if (!vbus) {
        vs->attached = false;
        hw->on_detach(hw->ctx);
        return false;
    }
    return true;
}
