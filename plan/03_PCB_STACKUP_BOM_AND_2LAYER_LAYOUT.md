# 2-Layer PCB Stackup, Verified Master BOM & Layout Rules (`03_PCB_STACKUP_BOM_AND_2LAYER_LAYOUT.md`)

## 1. Multi-Board Mechanical & Electrical Partitioning (3 Cheap 2-Layer JLCPCB Boards)

Because the enclosure has **two distinct Z-planes** (the North-Wall + Floor Mainboard plane at `Z = -38.4 mm`, and the Eurorack `3U` Patch-Bay plane at `Z = 0.0 mm` with `11.0 mm` Thonkiconn stack height), the hardware splits cleanly into 3 inexpensive 2-layer `1.6 mm` FR4 boards with **zero flying audio wires**:

1. **`main_board` (2-Layer `1.6 mm` FR4, JLCPCB Top-Side SMT PCBA + User North-Edge THT):**
   - Sits flat across the floor of the enclosure on `M3` brass heat-set standoffs.
   - **North Edge:** Directly mounts all North-wall connectors with zero hookup wire:
     - `4×` **Neutrik `NMJ4HCD2`** (`OUT R`, `OUT L/M`, `IN R`, `IN L/M`) — bolted through the North wall via outer chrome ferrule nuts!
     - `2×` **Same Sky / CUI `SJ1-3523N`** (`MIDI THRU`, `MIDI IN`)
     - `1×` **C&K `JS202011AQN`** right-angle DPDT (`MIDI TYPE A / B`) slide switch
     - `1×` **`TYPE-C-31-M-12`** SMD USB-C connector
     - `1×` `2-pin 2.54 mm` header/pad pair `J_PWR_IN` right beside the insulated panel-mount `9–18V` center-negative DC barrel jack.
   - **Center-Right Edge (Adjacent to Open `14 HP` Beads Bay):**
     - `1×` Shrouded **`2×5` (`2.54 mm`) Eurorack IDC Power Header (`J_EURO_PWR`)** with loud **`RED STRIPE / -12V`** silkscreen markings.
     - `1×` Hand-soldered **`DIP-6` `H11L1`** optocoupler socket + SMD **`BOOTSEL`** tactile button (`TS-1088`, Basic `$0` fee).
   - **South Edge (Under Stepped Stomp Apron):**
     - `2×` `2-pin 2.54 mm` headers/pads (`J_FS1`, `J_FS2`) + `2×` LED headers (`J_LED_FS1`, `J_LED_FS2`) right under the two soft-touch momentary panel footswitches (`FS1: BYPASS`, `FS2: FREEZE / TAP`).
   - **Left Bay Area:**
     - Carries all JLCPCB-assembled SMD circuitry (`TPS5430` + `TPS65131` + `LM317AG`/`79M12` power, `RP2040` + `W25Q128` + `12 MHz` Xtal, `4× MCP4822` + `4× TL072` + `CJ431`/`OP07` CV drivers, `2× Omron G6K-2F-Y` bypass relays + `2× Toshiba TLP172AM` PhotoMOS popless mute switches, `TL072`/`NE5532` guitar preamp/return stages, `MCP6002` guitar peak detector) and mates upward to `ui_mezzanine` via **two shrouded/keyed `2×8` (`2.54 mm`) board-to-board header/socket pairs (`J_BTB_AUDIO_CV`, `J_BTB_UI_DIG`)** separating analog audio/CV signals from digital I2C/encoder/LED lines!

