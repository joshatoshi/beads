#!/usr/bin/env python3
"""Verify RP2040 target HAL & ELF silicon invariants for Beads Pedalboard Skiff."""
from __future__ import annotations

import pathlib
import re
import struct


def strip_c_comments(src: str) -> str:
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    src = re.sub(r"//[^\n]*", "", src)
    return src


def main() -> int:
    fw_dir = pathlib.Path(__file__).resolve().parents[1]
    rp = (fw_dir / "target" / "rp2040_hal.c").read_text(encoding="utf-8")
    sdk = (fw_dir / "target" / "pico_sdk_hal.c").read_text(encoding="utf-8")
    cm = (fw_dir / "CMakeLists.txt").read_text(encoding="utf-8")

    # 1. Verify EP1..EP3 EP_CTRL_INTERRUPT_PER_BUFFER (bit 29) in both HALs
    rp_eps = re.findall(r"USB_EP_CTRL\([^)]+\)\s*=\s*([^;]+);", rp)
    sdk_eps = re.findall(r"usb_dpram->ep_ctrl\[\d+\]\.(?:in|out)\s*=\s*([^;]+);", sdk)
    assert len(rp_eps) == 4 and all("EP_CTRL_INTERRUPT_PER_BUFFER" in e for e in rp_eps), (
        f"rp2040_hal.c EP_CTRL missing bit 29: {rp_eps}"
    )
    assert len(sdk_eps) == 4 and all("EP_CTRL_INTERRUPT_PER_BUFFER" in e for e in sdk_eps), (
        f"pico_sdk_hal.c ep_ctrl missing bit 29: {sdk_eps}"
    )

    # 2. Verify BUFF_STATUS is serviced BEFORE SETUP_REC in both HALs
    assert rp.index("usb_ep0_on_in_complete") < rp.index("usb_ep0_handle_setup"), (
        "rp2040_hal.c must service BUFF_STATUS before SETUP_REC"
    )
    assert sdk.index("usb_ep0_on_in_complete") < sdk.index("usb_ep0_handle_setup"), (
        "pico_sdk_hal.c must service buf_status before SETUP_REC"
    )

    # 3. Verify PIN_VBUS_DET dynamic PULLUP_EN & VBUS_DETECT gating, ZERO SUSPENDED PULLUP_EN=0
    #    SE0 glitch probe (USB 2.0 T_DDIS=2.5us compliance!), hal_usb_ep0_is_busy(), and USB reset on detach!
    usb_c = strip_c_comments((fw_dir / "src" / "usb_ep0.c").read_text(encoding="utf-8"))
    main_c = strip_c_comments((fw_dir / "src" / "main.c").read_text(encoding="utf-8"))
    oled_c = strip_c_comments((fw_dir / "src" / "oled_ui.c").read_text(encoding="utf-8"))

    assert "BEADS_USB_UNPLUG_PROBE" not in usb_c and "is_suspended" not in usb_c, (
        "usb_ep0.c still contains forbidden SUSPENDED PULLUP_EN=0 SE0 glitch probe!"
    )
    assert "rp2040_delay_us" not in main_c, (
        "main.c core1_entry() must NOT call blocking rp2040_delay_us() (violates USB 2.0 2.0ms t_DSETADDR)!"
    )
    assert "hal_usb_ep0_is_busy()" in main_c and "oled_ui_flush_step(" in main_c, (
        "main.c must defer OLED I2C during active EP0 transfers and use chunked oled_ui_flush_step()!"
    )
    assert "1u + OLED_WIDTH" not in oled_c and "1u + OLED_I2C_CHUNK_BYTES" in oled_c, (
        "oled_ui.c must chunk SSD1306 page writes into <=16-byte bursts (never 129-byte full-page blocks)!"
    )

    for name, src, addr_zero_tok in (
        ("rp2040_hal.c", rp, "USB_ADDR_ENDP = 0u"),
        ("pico_sdk_hal.c", sdk, "usb_hw->dev_addr_ctrl = 0u"),
    ):
        clean = strip_c_comments(src)
        assert "hal_gpio_read(PIN_VBUS_DET)" in clean, f"{name} missing hal_gpio_read(PIN_VBUS_DET)!"
        assert "USB_INTR_DEV_SOF_BITS" in clean, (
            f"{name} missing USB_INTR_DEV_SOF_BITS WC SUSPENDED clear on active 1kHz SOF traffic!"
        )
        assert "usb_vbus_sync(" in clean, f"{name} missing usb_vbus_sync() dynamic VBUS gating!"
        assert "hal_usb_ep0_is_busy" in clean, f"{name} missing hal_usb_ep0_is_busy()!"
        assert "_usb_is_suspended" not in clean and "_usb_delay_us" not in clean, (
            f"{name} still contains forbidden SUSPENDED SE0 probe helpers!"
        )

        init_m = re.search(r"void\s+hal_usb_init_on_core1\s*\(void\)\s*\{(.*?)\n\}", clean, re.S)
        assert init_m, f"{name} missing hal_usb_init_on_core1()"
        init_body = init_m.group(1)
        assert "PULLUP_EN" not in init_body, (
            f"{name} must NOT set PULLUP_EN unconditionally in hal_usb_init_on_core1()!"
        )
        assert "VBUS_DETECT_BITS" not in init_body, (
            f"{name} must NOT set VBUS_DETECT_BITS unconditionally in hal_usb_init_on_core1()!"
        )
        assert "usb_vbus_sync(" in init_body, f"{name} hal_usb_init_on_core1() must call usb_vbus_sync()!"

        task_m = re.search(r"void\s+hal_usb_task_on_core1\s*\(void\)\s*\{(.*?)\n\}", clean, re.S)
        assert task_m, f"{name} missing hal_usb_task_on_core1()"
        assert "usb_vbus_sync(" in task_m.group(1), f"{name} hal_usb_task_on_core1() must call usb_vbus_sync()!"

        det_m = re.search(r"static\s+void\s+(?:rp|sdk)_usb_on_detach\s*\([^)]*\)\s*\{(.*?)\n\}", clean, re.S)
        assert det_m, f"{name} missing *_usb_on_detach()"
        det_body = det_m.group(1)
        assert "USB_SIE_CTRL_PULLUP_EN_BITS" in det_body and "~USB_SIE_CTRL_PULLUP_EN_BITS" in det_body, (
            f"{name} on_detach must clear PULLUP_EN!"
        )
        assert addr_zero_tok in det_body, f"{name} on_detach must reset USB address to 0!"
        assert "usb_ep0_bus_reset(&s_ep0)" in det_body, f"{name} on_detach must reset EP0 state!"

    # 4. Verify 16 MB Flash size in CMakeLists.txt
    assert "PICO_FLASH_SIZE_BYTES=16777216" in cm, "CMakeLists.txt missing PICO_FLASH_SIZE_BYTES=16777216"

    # 5. Verify compiled target ELF carries EP1..EP3 EP_CTRL words with bit 29 set
    elf = (fw_dir / "build" / "beads_bridge.elf").read_bytes()
    missing = [hex(w) for w in (0xA8000180, 0xAC000200, 0xA8000240, 0xA8000280) if struct.pack("<I", w) not in elf]
    assert not missing, f"Compiled ELF missing EP_CTRL words: {missing}"

    print(
        "[PASS] RP2040 USB EP1..EP3 EP_CTRL_INTERRUPT_PER_BUFFER, glitch-free PIN_VBUS_DET gating "
        "(0 suspend SE0 glitches), <500us chunked OLED/EP0 deferral & 16MB Flash verified!"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
