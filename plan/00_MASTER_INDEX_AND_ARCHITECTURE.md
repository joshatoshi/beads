# Beads Pedalboard Skiff, Audio/MIDI-to-CV Bridge & Drift Workstation — Master Plan (`00_MASTER_INDEX_AND_ARCHITECTURE.md`)

## 1. Executive Summary & Project Goal
Design and deliver a complete, fabrication-ready hardware + firmware + 3D-printed enclosure project in `/home/yerbaadmin/beads` that houses an unmodified **Mutable Instruments Beads** (`14 HP × 3U`) Eurorack granular texture synthesizer inside a **low-profile guitar pedalboard stompbox/skiff enclosure** (`PETG-HF`, optimized for **Bambu Lab X2D** dual-nozzle printing).

The unit sits directly in a standard **guitar pedalboard signal chain** powered by a standard **9V–18V DC center-negative guitar pedal power supply** (`~300 mA @ 9V DC`) and provides:
1. **Clean, Protected `9V–18V DC` → Eurorack `+12V / -12V` Power Conversion** (plus `+5V` and `+3.3V` local rails), feeding Mutable Instruments Beads via a standard **10-pin (`2×5`) Eurorack IDC ribbon cable** with explicit **`RED STRIPE / -12V`** markings on the PCB, plus **zero-backfeed isolation** when **USB-C** is plugged in simultaneously.
2. **Full Stereo `1/4"` Guitar ↔ Eurorack Audio Interface + Boutique Popless/Clickless Relay True Bypass:**
   - `4×` top-mounted **Neutrik `NMJ4HCD2`** `1/4"` jacks (`IN L/Mono`, `IN R` with passive hardware `L→R` normalling when mono, `OUT L/Mono`, `OUT R`),
   - Stereo `1 MΩ` JFET guitar preamps boosting instrument levels up to Eurorack (`+18.1 dB` at `12 o'clock` on dual-gang `IN TRIM`), outputting on **`SEND L` & `SEND R` `3.5 mm` Thonkiconn jacks** to patch into Beads `IN L / IN R`,
   - **`RET L` & `RET R` `3.5 mm` Thonkiconn jacks** patched from Beads `OUT L / OUT R`, attenuated back down to unity guitar level (`-18.1 dB` at `12 o'clock` on dual-gang `OUT TRIM` = exact `0.0 dB` end-to-end unity & `0°` phase),
   - **Boutique Popless / Clickless Stereo True Bypass:** Pairs `2× Omron G6K-2F-Y-TR DC5` gold-contact DPDT relays (fail-safe passive bypass when unpowered) with **`2× Toshiba TLP172AM` PhotoMOS Opto-FET optical shunt mutes**, `2.2 MΩ` zero-DC bleed networks on all switched nodes, slew-damped coil drive, a timed `15 ms` firmware mute-switch-unmute sequencer, AND `250 ms` power-on/brownout thump blanking—driven by soft-touch momentary **Footswitch 1 (`FS1: BYPASS`)** on the stepped front stomp apron (and controllable via MIDI CC / presets),
   - Built-in **Guitar Peak Envelope Follower & Transient Pluck Detector** assignable to any CV/Gate output.
3. **3.5 mm TRS MIDI In (Hardware `TYPE A / TYPE B` Switch) + Zero-Latency Hardware `MIDI THRU` + `USB-C` MIDI:**
   - Top-mounted `3.5 mm` TRS `MIDI IN` feeding a right-angle **C&K `JS202011AQN` DPDT** slide switch (labeled **`MIDI TYPE A` ↔ `MIDI TYPE B`** on both PCB silkscreen and top wall) into a hand-soldered **`H11L1` (`DIP-6`)** high-speed Schmitt optocoupler,
   - Pure hardware **`MIDI THRU`** (`3.5 mm` TRS Type A) buffered immediately off `H11L1` via cascaded `74HC14D` Schmitt inverters with zero MCU latency,
   - Parallel inverter feeding `RP2040` UART RX, merged seamlessly with **USB-C MIDI** (and **headerless USB-C UF2 firmware flashing**—no SWD pins needed).
