#!/usr/bin/env bash
# Master End-to-End CI Verification Suite for Mutable Instruments Beads Pedalboard Skiff
# Worktree-portable: resolves repo root dynamically via BASH_SOURCE[0].
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export PYTHONDONTWRITEBYTECODE=1
cd "$ROOT"

echo "================================================================================"
echo "  BEADS PEDALBOARD SKIFF — MASTER 5-GATE VERIFICATION SUITE"
echo "  Repo Root: $ROOT"
echo "================================================================================"

echo ""
echo ">>> [GATE 1/5] 3-Board KiCad 9 ERC & DRC + B.Cu GND Pour + BTB Congruence + DFM"
python3 "$ROOT/scripts/verify_pcb_gates.py"

echo ""
echo ">>> [GATE 2/5] JLCPCB Manufacturing Exports + 100% jlcpcb_parts.db & CPL Parity"
python3 "$ROOT/scripts/export_manufacturing.py"

echo ""
echo ">>> [GATE 3/5] ngspice Power, USB-Isolation, PhotoMOS Popless Bypass, Audio & CV"
python3 "$ROOT/hardware/spice/verify_analog.py"

echo ""
echo ">>> [GATE 4/5] RP2040 Dual-Core UF2 Firmware (-Werror, -fstack-usage, nm) & Host Tests"
make -C "$ROOT/firmware" clean all
python3 - "$ROOT/firmware/build/beads_bridge.uf2" <<'PY'
import pathlib, struct, sys
uf2 = pathlib.Path(sys.argv[1]).read_bytes()
assert len(uf2) >= 512 and len(uf2) % 512 == 0
m0, m1, flags, addr, psz, bno, nblk, fam = struct.unpack_from("<IIIIIIII", uf2, 0)
mend, = struct.unpack_from("<I", uf2, 508)
assert m0 == 0x0A324655 and m1 == 0x9E5D5157 and mend == 0x0AB16F30
assert fam == 0xE48BFF56, f"Expected RP2040 UF2 family 0xE48BFF56, got 0x{fam:08X}"
assert addr == 0x10000000 and psz == 256 and nblk == len(uf2) // 512
print(f"[PASS] Gate 4: Verified {sys.argv[1]} ({nblk} blocks, family=0x{fam:08X})")
PY

echo ""
echo ">>> [GATE 5/5] Build123d + OCP BRepAlgoAPI_Common 0.000 mm³ Enclosure Audit & Docs"
python3 "$ROOT/cad/verify_3d_collisions.py"
for doc in "$ROOT/README.md" "$ROOT/manufacturing/HAND_SOLDER_AND_BOM.md" "$ROOT/hardware_contract.json"; do
    test -s "$doc" || { echo "[FAIL] Missing or empty mandatory deliverable: $doc"; exit 1; }
done
# Hygiene check: zero stray tmp.kicad_* files or leaked hardcoded worktree paths in deliverables
if find "$ROOT/hardware" "$ROOT/manufacturing" "$ROOT/cad" -name 'tmp.kicad_*' | grep -q .; then
    echo "[FAIL] Stray tmp.kicad_* file found!"; exit 1
fi
if grep -rn --exclude-dir=__pycache__ --exclude='*.pyc' --exclude='*.png' --exclude='*.stl' --exclude='*.step' --exclude='run_all_checks.sh' '/home/yerbaadmin/beads/\.lane' "$ROOT/README.md" "$ROOT/manufacturing/HAND_SOLDER_AND_BOM.md" "$ROOT/hardware_contract.json" "$ROOT/scripts/" "$ROOT/cad/"; then
    echo "[FAIL] Ephemeral worktree path leaked into deliverable!"; exit 1
fi
echo "[PASS] Gate 5.5: Mandatory docs (README.md, HAND_SOLDER_AND_BOM.md) & worktree hygiene verified"

echo ""
echo "================================================================================"
echo "  ALL 5/5 HARD VERIFICATION GATES PASSED (100% CLEAN, EXIT 0)!"
echo "================================================================================"
