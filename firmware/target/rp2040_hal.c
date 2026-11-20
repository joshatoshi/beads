#include "hal.h"
#include "board_pins.h"
#include "usb_ep0.h"
#include <string.h>

/* ============================================================================
 * RP2040 Bare-Metal Silicon Register HAL (RP2040 Datasheet Rev 2.1)
 * Zero floating-point and zero 64-bit division helpers.
 * Includes full XOSC + PLL_SYS (120MHz) + PLL_USB (48MHz) + WATCHDOG_TICK init,
 * SRAM-resident XIP-off QSPI Flash programmer with Core 0 SRAM lockout,
 * and bare-metal USBCTRL Device (USB-MIDI + 1200-baud CDC UF2 auto-reset).
 * ============================================================================ */
#define REG32(addr) (*(volatile uint32_t *)(addr))

/* SIO (Single-Cycle IO) */
#define SIO_CPUID            REG32(0xD0000000u)
#define SIO_GPIO_IN          REG32(0xD0000004u)
#define SIO_GPIO_OUT_SET     REG32(0xD0000014u)
#define SIO_GPIO_OUT_CLR     REG32(0xD0000018u)
#define SIO_GPIO_OE_SET      REG32(0xD0000024u)
#define SIO_GPIO_OE_CLR      REG32(0xD0000028u)
#define SIO_SPINLOCK0        REG32(0xD0000100u)

/* RESETS */
#define RESETS_RESET         REG32(0x4000C000u)
#define RESETS_RESET_DONE    REG32(0x4000C008u)

/* XOSC (12.000 MHz Crystal) & WATCHDOG_TICK */
#define XOSC_CTRL            REG32(0x40024000u)
#define XOSC_STATUS          REG32(0x40024004u)
#define XOSC_STARTUP         REG32(0x4002400Cu)
#define WATCHDOG_TICK        REG32(0x4005802Cu)

/* PLL_SYS (0x40028000) & PLL_USB (0x4002C000) */
#define PLL_SYS_CS           REG32(0x40028000u)
#define PLL_SYS_PWR          REG32(0x40028004u)
#define PLL_SYS_FBDIV_INT    REG32(0x40028008u)
#define PLL_SYS_PRIM         REG32(0x4002800Cu)

#define PLL_USB_CS           REG32(0x4002C000u)
#define PLL_USB_PWR          REG32(0x4002C004u)
#define PLL_USB_FBDIV_INT    REG32(0x4002C008u)
#define PLL_USB_PRIM         REG32(0x4002C00Cu)

/* CLOCKS (0x40008000) */
#define CLK_REF_CTRL         REG32(0x40008030u)
#define CLK_REF_DIV          REG32(0x40008034u)
#define CLK_SYS_CTRL         REG32(0x4000803Cu)
#define CLK_SYS_DIV          REG32(0x40008040u)
#define CLK_PERI_CTRL        REG32(0x40008048u)
#define CLK_USB_CTRL         REG32(0x40008054u)
#define CLK_USB_DIV          REG32(0x40008058u)
#define CLK_ADC_CTRL         REG32(0x40008060u)
#define CLK_ADC_DIV          REG32(0x40008064u)

/* IO_BANK0 & PADS_BANK0 */
#define IO_BANK0_CTRL(pin)   REG32(0x40014004u + ((pin) * 8u))
#define PADS_BANK0_GPIO(pin) REG32(0x4001C004u + ((pin) * 4u))

/* TIMER */
#define TIMER_TIMERAWL       REG32(0x40054028u)

/* PL011 UART0 (31,250 bps MIDI IN on GPIO1 @ 48 MHz CLK_PERI) */
#define UART0_DR             REG32(0x40034000u)
#define UART0_RSR            REG32(0x40034004u)
#define UART0_FR             REG32(0x40034018u)
#define UART0_IBRD           REG32(0x40034024u)
#define UART0_FBRD           REG32(0x40034028u)
#define UART0_LCR_H          REG32(0x4003402Cu)
#define UART0_CR             REG32(0x40034030u)

/* PL022 SPI0 (12 MHz 16-bit MCP4822 DAC bus @ 48 MHz CLK_PERI) */
#define SPI0_CR0             REG32(0x4003C000u)
#define SPI0_CR1             REG32(0x4003C004u)
#define SPI0_DR              REG32(0x4003C008u)
#define SPI0_SR              REG32(0x4003C00Cu)
#define SPI0_CPSR            REG32(0x4003C010u)

/* DW_apb_i2c I2C0 (400 kHz SSD1306 OLED @ 120 MHz CLK_SYS) */
#define I2C0_CON             REG32(0x40044000u)
#define I2C0_TAR             REG32(0x40044004u)
#define I2C0_DATA_CMD        REG32(0x40044010u)
#define I2C0_FS_SCL_HCNT     REG32(0x4004401Cu)
#define I2C0_FS_SCL_LCNT     REG32(0x40044020u)
#define I2C0_ENABLE          REG32(0x4004406Cu)
#define I2C0_STATUS          REG32(0x40044070u)
#define I2C0_TX_ABRT_SRC     REG32(0x40044080u)
#define I2C0_CLR_TX_ABRT     REG32(0x40044054u)

