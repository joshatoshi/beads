# Power Supply, Protection & Zero-Backfeed USB-C Isolation Specification (`01_POWER_PROTECTION_AND_USB_ISOLATION.md`)

## 1. Power Budget & Rail Requirements

| Rail | Target Voltage & Tolerance | Continuous Capability | Actual Load Breakdown | Ripple / Noise Target |
|---|---|---|---|---|
| **`+VIN_RAW`** | **`+9.0V` to `+18.0V` DC** (from Center-Negative barrel jack) | `1.1 A` (`33V` PTC hold @ `25°C`, `~650 mA` @ `60°C`) | `~290–330 mA @ 9V` (`~155–175 mA @ 18V`) | Filtered via input LC Pi-filter |
| **`+5V_BUCK`** | **`+5.05V ± 2%`** | `>= 1.5 A` (`TPS5430DDAR` `3A` IC) | Feeds `TPS65131` (`~450 mA`), `2× G6K-2F-Y` relays (`40 mA`), `4× MCP4822` (`~3 mA`), `+3.3V` LDO (`~50 mA`) | `< 15 mVpp` @ `500 kHz` |
| **`+12V_EUR`** | **`+12.00V ± 2%`** | **`>= 300 mA`** continuous | Beads `+12V` (`100 mA` steady + STM32H743 boot inrush) + `8×` dual op-amps (`~24 mA`) | **`< 1.0 mVrms`** (linear post-LDO + ferrite LC) |
| **`-12V_EUR`** | **`-12.00V ± 2%`** | **`>= 150 mA`** continuous | Beads `-12V` (`10 mA`) + `8×` dual op-amps (`~24 mA`) | **`< 1.0 mVrms`** (linear post-LDO + ferrite LC) |
| **`+3V3_DIG`** | **`+3.30V ± 2%`** | `>= 300 mA` (`AMS1117-3.3`) | `RP2040` + `W25Q128` (`~28 mA`), `H11L1` + `74HC14` MIDI (`~10 mA`), `2× TLP172AM` (`15 mA` transient for `14 ms`), `0.96"` `SSD1306` OLED (`~12 mA` via isolated ferrite branch) | `< 2 mVrms` (`OLED_3V3` isolated via `120 Ω` ferrite + `10 µF`) |

---

## 2. Center-Negative `9V–18V DC` Input & Multi-Stage Pedalboard Protection

### 2.1 Center-Negative Polarity Convention (CRITICAL!)
Standard guitar pedal power supplies (Boss PSA, Strymon Zuma/Ojai, Cioks DC7, Truetone 1Spot CS, Voodoo Lab) are **2.1 mm × 5.5 mm Center-Negative**:
- **Barrel Center Pin (`PIN_CENTER`)** = **`0V GND`** (connected to PCB ground star at input filter).
- **Barrel Outer Sleeve (`PIN_SLEEVE`)** = **`+9V..+18V` Positive Supply (`J_DC_POS`)**.
- **Mechanical Isolation:** The enclosure is non-conductive `PETG-HF` plastic, AND the user hand-solders an **insulated plastic-housing `2.1 × 5.5 mm` panel-mount DC jack** (e.g., Lumberg `1614 16` / Cliff `FC68148`) wired to a clearly marked 2-pin header/pad pair `J_PWR_IN` on `main_board`:
  - Silkscreen MUST prominently display **`( - )──( ●──( + )  9-18V DC CENTER NEGATIVE`** plus explicit pin labels **`PIN 1: +9-18V (SLEEVE)`** and **`PIN 2: GND (CENTER)`**.

### 2.2 Input Protection Chain (In Exact Schematic Order)
1. **Resettable PTC Polyfuse (`F1`):**
   - Part: **`SMD1812B110TF/33` (`LCSC C269134`, Extended, `33V` max, `1.10A` hold @ `25°C`, `1.95A` trip)**.
   - Why: Never use `6V`-rated `0805` PTCs on `9–18V` rails! At `60°C` internal pedalboard case temp (`~0.6×` derating), `1.10A` holds `~660 mA` comfortably above our `~320 mA @ 9V` draw while tripping cleanly on sustained faults.
2. **Overvoltage / Transient Surge Clamp (`D_TVS1`):**
   - Part: **`SMBJ20CA` (`LCSC C19077576`, Preferred `$0` fee, `20V` standoff bidirectional `600W` TVS)** across `(VIN_FUSED, GND)`.
