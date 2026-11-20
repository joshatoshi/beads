#ifndef BEADS_USB_EP0_H
#define BEADS_USB_EP0_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

/* ============================================================================
 * Composite USB 2.0 Device Descriptors (USB-MIDI 1.0 + CDC-ACM 1.2)
 * and Multi-Packet EP0 IN/OUT Control Transfer Engine
 *
 * Shared between bare-metal RP2040 target HAL (rp2040_hal.c) and host unit
 * tests (test_beads_firmware.c) so every descriptor byte and multi-packet EP0
 * continuation path is verified with 100% assertion coverage.
 * ============================================================================ */

#define BEADS_USB_EP0_MAX_PKT     64u
#define BEADS_USB_CFG_DESC_LEN    146u

extern const uint8_t BEADS_USB_DEV_DESC[18];
extern const uint8_t BEADS_USB_CFG_DESC[BEADS_USB_CFG_DESC_LEN];
extern const uint8_t BEADS_USB_STR_LANG[4];
extern const uint8_t BEADS_USB_STR_MFR[26];
extern const uint8_t BEADS_USB_STR_PROD[38];

/* Hardware transport callbacks invoked by usb_ep0_* */
typedef struct {
    void (*ep0_tx)(void *ctx, const uint8_t *data, uint16_t len, uint8_t pid);
    void (*ep0_rx_arm)(void *ctx, uint16_t max_len, uint8_t pid);
    void (*ep0_stall)(void *ctx);
    void (*set_address)(void *ctx, uint8_t addr);
    void (*on_configured)(void *ctx, uint8_t config_val);
    void (*on_1200baud_reset)(void *ctx);
    void *ctx;
} usb_ep0_hw_t;

typedef struct {
    const uint8_t *tx_ptr;
    uint16_t       tx_rem;
    uint8_t        tx_pid;
    bool           tx_need_zlp;
    bool           tx_active;

    uint8_t        pending_addr;
    uint8_t        config_val;
    bool           expect_line_coding;
    uint8_t        line_coding[7];
} usb_ep0_state_t;

void usb_ep0_init(usb_ep0_state_t *st);
void usb_ep0_bus_reset(usb_ep0_state_t *st);
void usb_ep0_handle_setup(usb_ep0_state_t *st, const uint8_t setup[8], const usb_ep0_hw_t *hw);
void usb_ep0_on_in_complete(usb_ep0_state_t *st, const usb_ep0_hw_t *hw);
void usb_ep0_on_out_complete(usb_ep0_state_t *st, const uint8_t *rx_buf, uint16_t rx_len, const usb_ep0_hw_t *hw);

#endif /* BEADS_USB_EP0_H */