/* SAR ADC (ADC0 on GPIO26 @ 48 MHz CLK_ADC) */
#define ADC_CS               REG32(0x4004C000u)
#define ADC_RESULT           REG32(0x4004C004u)

/* USBCTRL DPRAM (0x50100000) & Registers (0x50110000) */
#define USB_DPRAM_BASE       0x50100000u
#define USB_SETUP_PKT        ((volatile uint8_t *)(USB_DPRAM_BASE + 0x0000u))
#define USB_EP_CTRL(ep, dir) REG32(USB_DPRAM_BASE + 0x0008u + (((ep) - 1u) * 8u) + ((dir) ? 0u : 4u))
#define USB_BUF_CTRL_IN(ep)  REG32(USB_DPRAM_BASE + 0x0080u + ((ep) * 8u))
#define USB_BUF_CTRL_OUT(ep) REG32(USB_DPRAM_BASE + 0x0084u + ((ep) * 8u))
#define USB_EP0_BUF0         ((volatile uint8_t *)(USB_DPRAM_BASE + 0x0100u))
#define USB_EP1_OUT_BUF      ((volatile uint8_t *)(USB_DPRAM_BASE + 0x0180u))
#define USB_EP2_IN_BUF       ((volatile uint8_t *)(USB_DPRAM_BASE + 0x0200u))
#define USB_EP3_OUT_BUF      ((volatile uint8_t *)(USB_DPRAM_BASE + 0x0240u))
#define USB_EP3_IN_BUF       ((volatile uint8_t *)(USB_DPRAM_BASE + 0x0280u))

#define USB_ADDR_ENDP        REG32(0x50110000u)
#define USB_MAIN_CTRL        REG32(0x50110040u)
#define USB_SIE_CTRL         REG32(0x5011004Cu)
#define USB_SIE_STATUS       REG32(0x50110050u)
#define USB_BUFF_STATUS      REG32(0x50110058u)
#define USB_EP_STALL_ARM     REG32(0x50110068u)
#define USB_USB_MUXING       REG32(0x50110074u)
#define USB_USB_PWR          REG32(0x50110078u)

/* Top two 4 KB sectors of 16 MB W25Q128JVSIQ XIP Flash for A/B CRC32 persistence */
#define FLASH_SLOT_A_XIP     0x10FFE000u
#define FLASH_SLOT_B_XIP     0x10FFF000u
#define FLASH_SLOT_A_OFF     0x00FFE000u
#define FLASH_SLOT_B_OFF     0x00FFF000u

static const uint8_t DAC_CS_PINS[4] = {
    PIN_CS_DAC0_N, PIN_CS_DAC1_N, PIN_CS_DAC2_N, PIN_CS_DAC3_N
};

static uint8_t  s_last_adc_ch = 0xFFu;
static uint32_t s_saved_primask[2] = { 0u, 0u };
static bool     s_spi_pwr_enabled = false;

/* Inter-core SRAM lockout handshake for XIP-off QSPI Flash programming */
static volatile uint32_t s_core0_lockout_req = 0u;
static volatile uint32_t s_core0_parked_ram  = 0u;

static uint32_t get_core_id(void) {
    return SIO_CPUID & 1u;
}

void hal_crit_enter(void) {
    uint32_t pm;
    __asm__ volatile("mrs %0, primask\ncpsid i" : "=r"(pm) :: "memory");
    while (SIO_SPINLOCK0 == 0u) { }
    __asm__ volatile("dmb" ::: "memory");
    s_saved_primask[get_core_id()] = pm;
}

void hal_crit_exit(void) {
    uint32_t pm = s_saved_primask[get_core_id()];
    __asm__ volatile("dmb" ::: "memory");
    SIO_SPINLOCK0 = 1u;
    __asm__ volatile("msr primask, %0" :: "r"(pm) : "memory");
}

/* SRAM-resident Core 0 lockout check called from Core 0 loop */
__attribute__((section(".ramfunc"), noinline))
void rp2040_core0_service_lockout(void) {
    if (s_core0_lockout_req != 0u) {
        uint32_t pm;
        __asm__ volatile("mrs %0, primask\ncpsid i" : "=r"(pm) :: "memory");
        s_core0_parked_ram = 1u;
        __asm__ volatile("dmb\nsev" ::: "memory");
        while (s_core0_lockout_req != 0u) {
            __asm__ volatile("nop");
        }
        s_core0_parked_ram = 0u;
        __asm__ volatile("dmb" ::: "memory");
        __asm__ volatile("msr primask, %0" :: "r"(pm) : "memory");
    }
}

uint32_t hal_time_us_32(void) {
    return TIMER_TIMERAWL;
}

void rp2040_delay_us(uint32_t us) {
    uint32_t start = hal_time_us_32();
    while ((uint32_t)(hal_time_us_32() - start) < us) {
        __asm__ volatile("nop");
    }
}

void hal_gpio_write(uint32_t pin, bool level) {
    uint32_t mask = 1u << pin;
    if (level) {
        SIO_GPIO_OUT_SET = mask;
    } else {
        SIO_GPIO_OUT_CLR = mask;
    }
}

