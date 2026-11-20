# `RP2040` Firmware, Popless Bypass Sequencer, Bezier Drift Engine, OLED UI & CI Gates (`05_FIRMWARE_DSP_UI_AND_VERIFICATION_GATES.md`)

## 1. Headerless USB-C Flashing & Dual-Core `RP2040` Architecture

### 1.1 Zero-Header USB-C UF2 Flashing
- **Fresh Board:** `RP2040` mask ROM mounts automatically over `USB-C` as `RPI-RP2` Mass Storage—drag-and-drop `beads_bridge.uf2` with zero SWD pins or external programmers.
- **In-Case Updates:**
  1. OLED Menu item **`SYSTEM → USB FIRMWARE UPDATE`** invokes `reset_usb_boot(0, 0)` cleanly.
  2. USB-CDC `1200-baud` auto-reset (`picotool load -f beads_bridge.uf2`).
  3. Onboard SMD `BOOTSEL` tactile button (`SW_BOOT` `C720477`) hardware fallback.

### 1.2 Complete `RP2040` GPIO Pinmux Allocation (Zero Collisions)
| `RP2040` Pin | Signal Name | Dir | Function |
|---|---|---|---|
| `GPIO0` | `DBG_TX_TP` | Out | Optional debug testpad (`MIDI THRU` is pure `74HC14` hardware!) |
| `GPIO1` | **`UART0_RX` (`31,250` bps)** | In | `74HC14` Gate 4 buffered copy of `H11L1` TRS `MIDI IN` |
| `GPIO4` | **`I2C0_SDA` (`400 kHz`)** | I/O | `0.96"` `SSD1306` OLED `SDA` (`4.7 kΩ` pull-up) |
| `GPIO5` | **`I2C0_SCL` (`400 kHz`)** | Out | `0.96"` `SSD1306` OLED `SCL` (`4.7 kΩ` pull-up) |
| `GPIO6, 7` | `ENC_A, ENC_B` | In | `EC11` Quadrature Encoder (`10 kΩ` ext pull-ups + `10 nF`, decoded via 16-state ISR LUT) |
| `GPIO8` | `ENC_SW` | In | `EC11` Push Switch (`10 kΩ` ext pull-up) |
| `GPIO9` | `BTN_BACK` | In | `14 HP` Panel `BACK` Button (`10 kΩ` ext pull-up) |
| `GPIO10` | **`FS1_BYPASS_SW`** | In | Stepped-apron Momentary Footswitch 1 (`10 kΩ` ext pull-up) |
| `GPIO11` | **`FS2_ACTION_SW`** | In | Stepped-apron Momentary Footswitch 2 (`10 kΩ` ext pull-up) |
| `GPIO12` | **`RELAY_BYPASS_EN`** | Out | Slew-damped NMOS driving `K1` + `K2` (`Omron G6K-2F-Y`: `1` = Active, `0` = True Bypass) |
| `GPIO13` | `LED_FS1_BYPASS` | Out | Apron LED 1 (Active/Bypass indicator) |
| `GPIO14` | `LED_FS2_STATUS` | Out | Apron LED 2 (`FREEZE` latch or `SEED` Tap-Tempo blink) |
| `GPIO15` | `LED_AUDIO_PEAK` | Out | `14 HP` Faceplate `PEAK / CLIP` PWM LED |
| `GPIO16, 17, 20, 21` | `~CS_DAC0..3` | Out | Direct `~CS` lines to `4× MCP4822` (`10 kΩ` pull-ups to `+3V3_DIG`) |
| `GPIO18, 19` | `SPI0_SCK, SPI0_TX` | Out | `10 MHz` SPI bus to `4× MCP4822` |
| `GPIO22` | **`PEDAL_PWR_GOOD`** | In | `+5V_BUCK` monitor (`1` = `9–18V` active; `0` = `USB-C` bench-only / brownout) |
| `GPIO23` | **`PHOTOMOS_MUTE_EN`** | Out | Soft-slewed NMOS driving **`2× Toshiba TLP172AM`** (`7.5 mA`/LED) for **popless/clickless bypass & POR blanking**! |
| `GPIO24` | **`VBUS_DET`** | In | `USB-C VBUS` sense ahead of `Q_USB` |
| `GPIO26` | **`ADC0` (`GTR_ENV_IN`)** | Analog | `0..3.30V` output from `MCP6002` guitar peak detector |

