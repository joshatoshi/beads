# Stereo Guitar Audio Chain, Popless True-Bypass, 8-Ch Bipolar CV DACs & Hardware MIDI THRU (`02_AUDIO_CHAIN_CV_DACS_AND_MIDI_SCHEMATIC.md`)

## 1. Stereo `1/4"` Guitar I/O, Passive `L→R` Normalling & Boutique Popless/Clickless Relay True Bypass

### 1.1 `4×` Neutrik `NMJ4HCD2` `1/4"` Jacks (User-Owned Stock, Direct North-Edge PCB Mount)
- **Footprint:** `Connector_Audio:Jack_6.35mm_Neutrik_NMJ4HCD2_Horizontal` (4 through-hole pins: `T` = Tip, `TN` = Tip-Normal, `S` = Sleeve, `SN` = Sleeve-Normal).
- **North-Wall Order (Viewing Pedal from Front/Top, Left-to-Right — Standard Pedalboard Right-to-Left Signal Flow):**
  - Left-side output pair: **`J_OUT_R`** (`OUT R`), **`J_OUT_L`** (`OUT L / MONO`)
  - Right-side input pair: **`J_IN_R`** (`IN R`), **`J_IN_L`** (`IN L / MONO`)
- **Exact Pin Wiring (`CRITICAL` — Never Ground Output `TN`!):**
  1. **`J_IN_L` (`IN L / MONO`):**
     - `T`: `GTR_IN_L_RAW` → Relay `K1` `COM_A` (`+ 2.2 MΩ` anti-pop bleed to `AGND`).
     - `TN`: Connected to `AGND` (quietly grounds input when no guitar cable is plugged into `IN L`).
     - `S`: `AGND`; `SN`: `no_connect` (`×`).
  2. **`J_IN_R` (`IN R` — Automatic Passive Mono-to-Stereo Normalling!):**
     - `T`: `GTR_IN_R_RAW` → Relay `K2` `COM_A` (`+ 2.2 MΩ` anti-pop bleed to `AGND`).
     - **`TN`: Connected directly to `GTR_IN_L_RAW` (`J_IN_L.T`)!** Plugging a single mono guitar cable into `IN L` automatically routes mono guitar to BOTH `L` and `R`; inserting a second plug into `IN R` mechanically breaks `TN` for discrete True Stereo!
     - `S`: `AGND`; `SN`: `no_connect` (`×`).
  3. **`J_OUT_L` (`OUT L / MONO`) & `J_OUT_R` (`OUT R`):**
     - `T`: Driven from Relay `K1` / `K2` `COM_B` (`GTR_OUT_L` / `GTR_OUT_R`).
     - **`TN` & `SN`: Strictly `no_connect` (`×`)!** *(Never ground `TN` on output jacks—doing so dead-shorts the output when unplugged!)*
     - `S`: `AGND`.

### 1.2 Boutique Popless / Clickless Stereo Relay True-Bypass Architecture
> *"Please make sure the true bypass solution has popless/clickless technology/componentry that most guitar pedals have these days."*

Bare mechanical relays click/pop in guitar chains due to **contact bounce (`1.5–3.0 ms`)** chopping live audio waveforms, **coil-to-contact capacitive `dV/dt` feedthrough**, and **residual DC voltage steps**. We eliminate all three using the exact **Solid-State PhotoMOS Opto-FET Shunt Mute + Timed DPDT Relay** architecture used in modern flagship boutique pedals (Strymon, Chase Bliss, EQD Flexi-Switch, Boss Waza):

```text
  J_IN_x.T ──┬──► K_x.COM_A ──(NC_A)──────────[Passive Straight Copper Bypass]──────────(NC_B)──┐
           [2.2M]            └─(NO_A)─► [2.2M] ─► 1MΩ JFET Preamp ─► SEND_x ... RET_x ─►       ├─► K_x.COM_B ─┬─► J_OUT_x.T
            AGND                                  NE5532 Return ─► 10uF ─► [2.2M] ─► [220Ω] ─(NO_B)            │
                                                                                                         [2.2M]┼──► TLP172AM (Pins 3,4)
                                                                                                              AGND  (Opto-FET Shunt Mute)
```