bool hal_gpio_read(uint32_t pin) {
    return ((SIO_GPIO_IN >> pin) & 1u) != 0u;
}

static void init_clocks_120mhz_48mhz(void) {
    /* 1. Start 12.000 MHz XOSC */
    XOSC_CTRL = 0xAA0u;          /* 1..15 MHz range */
    XOSC_STARTUP = 47u;          /* ~1 ms settle */
    XOSC_CTRL = 0xFABAA0u;       /* ENABLE */
    uint32_t guard = 0u;
    while (((XOSC_STATUS & (1u << 31u)) == 0u) && (guard++ < 500000u)) { }

    /* 2. Switch CLK_SYS & CLK_REF cleanly to XOSC before touching PLLs */
    CLK_SYS_CTRL &= ~1u;
    CLK_REF_CTRL = 2u;           /* SRC = XOSC (12 MHz) */
    CLK_REF_DIV  = (1u << 8u);

    /* 3. Enable 1.000 MHz WATCHDOG_TICK (12 MHz / 12) so TIMER_TIMERAWL ticks at 1 us! */
    WATCHDOG_TICK = (1u << 9u) | 12u;

    /* 4. Unreset PLL_SYS (bit 12) & PLL_USB (bit 13) */
    const uint32_t pll_bits = (1u << 12u) | (1u << 13u);
    RESETS_RESET |= pll_bits;
    RESETS_RESET &= ~pll_bits;
    guard = 0u;
    while (((RESETS_RESET_DONE & pll_bits) != pll_bits) && (guard++ < 100000u)) { }

    /* 5. PLL_SYS: 12 MHz * 120 = 1440 MHz VCO / (6 * 2) = 120.0 MHz */
    PLL_SYS_PWR = 0xFFFFFFFFu;
    PLL_SYS_CS = 1u;             /* REFDIV = 1 */
    PLL_SYS_FBDIV_INT = 120u;
    PLL_SYS_PWR &= ~((1u << 0u) | (1u << 5u)); /* Power on VCO + main */
    guard = 0u;
    while (((PLL_SYS_CS & (1u << 31u)) == 0u) && (guard++ < 500000u)) { }
    PLL_SYS_PRIM = (6u << 16u) | (2u << 12u);
    PLL_SYS_PWR &= ~(1u << 3u);  /* Power on post dividers */

    /* 6. PLL_USB: 12 MHz * 100 = 1200 MHz VCO / (5 * 5) = 48.000 MHz exact! */
    PLL_USB_PWR = 0xFFFFFFFFu;
    PLL_USB_CS = 1u;
    PLL_USB_FBDIV_INT = 100u;
    PLL_USB_PWR &= ~((1u << 0u) | (1u << 5u));
    guard = 0u;
    while (((PLL_USB_CS & (1u << 31u)) == 0u) && (guard++ < 500000u)) { }
    PLL_USB_PRIM = (5u << 16u) | (5u << 12u);
    PLL_USB_PWR &= ~(1u << 3u);

    /* 7. Route CLK_SYS=PLL_SYS(120MHz), CLK_PERI=PLL_USB(48MHz), CLK_USB=48MHz, CLK_ADC=48MHz */
    CLK_SYS_DIV  = (1u << 8u);
    CLK_SYS_CTRL = (0u << 5u) | 1u;       /* AUXSRC=PLL_SYS, SRC=AUX */
    CLK_PERI_CTRL = (1u << 11u) | (2u << 5u); /* ENABLE | AUXSRC=PLL_USB (48 MHz!) */
    CLK_USB_DIV  = (1u << 8u);
    CLK_USB_CTRL = (1u << 11u) | (0u << 5u);  /* ENABLE | AUXSRC=PLL_USB (48 MHz) */
    CLK_ADC_DIV  = (1u << 8u);
    CLK_ADC_CTRL = (1u << 11u) | (0u << 5u);  /* ENABLE | AUXSRC=PLL_USB (48 MHz) */
}

