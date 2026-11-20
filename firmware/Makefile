# Beads Pedalboard Skiff — RP2040 Dual-Core Target UF2 + Host Silicon-Mock Test Makefile
ARM_CC      := arm-none-eabi-gcc
ARM_NM      := arm-none-eabi-nm
HOST_CC     := gcc
BUILD_DIR   := build

CORE_SRCS   := src/bypass_sequencer.c \
               src/bezier_drift.c \
               src/dac_mcp4822.c \
               src/midi_router.c \
               src/presets.c \
               src/cv_engine.c \
               src/oled_ui.c \
               src/usb_ep0.c \
               src/main.c

CORE0_RT_OBJS := $(BUILD_DIR)/target/src/bypass_sequencer.o \
                 $(BUILD_DIR)/target/src/bezier_drift.o \
                 $(BUILD_DIR)/target/src/dac_mcp4822.o \
                 $(BUILD_DIR)/target/src/midi_router.o \
                 $(BUILD_DIR)/target/src/cv_engine.o \
                 $(BUILD_DIR)/target/src/main.o

TARGET_SRCS := $(CORE_SRCS) target/rp2040_startup.c target/rp2040_hal.c
TARGET_OBJS := $(patsubst %.c,$(BUILD_DIR)/target/%.o,$(TARGET_SRCS))

ARM_CFLAGS  := -mcpu=cortex-m0plus -mthumb -O2 -std=c11 -Iinclude \
               -Wall -Wextra -Werror -fstack-usage \
               -ffunction-sections -fdata-sections -DPICO_CORE1_STACK_SIZE=0x1000
ARM_LDFLAGS := -mcpu=cortex-m0plus -mthumb -T target/rp2040.ld -nostartfiles \
               -Wl,--gc-sections -Wl,-Map=$(BUILD_DIR)/beads_bridge.map --specs=nano.specs

HOST_CFLAGS := -O2 -std=c11 -Iinclude -Wall -Wextra -Werror -DBEADS_HOST_UNIT_TEST=1

.PHONY: all target test check_symbols check_stack check_hal_invariants clean

all: target check_symbols check_stack check_hal_invariants test

target: $(BUILD_DIR)/beads_bridge.uf2

$(BUILD_DIR)/target/%.o: %.c
	@mkdir -p $(dir $@)
	$(ARM_CC) $(ARM_CFLAGS) -c $< -o $@

$(BUILD_DIR)/beads_bridge.elf: $(TARGET_OBJS) target/rp2040.ld
	$(ARM_CC) $(TARGET_OBJS) $(ARM_LDFLAGS) -o $@

$(BUILD_DIR)/beads_bridge.uf2: $(BUILD_DIR)/beads_bridge.elf tools/elf2uf2.py
	python3 tools/elf2uf2.py $< $@