1. **Mechanical True-Bypass Relays (`K1` = Left, `K2` = Right):**
   - Part: **`2 × Omron G6K-2F-Y-TR DC5` (`LCSC C47190`, `5V` `100 mW` `237 Ω` polarized single-side stable coil, gold-clad silver-alloy bifurcated contacts)**.
   - **CRITICAL Polarized Coil & Pad-Pitch Rules (`G6K-2F-Y-TR DC5` Datasheet):**
     - `G6K-2F-Y` has a **polarized magnetic coil**: **`Pin 1 = +Coil` (`+5V_BUCK` + local `1N4148W` flyback diode Cathode)** and **`Pin 8 = -Coil` (switched NMOS Drain + local `1N4148W` flyback diode Anode)**! Reversing Pins 1 & 8 prevents relay actuation!
     - Verify exact Omron `G6K-2F-Y` Bellcore SMD pad pitch (`3.20 mm` coil-to-contact spacing, then `2.20 mm`, `2.20 mm`) and EasyEDA Pad-1/centroid coordinates on `F.Cu`.
   - **Fail-Safe Unpowered Passive Bypass:** When de-energized (`NC`), `J_IN_x.T` connects straight across copper to `J_OUT_x.T` while disconnecting `PREAMP_IN_x` completely (`True Bypass`).
