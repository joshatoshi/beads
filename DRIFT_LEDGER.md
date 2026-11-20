# Falsified & Closed Drift Ledger (`beads` — Beads Pedalboard Skiff & Drift Workstation)

Record empirically disproven auditor claims and locked architectural invariants here so subsequent rounds never repeat them.

- **Locked Architectural Choices (`PLAN.md` & `./plan/00..05_*.md`):**
  - **2-Layer Stackup on All 3 Boards (`main_board`, `ui_mezzanine`, `faceplate_14hp`):** Intentionally 2-layer `1.6 mm` FR4 (avoiding JLCPCB's `>100×100 mm` 4-layer surcharge) with `>88–90%` unbroken `B.Cu` ground plane on `main_board` and linear `LM317AG` (`+12.0V`) + `79M12(TP)` (`-12.0V`) post-LDOs + `2A` ferrite LC filters; do NOT demand 4-layer stackups.
  - **`ui_mezzanine` & `faceplate_14hp` Are Bare PCBs (`$0` PCBA Fee):** `ui_mezzanine` is a pure user-hand-soldered THT carrier (`12× WQP-PJ398SM`, `SSD1306` w/ reversible `JP_OLED_PWR`, `EC11`, `BACK`, `2×` dual pots, `PEAK` LED, `2×8` BTB sockets) and `faceplate_14hp` is a `70.80 × 128.50 mm` Matte-Black FR4 14HP Eurorack front panel; only `main_board` uses JLCPCB Top-Side SMT PCBA.
  - **Mutable Instruments Beads (`14 HP × 3U × 25 mm`) Is Off-The-Shelf User Hardware:** Modeled as a 3D mechanical/clearance envelope + `2×5` IDC ribbon load in `cad/` and `spice/`, never redesigned on PCB.

### Round 1 Falsified Auditor Claims (Bicameral `Carbon` + `Neon#xhigh` Council, `2026-11-20T09:07:36Z`)
- Hydrogen 2.2 claim that 0-degree internal ceiling overhangs in beads_enclosure_shell.stl violate printability: plan/04 §1 explicitly targets Bambu Lab X2D dual-nozzle breakaway/soluble support material for single-piece unibody flat printing rather than support_free_fdm.
- Neon 3.1 / Argon 2.2 / Hydrogen 3.2 perfectionist demands to rip up 0-DRC copper solely to move decoupling capacitors closer or eliminate minor 2-layer digital-analog crossings.
- Automated heuristic advisories on U_VREF_BUF.6 -> +2V495_REF (reference op-amp output net) and Q_USB gate voltage (5V rail well inside AO3401A +-12V V_GS,max).
- Hydrogen: Mono 4.0 Vpk guitar signal failing to trip the 2600/4095 PEAK LED threshold (disproven: J_IN_R.TN hardware-normals mono IN L to both SEND_L and SEND_R yielding 2.52 V > 2.095 V, and even single-channel Eurorack clip at 7.0 Vpk / 14 Vpp reaches 2.21 V > 2.095 V).
- Hydrogen: Fragile 0.65 mm North-wall web between DC_JACK and J_USB (disproven: accounting for their 8.80 mm Z separation, true radial wall web between the J_USB exterior overmold pocket and DC_JACK D-bore is 3.010 mm, and 4.54 mm to the inner USB oval).
- Hydrogen: Downward ceiling overhang faces in beads_enclosure_shell.stl violating support-free FDM printability (disproven: plan/04 explicitly targets Bambu Lab X2D dual-nozzle printing with dedicated breakaway/soluble support interface material, and hardware_contract.json does not require support_free_fdm).
- Hydrogen: VBUS_DET reaching 3.375 V at 5.25 V USB (non-blocking: implements plan/01 10k/18k divider verbatim, stays within RP2040 IOVDD+0.5V abs-max, and is current-limited by 10 kOhm to <20 uA).
- Hydrogen: scripts/layout_boards.py desynchronized from main_board.kicad_pcb (disproven: all 238/238 footprint placements match main_board.kicad_pcb with 0.00 mm delta).
- Carbon: SW_MIDI_AB recessed actuator as a blocking reach defect (non-blocking: plan/04 intentionally specifies a recessed MIDI A/B window to prevent accidental pedalboard bumps).
- Argon: 0 Critical / 0 High remaining findings (disproven across analog/power, RP2040 firmware, 3D mechanical/BOM, and 2-layer PCB SI/PI).
