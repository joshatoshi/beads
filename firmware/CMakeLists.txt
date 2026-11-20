cmake_minimum_required(VERSION 3.13)
project(beads_bridge C CXX ASM)
set(CMAKE_C_STANDARD 11)
set(CMAKE_C_STANDARD_REQUIRED ON)

set(BEADS_CORE_SRCS
    src/bypass_sequencer.c
    src/bezier_drift.c
    src/dac_mcp4822.c
    src/midi_router.c
    src/presets.c
    src/cv_engine.c
    src/oled_ui.c
    src/usb_ep0.c
    src/main.c
)

if(DEFINED ENV{PICO_SDK_PATH} AND EXISTS "$ENV{PICO_SDK_PATH}/external/pico_sdk_import.cmake")
    set(PICO_BOARD pico)
    include("$ENV{PICO_SDK_PATH}/external/pico_sdk_import.cmake")
    pico_sdk_init()
    # Use Pico SDK HAL adapter (target/pico_sdk_hal.c) rather than bare-metal target/rp2040_hal.c
    # so SDK clocks, multicore FIFO, IRQ vectors, and flash lockout never collide.
    add_executable(beads_bridge ${BEADS_CORE_SRCS} target/pico_sdk_hal.c)
    target_include_directories(beads_bridge PRIVATE include)
    target_compile_definitions(beads_bridge PRIVATE PICO_CORE1_STACK_SIZE=0x1000)
    target_compile_options(beads_bridge PRIVATE -Wall -Wextra -Werror -fstack-usage)
    target_link_libraries(beads_bridge pico_stdlib pico_multicore hardware_spi hardware_i2c hardware_adc hardware_uart hardware_flash)
    pico_add_extra_outputs(beads_bridge)
else()
    # Host silicon-mock unit test build via CMake/CTest (use firmware/Makefile for offline arm-none-eabi UF2 build)
    enable_testing()
    add_executable(test_beads_firmware ${BEADS_CORE_SRCS} tests/test_beads_firmware.c)
    target_include_directories(test_beads_firmware PRIVATE include)
    target_compile_definitions(test_beads_firmware PRIVATE BEADS_HOST_UNIT_TEST=1)
    target_compile_options(test_beads_firmware PRIVATE -Wall -Wextra -Werror -O2)
    add_test(NAME beads_unit_tests COMMAND test_beads_firmware)
endif()
