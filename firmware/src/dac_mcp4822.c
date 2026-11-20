#include "dac_mcp4822.h"
#include "hal.h"

void dac_bank_init(dac_bank_t *d) {
    d->enabled = false;
    d->spi_write_count = 0u;
    dac_bank_invalidate(d);
}

void dac_bank_invalidate(dac_bank_t *d) {
    /* Always use 0xFFFF sentinel (never uint8_t 0xFF!) so 0..4095 never collides! */
    for (uint8_t i = 0u; i < BEADS_NUM_CV_CHANNELS; i++) {
        d->shadow_code[i] = 0xFFFFu;
    }
}

void dac_bank_set_enabled(dac_bank_t *d, bool enabled) {
    if (enabled && !d->enabled) {
        /* Force fresh write of all 8 channels once analog rails clear POR */
        dac_bank_invalidate(d);
    }
    d->enabled = enabled;
}

uint16_t dac_mcp4822_encode_word(uint8_t ch_ab, uint16_t code12, bool gain_2x, bool active) {
    uint16_t w = (uint16_t)(code12 & 0x0FFFu);
    if (ch_ab != 0u) {
        w |= (1u << 15u); /* Bit 15: 0 = DAC A, 1 = DAC B */
    }
    if (!gain_2x) {
        w |= (1u << 13u); /* Bit 13 (~GA): 0 = 2x (0..4.095V), 1 = 1x (0..2.047V) */
    }
    if (active) {
        w |= (1u << 12u); /* Bit 12 (~SHDN): 1 = Active, 0 = Shutdown */
    }
    return w;
}

bool dac_bank_write_ch(dac_bank_t *d, uint8_t ch, uint16_t code12) {
    if (ch >= BEADS_NUM_CV_CHANNELS || !d->enabled) {
        return false;
    }
    if (code12 > 4095u) {
        code12 = 4095u;
    }
    /* Delta-gated SPI update: skip SPI clock bursts during steady state! */
    if (d->shadow_code[ch] == code12) {
        return false;
    }
    uint8_t dac_idx = (uint8_t)(ch >> 1u);   /* 0..3 -> U_DAC0..3 */
    uint8_t ch_ab   = (uint8_t)(ch & 1u);    /* 0 = VA, 1 = VB */
    uint16_t word = dac_mcp4822_encode_word(ch_ab, code12, true, true);
    hal_spi_dac_write16(dac_idx, word);
    d->shadow_code[ch] = code12;
    d->spi_write_count++;
    return true;
}
