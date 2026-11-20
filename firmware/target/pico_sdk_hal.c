#ifdef PICO_SDK_VERSION_MAJOR
/* ============================================================================
 * Pico SDK RP2040 HAL Adapter (used ONLY when building via CMake + PICO_SDK_PATH)
 * Prevents clock/multicore/USB/vector collisions with bare-metal rp2040_hal.c.
 * ============================================================================ */
#include "hal.h"
#include "board_pins.h"
#include "usb_ep0.h"

#include "pico/stdlib.h"
#include "pico/bootrom.h"
#include "pico/critical_section.h"
#include "pico/multicore.h"
#include "hardware/adc.h"
#include "hardware/flash.h"
#include "hardware/gpio.h"
#include "hardware/i2c.h"
#include "hardware/spi.h"
#include "hardware/sync.h"
#include "hardware/uart.h"
#include "hardware/regs/usb.h"
#include "hardware/structs/usb.h"
#include <string.h>

_Static_assert(PICO_FLASH_SIZE_BYTES == 16777216u, "Board carries 16 MB W25Q128JVSIQ QSPI Flash");
#define FLASH_SLOT_A_OFF (PICO_FLASH_SIZE_BYTES - 8192u)
#define FLASH_SLOT_B_OFF (PICO_FLASH_SIZE_BYTES - 4096u)

static const uint8_t DAC_CS_PINS[4] = {
    PIN_CS_DAC0_N, PIN_CS_DAC1_N, PIN_CS_DAC2_N, PIN_CS_DAC3_N
};

static critical_section_t s_crit;
static uint8_t s_last_adc_ch = 0xFFu;
static bool    s_spi_pwr_enabled = false;
static uint8_t s_flash_page_buf[4096];

void hal_crit_enter(void) { critical_section_enter_blocking(&s_crit); }
void hal_crit_exit(void)  { critical_section_exit(&s_crit); }
uint32_t hal_time_us_32(void) { return time_us_32(); }
void hal_gpio_write(uint32_t pin, bool level) { gpio_put(pin, level); }
bool hal_gpio_read(uint32_t pin) { return gpio_get(pin); }

void rp2040_launch_core1(void (*entry)(void)) { multicore_launch_core1(entry); }
void rp2040_delay_us(uint32_t us) { sleep_us(us); }
void rp2040_core0_service_lockout(void) { /* Handled by multicore_lockout_victim_init() IRQ */ }

void hal_spi_dac_set_power_safe(bool pedal_pwr_good) {
    if (!pedal_pwr_good) {
        gpio_set_function(PIN_SPI0_SCK, GPIO_FUNC_SIO);
        gpio_set_function(PIN_SPI0_TX,  GPIO_FUNC_SIO);
        gpio_set_dir(PIN_SPI0_SCK, GPIO_OUT);
        gpio_set_dir(PIN_SPI0_TX,  GPIO_OUT);
        gpio_put(PIN_SPI0_SCK, false);
        gpio_put(PIN_SPI0_TX,  false);
        for (uint8_t i = 0u; i < 4u; i++) {
            gpio_put(DAC_CS_PINS[i], false);
        }
        s_spi_pwr_enabled = false;
    } else if (!s_spi_pwr_enabled) {
        for (uint8_t i = 0u; i < 4u; i++) {
            gpio_put(DAC_CS_PINS[i], true);
        }
        gpio_set_function(PIN_SPI0_SCK, GPIO_FUNC_SPI);
        gpio_set_function(PIN_SPI0_TX,  GPIO_FUNC_SPI);
        s_spi_pwr_enabled = true;
    }
}

