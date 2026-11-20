/* RP2040 Linker Script for Beads Pedalboard Skiff (16 MB W25Q128 QSPI Flash + 264 KB SRAM) */
MEMORY
{
    FLASH(rx)  : ORIGIN = 0x10000000, LENGTH = 16376K /* Reserve top 8 KB (2x 4 KB) for A/B NVM */
    RAM(rwx)   : ORIGIN = 0x20000000, LENGTH = 256K
}

ENTRY(Reset_Handler)

SECTIONS
{
    .boot2 : {
        KEEP(*(.boot2))
        . = ALIGN(256);
    } > FLASH

    .text : {
        KEEP(*(.vectors))
        *(.text*)
        *(.rodata*)
        . = ALIGN(4);
        _etext = .;
    } > FLASH

    .data : AT(_etext) {
        _sdata = .;
        KEEP(*(.ramfunc*))
        *(.data*)
        . = ALIGN(4);
        _edata = .;
    } > RAM

    _sidata = LOADADDR(.data);

    .bss (NOLOAD) : {
        _sbss = .;
        *(.bss*)
        *(COMMON)
        . = ALIGN(4);
        _ebss = .;
    } > RAM

    /* Core 1 stack (4 KB = PICO_CORE1_STACK_SIZE) + Core 0 stack (4 KB) at top of SRAM */
    _core1_stack_bottom = ORIGIN(RAM) + LENGTH(RAM) - 0x2000;
    _core1_stack_top    = ORIGIN(RAM) + LENGTH(RAM) - 0x1000;
    _stack_top          = ORIGIN(RAM) + LENGTH(RAM);
}