2. **`ui_mezzanine` (`68.0 × 108.0 mm` 2-Layer `1.6 mm` FR4, Pure THT Carrier — `$2–$4` Bare PCB, `$0` PCBA Fee!):**
   - Sits `11.0 mm` behind `faceplate_14hp` inside Eurorack's `108.5 mm` between-rails clearance.
   - User hand-solders:
     - `12×` **Thonkiconn (`QingPu WQP-PJ398SM`)** vertical `3.5 mm` jacks (`SEND L`, `SEND R`, `RET L`, `RET R`, `CV 1..CV 8`),
     - `1×` **`0.96"` `SSD1306` 4-pin I2C OLED** (`2.54 mm` 4-pin female socket + **reversible `VCC/GND` solder-jumper pads `JP_OLED_PWR`** so BOTH `GND-VCC-SCL-SDA` and `VCC-GND-SCL-SDA` `0.96"` OLED modules work safely!),
     - `1×` **Alps `EC11E` vertical rotary encoder with push switch**,
     - `1×` **Tactile/panel `BACK` push button** (`SW_PUSH_6mm_H13mm`),
     - `2×` **Dual-Gang `9 mm` `10 kΩ` Linear vertical pots** (`RV_IN_TRIM`, `RV_OUT_TRIM`, `12 o'clock` = exact unity guitar staging across both Left & Right channels!),
     - `1×` `3 mm` THT **`PEAK / CLIP` LED**,
     - Bottom-side (`B.Cu`) `2×8` `2.54 mm` headers/ribbon sockets mating down to `main_board` (verified `< 0.05 mm` XY congruence!).

3. **`faceplate_14hp` (`70.80 × 128.50 mm` 2-Layer `1.6 mm` Matte-Black FR4 Eurorack Panel — `$2–$4` Bare PCB at JLCPCB):**
   - **Matte Black soldermask + Crisp White Silkscreen + Exposed Gold/Silver graphic accents** matching Mutable Instruments Beads!
   - Exact `4×` Doepfer M3 holes (`Ø3.2 mm` at `Y = 3.00 & 125.50 mm`, `X = 7.50 & 63.38 mm`), milled OLED viewing window (`26.0 × 15.0 mm`), `12×` `Ø6.3 mm` Thonkiconn holes, `Ø7.2 mm` encoder & dual-pot holes, `BACK` button hole, and `Ø3.2 mm` `PEAK` LED hole.

---

## 2. Verified JLCPCB SMT BOM (`main_board`)

Every LCSC part number below has been **verified directly against `/home/yerbaadmin/.local/share/kicad-mcp/jlcpcb_parts.db`**:

