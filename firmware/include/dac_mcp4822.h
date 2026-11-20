#ifndef BEADS_DAC_MCP4822_H
#define BEADS_DAC_MCP4822_H

#include <stdbool.h>
#include <stdint.h>
#include "board_pins.h"

/* Delta-gated 4x MCP4822-E/SN (8 channels) SPI0 driver.
 * Shadow cache uses uint16_t initialized to 0xFFFF (NEVER uint8_t 0xFF!). */
typedef struct {
    uint16_t shadow_code[BEADS_NUM_CV_CHANNELS];
    bool     enabled;
    uint32_t spi_write_count;
} dac_bank_t;

void dac_bank_init(dac_bank_t *d);
void dac_bank_invalidate(dac_bank_t *d);
void dac_bank_set_enabled(dac_bank_t *d, bool enabled);
bool dac_bank_write_ch(dac_bank_t *d, uint8_t ch, uint16_t code12);
uint16_t dac_mcp4822_encode_word(uint8_t ch_ab, uint16_t code12, bool gain_2x, bool active);

#endif /* BEADS_DAC_MCP4822_H */
