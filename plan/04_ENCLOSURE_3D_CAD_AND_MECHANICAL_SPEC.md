# Bambu Lab X2D `PETG-HF` 3D-Printed Low-Profile Stepped Enclosure Specification (`04_ENCLOSURE_3D_CAD_AND_MECHANICAL_SPEC.md`)

## 1. Printer, Material & Printability Constraints
- **Target 3D Printer:** **Bambu Lab X2D** (dual-nozzle capability with dedicated breakaway/soluble support interface material, large build volume accommodating the entire unibody case in a single flat print).
- **Target Filament:** **Bambu `PETG-HF`** (High-Flow PETG — impact-resistant under foot stomps on a guitar pedalboard, heat-tolerant for warm pedalboards & `M3` brass heat-set insert installation).
- **Wall & Rib Structural Thicknesses:**
  - Perimeter walls: **`3.60 mm`** (`North`, `South`, `Left`, `Right` — `5.0 mm` side bezels at the 3U rails).
  - Top 3U Eurorack rail lips & stepped front stomp apron deck: **`4.00 mm` thick**, reinforced with internal vertical gusset pillars flanking `FS1` and `FS2` down to the bottom lid so stomping `FS1`/`FS2` transfers foot force directly to the pedalboard floor.
  - Bottom removable service lid: **`3.00 mm` thick `PETG-HF`** countersunk flush into a `3.00 mm` bottom rabbet, secured by `6×` countersunk `M3 × 8 mm` machine screws into `6×` M3 brass heat-set inserts, with recessed `0.8 mm` underside pads for 3M Dual-Lock / rubber feet.

---

## 2. Exact Coordinate System & Envelope Dimensions (`152.0 × 185.6 × 45.0 mm`)

- **`X` Axis (Left-to-Right Width = `152.00 mm`):**
  - `X = 0.00 .. 5.00 mm`: Left outer bezel/wall.
  - **`X = 5.00 .. 75.80 mm` (`70.80 mm`):** **Left `14 HP` Bay (`faceplate_14hp`)**.
  - `X = 75.80 .. 76.20 mm` (`0.40 mm`): Clean Eurorack inter-panel seam.
  - **`X = 76.20 .. 147.00 mm` (`70.80 mm`):** **Right `14 HP` Bay (Mutable Instruments Beads)**.
  - `X = 147.00 .. 152.00 mm`: Right outer bezel/wall.
- **`Y` Axis (South/Front-to-North/Rear Depth = `185.60 mm`):**
  - `Y = 0.00 .. 3.60 mm`: Outer South wall.
  - **`Y = 3.60 .. 39.00 mm`:** **Stepped-Down Front Stomp Apron** (`FS1` at `(30.00, 21.00)`, `FS2` at `(122.00, 21.00)` → **`92.00 mm` foot spacing!** Status LEDs at `Y = 31.00 mm`).
  - `Y = 39.00 .. 42.60 mm`: Vertical `12.00 mm` step riser wall.
  - **`Y = 42.85 .. 171.35 mm` (`128.50 mm` 3U Eurorack panel span inside `[42.60, 171.60]` pocket):**
    - South Eurorack rail lip: `Y = 42.85 .. 52.60 mm` (`9.75 mm`).
    - Open 3U module cavity: **`Y = 52.60 .. 161.10 mm` (`108.50 mm` exact Doepfer clear span)**.
    - North Eurorack rail lip: `Y = 161.10 .. 171.35 mm`.
  - **`Y = 171.60 .. 185.60 mm` (`14.00 mm` North Rim, inner North wall face at `Y = 182.00 mm`):**
    - Gives **`20.90 mm` clear North bay (`Y = 161.10 .. 182.00 mm`)** completely north of Beads' inset rear PCB so all `4× Neutrik NMJ4HCD2` bodies (`20.2 mm` deep) sit 100% clear of Beads' `25 mm`-deep board!