# Gate: verify ZERO 64-bit/float soft-helpers in entire ELF AND ZERO 32-bit soft-division in Core 0 2kHz RT objects!
check_symbols: $(BUILD_DIR)/beads_bridge.elf
	@echo "[CHECK] Verifying zero 64-bit/float helpers in ELF and zero soft-division in Core 0 2kHz objects..."
	@if $(ARM_NM) -u $(BUILD_DIR)/beads_bridge.elf $(BUILD_DIR)/target/src/*.o | grep -E '__aeabi_(uldivmod|ldivmod|fadd|fsub|fmul|fdiv|dadd|dsub|dmul|ddiv|i2f|f2iz|ui2f|d2iz)'; then \
	  echo "[FAIL] Forbidden 64-bit/float helper detected in firmware objects!"; exit 1; \
	fi
	@if $(ARM_NM) -u $(CORE0_RT_OBJS) | grep -E '__aeabi_(uidiv|idiv|uidivmod|idivmod)'; then \
	  echo "[FAIL] Forbidden 32-bit software division helper detected in Core 0 2kHz real-time objects!"; exit 1; \
	fi
	@echo "[PASS] Zero 64-bit/float helpers in ELF and zero __aeabi_(u)idiv(mod) in Core 0 2kHz RT objects!"

# Gate: verify every compiled target function's stack frame fits comfortably inside PICO_CORE1_STACK_SIZE (4096 B)!
check_stack: $(BUILD_DIR)/beads_bridge.elf
	@python3 -c 'import pathlib, sys; su=list(pathlib.Path("build/target").rglob("*.su")); assert su; worst=0; bad=[]; [bad.append((l.strip(), int(l.split()[1]))) for f in su for l in f.read_text().splitlines() if l.strip() and int(l.split()[1]) > 768]; worst=max(int(l.split()[1]) for f in su for l in f.read_text().splitlines() if l.strip()); print(f"[PASS] -fstack-usage checked ({len(su)} units): max frame = {worst} bytes (<= 768 B inside 4096 B Core 1 stack)"); assert not bad, f"Oversized stack frames: {bad}"'

# Gate: verify RP2040 EP1..EP3 EP_CTRL_INTERRUPT_PER_BUFFER (1u<<29u) in both HALs + ELF binary, and 16MB Flash size in CMakeLists.txt
check_hal_invariants: $(BUILD_DIR)/beads_bridge.elf
	@python3 -c 'import pathlib, re, struct; \
	rp = pathlib.Path("target/rp2040_hal.c").read_text(); \
	sdk = pathlib.Path("target/pico_sdk_hal.c").read_text(); \
	cm = pathlib.Path("CMakeLists.txt").read_text(); \
	rp_eps = re.findall(r"USB_EP_CTRL\([^)]+\)\s*=\s*([^;]+);", rp); \
	sdk_eps = re.findall(r"usb_dpram->ep_ctrl\[\d+\]\.(?:in|out)\s*=\s*([^;]+);", sdk); \
	assert len(rp_eps) == 4 and all("EP_CTRL_INTERRUPT_PER_BUFFER" in e for e in rp_eps), f"rp2040_hal.c EP_CTRL missing bit 29: {rp_eps}"; \
	assert len(sdk_eps) == 4 and all("EP_CTRL_INTERRUPT_PER_BUFFER" in e for e in sdk_eps), f"pico_sdk_hal.c ep_ctrl missing bit 29: {sdk_eps}"; \
	assert rp.index("usb_ep0_on_in_complete") < rp.index("usb_ep0_handle_setup"), "rp2040_hal.c must service BUFF_STATUS before SETUP_REC"; \
	assert sdk.index("usb_ep0_on_in_complete") < sdk.index("usb_ep0_handle_setup"), "pico_sdk_hal.c must service buf_status before SETUP_REC"; \
	assert "PICO_FLASH_SIZE_BYTES=16777216" in cm, "CMakeLists.txt missing PICO_FLASH_SIZE_BYTES=16777216"; \
	elf = pathlib.Path("build/beads_bridge.elf").read_bytes(); \
	missing = [hex(w) for w in (0xA8000180, 0xAC000200, 0xA8000240, 0xA8000280) if struct.pack("<I", w) not in elf]; \
	assert not missing, f"Compiled ELF missing EP_CTRL words: {missing}"; \
	print("[PASS] RP2040 USB EP1..EP3 EP_CTRL_INTERRUPT_PER_BUFFER (0xA8000180..0xA8000280) & 16MB PICO_FLASH_SIZE_BYTES verified!")'

$(BUILD_DIR)/test_beads_firmware: $(CORE_SRCS) tests/test_beads_firmware.c
	@mkdir -p $(BUILD_DIR)
	$(HOST_CC) $(HOST_CFLAGS) $(CORE_SRCS) tests/test_beads_firmware.c -o $@

test: $(BUILD_DIR)/test_beads_firmware
	./$(BUILD_DIR)/test_beads_firmware

clean:
	rm -rf $(BUILD_DIR)
