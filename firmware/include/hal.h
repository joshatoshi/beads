#ifndef BEADS_HAL_H
#define BEADS_HAL_H

#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>

/* Hardware abstraction layer implemented by rp2040_hal.c (target Cortex-M0+)
 * or test_hal_mock.c (silicon-honest host unit tests). */

void     hal_init(void);
uint32_t hal_time_us_32(void);
void     hal_gpio_write(uint32_t pin, bool level);
bool     hal_gpio_read(uint32_t pin);

/* SPI0 16-bit MCP4822 write with dedicated chip-select index 0..3 */
void     hal_spi_dac_write16(uint8_t dac_idx, uint16_t word);

/* SAR ADC read (MUST discard 1 dummy conversion after every mux channel switch!) */
uint16_t hal_adc_read_ch(uint8_t adc_ch);

/* PL011 UART0 RX non-blocking read returning full 16-bit UARTDR (data[7:0] + err[11:8]) */
bool     hal_uart0_try_read_dr(uint16_t *out_dr);
void     hal_uart0_clear_rsr(void);

/* Bounded I2C0 write for SSD1306 (returns false on timeout/NACK, never hangs) */
bool     hal_i2c0_write_timeout(uint8_t addr7, const uint8_t *buf, size_t len, uint32_t timeout_us);

/* Dual-slot A/B QSPI Flash persistence (two 4KB sectors at end of 16MB W25Q128) */
bool     hal_flash_read(uint32_t slot_idx, void *dst, size_t len);
bool     hal_flash_erase_and_program(uint32_t slot_idx, const void *src, size_t len);

/* Cross-core critical section (spinlock + local IRQ save/restore on RP2040) */
void     hal_crit_enter(void);
void     hal_crit_exit(void);

/* Headerless USB-C UF2 ROM boot (OLED menu "USB FIRMWARE UPDATE" or 1200-baud CDC) */
void     hal_reset_usb_boot(uint32_t usb_activity_gpio_pin_mask, uint32_t disable_interface_mask);

/* TinyUSB Core 1 lifecycle (tusb_init & tud_task MUST run on the SAME core!) */
void     hal_usb_init_on_core1(void);
void     hal_usb_task_on_core1(void);
bool     hal_usb_midi_read_packet(uint8_t packet4[4]);

#endif /* BEADS_HAL_H */