3. **Zero-Drop High-Side P-MOSFET Reverse-Polarity Protection (`Q_RPP1`):**
   - Part: **`AO3401A` (`LCSC C15127`, Basic `$0` fee, `V_DS = -30V`, `V_GS = ±12V` abs-max, `R_DS(on) = 42 mΩ @ -4.5V`)**.
   - **Orientation:** **Drain (`Pin 3`)** faces `VIN_FUSED` (from `F1`); **Source (`Pin 2`)** faces downstream `VIN_PROT`. If a **center-positive** adapter is plugged in by mistake (`VIN_FUSED = -9V..-18V`), `V_GS > 0` holds `Q_RPP1` **100% OFF** (`0 µA` reverse current).
   - **Mandatory `V_GS` Protection for `18V` Operation (`±12V` Gate Limit!):**
     - Use a **two-resistor gate divider (`R_G1 = 10 kΩ` Source-to-Gate, `R_G2 = 10 kΩ` Gate-to-GND)** PLUS a parallel `9.1V` Zener clamp (**`BZX84-C9V1,215` `LCSC C96231`**, Anode to Gate, Cathode to Source):
       - At `VIN = 9.0V`: `V_SG = 4.50V` (`AO3401A` fully enhanced, `42 mΩ`).
       - At `VIN = 18.0V`: `V_SG = 9.00V` (clamped `<= 9.1V`, strictly inside `±12.0V` abs-max!).
4. **Input EMI / Pedalboard Noise Isolation Pi-Filter:**
   - `2 × 10 µF 50V X7R 1206` MLCCs → `BLM18PG121SN1D` (`LCSC C14709`, Basic `2A` `50 mΩ`) → `2 × 10 µF 50V X7R 1206` + `100 nF 50V X7R` MLCCs. Prevents `500 kHz` buck ripple from leaking back onto shared pedalboard supplies.

---

## 3. Two-Stage Low-Noise Eurorack Power Architecture (`9–18V → +5V → ±13.8V → Linear ±12.0V`)

### 3.1 Stage 1: Wide-Input Step-Down Buck (`+5V_BUCK`)
- **IC:** **`TPS5430DDAR` (`LCSC C9864`, JLCPCB Basic = `$0` setup fee, `5.5V–36V` in, `3A`, `500 kHz`, `SOIC-8-EP`)** — exposed thermal pad (`Pad 9`) tied to `GND` with thermal vias and segmented `F.Paste` (`50–70%`).
- **Components:** `C_BOOT = 10 nF 50V X7R`; catch diode `D_BUCK = SS34` (`C8678`, Basic `$0` fee); inductor `L1 = FXL0530-100-M` (`C177248`, `10 µH`, `3.5A` `I_sat`); feedback divider `R_FB_TOP = 31.6 kΩ` (`30 kΩ + 1.6 kΩ`), `R_FB_BOT = 10.0 kΩ` → `V_OUT = +5.08V`; output bulk `2 × 22 µF 25V X5R/X7R 1206` + `100 nF` + `10 kΩ` bleed/load resistor; **`PEDAL_PWR_GOOD`** divider (`10 kΩ / 15 kΩ` → `RP2040 GPIO22`).

### 3.2 Stage 2: `1.38 MHz` Dual Boost / Inverting Pre-Regulator (`±13.8V_RAW`)
- **IC:** **`TPS65131RGER` (`LCSC C87663`, `QFN-24-EP 4×4mm`, `2.7V–5.5V` input, `1.38 MHz` switching)**.
- **Datasheet Pinout & Mandatory Wiring Verification (`TI SLVS493E`):**
  - Exposed Thermal Pad (`Pad 25`): Tied to `GND` with `2×2` `0.3 mm` thermal vias and **segmented 4-window `F.Paste`**.
  - `INP` (`Pins 1, 24`), `INN` (`Pins 9, 10`), `VIN` (`Pin 19`): Fed from `+5V_BUCK` with local `10 µF` + `100 nF` MLCCs within `<= 4 mm`.
  - `VREF` (`Pin 17`): Bypassed to `GND` with **`>= 220 nF`** (`470 nF` or `220 nF` MLCC mandatory per `SLVS493E`).
  - `Pin 20`: **`NC` (Leave unconnected per datasheet)**.
  - `PSP` (`Pin 21`) & `PSN` (`Pin 15`): Tie to `+5V_BUCK` to lock fixed-frequency `1.38 MHz` PWM (prevents audio-band pulse-skipping ripple!).
  - `ENP` (`Pin 22`) & `ENN` (`Pin 16`): Sequenced HIGH from `+5V_BUCK` (`ENP` via `10 kΩ`, `ENN` via `10 kΩ + 220 nF` `~2 ms` soft-start).
  - `CP` (`Pin 18`) & `CN` (`Pin 14`): Compensation caps (`4.7 nF–10 nF`) per `SLVS493E`.
  - Inductors `L2` & `L3`: **`2 × FXL0530-100-M` (`LCSC C177248`, `10 µH`, `3.5A` `I_sat`)**.
  - Rectifier Schottkys `D_POS`, `D_NEG`: **`2 × SS34` (`LCSC C8678`, Basic `$0` fee)**.
  - Feedback dividers set to **`+13.9V`** (`104.7 kΩ / 10.0 kΩ` to `GND`) and **`-13.7V`** (`113 kΩ` to `V_NEG_RAW`, `10.0 kΩ` to `VREF`), decoupled with **`35V–50V` `X7R` MLCCs**.