### 2.1 Active ICs, Relays, PhotoMOS, Semiconductors & Inductors
| RefDes Group | Qty | MPN | Package | LCSC # | Tier (`Fee`) | Role |
|---|---:|---|---|---|---|---|
| `U_MCU` | 1 | `RP2040` | `LQFN-56(7x7)` | **`C2040`** | **Extended (`$3`)** | Dual-core 133 MHz MCU + ROM USB UF2 bootloader + USB-MIDI |
| `U_FLASH` | 1 | `W25Q128JVSIQ` | `SOIC-8-208mil` | **`C97521`** | **Basic (`$0`)** | 16 MB QSPI Flash (firmware + A/B CRC32 presets + cal LUT) |
| `Y1` | 1 | `X322512MSB4SI` | `SMD3225-4P` | **`C9002`** | **Basic (`$0`)** | `12.000 MHz` crystal (`Pins 1,3` = Xtal, `Pins 2,4` = GND) |
| `U_DAC0..3` | 4 | `MCP4822-E/SN` | `SOIC-8` | **`C16040`** | **Extended (`$3` once)** | `4×` Dual 12-bit SPI DAC w/ internal `2.048V` ref (`8` CV ch) |
| `U_OP_IN1..2`, `U_OP_RET2`, `U_OP_CV1..4` | 7 | `TL072CDT` | `SO-8` | **`C6961`** | **Basic (`$0`)** | Stereo `1 MΩ` JFET guitar preamps, return followers & `8×` `±8V` CV amps |
| `U_OP_RET1` | 1 | `NE5532DR` | `SOIC-8` | **`C7426`** | **Basic (`$0`)** | Ultra-low-noise stereo Eurorack return stage |
| `U_VREF_BUF` | 1 | `OP07CDR` | `SOIC-8` | **`C7433`** | **Basic (`$0`)** | Precision `75 µV`-offset buffer for `+2.495V` CV offset ref |
| `U_REF` | 1 | `CJ431` | `SOT-23` | **`C3113`** | **Basic (`$0`)** | Precision `2.495V` `0.5%` bandgap shunt reference *(Verify pinout!)* |
| `U_ENV` | 1 | `MCP6002T-I/SN` | `SOIC-8` | **`C7377`** | **Preferred (`$0`)** | `+3.3V` rail-to-rail guitar peak/envelope rectifier (overvoltage-proof ADC!) |
| `U_INV` | 1 | `74HC14D,653` | `SOIC-14` | **`C5605`** | **Basic (`$0`)** | Schmitt hex inverter for pure hardware `MIDI THRU` + UART RX |
| `K1, K2` | 2 | `G6K-2F-Y-TR DC5` | `SMD,10x6.5mm` | **`C47190`** | **Extended (`$3` once)** | Genuine Omron gold-clad DPDT relays for Stereo True Bypass |
| `U_MUTE_L, U_MUTE_R` | 2 | `TLP172AM(TPL,E` | `SOP-4-2.54mm` | **`C2152276`** | **Extended (`$3` once)** | Genuine Toshiba PhotoMOS Opto-FET (`1 Ω` `R_ON`, `3.75 kV` optical isolation) for **popless/clickless** relay switching & POR thump mute! |
| `U_BUCK5` | 1 | `TPS5430DDAR` | `SOIC-8-EP` | **`C9864`** | **Basic (`$0`)** | `9–18V → +5.08V` `3A` `500 kHz` step-down buck converter |
| `U_PMIC` | 1 | `TPS65131RGER` | `QFN-24-EP(4x4)` | **`C87663`** | **Extended (`$3`)** | `+5V → ±13.8V` `1.38 MHz` boost + inverting pre-regulator |
| `U_LDO_P12` | 1 | `LM317AG-TN3-R` | `TO-252(DPAK)` | **`C75510`** | **Preferred (`$0`)** | Linear `+12.00V` low-noise post-regulator (`CADJ` bypassed) |
| `U_LDO_N12` | 1 | `79M12(TP)` | `TO-252-2L` | **`C53477637`** | **Extended (`$3`)** | Linear `-12.00V` low-noise post-regulator *(Verify `1=GND, 2=IN, 3=OUT`!)* |
| `U_LDO_3V3` | 1 | `AMS1117-3.3` | `SOT-223` | **`C6186`** | **Basic (`$0`)** | `+3.30V` digital regulator (`>= 22 µF` directly on `VOUT`) |
| `L1, L2, L3` | 3 | `FXL0530-100-M` | `SMD,5.4x5.2mm` | **`C177248`** | **Extended (`$3` once)** | `3×` `10 µH` `3.2A` (`3.5A` `I_sat`) shielded molded power inductors |
| `FB1..FB4` | 4 | `BLM18PG121SN1D` | `0603` | **`C14709`** | **Basic (`$0`)** | `2A` `50 mΩ` power ferrite beads (`+12V`, `-12V`, `VIN`, `OLED_3V3`) |
| `F1` | 1 | `SMD1812B110TF/33` | `1812` | **`C269134`** | **Extended (`$3`)** | `33V 1.1A` resettable PTC fuse on `9–18V` DC input |
| `F_USB` | 1 | `JK-nSMD050-30` | `1206` | **`C720075`** | **Extended (`$3`)** | `30V 500 mA` resettable PTC fuse on `USB-C VBUS` |
| `D_TVS1` | 1 | `SMBJ20CA` | `DO-214AA(SMB)` | **`C19077576`** | **Preferred (`$0`)** | `20V` `600W` bidirectional TVS surge clamp on `9–18V` input |
| `D_Z_RPP` | 1 | `BZX84-C9V1,215` | `SOT-23` | **`C96231`** | **Extended (`$3`)** | `9.1V` Zener clamp across `AO3401A` `G-S` for `18V` gate protection |
| `U_USB_ESD` | 1 | `SRV05-4-P-T7` | `SOT-23-6` | **`C85364`** | **Preferred (`$0`)** | Low-capacitance USB `D+/D-/VBUS` ESD protection array |
| `J_USB` | 1 | `TYPE-C-31-M-12` | `SMD-16P` | **`C165948`** | **Extended (`$3`)** | Right-angle 16-pin USB-C receptacle (North edge) |
| `Q_RPP1, Q_USB` | 2 | `AO3401A` | `SOT-23` | **`C15127`** | **Basic (`$0`)** | Reverse-polarity `9–18V` PMOS + zero-backfeed `USB VBUS` blocker |
| `Q_REL, Q_MUTE, Q_LED..` | 4 | `AO3400A` | `SOT-23` | **`C20917`** | **Basic (`$0`)** | Low-side NMOS drivers for relays, PhotoMOS mute LEDs & status LEDs |
| `D_BUCK, D_P, D_N` | 3 | `SS34` | `SMA` | **`C8678`** | **Basic (`$0`)** | `40V 3A` Schottky rectifiers for `TPS5430` & `TPS65131` |
| `D_OR1..4` | 4 | `1N5819WS` | `SOD-323` | **`C191023`** | **Basic (`$0`)** | Power-OR & rail reverse-clamp Schottkys |
| `D_FLY1..2, D_MIDI, D_PK..` | 5 | `1N4148W` | `SOD-123` | **`C81598`** | **Basic (`$0`)** | Individual relay flybacks, `H11L1` anti-parallel & peak detector diodes |
| `D_CLAMP` | 1 | `BAV99,215` | `SOT-23` | **`C2500`** | **Basic (`$0`)** | Dual series clamp (`1=GND, 2=+3V3, 3=Sig`) on guitar env tap |
| `SW_BOOT` | 1 | `TS-1088-AR02016` | `SMD,4x3mm` | **`C720477`** | **Basic (`$0`)** | Onboard `BOOTSEL` tactile switch (`QSPI_SS` boot override) |