void hal_init(void) {
    init_clocks_120mhz_48mhz();

    /* De-assert resets on IO_BANK0(5), PADS_BANK0(8), TIMER(21), UART0(22), SPI0(16), I2C0(3), ADC(0), USBCTRL(24) */
    const uint32_t unreset = (1u << 5u) | (1u << 8u) | (1u << 21u) | (1u << 22u) |
                             (1u << 16u) | (1u << 3u) | (1u << 0u) | (1u << 24u);
    RESETS_RESET &= ~unreset;
    uint32_t guard = 0u;
    while (((RESETS_RESET_DONE & unreset) != unreset) && (guard++ < 200000u)) { }

    /* Configure PADS_BANK0: disable default PDE pull-downs on ADC0, I2C, UART & active-low switches! */
    PADS_BANK0_GPIO(PIN_ADC0_GTR_ENV) = (1u << 7u); /* OD=1, IE=0, PUE=0, PDE=0 (RP2040 §4.9.2!) */
    const uint8_t in_pullup_pins[] = {
        PIN_I2C0_SDA, PIN_I2C0_SCL, PIN_UART0_RX_MIDI,
        PIN_ENC_A, PIN_ENC_B, PIN_ENC_SW, PIN_BTN_BACK,
        PIN_FS1_BYPASS_SW, PIN_FS2_ACTION_SW
    };
    for (size_t i = 0u; i < sizeof(in_pullup_pins); i++) {
        PADS_BANK0_GPIO(in_pullup_pins[i]) = (1u << 6u) | (1u << 3u) | (1u << 1u); /* IE=1, PUE=1, SCHMITT=1, PDE=0 */
    }
    PADS_BANK0_GPIO(PIN_PEDAL_PWR_GOOD) = (1u << 6u) | (1u << 1u); /* IE=1, no pull */
    PADS_BANK0_GPIO(PIN_VBUS_DET)       = (1u << 6u) | (1u << 1u);

    /* Configure SIO inputs first so we can read PEDAL_PWR_GOOD */
    const uint8_t sio_pins[] = {
        PIN_ENC_A, PIN_ENC_B, PIN_ENC_SW, PIN_BTN_BACK,
        PIN_FS1_BYPASS_SW, PIN_FS2_ACTION_SW, PIN_RELAY_BYPASS_EN,
        PIN_LED_FS1_BYPASS, PIN_LED_FS2_STATUS, PIN_LED_AUDIO_PEAK,
        PIN_CS_DAC0_N, PIN_CS_DAC1_N, PIN_CS_DAC2_N, PIN_CS_DAC3_N,
        PIN_PEDAL_PWR_GOOD, PIN_PHOTOMOS_MUTE_EN, PIN_VBUS_DET
    };
    for (size_t i = 0u; i < sizeof(sio_pins); i++) {
        IO_BANK0_CTRL(sio_pins[i]) = 5u;
    }

    /* Safe boot state: Relays OFF, PhotoMOS MUTED; keep DAC ~CS LOW if +5V_BUCK is unpowered
     * (USB-only bench mode) so +3V3_DIG never back-powers +5V_BUCK through MCP4822 ESD diodes! */
    const uint32_t cs_mask = (1u << PIN_CS_DAC0_N) | (1u << PIN_CS_DAC1_N) |
                             (1u << PIN_CS_DAC2_N) | (1u << PIN_CS_DAC3_N);
    const uint32_t out_pins = (1u << PIN_RELAY_BYPASS_EN) | (1u << PIN_LED_FS1_BYPASS) |
                              (1u << PIN_LED_FS2_STATUS)  | (1u << PIN_LED_AUDIO_PEAK) |
                              (1u << PIN_PHOTOMOS_MUTE_EN) | cs_mask;
    SIO_GPIO_OUT_CLR = (1u << PIN_RELAY_BYPASS_EN) | (1u << PIN_LED_FS1_BYPASS) |
                       (1u << PIN_LED_FS2_STATUS)  | (1u << PIN_LED_AUDIO_PEAK) | cs_mask;
    SIO_GPIO_OUT_SET = (1u << PIN_PHOTOMOS_MUTE_EN) | (hal_gpio_read(PIN_PEDAL_PWR_GOOD) ? cs_mask : 0u);
    SIO_GPIO_OE_SET = out_pins;

    /* UART0 (GPIO0=TX, GPIO1=RX, FUNCSEL=2, exact 31,250 bps MIDI @ 48.000 MHz CLK_PERI) */
    IO_BANK0_CTRL(PIN_DBG_TX_TP) = 2u;
    IO_BANK0_CTRL(PIN_UART0_RX_MIDI) = 2u;
    UART0_CR = 0u;
    UART0_IBRD = 96u;
    UART0_FBRD = 0u;
    UART0_LCR_H = (3u << 5u) | (1u << 4u);
    UART0_CR = (1u << 9u) | (1u << 0u);

    /* SPI0 (GPIO18=SCK, GPIO19=TX, 16-bit Mode 0 @ 12.0 MHz <= 20 MHz MCP4822 max) */
    SPI0_CR1 = 0u;
    SPI0_CPSR = 4u;       /* 48 MHz / 4 = 12.0 MHz */
    SPI0_CR0 = 0x000Fu;   /* DSS=15 (16-bit), SPO=0, SPH=0 */
    SPI0_CR1 = (1u << 1u);
    /* Force SPI0 + ~CS lines to safe state matching PEDAL_PWR_GOOD (LOW in USB-only mode!) */
    s_spi_pwr_enabled = !hal_gpio_read(PIN_PEDAL_PWR_GOOD);
    hal_spi_dac_set_power_safe(hal_gpio_read(PIN_PEDAL_PWR_GOOD));

    /* I2C0 (GPIO4=SDA, GPIO5=SCL, FUNCSEL=3, 400 kHz Fast Mode @ 120 MHz CLK_SYS) */
    IO_BANK0_CTRL(PIN_I2C0_SDA) = 3u;
    IO_BANK0_CTRL(PIN_I2C0_SCL) = 3u;
    I2C0_ENABLE = 0u;
    I2C0_CON = 0x65u;
    I2C0_FS_SCL_HCNT = 112u;
    I2C0_FS_SCL_LCNT = 188u;
    I2C0_ENABLE = 1u;

    /* SAR ADC enable */
    ADC_CS = (1u << 0u);
    s_last_adc_ch = 0xFFu;
}