void hal_init(void) {
    critical_section_init(&s_crit);
    multicore_lockout_victim_init();

    const uint8_t in_pullup[] = {
        PIN_ENC_A, PIN_ENC_B, PIN_ENC_SW, PIN_BTN_BACK,
        PIN_FS1_BYPASS_SW, PIN_FS2_ACTION_SW
    };
    for (size_t i = 0u; i < sizeof(in_pullup); i++) {
        gpio_init(in_pullup[i]);
        gpio_set_dir(in_pullup[i], GPIO_IN);
        gpio_pull_up(in_pullup[i]);
    }
    gpio_init(PIN_PEDAL_PWR_GOOD); gpio_set_dir(PIN_PEDAL_PWR_GOOD, GPIO_IN); gpio_disable_pulls(PIN_PEDAL_PWR_GOOD);
    gpio_init(PIN_VBUS_DET);       gpio_set_dir(PIN_VBUS_DET, GPIO_IN);       gpio_disable_pulls(PIN_VBUS_DET);

    bool pwr_good = gpio_get(PIN_PEDAL_PWR_GOOD);
    const uint8_t outs[] = {
        PIN_RELAY_BYPASS_EN, PIN_LED_FS1_BYPASS, PIN_LED_FS2_STATUS,
        PIN_LED_AUDIO_PEAK, PIN_PHOTOMOS_MUTE_EN,
        PIN_CS_DAC0_N, PIN_CS_DAC1_N, PIN_CS_DAC2_N, PIN_CS_DAC3_N
    };
    for (size_t i = 0u; i < sizeof(outs); i++) {
        uint8_t p = outs[i];
        bool init_high = (p == PIN_PHOTOMOS_MUTE_EN) ||
                         (pwr_good && (p == PIN_CS_DAC0_N || p == PIN_CS_DAC1_N ||
                                       p == PIN_CS_DAC2_N || p == PIN_CS_DAC3_N));
        gpio_init(p);
        gpio_put(p, init_high);
        gpio_set_dir(p, GPIO_OUT);
    }

    uart_init(uart0, 31250u);
    gpio_set_function(PIN_DBG_TX_TP, GPIO_FUNC_UART);
    gpio_set_function(PIN_UART0_RX_MIDI, GPIO_FUNC_UART);
    uart_set_format(uart0, 8u, 1u, UART_PARITY_NONE);
    uart_set_fifo_enabled(uart0, true);

    spi_init(spi0, 12000000u);
    spi_set_format(spi0, 16u, SPI_CPOL_0, SPI_CPHA_0, SPI_MSB_FIRST);
    s_spi_pwr_enabled = !gpio_get(PIN_PEDAL_PWR_GOOD);
    hal_spi_dac_set_power_safe(gpio_get(PIN_PEDAL_PWR_GOOD));

    i2c_init(i2c0, 400000u);
    gpio_set_function(PIN_I2C0_SDA, GPIO_FUNC_I2C);
    gpio_set_function(PIN_I2C0_SCL, GPIO_FUNC_I2C);
    gpio_pull_up(PIN_I2C0_SDA);
    gpio_pull_up(PIN_I2C0_SCL);

    adc_init();
    adc_gpio_init(PIN_ADC0_GTR_ENV);
    s_last_adc_ch = 0xFFu;
}

void hal_spi_dac_write16(uint8_t dac_idx, uint16_t word) {
    if (dac_idx >= 4u) return;
    gpio_put(DAC_CS_PINS[dac_idx], false);
    spi_write16_blocking(spi0, &word, 1u);
    gpio_put(DAC_CS_PINS[dac_idx], true);
}

uint16_t hal_adc_read_ch(uint8_t adc_ch) {
    uint8_t ch = adc_ch & 0x03u;
    bool mux_changed = (s_last_adc_ch != ch);
    s_last_adc_ch = ch;
    adc_select_input(ch);
    if (mux_changed) {
        (void)adc_read();
    }
    return adc_read() & 0x0FFFu;
}

bool hal_uart0_try_read_dr(uint16_t *out_dr) {
    if (!uart_is_readable(uart0)) return false;
    *out_dr = (uint16_t)(uart_get_hw(uart0)->dr & 0x0FFFu);
    return true;
}

void hal_uart0_clear_rsr(void) {
    uart_get_hw(uart0)->rsr = 0x0Fu;
}

bool hal_i2c0_write_timeout(uint8_t addr7, const uint8_t *buf, size_t len, uint32_t timeout_us) {
    int rc = i2c_write_timeout_us(i2c0, addr7, buf, len, false, timeout_us);
    return (rc == (int)len);
}

bool hal_flash_read(uint32_t slot_idx, void *dst, size_t len) {
    uint32_t off = (slot_idx & 1u) ? FLASH_SLOT_B_OFF : FLASH_SLOT_A_OFF;
    memcpy(dst, (const void *)(XIP_BASE + off), len);
    return true;
}

