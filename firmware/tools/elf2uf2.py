#!/usr/bin/env python3
"""Convert an ARM Cortex-M0+ RP2040 ELF/BIN image into a valid RP2040 UF2 file
(Family ID = 0xE48BFF56, exact 512-byte UF2 blocks, W25Q128 boot2 CRC32 patched!)."""
from __future__ import annotations

import pathlib
import struct
import subprocess
import sys

UF2_MAGIC_START0 = 0x0A324655
UF2_MAGIC_START1 = 0x9E5D5157
UF2_MAGIC_END    = 0x0AB16F30
UF2_FLAG_FAMILY  = 0x00002000
RP2040_FAMILY_ID = 0xE48BFF56
RP2040_FLASH_BASE = 0x10000000


def rp2040_boot2_crc32(data252: bytes) -> int:
    """RP2040 Boot ROM CRC-32 (poly 0x04C11DB7, MSB-first, init 0xFFFFFFFF, no final XOR)."""
    crc = 0xFFFFFFFF
    for b in data252:
        crc ^= (b << 24)
        for _ in range(8):
            if crc & 0x80000000:
                crc = ((crc << 1) ^ 0x04C11DB7) & 0xFFFFFFFF
            else:
                crc = (crc << 1) & 0xFFFFFFFF
    return crc


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(f"Usage: {argv[0]} <input.elf> <output.uf2>", file=sys.stderr)
        return 2
    elf_path = pathlib.Path(argv[1])
    uf2_path = pathlib.Path(argv[2])
    bin_path = uf2_path.with_suffix(".bin")

    subprocess.run(
        ["arm-none-eabi-objcopy", "-O", "binary", str(elf_path), str(bin_path)],
        check=True,
    )
    raw = bytearray(bin_path.read_bytes())
    if len(raw) < 256:
        raise RuntimeError(f"Binary too small ({len(raw)} bytes < 256-byte boot2)")

    # Patch RP2040 stage-2 boot CRC32 into bytes [252..256)
    crc = rp2040_boot2_crc32(bytes(raw[:252]))
    struct.pack_into("<I", raw, 252, crc)

    # Pad to 256-byte payload multiple
    if len(raw) % 256 != 0:
        raw.extend(b"\x00" * (256 - (len(raw) % 256)))

    num_blocks = len(raw) // 256
    blocks = bytearray()
    for blk in range(num_blocks):
        payload = bytes(raw[blk * 256 : (blk + 1) * 256])
        header = struct.pack(
            "<IIIIIIII",
            UF2_MAGIC_START0,
            UF2_MAGIC_START1,
            UF2_FLAG_FAMILY,
            RP2040_FLASH_BASE + blk * 256,
            256,
            blk,
            num_blocks,
            RP2040_FAMILY_ID,
        )
        block = header + payload + b"\x00" * (476 - 256) + struct.pack("<I", UF2_MAGIC_END)
        assert len(block) == 512
        blocks.extend(block)

    uf2_path.write_bytes(bytes(blocks))
    print(f"[OK] Generated RP2040 UF2: {uf2_path} ({num_blocks} blocks, {len(blocks)} bytes, family=0x{RP2040_FAMILY_ID:08X})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