4. **8× Universal Bipolar CV / Calibrated `1V/Oct` / Gate Thonkiconn Outputs + OLED "Drift" Workstation:**
   - `8×` hand-soldered `3.5 mm` **Thonkiconn (`WQP-PJ398SM`)** jacks (`CV 1`–`CV 8`), all driven by `12-bit` SPI DACs (`4× MCP4822-E/SN` with internal `2.048V` `50 ppm/°C` reference) + bipolar `±12V` `TL072CDT` op-amps outputting **`-8.0V` to `+8.0V`** (with software multi-point `1V/Oct` calibration across all 8 channels),
   - **`0.96"` `SSD1306` (`128×64` I2C) OLED** + clickable rotary encoder + `BACK` button + **Footswitch 2 (`FS2: FREEZE / SEED TAP`)**,
   - Per-channel **MIDI-to-CV** (Note `1V/Oct`, Gate, Trigger, Velocity, Aftertouch, Pitch Bend, smoothed `CC #0–127`, MIDI Clock Divider), **Presets (`PC #0–31`)**, AND standalone **Autonomous Modulation ("Drift")** without external MIDI: smooth `C¹` **Cubic Bezier Random Drift**, free/synced **LFOs** (Sine, Tri, Ramp for `TIME` scrubbing, Square, Slew S&H), **Euclidean/Probabilistic Triggers**, and **Guitar Envelope/Pluck CV**.

---

## 2. Specification Document Index
Every detail agreed with the user is captured across these 6 documents:
- **`00_MASTER_INDEX_AND_ARCHITECTURE.md`** *(this file)* — System architecture, physical ergonomics, target Mutable Instruments Beads specs, PCBA vs. hand-solder split, target repo layout, and execution roadmap.
- **`01_POWER_PROTECTION_AND_USB_ISOLATION.md`** — `9V–18V` center-negative input protection, `TPS5430` + `TPS65131` + linear `±12.0V` post-LDO power supply, `2×5` red-stripe Eurorack power header, and zero-backfeed `USB-C VBUS` isolation.
- **`02_AUDIO_CHAIN_CV_DACS_AND_MIDI_SCHEMATIC.md`** — Pin-accurate schematic specifications for `Neutrik NMJ4HCD2` stereo I/O + `L→R` normalling, Popless/Clickless `TLP172AM` PhotoMOS + `Omron G6K-2F-Y` stereo true-bypass circuit, `TL072`/`NE5532` gain staging, guitar peak detector, `8×` `±8V` `MCP4822` CV outputs, `C&K JS202011AQN` Type A/B switch, `H11L1` `DIP-6` optocoupler, and `74HC14` hardware `MIDI THRU`.
- **`03_PCB_STACKUP_BOM_AND_2LAYER_LAYOUT.md`** — Verified JLCPCB Basic/Preferred/Extended BOM (`LCSC C#` + DigiKey/Thonk hand-solder BOM), 2-layer noise-immune PCB partitioning (`Main Floor PCB` + `14 HP Mezzanine PCB` + `14 HP Matte-Black FR4 Faceplate`), footprints, and DFM/CPL rules.
- **`04_ENCLOSURE_3D_CAD_AND_MECHANICAL_SPEC.md`** — Exact millimeter dimensions for the **Bambu Lab X2D `PETG-HF`** low-profile stepped enclosure, `8×` M3 brass heat-set inserts mapped to Doepfer `14 HP` (`70.8 × 128.5 mm`) rails for knurled M3 bolts, North-wall connector bores, front stepped stomp apron, and `Build123d` / `OCP` B-Rep collision checks.
- **`05_FIRMWARE_DSP_UI_AND_VERIFICATION_GATES.md`** — `RP2040` dual-core C/C++ architecture, PhotoMOS clickless bypass & POR mute FSM, Cubic Bezier/LFO/MIDI/Envelope algorithms, `SSD1306` UI menus, headerless USB-C UF2 boot/update support, Flash CRC32 presets, and automated CI verification suite (`scripts/run_all_checks.sh`).

---

## 3. Target Module Reference: Mutable Instruments Beads Specifications
*(Do NOT design or modify Beads itself—Beads is an off-the-shelf Eurorack module installed by the user into the Right `14 HP` bay.)*