bool hal_flash_erase_and_program(uint32_t slot_idx, const void *src, size_t len) {
    if (len == 0u || len > sizeof(s_flash_page_buf)) return false;
    uint32_t off = (slot_idx & 1u) ? FLASH_SLOT_B_OFF : FLASH_SLOT_A_OFF;
    size_t prog_len = (len + 255u) & ~255u;
    memset(s_flash_page_buf, 0xFF, prog_len);
    memcpy(s_flash_page_buf, src, len);
    if (!multicore_lockout_start_timeout_us(5000u)) {
        return false;
    }
    uint32_t saved = save_and_disable_interrupts();
    flash_range_erase(off, FLASH_SECTOR_SIZE);
    flash_range_program(off, s_flash_page_buf, prog_len);
    restore_interrupts(saved);
    (void)multicore_lockout_end_timeout_us(5000u);
    return true;
}

void hal_reset_usb_boot(uint32_t usb_activity_gpio_pin_mask, uint32_t disable_interface_mask) {
    reset_usb_boot(usb_activity_gpio_pin_mask, disable_interface_mask);
}

/* ============================================================================
 * Shared RP2040 USB Device Stack (Composite USB-MIDI + CDC-ACM 1200bps UF2)
 * Uses usb_ep0.c over RP2040 USBCTRL_DPRAM & USBCTRL_REGS in Pico SDK builds.
 * ============================================================================ */
#include "hardware/resets.h"

static usb_ep0_state_t  s_ep0;
static usb_vbus_state_t s_usb_vbus;
static uint8_t s_ep1_pid = 0u;
static uint8_t s_ep3_out_pid = 0u;
static uint8_t s_usb_midi_rx_q[64];
static uint8_t s_usb_midi_q_len = 0u;
static uint8_t s_usb_midi_q_pos = 0u;

static void sdk_ep0_tx(void *ctx, const uint8_t *data, uint16_t len, uint8_t pid) {
    (void)ctx;
    if (len > BEADS_USB_EP0_MAX_PKT) len = BEADS_USB_EP0_MAX_PKT;
    if (data != NULL) {
        for (uint16_t i = 0u; i < len; i++) {
            usb_dpram->ep0_buf_a[i] = data[i];
        }
    }
    uint32_t ctrl = (uint32_t)len | USB_BUF_CTRL_FULL | (pid ? USB_BUF_CTRL_DATA1_PID : 0u);
    usb_dpram->ep_buf_ctrl[0].in = ctrl;
    __asm__ volatile("nop\nnop\nnop");
    usb_dpram->ep_buf_ctrl[0].in = ctrl | USB_BUF_CTRL_AVAIL;
}

static void sdk_ep0_rx_arm(void *ctx, uint16_t max_len, uint8_t pid) {
    (void)ctx;
    if (max_len > BEADS_USB_EP0_MAX_PKT) max_len = BEADS_USB_EP0_MAX_PKT;
    uint32_t ctrl = (uint32_t)max_len | (pid ? USB_BUF_CTRL_DATA1_PID : 0u);
    usb_dpram->ep_buf_ctrl[0].out = ctrl;
    __asm__ volatile("nop\nnop\nnop");
    usb_dpram->ep_buf_ctrl[0].out = ctrl | USB_BUF_CTRL_AVAIL;
}

static void sdk_ep0_stall(void *ctx) {
    (void)ctx;
    usb_hw->ep_stall_arm = USB_EP_STALL_ARM_EP0_IN_BITS | USB_EP_STALL_ARM_EP0_OUT_BITS;
    usb_dpram->ep_buf_ctrl[0].in  = USB_BUF_CTRL_STALL;
    usb_dpram->ep_buf_ctrl[0].out = USB_BUF_CTRL_STALL;
}

static void sdk_ep1_out_arm(uint8_t pid) {
    uint32_t ctrl = 64u | (pid ? USB_BUF_CTRL_DATA1_PID : 0u);
    usb_dpram->ep_buf_ctrl[1].out = ctrl;
    __asm__ volatile("nop\nnop\nnop");
    usb_dpram->ep_buf_ctrl[1].out = ctrl | USB_BUF_CTRL_AVAIL;
}