---

## 2. Deterministic Popless / Clickless True-Bypass & Brownout State Machine (`bypass_sequencer`)

Executed deterministically inside **Core 0's `2.0 kHz` (`500 µs`) real-time tick**:
1. **Power-On & Brownout Thump Blanking (Highest Priority):**
   - Whenever `PEDAL_PWR_GOOD == 0` (either `USB-C` bench mode or `9–18V` brownout): immediately force `RELAY_BYPASS_EN = 0` (passive true bypass), assert `PHOTOMOS_MUTE_EN = 1`, and **hold `por_blank_ticks = 500` (`250.0 ms`) latched at full duration** (never decrementing during sustained undervoltage!).
   - Once `PEDAL_PWR_GOOD == 1` stabilizes continuously for `250.0 ms`, if the startup preset specifies `active`, switch `RELAY_BYPASS_EN = 1` at `240 ms` while still muted, then release `PHOTOMOS_MUTE_EN = 0` at `250 ms`—**zero power-up pop**!
2. **Runtime Clickless Relay Transition (`15.0 ms` Total):**
   - Triggered by debounced `FS1` press (supports both **Latching press** AND **EQD Flexi-Switch Auto-Momentary**: short tap `< 300 ms` toggles bypass; holding `FS1 > 350 ms` momentarily engages Beads only while your foot holds the switch, releasing cleanly back to bypass on foot-up!!), MIDI Bypass CC (`CC #102`), or Preset Recall when `target_active != current_active`:
     - **`BYP_STATE_MUTING` (`3.5 ms` = `7` ticks @ `2 kHz`):** Set `PHOTOMOS_MUTE_EN = 1`. Both `TLP172AM` Opto-FETs smoothly ramp from `> 1 GΩ` down to `1.0 Ω` (`> 46 dB` output mute, `0 pC` optical isolation).
     - **`BYP_STATE_SWITCHING` (`8.0 ms` = `16` ticks @ `2 kHz`):** At `t = 3.5 ms`, set `RELAY_BYPASS_EN = target_active` and update `LED_FS1_BYPASS`. Hold `PHOTOMOS_MUTE_EN = 1` across the entire `8.0 ms` window so 100% of `Omron G6K-2F-Y` armature flight (`<= 3.0 ms`) and contact bounce (`<= 3.0 ms`) settle in complete silence. *(Also snap any preset CV jumps immediately during this muted window!)*
     - **`BYP_STATE_UNMUTING` (`3.5 ms` = `7` ticks @ `2 kHz`):** At `t = 11.5 ms`, set `PHOTOMOS_MUTE_EN = 0`. Allow `3.5 ms` soft-knee optical release before returning to **`BYP_STATE_IDLE`** at `t = 15.0 ms`!

---

## 3. Dual-Core Real-Time Engine, Modulation Modes & Presets

