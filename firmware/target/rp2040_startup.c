#include <stdint.h>

extern uint32_t _sidata;
extern uint32_t _sdata;
extern uint32_t _edata;
extern uint32_t _sbss;
extern uint32_t _ebss;
extern uint32_t _stack_top;
extern uint32_t _core1_stack_top;

extern int main(void);

void Reset_Handler(void);
void Default_Handler(void);

/* ============================================================================
 * Genuine 256-byte RP2040 Stage-2 XIP Bootloader (W25Q128 0x03 Standard Read)
 * Assembled directly as Thumb-1 instructions into .boot2; CRC-32 (poly 0x04C11DB7)
 * is patched into bytes [252..255] by tools/elf2uf2.py.
 * Configures XIP_SSI (0x18000000):
 *   1. SSIENR (+0x08) = 0
 *   2. BAUDR  (+0x14) = 4  (CLK_SYS / 4)
 *   3. CTRLR0 (+0x00) = (31 << 16) | (3 << 8)  (DFS_32=32-bit, TMOD=EEPROM_READ)
 *   4. SPI_CTRLR0 (0x180000F4) = (0x03 << 24) | (2 << 8) | (6 << 2) (0x03 cmd, 8b inst, 24b addr)
 *   5. CTRLR1 (+0x04) = 0  (NDF=0 -> 1 data frame per XIP read)
 *   6. SSIENR (+0x08) = 1
 *   7. SCB->VTOR (0xE000ED08) = 0x10000100; MSP = [0x10000100]; BX [0x10000104]
 * ============================================================================ */
__asm__(
    ".syntax unified\n"
    ".cpu cortex-m0plus\n"
    ".thumb\n"
    ".section .boot2, \"ax\", %progbits\n"
    ".global rp2040_boot2_block\n"
    "rp2040_boot2_block:\n"
    "    ldr r3, =0x18000000\n"       /* XIP_SSI_BASE */
    "    movs r0, #0\n"
    "    str r0, [r3, #0x08]\n"       /* SSIENR = 0 */
    "    movs r0, #4\n"
    "    str r0, [r3, #0x14]\n"       /* BAUDR = 4 */
    "    ldr r0, =0x001F0300\n"       /* CTRLR0: DFS_32=31, TMOD=3 (EEPROM read) */
    "    str r0, [r3, #0x00]\n"
    "    ldr r2, =0x180000F4\n"       /* XIP_SSI_SPI_CTRLR0 */
    "    ldr r0, =0x03000218\n"       /* XIP_CMD=0x03, INST_L=2(8b), ADDR_L=6(24b), TRANS_TYPE=0 */
    "    str r0, [r2, #0x00]\n"
    "    movs r0, #0\n"
    "    str r0, [r3, #0x04]\n"       /* CTRLR1 = 0 */
    "    movs r0, #1\n"
    "    str r0, [r3, #0x08]\n"       /* SSIENR = 1 (XIP active!) */
    "    ldr r0, =0x10000100\n"       /* Application vector table in XIP Flash */
    "    ldr r1, =0xE000ED08\n"       /* PPB SCB->VTOR */
    "    str r0, [r1, #0x00]\n"
    "    ldmia r0, {r0, r1}\n"        /* r0 = initial MSP, r1 = Reset_Handler (+1 Thumb) */
    "    msr msp, r0\n"
    "    bx r1\n"
    "    .pool\n"
    "    .balign 256, 0x00\n"
);

#define VEC_DEFAULT ((uint32_t)Default_Handler)

__attribute__((section(".vectors"), used))
const uint32_t g_pfnVectors[48] = {
    (uint32_t)&_stack_top,
    (uint32_t)Reset_Handler,
    VEC_DEFAULT, /* NMI */
    VEC_DEFAULT, /* HardFault */
    0u, 0u, 0u, 0u, 0u, 0u, 0u,
    VEC_DEFAULT, /* SVCall */
    0u, 0u,
    VEC_DEFAULT, /* PendSV */
    VEC_DEFAULT, /* SysTick */
    /* 32 RP2040 External IRQs (0..31) — zero NULL vectors! */
    VEC_DEFAULT, VEC_DEFAULT, VEC_DEFAULT, VEC_DEFAULT,
    VEC_DEFAULT, VEC_DEFAULT, VEC_DEFAULT, VEC_DEFAULT,
    VEC_DEFAULT, VEC_DEFAULT, VEC_DEFAULT, VEC_DEFAULT,
    VEC_DEFAULT, VEC_DEFAULT, VEC_DEFAULT, VEC_DEFAULT,
    VEC_DEFAULT, VEC_DEFAULT, VEC_DEFAULT, VEC_DEFAULT,
    VEC_DEFAULT, VEC_DEFAULT, VEC_DEFAULT, VEC_DEFAULT,
    VEC_DEFAULT, VEC_DEFAULT, VEC_DEFAULT, VEC_DEFAULT,
    VEC_DEFAULT, VEC_DEFAULT, VEC_DEFAULT, VEC_DEFAULT,
};

void Default_Handler(void) {
    for (;;) {
        __asm__ volatile("wfi");
    }
}

void Reset_Handler(void) {
    /* Ensure Core 0 VTOR points to application vector table */
    *(volatile uint32_t *)0xE000ED08u = (uint32_t)g_pfnVectors;

    /* Copy .ramfunc and .data from XIP Flash into SRAM */
    uint32_t *src = &_sidata;
    uint32_t *dst = &_sdata;
    while (dst < &_edata) {
        *dst++ = *src++;
    }
    dst = &_sbss;
    while (dst < &_ebss) {
        *dst++ = 0u;
    }
    (void)main();
    for (;;) {
        __asm__ volatile("wfi");
    }
}

/* RP2040 SIO Inter-Core FIFO Launch for Core 1 (RP2040 Datasheet Section 2.8.2) */
#define SIO_FIFO_ST  (*(volatile uint32_t *)0xD0000050u)
#define SIO_FIFO_WR  (*(volatile uint32_t *)0xD0000054u)
#define SIO_FIFO_RD  (*(volatile uint32_t *)0xD0000058u)

static void sio_fifo_drain(void) {
    while ((SIO_FIFO_ST & 1u) != 0u) {
        (void)SIO_FIFO_RD;
    }
}

static void sio_fifo_push(uint32_t v) {
    while ((SIO_FIFO_ST & 2u) == 0u) { }
    SIO_FIFO_WR = v;
    __asm__ volatile("sev");
}

static uint32_t sio_fifo_pop(void) {
    while ((SIO_FIFO_ST & 1u) == 0u) {
        __asm__ volatile("wfe");
    }
    return SIO_FIFO_RD;
}

void rp2040_launch_core1(void (*entry)(void)) {
    const uint32_t cmd_seq[6] = {
        0u, 0u, 1u,
        (uint32_t)g_pfnVectors,
        (uint32_t)&_core1_stack_top,
        (uint32_t)entry,
    };
    uint32_t seq = 0u;
    while (seq < 6u) {
        uint32_t cmd = cmd_seq[seq];
        if (cmd == 0u) {
            sio_fifo_drain();
            __asm__ volatile("sev");
        }
        sio_fifo_push(cmd);
        uint32_t resp = sio_fifo_pop();
        if (resp == cmd) {
            seq++;
        } else {
            seq = 0u;
        }
    }
}
