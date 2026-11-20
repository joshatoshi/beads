# Falsified & Closed Drift Ledger (`beads` — Beads Pedalboard Skiff & Drift Workstation)

Record empirically disproven auditor claims and locked architectural invariants here so subsequent rounds never repeat them.

- **Locked Architectural Choices (`PLAN.md` & `./plan/00..05_*.md`):**
  - **2-Layer Stackup on All 3 Boards (`main_board`, `ui_mezzanine`, `faceplate_14hp`):** Intentionally 2-layer `1.6 mm` FR4 (avoiding JLCPCB's `>100×100 mm` 4-layer surcharge) with `>88–90%` unbroken `B.Cu` ground plane on `main_board` and linear `LM317AG` (`+12.0V`) + `79M12(TP)` (`-12.0V`) post-LDOs + `2A` ferrite LC filters; do NOT demand 4-layer stackups.
  - **`ui_mezzanine` & `faceplate_14hp` Are Bare PCBs (`$0` PCBA Fee):** `ui_mezzanine` is a pure user-hand-soldered THT carrier (`12× WQP-PJ398SM`, `SSD1306` w/ reversible `JP_OLED_PWR`, `EC11`, `BACK`, `2×` dual pots, `PEAK` LED, `2×8` BTB sockets) and `faceplate_14hp` is a `70.80 × 128.50 mm` Matte-Black FR4 14HP Eurorack front panel; only `main_board` uses JLCPCB Top-Side SMT PCBA.
  - **Mutable Instruments Beads (`14 HP × 3U × 25 mm`) Is Off-The-Shelf User Hardware:** Modeled as a 3D mechanical/clearance envelope + `2×5` IDC ribbon load in `cad/` and `spice/`, never redesigned on PCB.