### 2.2 User Hand-Soldered Through-Hole & Panel Hardware BOM
| Item | Qty | Manufacturer & MPN | Supplier / Status | Footprint / Mounting |
|---|---:|---|---|---|
| `1/4"` Guitar Jacks (`IN L/R`, `OUT L/R`) | 4 | **Neutrik `NMJ4HCD2`** | **User already owns in stock** | `Connector_Audio:Jack_6.35mm_Neutrik_NMJ4HCD2_Horizontal` (North edge of `main_board` + outer chrome nut) |
| `MIDI TYPE A/B` Switch | 1 | **C&K `JS202011AQN`** | DigiKey UK | `Button_Switch_THT:SW_CK_JS202011AQN_DPDT_Angled` (North edge of `main_board`) |
| `3.5 mm` TRS MIDI Jacks (`IN`, `THRU`) | 2 | **Same Sky (CUI) `SJ1-3523N`** | DigiKey UK | `Connector_Audio:Jack_3.5mm_CUI_SJ1-3523N_Horizontal` (North edge of `main_board`) |
| MIDI Optocoupler + Socket | 1 | **Onsemi / Lite-On `H11L1M` (`H11L1`)** + `DIP-6` socket | DigiKey UK / User stock | `Package_DIP:DIP-6_W7.62mm` (`main_board`) |
| Eurorack `3.5 mm` Patch Jacks | 12 | **QingPu `WQP-PJ398SM` ("Thonkiconn")** + knurled nuts | Thonk UK | `Connector_Audio:Jack_3.5mm_QingPu_WQP-PJ398SM_Vertical_CircularHoles` (`ui_mezzanine`) |
| `0.96"` OLED Module | 1 | **`0.96"` `SSD1306` `128×64` I2C OLED (4-pin)** | Thonk / Amazon | `PinSocket_1x04_P2.54mm_Vertical` on `ui_mezzanine` (with reversible `GND/VCC` jumper!) |
| Rotary Encoder + Knob | 1 | **Alps `EC11E15244G1`** (vertical, push-switch, 20mm shaft) | Thonk / DigiKey UK | `Rotary_Encoder:RotaryEncoder_Alps_EC11E-Switch_Vertical_H20mm_CircularMountingHoles` (`ui_mezzanine`) |
| `BACK` Push Button | 1 | **Tactile switch (`H=13mm`)** | DigiKey UK / Thonk | `Button_Switch_THT:SW_PUSH_6mm_H13mm` (`ui_mezzanine`) |
| `IN TRIM` & `OUT TRIM` Pots | 2 | **Bourns `PTD902-2020K-B103` / Alpha `RD902F-20` `10 kΩ` Dual-Gang Linear** | DigiKey UK / Thonk | Custom verified `9mm` vertical dual-gang footprint (`Pin 1=CCW/AGND, Pin 2=Wiper, Pin 3=CW/Signal`) |
| Eurorack Power Header + Ribbon | 1 | **Shrouded `2×5` `2.54 mm` IDC Box Header** + `15 cm` 10-pin Eurorack ribbon | Thonk / DigiKey UK | `Connector_IDC:IDC-Header_2x05_P2.54mm_Vertical` (`main_board`, marked `RED STRIPE / -12V`) |
| Stompbox Footswitches (`FS1, FS2`) | 2 | **Soft-touch SPST Momentary Panel Footswitch** (`Ø12 mm`, e.g. Alpha `SF12011F` / Lehle / Gorva) | Thonk / DigiKey UK | Panel-mounted in `Ø12.2 mm` bores on stepped front apron → wired to `J_FS1, J_FS2` |
| Stomp Status LEDs (`BYP`, `FRZ/CLK`) | 2 | `3 mm` diffused THT LEDs + snap-in bezels | DigiKey UK / Thonk | Stepped front apron beside `FS1` & `FS2` → wired to `J_LED1, J_LED2` |
| Panel DC Barrel Jack (`9–18V`) | 1 | **Insulated Plastic-Body `2.1 × 5.5 mm` Panel DC Jack** (Cliff `FC68148` / Lumberg `1614 16`) | DigiKey UK / Thonk | North wall bore → wired to `J_PWR_IN` (`Sleeve = +9-18V`, `Center = 0V GND`) |
| Board-to-Board Interconnect | 2 sets | `2×8` `2.54 mm` Male Pin Headers + Female Sockets / IDC ribbon jumpers | DigiKey UK / Thonk | Connects `main_board` ↔ `ui_mezzanine` |
| Heat-Set Inserts + Knurlies | 18 + 8 | **M3 Brass Heat-Set Inserts** (`M3 × L4.0 × OD4.6 mm`) + **`8×` M3 Knurled Eurorack Bolts** | User / Thonk | Pressed into `PETG-HF` enclosure bosses |