void hal_spi_dac_set_power_safe(bool pedal_pwr_good) {
    const uint32_t cs_mask = (1u << PIN_CS_DAC0_N) | (1u << PIN_CS_DAC1_N) |
                             (1u << PIN_CS_DAC2_N) | (1u << PIN_CS_DAC3_N);
    const uint32_t spi_mask = (1u << PIN_SPI0_SCK) | (1u << PIN_SPI0_TX);
    if (!pedal_pwr_good) {
        /* USB-only / brownout defense-in-depth: drive SPI0 + all ~CS GPIOs strictly LOW (0V) */
        IO_BANK0_CTRL(PIN_SPI0_SCK) = 5u; /* SIO */
        IO_BANK0_CTRL(PIN_SPI0_TX)  = 5u; /* SIO */
        SIO_GPIO_OUT_CLR = spi_mask | cs_mask;
        SIO_GPIO_OE_SET  = spi_mask | cs_mask;
        s_spi_pwr_enabled = false;
    } else if (!s_spi_pwr_enabled) {
        /* +5V_BUCK present: deassert ~CS HIGH and connect SPI0 peripheral */
        SIO_GPIO_OUT_SET = cs_mask;
        SIO_GPIO_OE_SET  = cs_mask;
        IO_BANK0_CTRL(PIN_SPI0_SCK) = 1u; /* SPI0_SCK */
        IO_BANK0_CTRL(PIN_SPI0_TX)  = 1u; /* SPI0_TX */
        s_spi_pwr_enabled = true;
    }
}

void hal_spi_dac_write16(uint8_t dac_idx, uint16_t word) {
    if (dac_idx >= 4u) return;
    /* Ensure all ~CS lines are deasserted HIGH once +5V_BUCK is active */
    const uint32_t cs_mask = (1u << PIN_CS_DAC0_N) | (1u << PIN_CS_DAC1_N) |
                             (1u << PIN_CS_DAC2_N) | (1u << PIN_CS_DAC3_N);
    SIO_GPIO_OUT_SET = cs_mask;

    /* Drain any stale RX FIFO entries before transfer */
    while ((SPI0_SR & (1u << 2u)) != 0u) {
        (void)SPI0_DR;
    }

    uint32_t cs_pin = DAC_CS_PINS[dac_idx];
    hal_gpio_write(cs_pin, false);

    uint32_t guard = 0u;
    while (((SPI0_SR & (1u << 1u)) == 0u) && (guard++ < 10000u)) { } /* TNF */
    SPI0_DR = word;

    /* Wait for RNE (bit 2) confirming all 16 bits shifted across CLK_PERI, drain DR, and wait BSY=0! */
    guard = 0u;
    while (((SPI0_SR & (1u << 2u)) == 0u) && (guard++ < 10000u)) { } /* RNE */
    (void)SPI0_DR;
    guard = 0u;
    while (((SPI0_SR & (1u << 4u)) != 0u) && (guard++ < 10000u)) { } /* BSY == 0 */

    hal_gpio_write(cs_pin, true);
}

uint16_t hal_adc_read_ch(uint8_t adc_ch) {
    uint32_t ch = (uint32_t)(adc_ch & 0x03u);
    bool mux_changed = (s_last_adc_ch != adc_ch);
    s_last_adc_ch = adc_ch;
    uint8_t passes = mux_changed ? 2u : 1u;
    uint16_t res = 0u;
    for (uint8_t p = 0u; p < passes; p++) {
        ADC_CS = (1u << 0u) | (ch << 12u) | (1u << 2u);
        uint32_t guard = 0u;
        while (((ADC_CS & (1u << 8u)) == 0u) && (guard++ < 2000u)) { }
        res = (uint16_t)(ADC_RESULT & 0x0FFFu);
    }
    return res;
}

bool hal_uart0_try_read_dr(uint16_t *out_dr) {
    if ((UART0_FR & (1u << 4u)) != 0u) {
        return false;
    }
    *out_dr = (uint16_t)(UART0_DR & 0x0FFFu);
    return true;
}

void hal_uart0_clear_rsr(void) {
    UART0_RSR = 0x0Fu;
}

bool hal_i2c0_write_timeout(uint8_t addr7, const uint8_t *buf, size_t len, uint32_t timeout_us) {
    if (len == 0u) return true;
    uint32_t start = hal_time_us_32();
    I2C0_ENABLE = 0u;
    I2C0_TAR = addr7 & 0x7Fu;
    I2C0_ENABLE = 1u;
    (void)I2C0_CLR_TX_ABRT;

    for (size_t i = 0u; i < len; i++) {
        while ((I2C0_STATUS & (1u << 1u)) == 0u) {
            if ((uint32_t)(hal_time_us_32() - start) >= timeout_us) return false;
            if (I2C0_TX_ABRT_SRC != 0u) return false;
        }
        uint32_t cmd = buf[i];
        if (i == len - 1u) {
            cmd |= (1u << 9u); /* STOP */
        }
        I2C0_DATA_CMD = cmd;
    }
    /* Wait for BOTH TX FIFO Empty (bit 2) AND Master Activity Idle (bit 5 == 0) so STOP completes! */
    while (((I2C0_STATUS & (1u << 2u)) == 0u) || ((I2C0_STATUS & (1u << 5u)) != 0u)) {
        if ((uint32_t)(hal_time_us_32() - start) >= timeout_us) return false;
        if (I2C0_TX_ABRT_SRC != 0u) return false;
    }
    return (I2C0_TX_ABRT_SRC == 0u);
}