2. **Optical Zero-Charge-Injection PhotoMOS Shunt Mutes (`U_MUTE_L`, `U_MUTE_R`):**
   - Part: **`2 × Toshiba TLP172AM(TPL,E` (`LCSC C2152276`, `SOP-4-2.54mm`, `60V` bipolar AC/DC, `R_ON = 1.0 Ω` typ / `2.0 Ω` max, `C_OFF ≈ 20 pF`, `> 1000 MΩ` off-resistance, `3.75 kVrms` optical isolation, `t_ON = 0.6 ms` typ / `2.0 ms` max, `t_OFF = 0.1 ms` typ / `1.0 ms` max)**.
   - **Audio-Side Wiring (`Pins 3 & 4` — Bidirectional Dual-DMOS Output):**
     - `Pin 3` connects to `K1.COM_B` (`GTR_OUT_L`) / `K2.COM_B` (`GTR_OUT_R`); `Pin 4` connects directly to `AGND`.
     - **Why PhotoMOS beats JFETs/CMOS switches:** `3.75 kV` infrared optical coupling has **`0 pC` gate-charge injection** (switching a JFET gate injects its own audible pop!) and stays **100% open-circuit (`> 1 GΩ`)** during normal play so passive True Bypass has zero semiconductor distortion. During the `15 ms` mute window, `1.0 Ω` shunts `OUT L/R` smoothly to `0.000V` (`> 46 dB` attenuation against the `220 Ω` return output isolator and `> 40–78 dB` against upstream pedals/pickups, while `220 Ω` limits `NE5532` peak mute current to `< 9 mA`).
   - **Soft-Slewed Infrared LED Drive (`Pins 1 & 2`):**
     - Driven from `+3V3_DIG` via low-side NMOS `Q_MUTE` (`AO3400A` `C20917` Basic, controlled by `RP2040` `GPIO23` `PHOTOMOS_MUTE_EN`) with an **`RC` soft-slew network (`R_SLEW = 2.2 kΩ`, `C_SLEW = 470 nF` → `τ ≈ 1.0 ms`)** so LED current ramps smoothly rather than snapping!
     - Each `TLP172AM` LED (`V_F = 1.27V`) has its own dedicated **`270 Ω` (`0603` Basic 1%)** series resistor (`I_F = (3.30V - 1.27V) / 270 Ω = 7.5 mA` — `2.5×` above Toshiba's `3.0 mA` worst-case `I_FT,max`, respecting `HARDWARE_LESSONS.md`: always size `TLP172AM` LED resistors `<= 330 Ω` on `3.3V`!).
3. **Zero-DC Offset Network (`< 50 µV` Across Every Contact):**
   - Place **`2.2 MΩ` (`0603` Basic) DC bleed resistors to `AGND`** on all 4 relay terminals per channel (`GTR_IN_x_RAW`, `PREAMP_IN_x` ahead of input AC cap, `RETURN_AC_OUT_x` after the `10 µF` return DC-blocking cap, and `GTR_OUT_x`). Every contact sits at `0.000V` DC at all times.
4. **Slew-Damped Relay Coil Drive (`Q_REL`):**
   - Low-side NMOS `Q_REL` (`AO3400A` `C20917`, controlled by `RP2040` `GPIO12` `RELAY_BYPASS_EN`) includes a gate `RC` (`1.0 kΩ` + `4.7 nF` → `~5 µs` edge) plus **two individual local `1N4148W` (`C81598`) flyback diodes** right across `K1` coil and `K2` coil, eliminating coil `dV/dt` capacitive click coupling.
5. **Timed Firmware Clickless Bypass & Power-On Blanking Sequence (`15.0 ms` Window):**
   - **On `FS1` press / MIDI Bypass CC / Preset Bypass change:**
     1. `t = 0.0 ms`: Assert `PHOTOMOS_MUTE_EN = 1` → wait **`3.5 ms`** (`> 2.0 ms` datasheet max `t_ON` + `1 ms` soft-knee; output glides silently to `0V`).
     2. `t = 3.5 ms`: Flip `RELAY_BYPASS_EN` (`K1` & `K2`) → hold muted for **`8.0 ms`** (`> 3.0 ms` max operate/release + `3.0 ms` max bounce on `G6K-2F-Y`).
     3. `t = 11.5 ms`: De-assert `PHOTOMOS_MUTE_EN = 0` → wait **`3.5 ms`** (`> 1.0 ms` max `t_OFF` + soft-knee release) → return to `IDLE` at `t = 15.0 ms`!
   - **Power-On & Brownout Thump Blanking:** Whenever `PEDAL_PWR_GOOD` (`GPIO22`) is LOW or recovering, latch `RELAY_BYPASS_EN = 0` (passive bypass) AND hold `PHOTOMOS_MUTE_EN = 1` for **`250 ms`** after `+5V_BUCK` stabilizes before allowing relay engagement so Beads' boot transient never reaches the guitar amp!

---

## 2. Guitar ↔ Eurorack Level Shifting (`12 o'clock` Trim = Exact `0.0 dB` Guitar Unity & `0°` Phase!)

### 2.1 Stereo `1 MΩ` JFET Guitar Input Preamp (`IN L/R` → `SEND L/R` Thonkiconn)
- **Op-Amps:** **`2 × TL072CDT` (`LCSC C6961`, Basic `$0` fee, `±12V_EUR` rails with local `100 nF` decoupling `<= 4 mm` from `Pins 8 & 4`)**.
- **Per-Channel Non-Inverting 2-Stage Topology (`L` and `R` identical, controlled by dual-gang `RV_IN_TRIM`):**
  1. `PREAMP_IN_x` → `1 µF 50V X7R 1206` coupling cap → `10 kΩ` RF stopper + `47 pF C0G` (`C1567` Basic) RF filter (`f_c = 338 kHz`) + **`1.0 MΩ` bias resistor to `AGND`** → `TL072` Stage 1A (`2.0×` = `+6.02 dB` non-inverting JFET buffer: `R_f = 10.0 kΩ`, `R_g = 10.0 kΩ`).
  2. **Dual-Gang Pot `RV_IN_TRIM` (`10 kΩ` Linear: `Pin 1 = CCW = AGND`, `Pin 3 = CW = Stage 1A Out`, `Pin 2 = Wiper`):** At `12 o'clock` (`50%`), wiper gain = `0.50 × 2.0 = 1.00×`.
  3. **`TL072` Stage 1B:** Fixed non-inverting **`8.00×` (`+18.06 dB`)** amplifier (`R_f = 68 kΩ + 2.0 kΩ = 70.0 kΩ`, `R_g = 10.0 kΩ` + `22 pF C0G` stability cap) → **`1.0 kΩ` series Eurorack output protection resistor** → **`J_SEND_L` / `J_SEND_R` (`WQP-PJ398SM` Thonkiconn, `Pin TN` = `no_connect`!)**.
  - **Result:** `12 o'clock` = **`+18.06 dB` (`8.0×`: `1.0 Vpp` guitar → `8.0 Vpp` Eurorack)**; `9 o'clock` = `+12.0 dB` (hot pickups/synths); `Full CW` = **`+24.1 dB` (`16.0×`)** clean boost!

### 2.2 Stereo Eurorack-to-Guitar Return Attenuator (`RET L/R` Thonkiconn → `OUT L/R` `1/4"`)
- **Op-Amps:** **`1 × NE5532DR` (`LCSC C7426`, Basic `$0` fee)** + **`1 × TL072CDT` (`LCSC C6961`, Basic `$0` fee)**.
- **Per-Channel Non-Inverting Topology (`0°` Phase Preservation!):**
  1. **`J_RET_L` & `J_RET_R` (`WQP-PJ398SM` Thonkiconn):** Wire `J_RET_L.T` to `J_RET_R.TN` so patching a single mono cable into `RET L` automatically normals to `RET R`, while patching both gives discrete stereo!
  2. **`100 kΩ` Precision Input Pad (`0.250×` = `-12.04 dB`):** `R_TOP = 75.0 kΩ`, `R_BOT = 25.0 kΩ` (`24 kΩ + 1.0 kΩ` Basic 1% → exact `100.0 kΩ` Eurorack input load, attenuating `16 Vpp` peaks to `4.0 Vpp`!) → `NE5532DR` unity follower (`1.00×`).
  3. **Dual-Gang Pot `RV_OUT_TRIM` (`10 kΩ` Linear: `Pin 1 = CCW = AGND`, `Pin 3 = CW = NE5532 Out`, `Pin 2 = Wiper`):** Feeds `TL072CDT` unity follower (`1.00×`) → `10 µF 25V` DC-blocking cap + `2.2 MΩ` bleed to `AGND` → **`220 Ω` series output isolator (`R_OUT_SER`)** → `K1/K2 NO_B`!
  - **End-to-End Unity Proof at `12 o'clock` (`50%` on Both Trims):**
    `Gain_total = 8.00 × (0.250 × 0.50 × 1.00) = 8.00 × 0.125 = 1.000×` (**`0.00 dB` exact unity gain and `0°` non-inverting phase**!), with `+6.0 dB` makeup boost available at `Full CW`.

### 2.3 Overvoltage-Proof Guitar Peak & Pluck Detector (`MCP6002` on `+3.30V` → `RP2040 ADC0`)
- **IC:** **`MCP6002T-I/SN` (`LCSC C7377`, Preferred `$0` fee, powered strictly from `+3V3_DIG` and `GND`)** — output physically cannot exceed `+3.30V` or go below `0V`, guaranteeing `RP2040 GPIO26 (ADC0)` latch-up immunity!
- **Circuit:** Sum pre-resistor `SEND_L` + `SEND_R` via `2 × 47 kΩ` + `BAV99` (`C2500` Basic: `1=GND, 2=+3V3_DIG, 3=Node`) → `MCP6002A` active precision half-wave rectifier (`~0.35×` scaling `4 Vpk` to `~2.8V`) → **`100 Ω` series damping resistor** (mandatory before peak-hold diode/cap!) → `1N4148W` (`C81598`) → `C_PK = 47 nF` || `R_BLEED = 100 kΩ` (`τ = 4.7 ms` fast pick capture) → `MCP6002B` unity buffer → `220 Ω + 1 nF C0G` → `RP2040 GPIO26 (ADC0)`.

---

## 3. 8-Channel Universal Bipolar CV / `1V/Oct` / Gate Output Stage (`CV 1..CV 8`)

- **DACs:** **`4 × MCP4822-E/SN` (`LCSC C16040`, `SOIC-8`, `12-bit` Dual SPI DAC with internal `2.048V` `50 ppm/°C` reference, `2×` gain mode = `0..4.095V`)** on `SPI0` with 4 dedicated direct MCU `~CS` pins (`GPIO16, 17, 20, 21`).
- **Precision Offset Reference (`+2.495V`):** **`CJ431` (`LCSC C3113` Basic, `REF` tied directly to `K` = zero-divider-error `+2.495V`)** buffered by **`OP07CDR` (`LCSC C7433` Basic `75 µV`-offset op-amp)**. *(Verify `CJ431` SOT-23 datasheet pinout before routing!)*
- **8× Symmetric Bipolar Amplifiers (`4 × TL072CDT` `C6961` Basic on `±12V_EUR`):**
  - Per channel: `R_G = 10.0 kΩ` (`+2.495V_REF` → `IN-`), `R_FB = 33.0 kΩ` (`+ 47 pF C0G` feedback cap), `R_P1 = 1.50 kΩ` (`V_DAC` → `IN+`), `R_P2 = 22.0 kΩ` (`IN+` → `AGND`).
  - Output swing: `code 0` = **`-8.23V`**, `code 2048` = **`+0.01V` (`~0.00V`)**, `code 4095` = **`+8.25V`** (`4.02 mV/LSB` covering Beads' full `±8V` and `±5V` spans, `0..+5V` sub-microsecond Gates/Triggers, and Flash-calibrated `1V/Oct` pitch on **all 8 channels**!).
  - Series **`1.0 kΩ` (`0603` Basic 1%)** short-circuit protection resistor from each `TL072` output to its **`WQP-PJ398SM` Thonkiconn** tip (`Pin TN` = `no_connect`!).

---

## 4. `3.5 mm` TRS MIDI IN (`TYPE A / TYPE B` Switch) & Pure Hardware `MIDI THRU`

- **Jacks (`J_MIDI_IN`, `J_MIDI_THRU`):** **`2 × Same Sky / CUI SJ1-3523N`** (`Pin 1 = Sleeve`, `Pin 2 = Tip`, `Pin 3 = Ring`; leave `J_MIDI_IN.Pin 1` `no_connect` per MMA RP-054 ground-loop isolation!).
- **Passive `TYPE A / TYPE B` Crossover Switch (`SW_MIDI_AB` = C&K `JS202011AQN` Right-Angle 6-Pin DPDT):**
  - `COM1 (Pin 2)` → `220 Ω` → `H11L1 Pin 1 (Anode)`; `COM2 (Pin 5)` → `H11L1 Pin 2 (Cathode)` (with anti-parallel `1N4148W` `C81598` across Pins 1–2).
  - **Left (`TYPE A`):** `Pin 1 = Ring`, `Pin 4 = Tip`. **Right (`TYPE B`):** `Pin 3 = Tip`, `Pin 6 = Ring`.
  - Label **`◄ MIDI TYPE A | MIDI TYPE B ►`** prominently on `F.SilkS` and North case wall!
- **Optocoupler (`U_OPTO` = Hand-Soldered `H11L1` in `DIP-6`):** `Pin 1=A, 2=K, 3=NC, 4=Vo` (`470 Ω` pull-up to `+3V3_DIG`), `5=DGND, 6=+3V3_DIG` (`+ 100 nF` local cap).
- **Zero-Latency Hardware `MIDI THRU` + Isolated MCU Copy (`U_INV` = `74HC14D,653` `C5605` Basic on `+3V3_DIG`):**
  - `H11L1 Pin 4` → `74HC14` Gate 1 (`1→2`) → parallel Gates 2 & 3 (`3+5 → 4+6`) → **`10 Ω` (`R_THRU_SINK`)** → `J_MIDI_THRU.Pin 2 (Tip)`; `+3V3_DIG` → **`33 Ω` (`R_THRU_SRC`)** → `J_MIDI_THRU.Pin 3 (Ring)` (MMA CA-033 `3.3V` MIDI spec!).
  - Separate `74HC14` Gate 4 (`9→8`) buffers `Gate 1 Out` cleanly to **`RP2040 GPIO1 (UART0_RX)`**; unused `74HC14` inputs (`11, 13`) tied to `DGND`.