static void sdk_ep3_out_arm(uint8_t pid) {
    uint32_t ctrl = 64u | (pid ? USB_BUF_CTRL_DATA1_PID : 0u);
    usb_dpram->ep_buf_ctrl[3].out = ctrl;
    __asm__ volatile("nop\nnop\nnop");
    usb_dpram->ep_buf_ctrl[3].out = ctrl | USB_BUF_CTRL_AVAIL;
}

static void sdk_set_address(void *ctx, uint8_t addr) {
    (void)ctx;
    usb_hw->dev_addr_ctrl = addr & 0x7Fu;
}

static void sdk_on_configured(void *ctx, uint8_t config_val) {
    (void)ctx;
    (void)config_val;
    s_ep1_pid = 0u;
    s_ep3_out_pid = 0u;
    sdk_ep1_out_arm(0u);
    sdk_ep3_out_arm(0u);
}

static void sdk_on_1200baud_reset(void *ctx) {
    (void)ctx;
    sleep_us(2000u);
    hal_reset_usb_boot(0u, 0u);
}

static const usb_ep0_hw_t SDK_USB_EP0_HW = {
    .ep0_tx            = sdk_ep0_tx,
    .ep0_rx_arm        = sdk_ep0_rx_arm,
    .ep0_stall         = sdk_ep0_stall,
    .set_address       = sdk_set_address,
    .on_configured     = sdk_on_configured,
    .on_1200baud_reset = sdk_on_1200baud_reset,
    .ctx               = NULL,
};

static bool sdk_usb_read_vbus_det(void *ctx) {
    (void)ctx;
    return hal_gpio_read(PIN_VBUS_DET);
}

static void sdk_usb_set_pullup(void *ctx, bool en) {
    (void)ctx;
    if (en) {
        usb_hw->sie_ctrl |= USB_SIE_CTRL_PULLUP_EN_BITS;
    } else {
        usb_hw->sie_ctrl &= ~USB_SIE_CTRL_PULLUP_EN_BITS;
    }
}

static void sdk_usb_on_attach(void *ctx) {
    (void)ctx;
    usb_hw->dev_addr_ctrl = 0u;
    usb_ep0_bus_reset(&s_ep0);
    s_ep1_pid = 0u;
    s_ep3_out_pid = 0u;
    s_usb_midi_q_len = 0u;
    s_usb_midi_q_pos = 0u;
    (void)usb_hw->sof_rd;
    usb_hw->buf_status = 0xFFFFFFFFu;
    usb_hw->sie_status = USB_SIE_STATUS_BUS_RESET_BITS | USB_SIE_STATUS_SETUP_REC_BITS |
                         USB_SIE_STATUS_CONNECTED_BITS | USB_SIE_STATUS_SUSPENDED_BITS |
                         USB_SIE_STATUS_RESUME_BITS;
    sdk_ep1_out_arm(0u);
    sdk_ep3_out_arm(0u);
    usb_hw->pwr = USB_USB_PWR_VBUS_DETECT_BITS | USB_USB_PWR_VBUS_DETECT_OVERRIDE_EN_BITS;
    usb_hw->sie_ctrl |= USB_SIE_CTRL_PULLUP_EN_BITS;
}

static void sdk_usb_on_detach(void *ctx) {
    (void)ctx;
    usb_hw->sie_ctrl &= ~USB_SIE_CTRL_PULLUP_EN_BITS;
    usb_hw->pwr = USB_USB_PWR_VBUS_DETECT_OVERRIDE_EN_BITS; /* VBUS_DETECT = 0 */
    usb_hw->dev_addr_ctrl = 0u;
    usb_ep0_bus_reset(&s_ep0);
    s_ep1_pid = 0u;
    s_ep3_out_pid = 0u;
    s_usb_midi_q_len = 0u;
    s_usb_midi_q_pos = 0u;
    usb_dpram->ep_buf_ctrl[0].in  = 0u;
    usb_dpram->ep_buf_ctrl[0].out = 0u;
    usb_dpram->ep_buf_ctrl[1].out = 0u;
    usb_dpram->ep_buf_ctrl[3].out = 0u;
    (void)usb_hw->sof_rd;
    usb_hw->buf_status = 0xFFFFFFFFu;
    usb_hw->sie_status = USB_SIE_STATUS_BUS_RESET_BITS | USB_SIE_STATUS_SETUP_REC_BITS |
                         USB_SIE_STATUS_CONNECTED_BITS | USB_SIE_STATUS_SUSPENDED_BITS |
                         USB_SIE_STATUS_RESUME_BITS;
}