- **`Z` Axis (Vertical Height = `45.00 mm`):**
  - **`Z = 0.00 mm`:** Flush top surface of BOTH `faceplate_14hp` and Mutable Instruments Beads!
  - **`Z = -1.60 mm`:** Left `14 HP` rail shelf (`compensates for 1.60 mm FR4 faceplate`).
  - **`Z = -2.00 mm`:** Right `14 HP` rail shelf (`compensates for 2.00 mm Beads anodized aluminum faceplate`).
  - **`Z = -12.00 mm`:** Top deck of the Stepped-Down Front Stomp Apron (`12 mm` below patch cables).
  - **`Z = -27.00 mm`:** Bottom of Beads' `25.0 mm` PCB (`11.40 mm` clear beneath it down to `Z = -38.40 mm` for the `2×5` Eurorack IDC ribbon plug!).
  - **`Z = -38.40 mm`:** `F.Cu` top surface of `main_board` (`Z = -38.40 .. -40.00 mm`, supported above `Z = -42.00 mm` inner lid face).
  - **`Z = -45.00 mm`:** Flat outer bottom face of enclosure + flush bottom lid.

---

## 3. Exact `8×` Doepfer M3 Brass Heat-Set Insert Coordinates (`M3 × L4.0 × OD4.6 mm`)
- Printed insert pocket: **`Ø4.15 mm` × `6.5 mm` deep** with `0.6 mm × 45°` entry chamfer in `>= Ø8.5 mm` rail bosses:
  1. Left Panel Bottom-Left: **`(12.50, 45.85, Z = -1.60)`**
  2. Left Panel Bottom-Right: **`(68.38, 45.85, Z = -1.60)`**
  3. Left Panel Top-Left: **`(12.50, 168.35, Z = -1.60)`**
  4. Left Panel Top-Right: **`(68.38, 168.35, Z = -1.60)`**
  5. Beads Bottom-Left: **`(83.70, 45.85, Z = -2.00)`**
  6. Beads Bottom-Right: **`(139.58, 45.85, Z = -2.00)`**
  7. Beads Top-Left: **`(83.70, 168.35, Z = -2.00)`**
  8. Beads Top-Right: **`(139.58, 168.35, Z = -2.00)`**

---

## 4. North Wall Connector Bores (`Y_OUTER = 185.60 mm`, Derived from `Z_FCU = -38.40 mm`)
1. **`4×` Neutrik `NMJ4HCD2` (`OUT R`, `OUT L/M`, `IN R`, `IN L/M` at `X = 18, 38, 58, 78 mm`):**
   - Centerline `Z = -38.40 + 8.14 = -30.26 mm`, bore `Ø11.50 mm` + exterior `Ø16.50 mm` spotface (`wall = 2.50 mm`) for full chrome ferrule nut thread engagement.
2. **`2×` Same Sky `SJ1-3523N` `3.5 mm` TRS (`MIDI THRU` at `X = 96 mm`, `MIDI IN` at `X = 114 mm`):**
   - Centerline `Z = -38.40 + 2.50 = -35.90 mm`, bore `Ø6.40 mm` (include `0.7 mm` PCB/ledge relief for `SJ1-3523N` front `-0.50 mm` collar step).
3. **`1×` C&K `JS202011AQN` Right-Angle DPDT Switch (`MIDI TYPE A / B` at `X = 105 mm`):**
   - Recessed actuator window (`5.2 × 2.8 mm`) with debossed **`A ◄ ► B`** lettering on the North wall.
4. **`1×` `TYPE-C-31-M-12` `USB-C` (`X = 127 mm`):**
   - Oval bore (`9.40 × 3.60 mm`) at `Z = -38.40 + 1.60 = -36.80 mm` with exterior `13.0 × 7.5 × 1.6 mm` overmold relief pocket.
5. **`1×` Insulated Panel-Mount `2.1 × 5.5 mm` DC Barrel Jack (`X = 141 mm`, `Z = -28.00 mm`):**
   - Sized to exact datasheet D-bore + `360°` internal hex nut corner sweep (`SW / cos 30°`) clear of `main_board`.

---

## 5. Mandatory Automated 3D B-Rep Verification (`cad/verify_3d_collisions.py`)
Using `build123d` + `OCP` (`BRepAlgoAPI_Common` — never `cadquery` on `OCP 8.0`), assert **`0.000 mm³` pairwise intersection** across all un-grouped solids (`enclosure_shell`, `bottom_lid`, `main_board`, `ui_mezzanine`, `faceplate_14hp`, `beads_module + 2×5 ribbon`, `4× NMJ4HCD2`, `2× SJ1-3523N`, `JS202011AQN`, `USB-C`, panel DC jack + nut, `2×` footswitches + nuts, `12× WQP-PJ398SM`, `SSD1306`, `EC11`, `2×` dual pots, and all `M3` inserts/bolts), plus `>= 8.0 mm` shaft protrusion above `faceplate_14hp`.