| Parameter | Official Mutable Instruments Beads Value | Impact on Our Design |
|---|---|---|
| **Panel Width** | `14 HP` = `70.80 mm` nominal (`14 × 5.08 = 71.12 mm` grid, `0.32 mm` clearance) | Right bay cutout width = `70.8 mm` nominal (`+0.4 mm` clearance); Left custom FR4 faceplate = `14 HP` (`70.80 mm`). |
| **Panel Height** | `3U` = `128.50 mm` (`2.0 mm` anodized aluminum thickness) | 3U bay height = `129.0 mm` pocket with top/bottom `9.75 mm` Eurorack mounting lips. |
| **M3 Mounting Holes** | Vertical `Y` center-to-center = **`122.50 mm`** (`3.00 mm` from top & bottom edges). Horizontal `X` = `7.50 mm` from left panel edge and `7.50 + 11 × 5.08 = 63.38 mm` (`55.88 mm` span, slotted on Beads). | `4×` M3 brass heat-set inserts placed at exact `(7.50, 3.00)`, `(63.38, 3.00)`, `(7.50, 125.50)`, `(63.38, 125.50)` in Beads' local panel frame for **M3 Knurled Eurorack Bolts**. |
| **Depth Behind Panel** | `25.0 mm` module depth (`+ ~11 mm` for `2×5` IDC ribbon connector & strain relief = `36.0 mm` min; rear PCB inset `~10 mm` inside top/bottom Eurorack rails) | Internal cavity depth under Beads `>= 38.5 mm` (`45.0 mm` outer case height). Adding a `14.0 mm` North bezel above the 3U rail gives `>20.9 mm` North-wall depth completely clear of Beads' rear PCB for `NMJ4HCD2` jacks! |
| **Power Draw** | **`+12V @ 100 mA`**, **`-12V @ 10 mA`**, **`+5V @ 0 mA`** (`2×5` 10-pin Eurorack header, `-12V` = Red Stripe) | Design `+12.0V` rail for `>= 300 mA` continuous (handles `STM32H743` startup inrush + op-amps) and `-12.0V` rail for `>= 150 mA` continuous. |
| **Audio I/O** | Front-panel `3.5 mm` `IN L` (mono), `IN R`, `OUT L` (mono sum when `OUT R` unpatched), `OUT R` (`100 kΩ` in, `~8–16 Vpp` Eurorack level; **no rear audio header**) | Custom Left panel provides `SEND L`, `SEND R`, `RET L`, `RET R` `3.5 mm` Thonkiconn jacks bridged to Beads with short `10–15 cm` patch cables. High-Z `1 MΩ` preamp lets user lock Beads input gain to manual `0 dB` (eliminating Beads' `+32 dB` auto-gain silence hiss). |
| **Control Inputs (8 total)** | **Gates/Clocks (2):** `FREEZE`, `SEED` (`48 kHz` audio-rate sampled). **CVs (6):** `TIME`, `PITCH` (`1V/Oct`), `SIZE`, `SHAPE` (`±8V` range); `DENSITY` (`1V/Oct`), `ASSIGN` (`Feedback/Dry-Wet/Reverb`) (`±5V` range). | `8×` universal `-8V..+8V` DAC Thonkiconn outputs (`CV 1..CV 8`) allow every single control input on Beads to be patched simultaneously with true bipolar excursion around knob positions. |

---

## 4. Physical Layout & Ergonomic Partitioning

```text
          NORTH (TOP) WALL — ALL PEDALBOARD CABLES EXIT NORTH EDGE
   [OUT R] [OUT L/M]  [IN R] [IN L/M]  [MIDI THRU] [A|B] [MIDI IN] [USB-C] [9-18V DC]
  ┌───────────────────────────────────┬───────────────────────────────────────┐
  │ (o) M3 Knurlie                (o) │ (o) M3 Knurlie                    (o) │
  │  ┌──────────────────┐             │                                       │
  │  │  0.96" SSD1306   │   (ENC+SW)  │     [IN L] [IN R]       (FREEZE)      │
  │  │  CV1: Bezier ±5V │   [BACK]    │                                       │
  │  └──────────────────┘             │       Mutable Instruments             │
  │  (IN TRIM)  (OUT TRIM)  [PK LED]  │              B E A D S                │
  │                                   │        (14 HP × 3U = 70.8×128.5mm)    │
  │  AUDIO BRIDGE    8× CV / GATE OUT │                                       │
  │  (o) SEND L     (o) CV 1  (o) CV 2│      (Unmodified user module bolted   │
  │  (o) SEND R     (o) CV 3  (o) CV 4│       into 4× M3 brass heat-set       │
  │  (o) RET L      (o) CV 5  (o) CV 6│       inserts; powered underneath     │
  │  (o) RET R      (o) CV 7  (o) CV 8│       from RED-STRIPE 2×5 IDC header) │
  │ (o)                           (o) │ (o)                               (o) │
  ├───────────────────────────────────┴───────────────────────────────────────┤
  │   STEPPED-DOWN FRONT STOMP APRON (~12 mm lower so shoes clear patch cables)│
  │       ( * ) BYP LED                                   ( * ) FRZ/CLK LED   │
  │      [ FS1: BYPASS ]          <── 92.0 mm ──>       [ FS2: FREEZE / TAP ] │
  └───────────────────────────────────────────────────────────────────────────┘
       LEFT BAY: 14 HP Matte-Black FR4 Panel       RIGHT BAY: 14 HP Beads Cutout
                 Overall Enclosure: 152.0 mm (W) × 185.6 mm (D) × 45.0 mm (H)
```

---

## 5. Manufacturing & Assembly Split (JLCPCB PCBA vs. User Hand-Soldering)

- **PCB Layer Stackup:** **2-Layer Cost-Optimized** (`1.6 mm` FR4, `1 oz` copper) for all PCBs to avoid JLCPCB's >`100×100 mm` 4-layer surcharge, using strict spatial zoning, linear `±12.0V` post-regulators, and `>90%` unbroken `B.Cu` ground pours.
- **JLCPCB SMT Assembly (Top-Side Single-Sided PCBA):**
  - Maximize **JLCPCB Basic & Preferred (`$0` setup fee)** parts (`TL072CDT`, `NE5532DR`, `OP07CDR`, `CJ431`, `MCP6002T-I/SN`, `74HC14D`, `TPS5430DDAR`, `LM317AG-TN3-R`, `AMS1117-3.3`, `W25Q128JVSIQ`, `12 MHz` crystal, `AO3401A`, `AO3400A`/`2N7002`, `SMBJ20CA`, `SRV05-4`, `BAV99`, `1N4148W`, `1N5819WS`, `SS34`, `BLM18PG121SN1D`, SMD LEDs, tactile `BOOTSEL` switch, all `0603`/`0805`/`1206` resistors & MLCCs).
  - Consolidate **Extended (`$3` setup fee)** parts to the strict minimum (`RP2040` `C2040`, `MCP4822-E/SN` `C16040` ×4, `Omron G6K-2F-Y-TR DC5` `C47190` ×2, `Toshiba TLP172AM(TPL,E` `C2152276` ×2 PhotoMOS clickless mute switches, `TYPE-C-31-M-12` `C165948`, `SMD1812B110TF/33` `C269134` + `JK-nSMD050-30` `C720075` PTCs, `TPS65131RGER` `C87663`, `FXL0530-100-M` `C177248` ×3 inductors, `79M12(TP)` `C53477637`, and `BZX84-C9V1` `C96231`).
- **User Hand-Soldered Through-Hole / Panel Parts (Excluded from JLCPCB CPL, included in Schematic & Master BOM):**
  1. `4×` **Neutrik `NMJ4HCD2`** `1/4"` switched horizontal jacks (user already owns in large stock — soldered directly to North edge of `main_board` + bolted through North case wall via chrome ferrule nuts; **no flying audio wires**).
  2. `1×` **C&K `JS202011AQN`** right-angle DPDT slide switch (DigiKey UK — soldered to North edge of `main_board` beside `MIDI IN`).
  3. `2×` **Same Sky / CUI `SJ1-3523N`** horizontal `3.5 mm` TRS jacks (`MIDI IN` & `MIDI THRU`, North edge of `main_board`).
  4. `1×` **`H11L1` / `H11L1M` in `DIP-6` (`7.62 mm`)** socket/optocoupler.
  5. `12×` **Thonkiconn (`QingPu WQP-PJ398SM`)** vertical `3.5 mm` mono Eurorack jacks (`SEND L/R`, `RET L/R`, `CV 1..CV 8` on `ui_mezzanine`).
  6. `1×` **`0.96"` `SSD1306` I2C OLED module** (`128×64`, 4-pin `2.54 mm` header with reversible `VCC/GND` jumper).
  7. `1×` **EC11 vertical rotary encoder with push-switch** + `1×` tactile/panel **`BACK` button** + `2×` **Dual-Gang `9 mm` vertical linear `10 kΩ` pots** (`IN TRIM`, `OUT TRIM`).
  8. `1×` **Shrouded `2×5` (`2.54 mm`) Eurorack IDC box header** (marked `RED STRIPE / -12V`).
  9. `2×` **Soft-touch momentary SPST panel footswitches** (`FS1`, `FS2` on the stepped front apron) + `2×` apron status LEDs + `1×` **Insulated plastic-body `2.1 × 5.5 mm` panel-mount DC barrel jack** (`Center = 0V GND`, `Sleeve = +9..18V`) connected via 2-pin `2.54 mm` headers/solder pads, plus board-to-board `2.54 mm` male/female headers between `main_board` and `ui_mezzanine`.

---

## 6. Target Repository Directory Layout (`/home/yerbaadmin/beads`)
```text
/home/yerbaadmin/beads/
├── PLAN.md                           # Master entry-point index pointing to ./plan/00..05
├── README.md                         # Project overview, specs, assembly & flashing guide
├── plan/                             # Authoritative 00..05 specification files
├── hardware/
│   ├── main_board/                   # KiCad 9 2-layer Main Floor PCB (Power, Audio, Relays+PhotoMOS, MIDI, RP2040, DACs)
│   ├── ui_mezzanine/                 # KiCad 9 2-layer 14HP Patch/OLED/Controls Mezzanine PCB
│   ├── faceplate_14hp/               # KiCad 9 14HP (70.8×128.5mm) Matte-Black FR4 Front Panel
│   ├── beads_custom.pretty/          # Project-local verified footprints (${KIPRJMOD} portable paths)
│   ├── beads_custom.3dshapes/        # Project-local STEP models for populated 3D verification
│   └── spice/                        # ngspice netlists & verification scripts (power, popless mute, preamp, CV, MIDI)
├── manufacturing/
│   ├── main_board/                   # Gerbers, Drill, JLCPCB BOM & verified CPL CSV
│   ├── ui_mezzanine/                 # Gerbers, Drill, THT placement map
│   ├── faceplate_14hp/               # Gerbers & Drill for matte-black 14HP panel
│   └── HAND_SOLDER_AND_BOM.md        # Complete user shopping list (DigiKey/Thonk) & step-by-step assembly guide
├── firmware/
│   ├── CMakeLists.txt                # Pico SDK RP2040 UF2 build + host unit-test targets
│   ├── include/                      # Headers (cv_engine, bezier_drift, bypass_sequencer, midi_router, oled_ui, presets)
│   ├── src/                          # RP2040 dual-core firmware + USB-MIDI descriptors
│   └── tests/                        # Deterministic host C/C++ assert() unit tests + silicon mocks
├── cad/
│   ├── build_enclosure.py            # Parametric Build123d generator for Bambu X2D PETG-HF case + lid + full assembly
│   ├── verify_3d_collisions.py       # OCP BRepAlgoAPI_Common zero-intersection & wall-bore datum audit
│   └── exports/                      # Print-ready STLs, STEP enclosure, lid, and full populated assembly STEP
└── scripts/
    ├── export_manufacturing.py       # Worktree-portable Gerber/BOM/CPL exporter + jlcpcb_parts.db verifier
    └── run_all_checks.sh             # Master end-to-end CI gate (ERC, DRC, BOM/DB, SPICE, Firmware ELF/Tests, 3D B-Rep)
```

---

## 7. Recommended Single-Domain Atomic Build Phases
1. **Phase 1 — Hardware Schematics, Custom Footprints & SPICE Verification:** Author KiCad 9 schematics (`main_board`, `ui_mezzanine`, `faceplate_14hp`), verify every LCSC part against `/home/yerbaadmin/.local/share/kicad-mcp/jlcpcb_parts.db`, pass `ERC = 0`, and validate power/isolation/popless-bypass/preamp/CV/envelope stages in `ngspice`.
2. **Phase 2 — 2-Layer PCB Layouts & Manufacturing Exports:** Place & route all three 2-layer boards (`unconnected = 0`, `DRC = 0`, `>90%` `B.Cu` ground pour on `main_board`), verify JLCPCB CPL Pin-1 rotations & centroids, and generate Gerbers/BOM/CPL.
3. **Phase 3 — `RP2040` Firmware, Popless Bypass Sequencer, Bezier/MIDI/OLED Engine & Unit Tests:** Implement the dual-core UF2 firmware, PhotoMOS clickless relay & POR mute FSM, USB-MIDI + UART MIDI merger, 8-ch Cubic Bezier/LFO/1V-Oct/Envelope engine, `SSD1306` oscilloscope UI, Flash CRC32 presets, `arm-none-eabi-gcc` cross-compilation (`-Wall -Wextra -Werror -fstack-usage`), and host `assert()` test suite.
4. **Phase 4 — Parametric `Build123d` `PETG-HF` Enclosure, 3D B-Rep Audit & Final Assembly Docs:** Build the exact stepped enclosure + bottom lid + populated assembly STEP, verify `0.000 mm³` B-Rep collisions, and write the complete user build/wiring/flashing guide.