static const usb_vbus_hw_t SDK_USB_VBUS_HW = {
    .read_vbus_det = sdk_usb_read_vbus_det,
    .set_pullup    = sdk_usb_set_pullup,
    .on_attach     = sdk_usb_on_attach,
    .on_detach     = sdk_usb_on_detach,
    .ctx           = NULL,
};

bool hal_usb_ep0_is_busy(void) {
    return usb_ep0_is_busy(&s_ep0);
}

void hal_usb_init_on_core1(void) {
    reset_block(RESETS_RESET_USBCTRL_BITS);
    unreset_block_wait(RESETS_RESET_USBCTRL_BITS);

    usb_ep0_init(&s_ep0);
    usb_vbus_init(&s_usb_vbus);
    s_ep1_pid = 0u;
    s_ep3_out_pid = 0u;
    s_usb_midi_q_len = 0u;
    s_usb_midi_q_pos = 0u;

    memset(usb_dpram, 0, sizeof(*usb_dpram));
    usb_hw->muxing    = USB_USB_MUXING_TO_PHY_BITS | USB_USB_MUXING_SOFTCON_BITS;
    /* Start with VBUS_DETECT = 0 & PULLUP_EN = 0 so +3.3V D+ pull-up NEVER back-feeds
     * SRV05-4 -> J_USB.VBUS into powered-off (0V) hosts! Gated dynamically by PIN_VBUS_DET. */
    usb_hw->pwr       = USB_USB_PWR_VBUS_DETECT_OVERRIDE_EN_BITS;
    usb_hw->main_ctrl = USB_MAIN_CTRL_CONTROLLER_EN_BITS;
    usb_hw->sie_ctrl  = USB_SIE_CTRL_EP0_INT_1BUF_BITS;

    usb_dpram->ep_ctrl[0].out = EP_CTRL_ENABLE_BITS | EP_CTRL_INTERRUPT_PER_BUFFER | (2u << EP_CTRL_BUFFER_TYPE_LSB) | 0x0180u; /* EP1 OUT */
    usb_dpram->ep_ctrl[1].in  = EP_CTRL_ENABLE_BITS | EP_CTRL_INTERRUPT_PER_BUFFER | (3u << EP_CTRL_BUFFER_TYPE_LSB) | 0x0200u; /* EP2 IN  */
    usb_dpram->ep_ctrl[2].out = EP_CTRL_ENABLE_BITS | EP_CTRL_INTERRUPT_PER_BUFFER | (2u << EP_CTRL_BUFFER_TYPE_LSB) | 0x0240u; /* EP3 OUT */
    usb_dpram->ep_ctrl[2].in  = EP_CTRL_ENABLE_BITS | EP_CTRL_INTERRUPT_PER_BUFFER | (2u << EP_CTRL_BUFFER_TYPE_LSB) | 0x0280u; /* EP3 IN  */

    /* Dynamically assert VBUS_DETECT & PULLUP_EN ONLY when PIN_VBUS_DET is HIGH */
    (void)usb_vbus_sync(&s_usb_vbus, &SDK_USB_VBUS_HW);
}

