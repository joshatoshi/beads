#ifndef BEADS_BOARD_PINS_H
#define BEADS_BOARD_PINS_H

#include <stdint.h>

/* ============================================================================
 * Beads Pedalboard Skiff — RP2040 GPIO Pinmux (100% synced to main_board.net
 * & hardware_contract.json — zero collisions!)
 * ============================================================================ */
#define PIN_DBG_TX_TP          0u   /* Optional UART0_TX debug pad (MIDI THRU is 74HC14 HW) */
#define PIN_UART0_RX_MIDI      1u   /* 74HC14 Gate 4 buffered H11L1 TRS MIDI IN (31,250 bps) */

#define PIN_I2C0_SDA           4u   /* 0.96" SSD1306 OLED SDA (4.7k pull-up, 400 kHz) */
#define PIN_I2C0_SCL           5u   /* 0.96" SSD1306 OLED SCL (4.7k pull-up, 400 kHz) */

#define PIN_ENC_A              6u   /* EC11 Quadrature A (10k pull-up + 10nF) */
#define PIN_ENC_B              7u   /* EC11 Quadrature B (10k pull-up + 10nF) */
#define PIN_ENC_SW             8u   /* EC11 Push Switch (10k pull-up, active-low) */
#define PIN_BTN_BACK           9u   /* 14HP Panel BACK Button (10k pull-up, active-low) */

#define PIN_FS1_BYPASS_SW     10u   /* Stepped-apron FS1 Momentary Footswitch (active-low) */
#define PIN_FS2_ACTION_SW     11u   /* Stepped-apron FS2 Momentary Footswitch (active-low) */

#define PIN_RELAY_BYPASS_EN   12u   /* Slew-damped NMOS -> K1+K2 Omron G6K-2F-Y (1=Active) */
#define PIN_LED_FS1_BYPASS    13u   /* Apron LED 1 (Bypass/Active status) */
#define PIN_LED_FS2_STATUS    14u   /* Apron LED 2 (FREEZE / SEED Tap-Tempo) */
#define PIN_LED_AUDIO_PEAK    15u   /* 14HP Faceplate PEAK/CLIP LED */

#define PIN_CS_DAC0_N         16u   /* MCP4822 U_DAC0 ~CS (CV1, CV2) */
#define PIN_CS_DAC1_N         17u   /* MCP4822 U_DAC1 ~CS (CV3, CV4) */
#define PIN_SPI0_SCK          18u   /* 10 MHz SPI0 SCK -> 4x MCP4822 */
#define PIN_SPI0_TX           19u   /* 10 MHz SPI0 MOSI -> 4x MCP4822 */
#define PIN_CS_DAC2_N         20u   /* MCP4822 U_DAC2 ~CS (CV5, CV6) */
#define PIN_CS_DAC3_N         21u   /* MCP4822 U_DAC3 ~CS (CV7, CV8) */

#define PIN_PEDAL_PWR_GOOD    22u   /* +5V_BUCK monitor (10k/15k divider: 1=9-18V OK) */
#define PIN_PHOTOMOS_MUTE_EN  23u   /* Soft-slewed NMOS -> 2x TLP172AM PhotoMOS mute (1=Mute) */
#define PIN_VBUS_DET          24u   /* USB-C VBUS sense (10k/18k divider) */

#define PIN_ADC0_GTR_ENV      26u   /* ADC0: 0..3.30V MCP6002 Guitar Peak/Pluck Detector */
#define ADC_CH_GTR_ENV         0u

/* Core 1 stack budget enforced by CI -fstack-usage gate */
#ifndef PICO_CORE1_STACK_SIZE
#define PICO_CORE1_STACK_SIZE  0x1000u
#endif

/* Core 0 deterministic control tick frequency */
#define CORE0_TICK_HZ          2000u
#define CORE0_TICK_US          500u

/* Number of universal bipolar CV/Gate channels */
#define BEADS_NUM_CV_CHANNELS  8u
#define BEADS_NUM_PRESETS      32u
#define BEADS_CAL_OCTAVES      10u  /* C0..C9 9-octave 1V/Oct LUT (10 knot points) */

#endif /* BEADS_BOARD_PINS_H */