- **Core 0 (`2.0 kHz` Real-Time Tick via positive `add_repeating_timer_us(+500, ...)`):**
  - Scales phase/envelope steps by clamped `dt_us = now_us - prev_tick_us`.
  - Drains `UART0` (`PL011`) MIDI RX SPSC ring buffer (checking `UARTDR[11:8]` error flags, clearing `UARTRSR`, resetting Running Status on overflow or `0xFF` System Reset) + merges Core 1 USB-MIDI SPSC queue.
  - Updates all **8 universal `-8.2V..+8.2V` CV/Gate channels (`CV 1..CV 8`)** via delta-gated `uint16_t s_last_dac_code[8]` initialized to `0xFFFF` (after `PEDAL_PWR_GOOD` clears POR):
    1. **`MODE_BEZIER_DRIFT`:** Piecewise `C¹`-continuous **Cubic Bezier** organic random drift (`B(t) = (1-t)³P₀ + 3(1-t)²tP₁ + 3(1-t)t²P₂ + t³P₃` with matched endpoint derivatives `P₁ = y₀ + (τ/3)v₀`, `P₂ = y₁ - (τ/3)v₁`), adjustable Rate (`0.005..20 Hz`), Smoothness/Tension, Center Offset, and Span (`±8V`, `±5V`, `±2.5V`, `0..5V`, `0..8V`).
    2. **`MODE_LFO`:** 32-bit phase accumulator + 256-entry LUT (Sine, Triangle, Ramp Up/Down for `TIME` scrubbing, Square, Slewed S&H), free-running or synced/divided to MIDI Clock / `FS2` Tap Tempo, with `0°..270°` phase offset.
    3. **`MODE_RANDOM_TRIG`:** Euclidean `(Steps, Hits)` or Bernoulli probability `+5V` trigger/gate generator for autonomous Beads `SEED` & `FREEZE` modulation.
    4. **`MODE_MIDI_NOTE_1VOCT`:** Chromatic `1V/Oct` Pitch CV interpolated across a 9-octave Flash Calibration LUT + Pitch Bend + Glide + Mono/Duophonic/Poly-Grain voice allocation.
    5. **`MODE_MIDI_GATE_TRIG` / `MODE_MIDI_CLOCK_DIV`:** Note Gate, Retrigger pulse, Transport Run, or divided `24 PPQN` clock (`/1.. /96`).
    6. **`MODE_MIDI_CC` / `VELOCITY` / `AFTERTOUCH`:** Any `CC #0..127` with deadband-free rounded fixed-point smoothing (`±1` step when `0 < |diff| < (1<<k)`).
    7. **`MODE_GUITAR_ENVELOPE` & `MODE_GUITAR_PLUCK_TRIG`:** `ADC0` peak follower (discarding 1 dummy read on mux changes) with Attack, Release, Sensitivity, Ducking Invert, and `dE/dt` Pluck Trigger.
    8. **`MODE_FOOTSWITCH_FS2`:** Latching/Momentary `FREEZE` Gate, `SEED` Tap-Tempo Clock, or Dual-Action (`Short Tap = Tap Tempo / Seed`, `Hold > 350 ms = Freeze`).
- **Core 1 (TinyUSB `USB-MIDI` + Page-Sliced `SSD1306` Oscilloscope UI + Idle A/B CRC32 QSPI Flash Saver):**
  - Calls both `tusb_init()` and `tud_task()` on Core 1; isolates USB `CIN=0x0F` from UART Running Status; protects shared state with `critical_section_t`; defers QSPI Flash A/B `CRC32` writes until `BYP_STATE_IDLE` and `>= 300 ms` of non-realtime MIDI silence; enforces `PICO_CORE1_STACK_SIZE=0x1000`.

---

## 4. Mandatory End-to-End CI Verification Suite (`scripts/run_all_checks.sh`)
`bash scripts/run_all_checks.sh` MUST exit `0` and verify:
1. **KiCad 9 ERC = 0 & DRC = 0** across `main_board`, `ui_mezzanine`, and `faceplate_14hp` (`unconnected = 0`, `>88%` continuous `B.Cu` GND pour, `< 0.05 mm` `J_BTB_*` mating congruence, `F.CrtYd >= F.Fab`).
2. **100% `jlcpcb_parts.db` & CPL Parity:** Real stock, package/pin-count match, `>= 35–50V` capacitor derating, EasyEDA Pin-1 rotations & DPAK centroids, zero THT in `*_cpl.csv`.
3. **`ngspice` Simulation (`hardware/spice/verify_analog.py`):** Verify `9–18V` `AO3401A` gate clamp & reverse-polarity block, `< 1 µA` bidirectional `USB-C VBUS` ↔ `+5V_BUCK` isolation, **`> 45 dB` `TLP172AM` PhotoMOS popless mute attenuation with `< 2 mV` transient spike during simulated relay contact bounce**, `0.00 dB` `12-o'clock` stereo guitar unity & `0°` phase, `-8V..+8V` CV span, and `<= +3.30V` `MCP6002` ADC clamp.
4. **Firmware Target ELF + Host `assert()` Unit Tests:** `arm-none-eabi-gcc -Wall -Wextra -Werror -fstack-usage` UF2 build, zero 64-bit/float ISR helpers in Core 0 tick, plus unit tests covering **all states/timings of the `15 ms` PhotoMOS popless bypass FSM + Flexi-Switch hold + `250 ms` brownout blanking**, `C¹` Cubic Bezier continuity, LFO symmetry, `1V/Oct` LUT accuracy, MIDI parser recovery, and A/B Flash `CRC32` + `write_seq` persistence.
5. **`Build123d` + `OCP` 3D B-Rep Collision Gate (`cad/verify_3d_collisions.py`):** **`0.000 mm³` pairwise intersection** across all enclosure, lid, PCB, Beads, connector, insert, and switch solids.