### 3.3 Stage 3: Linear `±12.0V` Post-Regulators + Ferrite LC Filters (`+12V_EUR`, `-12V_EUR`)
- **Positive `+12.0V` Post-LDO (`U_LDO_P12`):** **`LM317AG-TN3-R` (`LCSC C75510`, Preferred `$0` fee, `TO-252` DPAK)** set to `+12.00V` (`240 Ω` + `2.05 kΩ 1%`, with `10 µF` `CADJ` bypass cap for `80 dB` ripple rejection + protection diode).
- **Negative `-12.0V` Post-LDO (`U_LDO_N12`):** **`79M12(TP)` (`LCSC C53477637`, `TO-252-2L` DPAK)** — **Verify `79M12` pinout (`Pin 1 = GND`, `Pin 2/Tab = -13.7V_RAW INPUT`, `Pin 3 = -12.0V OUTPUT`)!** Include local ESR-damped output network (`10 µF` MLCC + `0.47 Ω` series resistor + `1 µF` MLCC) right at `VOUT` plus reverse-clamp `1N5819WS` (`C191023`) diodes across both `+12V→GND` and `GND→-12V`.
- **Eurorack Power Header (`J_EURO_PWR` — `Connector_IDC:IDC-Header_2x05_P2.54mm_Vertical`):**
  - Filtered via `2 × BLM18PG121SN1D` (`C14709`, Basic `2A`) + `47 µF 25V` + `100 nF` right at header:
    - **`Pins 1, 2` = `-12V_EUR`** — **Prominent silkscreen bar + `RED STRIPE / -12V` text!**
    - **`Pins 3, 4, 5, 6, 7, 8` = `GND`**
    - **`Pins 9, 10` = `+12V_EUR`**

---

## 4. Bulletproof Dual-Power Isolation (`USB-C VBUS` + `9–18V` Center-Negative Supply)

```text
 [USB-C VBUS] ──► [F_USB: 500mA PTC] ──► [TVS: SRV05-4] ──┬──► [D_USB_FWD: 1N5819WS] ──► [Q_USB: AO3401A] ──┐
                                                          │                              Gate ◄─ +5V_BUCK    ├──► VIN_3V3_LDO ──► [AMS1117-3.3] ──► +3V3_DIG
                                                          └──► [10k / 18k Divider] ──► RP2040 VBUS_DET (GP24)│
 [9-18V Pedal] ──► [F1 + TVS + Q_RPP1] ──► [TPS5430 +5V_BUCK] ─┬───────────────────────► [D_OR_PED: 1N5819WS]┘
                                                               ├──► TPS65131 (±12V Beads & Op-Amps) + Relays + MCP4822 DACs
                                                               └──► [10k / 15k Divider] ──► RP2040 PEDAL_PWR_GOOD (GP22)
```

1. **`USB-C` (`J_USB` = `TYPE-C-31-M-12` `C165948`):** Separate `5.1 kΩ 1%` pull-downs on `CC1` and `CC2`; `SRV05-4-P-T7` (`C85364` Preferred) ESD array on `D+/D-/VBUS`; `27 Ω` series resistors on `D+/D-`; `30V 500 mA` PTC (`JK-nSMD050-30` `C720075`) on `VBUS`.
2. **Guaranteed `< 1 µA` Zero Back-Current in Both Directions:**
   - When `9–18V` is ON (`+5V_BUCK = +5.08V`), `Q_USB` (`AO3401A` `C15127`, Source at `VIN_3V3_LDO = +4.75V`, Gate pulled to `+5V_BUCK` via `4.7 kΩ`) has `V_GS = +0.33V > 0V` (MOSFET hard cutoff `< 0.1 µA` in series with reverse-biased `D_USB_FWD`)—**zero current can ever flow out of `USB-C` into a laptop/iPad/hub**, even if the host is powered off at `0V`.
   - When `9–18V` is UNPLUGGED (`+5V_BUCK = 0V` via `10 kΩ` bleed), `Q_USB` Gate sits at `0V`, turning `Q_USB` ON (`V_GS = -4.6V`) so `USB-C` powers ONLY `AMS1117-3.3` (`RP2040` + OLED `< 50 mA` for bench UF2 flashing or preset editing), while `D_OR_PED` blocks `USB_VBUS` from back-powering `+5V_BUCK`, `±12V`, relays, or the `9–18V` barrel jack!
3. **`AMS1117-3.3` (`C6186` Basic):** Place `>= 22 µF` (`2 × 10 µF` MLCCs) directly on `VOUT` (`Pin 2 + Tab Pin 4`), with a separate `BLM18PG121SN1D` + `10 µF` branch feeding the `0.96"` `SSD1306` OLED.