bool hal_flash_read(uint32_t slot_idx, void *dst, size_t len) {
    const void *src = (const void *)(uintptr_t)((slot_idx & 1u) ? FLASH_SLOT_B_XIP : FLASH_SLOT_A_XIP);
    memcpy(dst, src, len);
    return true;
}

/* RP2040 Boot ROM table lookup (RP2040 Datasheet Section 2.8.3.1) */
typedef void *(*rom_table_lookup_fn)(uint16_t *table, uint32_t code);
typedef void  (*rom_reset_usb_boot_fn)(uint32_t usb_activity_gpio_pin_mask, uint32_t disable_interface_mask);
typedef void  (*rom_connect_internal_flash_fn)(void);
typedef void  (*rom_flash_exit_xip_fn)(void);
typedef void  (*rom_flash_range_erase_fn)(uint32_t addr, size_t count, uint32_t block_size, uint8_t block_cmd);
typedef void  (*rom_flash_range_program_fn)(uint32_t addr, const uint8_t *data, size_t count);
typedef void  (*rom_flash_flush_cache_fn)(void);
typedef void  (*rom_flash_enter_cmd_xip_fn)(void);

static uint16_t rom_hword_as_ptr(uint32_t rom_addr) {
    volatile uint32_t addr = rom_addr;
    return *(const volatile uint16_t *)(uintptr_t)addr;
}

static void *rom_func_lookup(uint8_t c1, uint8_t c2) {
    rom_table_lookup_fn lookup = (rom_table_lookup_fn)(uintptr_t)rom_hword_as_ptr(0x00000018u);
    uint16_t *func_table = (uint16_t *)(uintptr_t)rom_hword_as_ptr(0x00000014u);
    return lookup(func_table, (uint32_t)c1 | ((uint32_t)c2 << 8u));
}

/* Zero-padded 4 KB sector staging buffer in SRAM (prevents OOB read past 2740-byte struct!) */
static uint8_t s_flash_page_buf[4096];

/* SRAM-resident inner XIP-off routine: zero XIP Flash instruction fetches while Flash is unmapped! */
__attribute__((section(".ramfunc"), noinline))
static void flash_do_erase_program_in_ram(
    uint32_t flash_off,
    size_t prog_len,
    rom_connect_internal_flash_fn f_conn,
    rom_flash_exit_xip_fn f_exit,
    rom_flash_range_erase_fn f_ers,
    rom_flash_range_program_fn f_prg,
    rom_flash_flush_cache_fn f_flsh,
    rom_flash_enter_cmd_xip_fn f_xip
) {
    uint32_t pm;
    __asm__ volatile("mrs %0, primask\ncpsid i" : "=r"(pm) :: "memory");
    f_conn();
    f_exit();
    f_ers(flash_off, 4096u, 65536u, 0xD8u);
    f_prg(flash_off, s_flash_page_buf, prog_len);
    f_flsh();
    f_xip();
    __asm__ volatile("msr primask, %0" :: "r"(pm) : "memory");
}

bool hal_flash_erase_and_program(uint32_t slot_idx, const void *src, size_t len) {
    if (len == 0u || len > sizeof(s_flash_page_buf)) {
        return false;
    }
    uint32_t flash_off = (slot_idx & 1u) ? FLASH_SLOT_B_OFF : FLASH_SLOT_A_OFF;
    rom_connect_internal_flash_fn f_conn = (rom_connect_internal_flash_fn)rom_func_lookup('I', 'F');
    rom_flash_exit_xip_fn         f_exit = (rom_flash_exit_xip_fn)rom_func_lookup('E', 'X');
    rom_flash_range_erase_fn      f_ers  = (rom_flash_range_erase_fn)rom_func_lookup('R', 'E');
    rom_flash_range_program_fn    f_prg  = (rom_flash_range_program_fn)rom_func_lookup('R', 'P');
    rom_flash_flush_cache_fn      f_flsh = (rom_flash_flush_cache_fn)rom_func_lookup('F', 'C');
    rom_flash_enter_cmd_xip_fn    f_xip  = (rom_flash_enter_cmd_xip_fn)rom_func_lookup('C', 'X');
    if (!f_conn || !f_exit || !f_ers || !f_prg || !f_flsh || !f_xip) {
        return false;
    }

    size_t prog_len = (len + 255u) & ~255u;
    memset(s_flash_page_buf, 0xFF, prog_len);
    memcpy(s_flash_page_buf, src, len);

    /* Request Core 0 to park safely in SRAM before unmapping XIP Flash! */
    s_core0_lockout_req = 1u;
    __asm__ volatile("dmb\nsev" ::: "memory");
    uint32_t wait_start = hal_time_us_32();
    while ((s_core0_parked_ram == 0u) && ((uint32_t)(hal_time_us_32() - wait_start) < 5000u)) {
        __asm__ volatile("nop");
    }
    if (s_core0_parked_ram == 0u) {
        /* Core 0 did not park in SRAM: ABORT cleanly to prevent XIP HardFault! */
        s_core0_lockout_req = 0u;
        __asm__ volatile("dmb\nsev" ::: "memory");
        return false;
    }

    flash_do_erase_program_in_ram(flash_off, prog_len, f_conn, f_exit, f_ers, f_prg, f_flsh, f_xip);

    s_core0_lockout_req = 0u;
    __asm__ volatile("dmb\nsev" ::: "memory");
    return true;
}