void hal_usb_task_on_core1(void) {
    /* Dynamically gate PULLUP_EN & VBUS_DETECT strictly on PIN_VBUS_DET (zero suspend SE0 glitch!) */
    if (!usb_vbus_sync(&s_usb_vbus, &SDK_USB_VBUS_HW)) {
        return;
    }

    if ((usb_hw->intr & USB_INTR_DEV_SOF_BITS) != 0u) {
        (void)usb_hw->sof_rd;
        usb_hw->sie_status = USB_SIE_STATUS_SUSPENDED_BITS | USB_SIE_STATUS_RESUME_BITS;
    }

    uint32_t sie = usb_hw->sie_status;
    if ((sie & USB_SIE_STATUS_BUS_RESET_BITS) != 0u) {
        (void)usb_hw->sof_rd;
        usb_hw->sie_status = USB_SIE_STATUS_BUS_RESET_BITS | USB_SIE_STATUS_SUSPENDED_BITS | USB_SIE_STATUS_RESUME_BITS;
        usb_hw->dev_addr_ctrl = 0u;
        usb_ep0_bus_reset(&s_ep0);
        s_ep1_pid = 0u;
        s_ep3_out_pid = 0u;
        sdk_ep1_out_arm(0u);
        sdk_ep3_out_arm(0u);
    }
    uint32_t bstat = usb_hw->buf_status;
    if (bstat != 0u) {
        /* Service buf_status BEFORE SETUP_REC so a prior EP0_IN completion
         * never overwrites a newly armed SETUP response! */
        if ((bstat & (1u << 0u)) != 0u) {
            usb_hw->buf_status = (1u << 0u);
            usb_ep0_on_in_complete(&s_ep0, &SDK_USB_EP0_HW);
        }
        if ((bstat & (1u << 1u)) != 0u) {
            uint16_t rx_len = (uint16_t)(usb_dpram->ep_buf_ctrl[0].out & USB_BUF_CTRL_LEN_MASK);
            usb_hw->buf_status = (1u << 1u);
            uint8_t rx_copy[64];
            if (rx_len > sizeof(rx_copy)) rx_len = (uint16_t)sizeof(rx_copy);
            for (uint16_t i = 0u; i < rx_len; i++) {
                rx_copy[i] = usb_dpram->ep0_buf_a[i];
            }
            usb_ep0_on_out_complete(&s_ep0, rx_copy, rx_len, &SDK_USB_EP0_HW);
        }
        if ((bstat & (1u << 3u)) != 0u) {
            uint16_t rx_len = (uint16_t)(usb_dpram->ep_buf_ctrl[1].out & USB_BUF_CTRL_LEN_MASK);
            usb_hw->buf_status = (1u << 3u);
            const volatile uint8_t *ep1_out = (const volatile uint8_t *)usb_dpram + 0x0180u;
            if (rx_len >= 4u && rx_len <= sizeof(s_usb_midi_rx_q) && s_usb_midi_q_pos >= s_usb_midi_q_len) {
                for (uint16_t i = 0u; i < rx_len; i++) {
                    s_usb_midi_rx_q[i] = ep1_out[i];
                }
                s_usb_midi_q_len = (uint8_t)(rx_len & ~3u);
                s_usb_midi_q_pos = 0u;
            }
            s_ep1_pid ^= 1u;
            sdk_ep1_out_arm(s_ep1_pid);
        }
        if ((bstat & (1u << 7u)) != 0u) {
            usb_hw->buf_status = (1u << 7u);
            s_ep3_out_pid ^= 1u;
            sdk_ep3_out_arm(s_ep3_out_pid);
        }
        uint32_t rest = bstat & ~((1u << 0u) | (1u << 1u) | (1u << 3u) | (1u << 7u));
        if (rest != 0u) {
            usb_hw->buf_status = rest;
        }
    }

    sie = usb_hw->sie_status;
    if ((sie & USB_SIE_STATUS_SETUP_REC_BITS) != 0u) {
        usb_hw->sie_status = USB_SIE_STATUS_SETUP_REC_BITS;
        uint8_t setup[8];
        for (uint8_t i = 0u; i < 8u; i++) {
            setup[i] = usb_dpram->setup_packet[i];
        }
        usb_ep0_handle_setup(&s_ep0, setup, &SDK_USB_EP0_HW);
    }
}

bool hal_usb_midi_read_packet(uint8_t packet4[4]) {
    if ((uint8_t)(s_usb_midi_q_pos + 4u) <= s_usb_midi_q_len) {
        packet4[0] = s_usb_midi_rx_q[s_usb_midi_q_pos + 0u];
        packet4[1] = s_usb_midi_rx_q[s_usb_midi_q_pos + 1u];
        packet4[2] = s_usb_midi_rx_q[s_usb_midi_q_pos + 2u];
        packet4[3] = s_usb_midi_rx_q[s_usb_midi_q_pos + 3u];
        s_usb_midi_q_pos = (uint8_t)(s_usb_midi_q_pos + 4u);
        if (s_usb_midi_q_pos >= s_usb_midi_q_len) {
            s_usb_midi_q_pos = 0u;
            s_usb_midi_q_len = 0u;
        }
        return true;
    }
    return false;
}
#endif /* PICO_SDK_VERSION_MAJOR */
