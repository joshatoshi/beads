# Project Operating Rules & Architectural Invariants (`/home/yerbaadmin/beads`)

Read **`PLAN.md`** and **ALL SIX** authoritative specification documents in **`./plan/`** (`00_MASTER_INDEX_AND_ARCHITECTURE.md` through `05_FIRMWARE_DSP_UI_AND_VERIFICATION_GATES.md`) in full before creating or modifying any schematic, PCB, SPICE model, `RP2040` firmware, `Build123d` 3D enclosure, or documentation file. Treat every part number, pinout, voltage, dimension, and state machine in `./plan/` as non-negotiable specification.

## 1. Master Verification Suite (`scripts/run_all_checks.sh`)
```bash
bash scripts/run_all_checks.sh
```
`scripts/run_all_checks.sh` MUST exit `0` across all 5 hard gates before project sign-off:
1. **3-Board KiCad 9 ERC & DRC (`main_board`, `ui_mezzanine`, `faceplate_14hp`):** `ERC = 0/0`, `DRC = 0` errors, `unconnected = 0`, `>88%` continuous unbroken `B.Cu` ground pour on `main_board`, `< 0.05 mm` XY mating congruence across `J_BTB_AUDIO_CV` & `J_BTB_UI_DIG`, `F.CrtYd >= F.Fab`, and complete `.kicad_pro` + `.kicad_sch` (+ schematic PDFs) + `.kicad_pcb` for all 3 boards.
2. **100% `jlcpcb_parts.db` & CPL Parity (`scripts/export_manufacturing.py`):** Verified live stock, package/pin-count parity, `>= 35–50V` capacitor derating on `±12V`/`±13.8V`/`9–18V` rails, verified EasyEDA Pin-1 quadrant rotations & `TO-252` DPAK (`-1.20 mm`) centroids, and zero THT parts in `*_cpl.csv`.
3. **`ngspice` Analog, Power, USB-Isolation & Popless Bypass Verification (`hardware/spice/verify_analog.py`):** Verified `9–18V` `AO3401A` gate clamp (`<= 9.1V`) & reverse-polarity block, `< 1 µA` bidirectional `USB-C VBUS` ↔ `+5V_BUCK` isolation, `> 45 dB` `TLP172AM` PhotoMOS popless mute attenuation (`< 2 mV` bounce spike), `0.00 dB` `12-o'clock` stereo guitar unity & `0°` phase, `-8V..+8V` CV span, and `<= +3.30V` `MCP6002` ADC clamp.
4. **Headerless USB-C UF2 `RP2040` Dual-Core Firmware & Host Unit Tests (`firmware/`):** `arm-none-eabi-gcc -Wall -Wextra -Werror -fstack-usage` producing `beads_bridge.uf2` (`0xE48BFF56` family ID), zero 64-bit/float ISR helpers in Core 0 `2 kHz` tick, and 100% host `assert()` unit tests (`15 ms` PhotoMOS clickless bypass + EQD Flexi-Switch auto-momentary + `250 ms` POR/brownout blanking, `C¹` Cubic Bezier continuity, LFO symmetry, `1V/Oct` LUT, MIDI parser + Running-Status reset, and A/B `CRC32` + `write_seq` QSPI Flash persistence).
5. **`Build123d` Bambu X2D `PETG-HF` 3D Enclosure & `OCP BRepAlgoAPI_Common` Gate (`cad/verify_3d_collisions.py`):** Print-ready enclosure + bottom lid STLs/STEPs + full populated assembly STEP + multi-angle studio PNG renders with **`0.000 mm³` pairwise intersection** across all un-grouped solids (`enclosure_shell`, `bottom_lid`, `main_board`, `ui_mezzanine`, `faceplate_14hp`, `beads_module + 2×5 ribbon`, `4× NMJ4HCD2`, `2× SJ1-3523N`, `JS202011AQN`, `TYPE-C-31-M-12`, panel DC jack + nut, `2×` footswitches + nuts, `12× WQP-PJ398SM`, `SSD1306`, `EC11`, `2×` dual pots, and all `M3` heat-set inserts/bolts) + `>= 8.0 mm` shaft protrusion.

## 2. KiCad 9, Portability & Verified Pinout Ground Truth
- Author/modify `.kicad_sch`, `.kicad_pcb`, `.kicad_pro`, `fp-lib-table`, and `sym-lib-table` via Konnect MCP / `pcbnew` / deterministic generator scripts—keep `${KIPRJMOD}` relative library/3D paths (`hardware/beads_custom.pretty/`, `hardware/beads_custom.3dshapes/`), relative `Path(__file__).resolve()` script paths, and `/tmp/opencode/` for scratch files.
- Include valid `.kicad_pro`, `.kicad_sch` (even `faceplate_14hp` must have a clean schematic sheet with title block & `MH1..MH4` mounting symbols so KiCad 9 opens all 3 projects cleanly!), and `.kicad_pcb` for all 3 boards.
- **Verified EasyEDA / Datasheet Pinouts (Do NOT Swap):**
  - `CJ431` (`C3113`, `SOT-23`): **`Pin 1 = REF, Pin 2 = K (Cathode), Pin 3 = A (Anode = AGND)`** (`Pins 1+2` tied to `+2.495V_REF`).
  - `79M12(TP)` (`C53477637`, `Package_TO_SOT_SMD:TO-252-2`): **`Pin 1 = GND, Pin 2 (Tab) = -13.7V_RAW INPUT, Pin 3 = -12.0V_EUR OUTPUT`** (include `10 µF + 0.47 Ω + 1 µF` local ESR-damped VOUT network!).
  - `LM317AG-TN3-R` (`C75510`, `Package_TO_SOT_SMD:TO-252-2`): **`Pin 1 = ADJ, Pin 2 (Tab) = +12.0V_EUR OUTPUT, Pin 3 = +13.9V_RAW INPUT`**.
  - `Omron G6K-2F-Y-TR DC5` (`C47190`, `Relay:G6K-2` + `Relay_SMD:Relay_DPDT_Omron_G6K-2F-Y`): **polarized coil `Pin 1 = +Coil (+5V_BUCK + 1N4148W Cathode)`, `Pin 8 = -Coil (NMOS Drain + 1N4148W Anode)`**; `2=NC1, 3=COM1, 4=NO1, 7=NC2, 6=COM2, 5=NO2`.
  - `Toshiba TLP172AM(TPL,E` (`C2152276`, `SOP-4-2.54mm` with `"F.Paste"` enabled): `1 = LED Anode`, `2 = LED Cathode` (`270 Ω` from `+3V3_DIG`), `3 = GTR_OUT_x`, `4 = AGND`.
  - `BAV99,215` (`C2500`, `SOT-23`): physical pins **`1 = GND, 2 = +3V3_DIG, 3 = Signal`**.
  - `TS-1088-AR02016` (`C720477`, `4.0×3.0 mm` `SW_BOOT`): custom `4.0×3.0 mm` footprint (`±2.15 mm` pad centers).