void hal_reset_usb_boot(uint32_t usb_activity_gpio_pin_mask, uint32_t disable_interface_mask) {
    rom_reset_usb_boot_fn fn = (rom_reset_usb_boot_fn)rom_func_lookup('U', 'B');
    if (fn != NULL) {
        fn(usb_activity_gpio_pin_mask, disable_interface_mask);
    }
    for (;;) {
        __asm__ volatile("wfi");
    }
}

/* ============================================================================
 * Bare-Metal RP2040 USB Device Stack (Composite USB-MIDI + CDC-ACM 1200bps)
 * Uses shared multi-packet EP0 engine (usb_ep0.c) verified by host unit tests.
 * ============================================================================ */
static usb_ep0_state_t s_ep0;
static uint8_t  s_ep1_pid = 0u;
static uint8_t  s_ep3_out_pid = 0u;
static uint8_t  s_usb_midi_rx_q[64];
static uint8_t  s_usb_midi_q_len = 0u;
static uint8_t  s_usb_midi_q_pos = 0u;

static void rp_ep0_tx(void *ctx, const uint8_t *data, uint16_t len, uint8_t pid) {
    (void)ctx;
    if (len > BEADS_USB_EP0_MAX_PKT) len = BEADS_USB_EP0_MAX_PKT;
    if (data != NULL) {
        for (uint16_t i = 0u; i < len; i++) {
            USB_EP0_BUF0[i] = data[i];
        }
    }
    uint32_t ctrl = (uint32_t)len | (1u << 15u) | ((pid ? 1u : 0u) << 13u);
    USB_BUF_CTRL_IN(0u) = ctrl;
    __asm__ volatile("nop\nnop\nnop");
    USB_BUF_CTRL_IN(0u) = ctrl | (1u << 10u); /* AVAILABLE */
}

static void rp_ep0_rx_arm(void *ctx, uint16_t max_len, uint8_t pid) {
    (void)ctx;
    if (max_len > BEADS_USB_EP0_MAX_PKT) max_len = BEADS_USB_EP0_MAX_PKT;
    uint32_t ctrl = (uint32_t)max_len | ((pid ? 1u : 0u) << 13u);
    USB_BUF_CTRL_OUT(0u) = ctrl;
    __asm__ volatile("nop\nnop\nnop");
    USB_BUF_CTRL_OUT(0u) = ctrl | (1u << 10u);
}

static void rp_ep0_stall(void *ctx) {
    (void)ctx;
    USB_EP_STALL_ARM = (1u << 0u) | (1u << 1u);
    USB_BUF_CTRL_IN(0u)  = (1u << 11u); /* STALL */
    USB_BUF_CTRL_OUT(0u) = (1u << 11u);
}

static void rp_ep1_out_arm(uint8_t pid) {
    uint32_t ctrl = 64u | ((pid ? 1u : 0u) << 13u);
    USB_BUF_CTRL_OUT(1u) = ctrl;
    __asm__ volatile("nop\nnop\nnop");
    USB_BUF_CTRL_OUT(1u) = ctrl | (1u << 10u);
}

static void rp_ep3_out_arm(uint8_t pid) {
    uint32_t ctrl = 64u | ((pid ? 1u : 0u) << 13u);
    USB_BUF_CTRL_OUT(3u) = ctrl;
    __asm__ volatile("nop\nnop\nnop");
    USB_BUF_CTRL_OUT(3u) = ctrl | (1u << 10u);
}

static void rp_set_address(void *ctx, uint8_t addr) {
    (void)ctx;
    USB_ADDR_ENDP = addr & 0x7Fu;
}

static void rp_on_configured(void *ctx, uint8_t config_val) {
    (void)ctx;
    (void)config_val;
    s_ep1_pid = 0u;
    s_ep3_out_pid = 0u;
    rp_ep1_out_arm(0u);
    rp_ep3_out_arm(0u);
}

static void rp_on_1200baud_reset(void *ctx) {
    (void)ctx;
    rp2040_delay_us(2000u);
    hal_reset_usb_boot(0u, 0u);
}

static const usb_ep0_hw_t RP_USB_EP0_HW = {
    .ep0_tx            = rp_ep0_tx,
    .ep0_rx_arm        = rp_ep0_rx_arm,
    .ep0_stall         = rp_ep0_stall,
    .set_address       = rp_set_address,
    .on_configured     = rp_on_configured,
    .on_1200baud_reset = rp_on_1200baud_reset,
    .ctx               = NULL,
};