---

## 3. Critical 2-Layer PCB Layout, Grounding & DFM Rules

1. **Continuous `B.Cu` Ground Plane (`> 90%` Unbroken Copper on `main_board`):**
   - Route `95%+` of signals and power trunks (`>= 0.5–0.8 mm` width) on **`F.Cu`**; keep **`B.Cu`** as a single unbroken solid `GND` plane without split-moat chasms.
   - **Spatial Zoning:** North-East = `9–18V` DC-DC switchers + `J_EURO_PWR`; North-Center = `USB-C`, `RP2040`, `MIDI IN/THRU`; North-West = `4× NMJ4HCD2`, `K1/K2` relays, `TLP172AM` PhotoMOS mutes, `TL072`/`NE5532` audio stages; South-West = `4× MCP4822` + `TL072` CV buffers + `J_BTB_*`.
2. **Thermal Pads, Paste Layers, Relay Coil Polarity & Standoff Keepouts (`HARDWARE_LESSONS.md`):**
   - Include `"F.Paste"` on `TLP172AM` (`SOP-4-2.54mm`) and `G6K-2F-Y-TR DC5` (`C47190`) SMD pads; **verify polarized coil orientation on `G6K-2F-Y-TR DC5` (`Pin 1 = +Coil/+5V_BUCK/Flyback Cathode`, `Pin 8 = -Coil/NMOS Drain/Flyback Anode`)** alongside Bellcore `3.20 / 2.20 / 2.20 mm` pitch; segment `F.Paste` (`50–70%` 4-window grid) on `RP2040` (`Pad 57`), `TPS5430` (`Pad 9`), and `TPS65131` (`Pad 25`) thermal pads avoiding open `0.3 mm` thermal vias.
   - Keep non-GND copper/vias **`>= 3.0 mm` clear of M3 mounting holes (`MH*`)**.
   - Verify EasyEDA Pin-1 quadrant rotations and `TO-252` DPAK centroid offsets (`-1.20 mm`) on every CPL entry; exclude all THT parts from `*_cpl.csv`.