void hal_usb_init_on_core1(void) {
    usb_ep0_init(&s_ep0);
    s_ep1_pid = 0u;
    s_ep3_out_pid = 0u;
    s_usb_midi_q_len = 0u;
    s_usb_midi_q_pos = 0u;

    memset((void *)USB_DPRAM_BASE, 0, 4096u);
    USB_USB_MUXING = (1u << 0u) | (1u << 3u); /* TO_PHY | SOFTCON */
    USB_USB_PWR    = (1u << 2u) | (1u << 3u); /* VBUS_DETECT | OVERRIDE_EN */
    USB_MAIN_CTRL  = 1u;                      /* CONTROLLER_EN (Device mode) */
    USB_SIE_CTRL   = (1u << 29u);             /* EP0_INT_1BUF */

    /* Configure EP1 OUT (MIDI Bulk @ 0x0180), EP2 IN (CDC Int @ 0x0200),
     * EP3 OUT (CDC Data Bulk @ 0x0240), EP3 IN (CDC Data Bulk @ 0x0280) */
    USB_EP_CTRL(1u, 0u) = (1u << 31u) | (2u << 26u) | 0x0180u;
    USB_EP_CTRL(2u, 1u) = (1u << 31u) | (3u << 26u) | 0x0200u;
    USB_EP_CTRL(3u, 0u) = (1u << 31u) | (2u << 26u) | 0x0240u;
    USB_EP_CTRL(3u, 1u) = (1u << 31u) | (2u << 26u) | 0x0280u;
    rp_ep1_out_arm(0u);
    rp_ep3_out_arm(0u);

    USB_SIE_CTRL |= (1u << 16u);              /* PULLUP_EN = 1 */
}

void hal_usb_task_on_core1(void) {
    uint32_t sie = USB_SIE_STATUS;

    /* Bus Reset */
    if ((sie & (1u << 19u)) != 0u) {
        USB_SIE_STATUS = (1u << 19u);
        USB_ADDR_ENDP = 0u;
        usb_ep0_bus_reset(&s_ep0);
        s_ep1_pid = 0u;
        s_ep3_out_pid = 0u;
        rp_ep1_out_arm(0u);
        rp_ep3_out_arm(0u);
    }

    /* EP0 SETUP packet received */
    if ((sie & (1u << 17u)) != 0u) {
        USB_SIE_STATUS = (1u << 17u);
        uint8_t setup[8];
        for (uint8_t i = 0u; i < 8u; i++) {
            setup[i] = USB_SETUP_PKT[i];
        }
        usb_ep0_handle_setup(&s_ep0, setup, &RP_USB_EP0_HW);
    }

    uint32_t bstat = USB_BUFF_STATUS;
    if (bstat != 0u) {
        /* EP0 IN complete (bit 0) -> multi-packet continuation or pending SET_ADDRESS */
        if ((bstat & (1u << 0u)) != 0u) {
            USB_BUFF_STATUS = (1u << 0u);
            usb_ep0_on_in_complete(&s_ep0, &RP_USB_EP0_HW);
        }
        /* EP0 OUT complete (bit 1) -> CDC SET_LINE_CODING payload or IN status ZLP */
        if ((bstat & (1u << 1u)) != 0u) {
            uint16_t rx_len = (uint16_t)(USB_BUF_CTRL_OUT(0u) & 0x03FFu);
            USB_BUFF_STATUS = (1u << 1u);
            uint8_t rx_copy[64];
            if (rx_len > sizeof(rx_copy)) rx_len = (uint16_t)sizeof(rx_copy);
            for (uint16_t i = 0u; i < rx_len; i++) {
                rx_copy[i] = USB_EP0_BUF0[i];
            }
            usb_ep0_on_out_complete(&s_ep0, rx_copy, rx_len, &RP_USB_EP0_HW);
        }
        /* EP1 OUT complete (bit 3) -> queue 4-byte USB-MIDI event packets */
        if ((bstat & (1u << 3u)) != 0u) {
            uint16_t rx_len = (uint16_t)(USB_BUF_CTRL_OUT(1u) & 0x03FFu);
            USB_BUFF_STATUS = (1u << 3u);
            if (rx_len >= 4u && rx_len <= sizeof(s_usb_midi_rx_q) && s_usb_midi_q_pos >= s_usb_midi_q_len) {
                for (uint16_t i = 0u; i < rx_len; i++) {
                    s_usb_midi_rx_q[i] = USB_EP1_OUT_BUF[i];
                }
                s_usb_midi_q_len = (uint8_t)(rx_len & ~3u);
                s_usb_midi_q_pos = 0u;
            }
            s_ep1_pid ^= 1u;
            rp_ep1_out_arm(s_ep1_pid);
        }
        /* EP3 OUT complete (bit 7) -> drain & re-arm CDC Data OUT cleanly */
        if ((bstat & (1u << 7u)) != 0u) {
            USB_BUFF_STATUS = (1u << 7u);
            s_ep3_out_pid ^= 1u;
            rp_ep3_out_arm(s_ep3_out_pid);
        }
        /* Clear any unexpected residual status bits safely */
        uint32_t rest = bstat & ~((1u << 0u) | (1u << 1u) | (1u << 3u) | (1u << 7u));
        if (rest != 0u) {
            USB_BUFF_STATUS = rest;
        }
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
