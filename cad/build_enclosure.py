#!/usr/bin/env python3
"""Parametric Build123d 3D Enclosure, Populated Assembly, Studio Renderer & Wiring Diagram
Generator for the Mutable Instruments Beads Pedalboard Skiff & Drift Workstation.

Worktree-portable: resolves repo root dynamically via Path(__file__).resolve().parents[1].
Generates:
  - cad/exports/beads_enclosure_shell.stl & .step  (Print-ready Bambu Lab X2D PETG-HF case)
  - cad/exports/beads_bottom_lid.stl & .step       (Flush 3.0mm bottom service lid)
  - cad/exports/beads_full_assembly.step           (Complete 90+ solid populated assembly)
  - cad/exports/render_iso_front.png               (Studio 3/4 front isometric render)
  - cad/exports/render_north_io.png                (North-wall pedalboard I/O & spotfaces view)
  - cad/exports/render_bottom_interior.png         (Exploded/interior underside stackup view)
  - cad/exports/render_side_cross_section.png      (True Y-Z mechanical cross-section diagram)
  - cad/exports/diagram_wiring_and_assembly.png    (Labeled user hand-solder & wiring guide)
"""
from __future__ import annotations

import json
import math
import pathlib
import sys
from typing import Dict, List, Tuple

import build123d as bd
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import pcbnew

ROOT = pathlib.Path(__file__).resolve().parents[1]
CONTRACT = json.loads((ROOT / "hardware_contract.json").read_text(encoding="utf-8"))
EXPORT_DIR = ROOT / "cad" / "exports"

# Exact locked coordinate frame constants from hardware_contract.json & plan/04
W_CASE, D_CASE, H_CASE = CONTRACT["coordinate_frame"]["enclosure_outer_mm"]  # 152.0, 185.6, 45.0
WALL = CONTRACT["coordinate_frame"]["wall_thickness_mm"]                     # 3.60
Z_MAIN_FCU = CONTRACT["coordinate_frame"]["z_fcu_main_board_mm"]             # -38.40
Z_MAIN_BCU = Z_MAIN_FCU - 1.60                                               # -40.00
Z_MEZZ_FCU = CONTRACT["coordinate_frame"]["z_fcu_ui_mezzanine_mm"]           # -11.60
Z_MEZZ_BCU = Z_MEZZ_FCU - 1.60                                               # -13.20
Z_SHELF_LEFT = CONTRACT["coordinate_frame"]["z_shelf_left_14hp_mm"]          # -1.60
Z_SHELF_RIGHT = CONTRACT["coordinate_frame"]["z_shelf_right_beads_mm"]       # -2.00
Z_APRON = CONTRACT["coordinate_frame"]["z_apron_top_mm"]                     # -12.00
Z_LID_TOP = -42.00
Z_BOTTOM = -45.00

# 8x Doepfer M3 heat-set insert coordinates: (name, x, y, z_top)
DOEPFER_INSERTS: List[Tuple[str, float, float, float]] = [
    ("INS_RAIL_L_BL", 12.50,  45.85, Z_SHELF_LEFT),
    ("INS_RAIL_L_BR", 68.38,  45.85, Z_SHELF_LEFT),
    ("INS_RAIL_L_TL", 12.50, 168.35, Z_SHELF_LEFT),
    ("INS_RAIL_L_TR", 68.38, 168.35, Z_SHELF_LEFT),
    ("INS_RAIL_R_BL", 83.70,  45.85, Z_SHELF_RIGHT),
    ("INS_RAIL_R_BR", 139.58, 45.85, Z_SHELF_RIGHT),
    ("INS_RAIL_R_TL", 83.70, 168.35, Z_SHELF_RIGHT),
    ("INS_RAIL_R_TR", 139.58, 168.35, Z_SHELF_RIGHT),
]

# 4x South apron bottom-lid M3 heat-set insert coordinates (facing -Z at Z = -42.00)
SOUTH_LID_INSERTS: List[Tuple[str, float, float, float]] = [
    ("INS_LID_SW",  12.00, 9.00, Z_LID_TOP),
    ("INS_LID_SCW", 55.00, 9.00, Z_LID_TOP),
    ("INS_LID_SCE", 97.00, 9.00, Z_LID_TOP),
    ("INS_LID_SE", 140.00, 9.00, Z_LID_TOP),
]

# Footswitch & apron LED coordinates (13.5mm center-to-center clears 360-deg M12 nut corner sweep + LED bezel!)
FS_SPECS = [
    ("FS1", 30.00, 18.50, 32.00),
    ("FS2", 122.00, 18.50, 32.00),
]


def box_xyz(x1: float, x2: float, y1: float, y2: float, z1: float, z2: float) -> bd.Solid:
    return (
        bd.Pos((x1 + x2) / 2.0, (y1 + y2) / 2.0, (z1 + z2) / 2.0)
        * bd.Box(x2 - x1, y2 - y1, z2 - z1)
    ).solids()[0]


def cyl_z(cx: float, cy: float, z1: float, z2: float, dia: float) -> bd.Solid:
    return (
        bd.Pos(cx, cy, (z1 + z2) / 2.0)
        * bd.Cylinder(dia / 2.0, z2 - z1)
    ).solids()[0]


def cone_z(cx: float, cy: float, z1: float, z2: float, r_bot: float, r_top: float) -> bd.Solid:
    return (
        bd.Pos(cx, cy, (z1 + z2) / 2.0)
        * bd.Cone(r_bot, r_top, z2 - z1)
    ).solids()[0]


def cyl_y(cx: float, zc: float, y1: float, y2: float, dia: float) -> bd.Solid:
    return (
        bd.Pos(cx, (y1 + y2) / 2.0, zc)
        * bd.Rot(90, 0, 0)
        * bd.Cylinder(dia / 2.0, y2 - y1)
    ).solids()[0]


def oval_slot_y(cx: float, zc: float, y1: float, y2: float, w: float, h: float) -> bd.Solid:
    """Horizontal rounded-oval extrusion along Y centered at (cx, zc)."""
    r = h / 2.0
    span = max(0.01, w - h)
    c_mid = box_xyz(cx - span / 2.0, cx + span / 2.0, y1, y2, zc - r, zc + r)
    c_l = cyl_y(cx - span / 2.0, zc, y1, y2, h)
    c_r = cyl_y(cx + span / 2.0, zc, y1, y2, h)
    return (c_mid + c_l + c_r).solids()[0]


def d_bore_y(cx: float, zc: float, y1: float, y2: float, dia: float, flat_span: float) -> bd.Solid:
    """D-bore cutout along Y: circle of diameter `dia` clipped to `flat_span` height at top flat."""
    r = dia / 2.0
    z_top_flat = zc - r + flat_span
    cyl = cyl_y(cx, zc, y1, y2, dia)
    clip = box_xyz(cx - r - 1.0, cx + r + 1.0, y1 - 0.5, y2 + 0.5, zc - r - 1.0, z_top_flat)
    return cyl.intersect(clip).solids()[0]


def build_enclosure_shell(installed_inserts: bool = False) -> bd.Solid:
    """Build the unibody Bambu Lab X2D PETG-HF stepped enclosure.

    If `installed_inserts=False`, cuts exact Ø4.15 x 6.5mm pre-heat-set print pockets
    with 0.6mm x 45 deg entry chamfers per plan/04 §3 (for STL/STEP 3D printing).
    If `installed_inserts=True`, includes the post-heat-set Ø4.64 x 4.05mm brass-insert
    melted seats so the 18x OD4.60mm brass inserts seat with 0.000 mm³ B-Rep overlap.
    """
    # 1. Outer envelope: fillet the 4 vertical corners FIRST, THEN cut the front stepped apron!
    outer = box_xyz(0.0, W_CASE, 0.0, D_CASE, Z_BOTTOM, 0.0)
    v_edges = [e for e in outer.edges() if abs(e.tangent_at(0).Z) > 0.99]
    outer = bd.fillet(v_edges, radius=1.50).solids()[0]
    outer = (outer - box_xyz(-2.0, W_CASE + 2.0, -2.0, 39.0, Z_APRON, 2.0)).solids()[0]

    # 2. Hollow interior cavities + bottom flush lid rabbet
    rabbet = box_xyz(2.20, W_CASE - 2.20, 2.20, D_CASE - 2.20, Z_BOTTOM - 0.5, Z_LID_TOP)
    cav_apron = box_xyz(WALL, W_CASE - WALL, WALL, 43.00, Z_LID_TOP - 0.1, Z_APRON - 4.00)
    cav_main = box_xyz(WALL, W_CASE - WALL, 42.60, D_CASE - WALL, Z_LID_TOP - 0.1, -6.00)
    cav_north = box_xyz(WALL, W_CASE - WALL, 171.35, D_CASE - WALL, Z_LID_TOP - 0.1, -4.00)
    shell = (outer - rabbet - cav_apron - cav_main - cav_north).solids()[0]

    # 3. Top 3U Eurorack stepped panel pockets & 108.50mm Doepfer clear cavities
    #    Left 14HP (faceplate_14hp = 1.60mm FR4 -> Z_shelf = -1.60mm)
    pocket_left = box_xyz(4.80, 76.00, 42.65, 171.55, Z_SHELF_LEFT, 0.50)
    #    Right 14HP (Mutable Instruments Beads = 2.00mm Aluminum -> Z_shelf = -2.00mm)
    pocket_right = box_xyz(76.00, 147.20, 42.65, 171.55, Z_SHELF_RIGHT, 0.50)
    #    Open 108.50mm clear module cavities (preserving sturdy center rail tie-bar X=[74.70, 78.20] below Z=-2.00)
    open_left = box_xyz(5.20, 74.70, 52.60, 161.10, -7.00, 0.50)
    open_right = box_xyz(78.20, 146.80, 52.60, 161.10, -7.00, 0.50)
    #    Trim center tie-bar top down to Z=-2.05mm across Y=[52.60, 161.10] so both panels sit completely clear
    open_seam_top = box_xyz(74.60, 78.30, 52.60, 161.10, -2.10, 0.50)
    shell = (shell - pocket_left - pocket_right - open_left - open_right - open_seam_top).solids()[0]

    # 4. Fuse monolithic structural bosses, stomp load-transfer pillars & PCB standoffs
    additions: List[bd.Solid] = []

    # 4a. Center structural spine along X=[74.70, 78.20], Y=[42.60, 171.35], Z=[-6.50, -2.10]
    additions.append(box_xyz(74.70, 78.20, 42.60, 171.35, -6.50, -2.05))

    # 4b. 8x Doepfer 3U rail M3 heat-set bosses (Ø8.8mm down 7.0mm + 45 deg lower chamfer cone)
    for _, ix, iy, iz in DOEPFER_INSERTS:
        additions.append(cyl_z(ix, iy, iz - 7.00, iz, 8.80))
        additions.append(cone_z(ix, iy, iz - 8.20, iz - 7.00, 3.20, 4.40))

    # 4c. 4x Full-height stepped-apron stomp load-transfer pillars flanking FS1 & FS2 down to Z=-42.00
    for px in (16.50, 43.50, 108.50, 135.50):
        additions.append(cyl_z(px, 18.50, Z_LID_TOP, Z_APRON - 3.50, 7.00))

    # 4d. 4x South apron bottom-lid M3 heat-set columns + South wall tie-webs
    for _, lx, ly, _ in SOUTH_LID_INSERTS:
        additions.append(cyl_z(lx, ly, Z_LID_TOP, Z_APRON - 3.50, 8.60))
        additions.append(box_xyz(lx - 2.50, lx + 2.50, WALL - 0.40, ly, Z_LID_TOP, Z_APRON - 3.50))

    # 4e. 6x main_board upper clamping bosses (bottom face at exact Z_MAIN_FCU = -38.40 mm!)
    mhs = {m["ref"]: (m["x"], m["y"]) for m in CONTRACT["boards"]["main_board"]["mounting_holes_world_mm"]}
    # MH101, MH102, MH103 (Y=41.00 -> fused straight up into the Y=[39.0, 42.6] step riser & South 3U rail!)
    for mref in ("MH101", "MH102", "MH103"):
        mx, my = mhs[mref]
        additions.append(cyl_z(mx, my, Z_MAIN_FCU, -5.50, 8.00))
        additions.append(box_xyz(mx - 2.60, mx + 2.60, 38.60, 43.20, Z_MAIN_FCU, -15.50))
    # MH104 (10.0, 152.0 -> fused to West wall below Z=-15.50, 2.3mm clear below ui_mezzanine B.Cu=-13.20!)
    mx4, my4 = mhs["MH104"]
    additions.append(cyl_z(mx4, my4, Z_MAIN_FCU, -15.50, 8.00))
    additions.append(box_xyz(WALL - 0.40, mx4, my4 - 3.00, my4 + 3.00, Z_MAIN_FCU, -15.50))
    additions.append(cone_z(mx4, my4, -15.50, -13.50, 4.00, 1.00))  # 45-deg top taper into West wall
    # Settle MH104 top cleanly into West wall without touching ui_mezzanine (X>=6.4, Z>=-13.2)
    # Wait: cone_z is below Z=-13.50, which is strictly < Z_MEZZ_BCU (-13.20)!
    # MH105 (76.0, 152.0 -> Ø8.0mm boss below Z=-28.50, connected via X=[74.70, 78.20] spine column up to center spine!)
    mx5, my5 = mhs["MH105"]
    additions.append(cyl_z(mx5, my5, Z_MAIN_FCU, -28.50, 8.00))
    additions.append(box_xyz(74.70, 78.20, my5 - 3.00, 163.50, Z_MAIN_FCU, -5.50))
    # Wait: check J_IN_L (NMJ4HCD2 at cx=75.50, body_south=161.19, tab_south=158.19, Z=[-38.40, -22.20]):
    # Keep MH105 vertical spine at Y <= 157.50 below Z=-21.50, and bridge North to North rail ABOVE Z=-21.50!
    # Let's refine MH105 column so it stays 100% South of Y=157.50 below Z=-21.50!
    additions.pop()  # replace with stepped L-column that clears J_IN_L by >0.7mm!
    additions.append(box_xyz(74.70, 78.20, my5 - 3.00, 157.40, Z_MAIN_FCU, -5.50))
    additions.append(box_xyz(74.70, 78.20, 156.50, 164.00, -21.00, -5.50))

    # MH106 (142.0, 152.0 -> Ø8.0mm boss + East wall web below Z=-28.50, 1.5mm clear below Beads Z=-27.00!)
    mx6, my6 = mhs["MH106"]
    additions.append(cyl_z(mx6, my6, Z_MAIN_FCU, -28.50, 8.00))
    additions.append(box_xyz(mx6, W_CASE - WALL + 0.40, my6 - 3.00, my6 + 3.00, Z_MAIN_FCU, -28.50))

    for a in additions:
        shell = (shell + a).solids()[0]

    # 5. Cut all 18x M3 brass heat-set insert pockets
    cuts: List[bd.Solid] = []

    def cut_insert_top_down(cx: float, cy: float, z_surface: float) -> None:
        # 6.50mm deep Ø4.15mm pilot bore + 0.60mm x 45 deg entry chamfer
        cuts.append(cyl_z(cx, cy, z_surface - 6.50, z_surface + 0.20, 4.15))
        cuts.append(cone_z(cx, cy, z_surface - 0.60, z_surface + 0.05, 2.075, 2.725))
        if installed_inserts:
            cuts.append(cyl_z(cx, cy, z_surface - 4.05, z_surface + 0.10, 4.64))

    def cut_insert_bottom_up(cx: float, cy: float, z_surface: float) -> None:
        # Facing -Z (installed upward from bottom opening)
        cuts.append(cyl_z(cx, cy, z_surface - 0.20, z_surface + 6.50, 4.15))
        cuts.append(cone_z(cx, cy, z_surface - 0.05, z_surface + 0.60, 2.725, 2.075))
        if installed_inserts:
            cuts.append(cyl_z(cx, cy, z_surface - 0.10, z_surface + 4.05, 4.64))

    for _, ix, iy, iz in DOEPFER_INSERTS:
        cut_insert_top_down(ix, iy, iz)
    for _, lx, ly, lz in SOUTH_LID_INSERTS:
        cut_insert_bottom_up(lx, ly, lz)
    for mref in ("MH101", "MH102", "MH103", "MH104", "MH105", "MH106"):
        mx, my = mhs[mref]
        cut_insert_bottom_up(mx, my, Z_MAIN_FCU)

    # 6. Cut Stepped Front Apron Bores (FS1, FS2 Ø12.30mm + Status LEDs Ø5.20mm)
    for _, fx, fy_sw, fy_led in FS_SPECS:
        cuts.append(cyl_z(fx, fy_sw, Z_APRON - 5.00, Z_APRON + 1.00, 12.30))
        cuts.append(cyl_z(fx, fy_led, Z_APRON - 5.00, Z_APRON + 1.00, 5.20))

    # 7. Cut North-Wall Connector Bores & Exterior Spotfaces/Reliefs (Y_inner=182.00, Y_outer=185.60)
    nc = CONTRACT["boards"]["main_board"]["north_wall_connectors_world_mm"]
    # 7a. 4x Neutrik NMJ4HCD2: Ø11.50mm bore + Ø16.50mm exterior spotface leaving 2.50mm wall (Y=184.50..186.50)
    for jref in ("J_OUT_R", "J_OUT_L", "J_IN_R", "J_IN_L"):
        spec = nc[jref]
        cuts.append(cyl_y(spec["x_center"], spec["z_center"], 181.00, 186.50, spec["bore_dia"]))
        cuts.append(cyl_y(spec["x_center"], spec["z_center"], 184.50, 186.50, spec["spotface_dia"]))

    # 7b. 2x Same Sky SJ1-3523N: Ø6.40mm bore + Ø10.40mm x 1.00mm exterior TRS plug-shoulder relief
    for jref in ("J_MIDI_THRU", "J_MIDI_IN"):
        spec = nc[jref]
        cuts.append(cyl_y(spec["x_center"], spec["z_center"], 181.00, 186.50, spec["bore_dia"]))
        cuts.append(cyl_y(spec["x_center"], spec["z_center"], 184.60, 186.50, 10.40))

    # 7c. C&K JS202011AQN DPDT MIDI Type A/B Switch: 5.4x3.0mm window + exterior finger bevel pocket
    sws = nc["SW_MIDI_AB"]
    sw_w, sw_h = sws["window_wh"]
    cuts.append(box_xyz(sws["x_center"] - sw_w / 2.0, sws["x_center"] + sw_w / 2.0,
                        181.00, 186.50,
                        sws["z_center"] - sw_h / 2.0, sws["z_center"] + sw_h / 2.0))
    cuts.append(box_xyz(sws["x_center"] - 4.30, sws["x_center"] + 4.30,
                        183.40, 186.50,
                        sws["z_center"] - 2.50, sws["z_center"] + 2.50))

    # 7d. TYPE-C-31-M-12 USB-C: 9.40x3.60mm rounded oval + 12.40x6.80mm exterior overmold relief (wall=2.0mm)
    usbs = nc["J_USB"]
    uw, uh = usbs["oval_wh"]
    cuts.append(oval_slot_y(usbs["x_center"], usbs["z_center"], 181.00, 186.50, uw, uh))
    cuts.append(oval_slot_y(usbs["x_center"], usbs["z_center"], 184.00, 186.50, 12.40, 6.80))

    # 7e. Tensility 54-00401 Insulated Panel DC Jack: Ø11.10 x 10.00mm D-bore
    dcs = nc["DC_JACK"]
    cuts.append(d_bore_y(dcs["x_center"], dcs["z_center"], 181.00, 186.50,
                         dcs["d_bore_dia"], dcs["d_flat_mm"]))

    for c in cuts:
        shell = (shell - c).solids()[0]

    assert len(shell.solids()) == 1, f"Expected single monolithic enclosure_shell solid, got {len(shell.solids())}"
    return shell


def build_bottom_lid() -> bd.Solid:
    """Build the 3.00mm flush PETG-HF bottom service lid (Z = [-45.00, -42.00]) with:
      - 0.25mm perimeter clearance inside the [2.20, 149.80] x [2.20, 183.40] rabbet
      - 3x integral 2.00mm North spacer collars under MH104..106 (Z = [-42.00, -40.00])
      - 7x countersunk M3 screw bores (4x South + 3x North MH104..106)
      - 4x 0.80mm recessed underside pads for 3M Dual-Lock / rubber feet
    """
    lid = box_xyz(2.45, W_CASE - 2.45, 2.45, D_CASE - 2.45, Z_BOTTOM, Z_LID_TOP)
    v_edges = [e for e in lid.edges() if abs(e.tangent_at(0).Z) > 0.99]
    lid = bd.fillet(v_edges, radius=1.00).solids()[0]

    mhs = {m["ref"]: (m["x"], m["y"]) for m in CONTRACT["boards"]["main_board"]["mounting_holes_world_mm"]}

    # Add 3x integral 2.00mm North standoffs (Z = -42.00 .. -40.02, 0.02mm seat clearance to main_board B.Cu=-40.00)
    for mref in ("MH104", "MH105", "MH106"):
        mx, my = mhs[mref]
        lid = (lid + cyl_z(mx, my, Z_LID_TOP - 0.20, Z_MAIN_BCU - 0.02, 7.20)).solids()[0]

    # Cut 7x countersunk M3 screw holes (Ø3.30mm shank + Ø6.40mm 90-deg countersink at Z=-45.00)
    screw_xy = [(lx, ly) for _, lx, ly, _ in SOUTH_LID_INSERTS] + [mhs[r] for r in ("MH104", "MH105", "MH106")]
    for sx, sy in screw_xy:
        lid = (lid - cyl_z(sx, sy, Z_BOTTOM - 0.50, Z_MAIN_BCU + 0.50, 3.30)).solids()[0]
        lid = (lid - cone_z(sx, sy, Z_BOTTOM - 0.05, Z_BOTTOM + 1.85, 3.35, 1.50)).solids()[0]

    # Cut 4x 0.80mm recessed 3M Dual-Lock / rubber foot pockets on underside (clear of screw holes!)
    for fx1, fx2, fy1, fy2 in [
        (22.0, 46.0, 12.0, 28.0),
        (106.0, 130.0, 12.0, 28.0),
        (22.0, 46.0, 158.0, 174.0),
        (106.0, 130.0, 158.0, 174.0),
    ]:
        lid = (lid - box_xyz(fx1, fx2, fy1, fy2, Z_BOTTOM - 0.20, Z_BOTTOM + 0.80)).solids()[0]

    assert len(lid.solids()) == 1, f"Expected single monolithic bottom_lid solid, got {len(lid.solids())}"
    return lid


def build_populated_solids() -> Dict[str, Tuple[bd.Solid, Tuple[float, float, float]]]:
    """Construct all 90+ individual UN-GROUPED B-Rep solids in exact world coordinates."""
    solids: Dict[str, Tuple[bd.Solid, Tuple[float, float, float]]] = {}

    # Palette (RGB 0..1)
    C_SHELL   = (0.17, 0.19, 0.22)   # Charcoal PETG-HF
    C_LID     = (0.22, 0.24, 0.28)   # Dark Slate PETG-HF
    C_PCB_GRN = (0.08, 0.36, 0.20)   # Solder-mask green FR4
    C_PCB_BLK = (0.10, 0.10, 0.12)   # Matte-black FR4 14HP faceplate
    C_BEADS   = (0.82, 0.83, 0.85)   # Mutable Instruments anodized silver aluminum
    C_BRASS   = (0.82, 0.65, 0.22)   # Brass heat-set inserts
    C_CHROME  = (0.76, 0.79, 0.83)   # Chrome nuts, shafts, metal shells
    C_BLACK   = (0.14, 0.14, 0.16)   # Black nylon connector housings & IC packages
    C_RED     = (0.82, 0.18, 0.18)   # Red LEDs / red-stripe orientation
    C_OLED    = (0.08, 0.45, 0.72)   # OLED glass bezel
    C_RIBBON  = (0.36, 0.38, 0.42)   # 10-pin Eurorack ribbon cable

    # 1. Enclosure Shell (post-heat-set installed state) & Bottom Lid
    solids["enclosure_shell"] = (build_enclosure_shell(installed_inserts=True), C_SHELL)
    solids["bottom_lid"] = (build_bottom_lid(), C_LID)

    # 2. main_board (142.0 x 146.6 x 1.6 mm at X=[5,147], Y=[35,181.6], Z=[-40.0,-38.4])
    mb_solid = box_xyz(5.00, 147.00, 35.00, 181.60, Z_MAIN_BCU, Z_MAIN_FCU)
    for mh in CONTRACT["boards"]["main_board"]["mounting_holes_world_mm"]:
        mb_solid = (mb_solid - cyl_z(mh["x"], mh["y"], Z_MAIN_BCU - 0.5, Z_MAIN_FCU + 0.5, mh["drill_mm"])).solids()[0]
    solids["main_board"] = (mb_solid, C_PCB_GRN)

    # 3. ui_mezzanine (68.0 x 108.0 x 1.6 mm at X=[6.4,74.4], Y=[52.85,160.85], Z=[-13.2,-11.6])
    mz_solid = box_xyz(6.40, 74.40, 52.85, 160.85, Z_MEZZ_BCU, Z_MEZZ_FCU)
    solids["ui_mezzanine"] = (mz_solid, C_PCB_GRN)

    # 4. faceplate_14hp (70.80 x 128.50 x 1.60 mm Matte-Black FR4 at X=[5.0,75.8], Y=[42.85,171.35], Z=[-1.6,0.0])
    fp_solid = box_xyz(5.00, 75.80, 42.85, 171.35, Z_SHELF_LEFT, 0.00)
    ox_fp, oy_fp = CONTRACT["boards"]["faceplate_14hp"]["kicad_origin_world_mm"]
    for mh in CONTRACT["boards"]["faceplate_14hp"]["doepfer_m3_holes_pcb_mm"]:
        fp_solid = (fp_solid - cyl_z(ox_fp + mh["x"], oy_fp - mh["y"], -2.5, 0.5, mh["drill_mm"])).solids()[0]
    feats = CONTRACT["boards"]["ui_mezzanine"]["panel_features_mezz_mm"]
    ox_mz, oy_mz = CONTRACT["boards"]["ui_mezzanine"]["kicad_origin_world_mm"]
    ow = feats["OLED_WINDOW"]
    ow_wx, ow_wy = ox_mz + ow["x"], oy_mz - ow["y"]
    fp_solid = (fp_solid - box_xyz(ow_wx - ow["w"] / 2.0, ow_wx + ow["w"] / 2.0,
                                   ow_wy - ow["h"] / 2.0, ow_wy + ow["h"] / 2.0, -2.5, 0.5)).solids()[0]
    for k, f in feats.items():
        if k == "OLED_WINDOW":
            continue
        fp_solid = (fp_solid - cyl_z(ox_mz + f["x"], oy_mz - f["y"], -2.5, 0.5, f["drill_mm"])).solids()[0]
    solids["faceplate_14hp"] = (fp_solid, C_PCB_BLK)

    # 5. Mutable Instruments Beads (14HP x 3U x 2.0mm Aluminum Panel + 25mm total depth rear module)
    beads_panel = box_xyz(76.20, 147.00, 42.85, 171.35, Z_SHELF_RIGHT, 0.00)
    for _, bx, by, _ in DOEPFER_INSERTS[4:]:
        beads_panel = (beads_panel - cyl_z(bx, by, -3.0, 0.5, 3.20)).solids()[0]
    beads_rear = box_xyz(78.80, 144.40, 54.60, 159.60, -27.00, Z_SHELF_RIGHT)
    beads_mod = (beads_panel + beads_rear).solids()[0]
    # Add representative Beads front-panel knobs (4 large + 3 attenuverters) for visual realism & clearance verification
    for kx, ky, kr, kh in [
        (93.0, 142.0, 6.5, 14.5), (130.0, 142.0, 6.5, 14.5),
        (111.6, 122.0, 8.0, 15.5),
        (93.0, 102.0, 6.5, 14.5), (130.0, 102.0, 6.5, 14.5),
        (92.0, 82.0, 4.2, 11.0), (111.6, 82.0, 4.2, 11.0), (131.2, 82.0, 4.2, 11.0),
    ]:
        beads_mod = (beads_mod + cyl_z(kx, ky, 0.00, kh, kr * 2.0)).solids()[0]
    solids["beads_module"] = (beads_mod, C_BEADS)

    # 6. Shrouded 2x5 Eurorack Power Header (J_EURO_PWR) + 2x5 IDC Ribbon Cable inside Z=[-38.40, -27.00]
    mb_board = pcbnew.LoadBoard(str(ROOT / "hardware/main_board/main_board.kicad_pcb"))
    ox_mb, oy_mb = CONTRACT["boards"]["main_board"]["kicad_origin_world_mm"]
    mb_fps = {fp.GetReference(): fp for fp in mb_board.GetFootprints()}

    jpwr_pads = [(ox_mb + pcbnew.ToMM(p.GetPosition().x), oy_mb - pcbnew.ToMM(p.GetPosition().y))
                 for p in mb_fps["J_EURO_PWR"].Pads()]
    ex_c = (min(x for x, _ in jpwr_pads) + max(x for x, _ in jpwr_pads)) / 2.0
    ey_c = (min(y for _, y in jpwr_pads) + max(y for _, y in jpwr_pads)) / 2.0
    # Shrouded 2x5 box header (8.8mm x 20.3mm x 8.9mm above main_board F.Cu -> Z=[-38.38, -29.50])
    solids["J_EURO_PWR_header"] = (box_xyz(ex_c - 4.40, ex_c + 4.40, ey_c - 10.15, ey_c + 10.15,
                                           Z_MAIN_FCU + 0.02, Z_MAIN_FCU + 8.90), C_BLACK)
    # 2x5 IDC ribbon cable curving cleanly West from J_EURO_PWR into Beads' lower power bay (Z=[-29.30, -27.20])
    ribbon = (
        box_xyz(ex_c - 4.00, ex_c + 4.00, ey_c - 7.00, ey_c + 7.00, Z_MAIN_FCU + 8.95, -27.20)
        + box_xyz(108.00, ex_c + 4.00, ey_c - 6.35, ey_c + 6.35, -28.60, -27.20)
    ).solids()[0]
    solids["eurorack_2x5_ribbon"] = (ribbon, C_RIBBON)

    # 7. North-Wall Connectors (exact datasheet envelopes derived from pcbnew pad coordinates!)
    nc = CONTRACT["boards"]["main_board"]["north_wall_connectors_world_mm"]

    # 7a. 4x Neutrik NMJ4HCD2 + 4x Outer Chrome Ferrule Nuts (ST-NMJ4HCD2: S/SN North, T/TN 12.7mm South, shoulder +16.70mm North of T!)
    for jref in ("J_OUT_R", "J_OUT_L", "J_IN_R", "J_IN_L"):
        pads = {p.GetName(): (ox_mb + pcbnew.ToMM(p.GetPosition().x), oy_mb - pcbnew.ToMM(p.GetPosition().y))
                for p in mb_fps[jref].Pads()}
        cx = (pads["T"][0] + pads["TN"][0]) / 2.0
        yt = pads["T"][1]
        ys = pads["S"][1]
        assert ys > yt + 12.0, f"Expected S pad North (+Y_w) of T pad on {jref}: S={ys}, T={yt}"
        y_sh = yt + 16.70     # 181.80 (4.00mm North of S at 177.80; 0.20mm South of Y_inner=182.00)
        zc = nc[jref]["z_center"]  # -30.26
        body = box_xyz(cx - 9.10, cx + 9.10, yt - 3.91, y_sh, Z_MAIN_FCU + 0.02, Z_MAIN_FCU + 16.20)
        nose = cyl_y(cx, zc, y_sh, y_sh + 5.79, 11.10)
        tab = box_xyz(cx - 4.35, cx + 4.35, yt - 6.83, yt - 3.91, zc - 2.80, zc + 2.80)
        solids[jref] = ((body + nose + tab).solids()[0], C_BLACK)
        # Outer chrome ferrule nut seated in Ø16.50mm spotface (Y=184.55..187.30, OD=15.60mm, ID=11.20mm)
        nut = (cyl_y(cx, zc, 184.55, 187.30, 15.60) - cyl_y(cx, zc, 184.00, 188.00, 11.20)).solids()[0]
        solids[f"{jref}_nut"] = (nut, C_CHROME)

    # 7b. 2x Same Sky SJ1-3523N (including -0.50mm front Ø6.00mm collar step below F.Cu!)
    for jref in ("J_MIDI_THRU", "J_MIDI_IN"):
        fp = mb_fps[jref]
        px = ox_mb + pcbnew.ToMM(fp.GetPosition().x)
        py = oy_mb - pcbnew.ToMM(fp.GetPosition().y)  # Pin 1 (S) at Y_w = 178.30
        zc = nc[jref]["z_center"]                     # -35.90
        # Main housing: py - 7.70 .. py + 3.50 (170.60 .. 181.80), Z = F.Cu+0.02 .. F.Cu+5.00
        sjb = box_xyz(px - 6.00, px + 6.00, py - 7.70, py + 3.50, Z_MAIN_FCU + 0.02, Z_MAIN_FCU + 5.00)
        # Front Ø6.00mm collar: py + 3.50 .. py + 6.50 (181.80 .. 184.80 -> 0.20mm North of PCB North edge 181.60!)
        # Reaches Z = -35.90 - 3.00 = -38.90 (0.50mm below Z_MAIN_FCU!)
        sjc = cyl_y(px, zc, py + 3.50, py + 6.50, 6.00)
        solids[jref] = ((sjb + sjc).solids()[0], C_BLACK)

    # 7c. C&K JS202011AQN Right-Angle DPDT Switch (swept across full 2.0mm TYPE A <-> TYPE B actuator travel!)
    sw_pads = {p.GetName(): (ox_mb + pcbnew.ToMM(p.GetPosition().x), oy_mb - pcbnew.ToMM(p.GetPosition().y))
               for p in mb_fps["SW_MIDI_AB"].Pads()}
    sw_cx, sw_py = sw_pads["2"]
    js_body = box_xyz(sw_cx - 4.50, sw_cx + 4.50, sw_py - 0.35, sw_py + 3.65, Z_MAIN_FCU + 0.02, Z_MAIN_FCU + 3.52)
    # Swept actuator envelope: 1.5mm actuator + 2.0mm travel = 3.5mm X-sweep, protruding 2.0mm North (180.75..182.75)
    js_act = box_xyz(sw_cx - 1.75, sw_cx + 1.75, sw_py + 3.65, sw_py + 5.65,
                     Z_MAIN_FCU + 1.00, Z_MAIN_FCU + 2.50)
    solids["SW_MIDI_AB"] = ((js_body + js_act).solids()[0], C_BLACK)

    # 7d. TYPE-C-31-M-12 USB-C Receptacle
    upx = ox_mb + pcbnew.ToMM(mb_fps["J_USB"].GetPosition().x)
    upy = oy_mb - pcbnew.ToMM(mb_fps["J_USB"].GetPosition().y)
    # Front oval tongue protrudes slightly into North wall oval bore (Y=174.70..182.40)
    usbc = oval_slot_y(upx, nc["J_USB"]["z_center"], upy - 3.65, upy + 4.05, 8.94, 3.16)
    solids["J_USB"] = (usbc, C_CHROME)

    # 7e. Tensility 54-00401 Insulated Panel DC Jack + 360-deg M11 Hex Nut Sweep (SW=13.0mm -> Ø15.011mm)
    dcx, dcz = nc["DC_JACK"]["x_center"], nc["DC_JACK"]["z_center"]
    dc_flange = cyl_y(dcx, dcz, 185.62, 188.12, 13.50)
    dc_shank = d_bore_y(dcx, dcz, 170.50, 185.62, 10.85, 9.75)
    solids["DC_JACK"] = ((dc_flange + dc_shank).solids()[0], C_BLACK)
    # 1.1mm lock washer (OD=14.0) + 2.5mm M11 hex nut 360-deg corner sweep (13.0 / cos(30) = 15.011mm) inside Y=178.30..181.95
    dc_nut_sweep = (
        cyl_y(dcx, dcz, 178.35, 181.95, 13.00 / math.cos(math.radians(30.0)))
        - cyl_y(dcx, dcz, 178.00, 182.50, 11.05)
    ).solids()[0]
    solids["DC_JACK_nut_sweep"] = (dc_nut_sweep, C_CHROME)

    # 8. Stepped-Apron Footswitches (2x E-Switch FS5700SPMT2B2M1QEH + 360-deg inner/outer nuts + 2x bezel LEDs)
    nut_fs_od = 14.00 / math.cos(math.radians(30.0))  # 16.166 mm 360-deg across-corners sweep!
    for fs_name, fx, fy_sw, fy_led in FS_SPECS:
        # Switch body (13.4 x 12.0 x 13.0mm + 3.5mm lugs) below inner nut (Z=-18.05..-34.55) + M12 bushing + plunger
        fs_body = box_xyz(fx - 6.70, fx + 6.70, fy_sw - 6.00, fy_sw + 6.00, -34.55, -18.05)
        fs_bush = cyl_z(fx, fy_sw, -18.05, Z_APRON + 3.80, 11.90)
        fs_btn = cyl_z(fx, fy_sw, Z_APRON + 3.80, Z_APRON + 9.60, 10.00)
        solids[fs_name] = ((fs_body + fs_bush + fs_btn).solids()[0], C_CHROME)
        # Inner backup hex nut 360-deg corner sweep (Z = -18.02 .. -16.02, against Z=-16.00 apron underside)
        in_nut = (cyl_z(fx, fy_sw, -18.02, -16.02, nut_fs_od) - cyl_z(fx, fy_sw, -18.5, -15.5, 12.05)).solids()[0]
        solids[f"{fs_name}_inner_nut"] = (in_nut, C_CHROME)
        # Outer washer + hex nut (Z = -11.98 .. -8.98, above Z=-12.00 apron deck)
        out_nut = (cyl_z(fx, fy_sw, Z_APRON + 0.02, Z_APRON + 3.02, nut_fs_od)
                   - cyl_z(fx, fy_sw, Z_APRON - 0.5, Z_APRON + 3.5, 12.05)).solids()[0]
        solids[f"{fs_name}_outer_nut"] = (out_nut, C_CHROME)
        # Apron status LED + snap-in bezel
        led_part = (
            cyl_z(fx, fy_led, Z_APRON - 5.50, Z_APRON + 0.02, 4.90)
            + cyl_z(fx, fy_led, Z_APRON + 0.02, Z_APRON + 1.20, 6.20)
            + cyl_z(fx, fy_led, Z_APRON + 1.20, Z_APRON + 2.80, 3.00)
        ).solids()[0]
        solids[f"LED_{fs_name}"] = (led_part, C_RED)

    # 9. UI Mezzanine Populated Controls & Jacks (12x WQP-PJ398SM, SSD1306, EC11, BACK, 2x Dual Pots, PEAK LED)
    for jkey in ["J_SEND_L", "J_SEND_R", "J_RET_L", "J_RET_R"] + [f"J_CV{i}" for i in range(1, 9)]:
        f = feats[jkey]
        jx, jy = ox_mz + f["x"], oy_mz - f["y"]  # Bushing world center
        # WQP-PJ398SM body (9.0 x 10.5 x 9.96mm between Z=-11.58 and Z=-1.62) + M6 bushing through faceplate
        j_body = box_xyz(jx - 4.50, jx + 4.50, jy - 5.98, jy + 4.52, Z_MEZZ_FCU + 0.02, Z_SHELF_LEFT - 0.02)
        j_bush = cyl_z(jx, jy, Z_SHELF_LEFT - 0.02, 1.90, 5.95)
        solids[jkey] = ((j_body + j_bush).solids()[0], C_BLACK)
        # Knurled Thonkiconn front nut above faceplate_14hp (Z = +0.02 .. +1.60, OD=8.0mm, ID=6.05mm)
        j_nut = (cyl_z(jx, jy, 0.02, 1.60, 8.00) - cyl_z(jx, jy, -0.2, 2.0, 6.05)).solids()[0]
        solids[f"{jkey}_nut"] = (j_nut, C_CHROME)

    # 9b. 0.96" SSD1306 OLED Module + Low-Profile 1x4 Socket (Samtec SLW-104-01-G-S, 6.09mm mated stack)
    mz_board = pcbnew.LoadBoard(str(ROOT / "hardware/ui_mezzanine/ui_mezzanine.kicad_pcb"))
    mz_fps = {fp.GetReference(): fp for fp in mz_board.GetFootprints()}
    oled_pads = [(ox_mz + pcbnew.ToMM(p.GetPosition().x), oy_mz - pcbnew.ToMM(p.GetPosition().y))
                 for p in mz_fps["J_OLED"].Pads()]
    ocx = (min(x for x, _ in oled_pads) + max(x for x, _ in oled_pads)) / 2.0
    ocy = oled_pads[0][1]
    solids["J_OLED_socket"] = (box_xyz(ocx - 5.20, ocx + 5.20, ocy - 1.27, ocy + 1.27,
                                       Z_MEZZ_FCU + 0.02, Z_MEZZ_FCU + 4.59), C_BLACK)
    # Full 27.3 x 27.8 mm SSD1306 breakout PCB (Z = -5.51 .. -3.91) + 26.7 x 19.2 x 1.45mm OLED glass + header collar
    oled_pcb = box_xyz(ow_wx - 13.65, ow_wx + 13.65, ocy - 25.80, ocy + 2.00,
                       Z_MEZZ_FCU + 6.09, Z_MEZZ_FCU + 7.69)
    oled_glass = box_xyz(ow_wx - 12.80, ow_wx + 12.80, ow_wy - 7.30, ow_wy + 7.30,
                         Z_MEZZ_FCU + 7.69, Z_MEZZ_FCU + 9.14)
    oled_hdr = box_xyz(ocx - 5.08, ocx + 5.08, ocy - 1.25, ocy + 1.25,
                       Z_MEZZ_FCU + 4.62, Z_MEZZ_FCU + 6.09)
    solids["SSD1306_oled"] = ((oled_pcb + oled_glass + oled_hdr).solids()[0], C_OLED)

    # 9c. Alps EC11E15244G1 Rotary Encoder (H=20.0mm above ui_mezzanine F.Cu -> shaft top Z = +8.40 mm >= +8.00 mm!)
    ex, ey = ox_mz + feats["SW_ENC"]["x"], oy_mz - feats["SW_ENC"]["y"]
    ec_solid = (
        box_xyz(ex - 6.00, ex + 6.00, ey - 5.80, ey + 5.80, Z_MEZZ_FCU + 0.02, Z_MEZZ_FCU + 6.50)
        + cyl_z(ex, ey, Z_MEZZ_FCU + 6.50, Z_MEZZ_FCU + 13.50, 6.80)
        + cyl_z(ex, ey, Z_MEZZ_FCU + 13.50, Z_MEZZ_FCU + 20.00, 6.00)
    ).solids()[0]
    solids["SW_ENC"] = (ec_solid, C_CHROME)
    solids["SW_ENC_nut"] = ((cyl_z(ex, ey, 0.02, 1.80, 10.00) - cyl_z(ex, ey, -0.2, 2.2, 6.95)).solids()[0], C_CHROME)

    # 9d. 2x Dual-Gang 9mm Pots (RV_IN_TRIM, RV_OUT_TRIM -> shaft top Z = +8.40 mm >= +8.00 mm!)
    for pkey in ("RV_IN_TRIM", "RV_OUT_TRIM"):
        px, py = ox_mz + feats[pkey]["x"], oy_mz - feats[pkey]["y"]
        pot_solid = (
            box_xyz(px - 6.50, px + 4.80, py - 4.75, py + 4.75, Z_MEZZ_FCU + 0.02, Z_SHELF_LEFT - 0.02)
            + cyl_z(px, py, Z_SHELF_LEFT - 0.02, 3.40, 6.80)
            + cyl_z(px, py, 3.40, Z_MEZZ_FCU + 20.00, 6.00)
        ).solids()[0]
        solids[pkey] = (pot_solid, C_CHROME)
        solids[f"{pkey}_nut"] = ((cyl_z(px, py, 0.02, 1.80, 10.00) - cyl_z(px, py, -0.2, 2.2, 6.95)).solids()[0], C_CHROME)

    # 9e. Tactile BACK Button (H=13.0mm -> top Z = +1.40mm) & PEAK 3mm LED
    bkx, bky = ox_mz + feats["SW_BACK"]["x"], oy_mz - feats["SW_BACK"]["y"]
    solids["SW_BACK"] = ((
        box_xyz(bkx - 3.00, bkx + 3.00, bky - 3.00, bky + 3.00, Z_MEZZ_FCU + 0.02, Z_MEZZ_FCU + 3.50)
        + cyl_z(bkx, bky, Z_MEZZ_FCU + 3.50, Z_MEZZ_FCU + 13.00, 3.50)
    ).solids()[0], C_BLACK)

    pkx, pky = ox_mz + feats["D_PEAK"]["x"], oy_mz - feats["D_PEAK"]["y"]
    solids["D_PEAK"] = (cyl_z(pkx, pky, Z_MEZZ_FCU + 0.02, 0.80, 2.95), C_RED)

    # 10. Mated 2x8 Board-to-Board Interconnects (real 16-cavity telescoping pin/socket mating!)
    for btb_ref in ("J_BTB_AUDIO_CV", "J_BTB_UI_DIG"):
        pads = [(ox_mb + pcbnew.ToMM(p.GetPosition().x), oy_mb - pcbnew.ToMM(p.GetPosition().y))
                for p in mb_fps[btb_ref].Pads()]
        bx1, bx2 = min(x for x, _ in pads), max(x for x, _ in pads)
        by1, by2 = min(y for _, y in pads), max(y for _, y in pads)
        bcx, bcy = (bx1 + bx2) / 2.0, (by1 + by2) / 2.0
        # Female socket on ui_mezzanine B.Cu (Sullins PPPC082LFBN-RC, 8.51mm tall: Z=[-21.73, -13.22])
        sock = box_xyz(bcx - 2.54, bcx + 2.54, bcy - 10.20, bcy + 10.20, Z_MEZZ_BCU - 8.53, Z_MEZZ_BCU - 0.02)
        for px, py in pads:
            sock = (sock - box_xyz(px - 0.42, px + 0.42, py - 0.42, py + 0.42,
                                   Z_MEZZ_BCU - 8.60, Z_MEZZ_BCU - 1.20)).solids()[0]
        solids[f"{btb_ref}_mz_socket"] = (sock, C_BLACK)
        # Tall board-stacker male header on main_board F.Cu (Samtec DW-08-14, spacer Z=[-38.38, -21.76] + 16 posts to -15.80)
        hdr = box_xyz(bcx - 2.54, bcx + 2.54, bcy - 10.20, bcy + 10.20, Z_MAIN_FCU + 0.02, Z_MEZZ_BCU - 8.56)
        for px, py in pads:
            hdr = (hdr + box_xyz(px - 0.32, px + 0.32, py - 0.32, py + 0.32,
                                 Z_MEZZ_BCU - 8.56, Z_MEZZ_BCU - 2.60)).solids()[0]
        solids[f"{btb_ref}_mb_header"] = (hdr, C_BLACK)

    # 11. Key tall components on main_board (DIP-6 H11L1, 47uF electrolytics, inductors, relays)
    for cref, dia, h in [("C18", 6.3, 7.7), ("C22", 6.3, 7.7)]:
        fp = mb_fps[cref]
        solids[cref] = (cyl_z(ox_mb + pcbnew.ToMM(fp.GetPosition().x),
                              oy_mb - pcbnew.ToMM(fp.GetPosition().y),
                              Z_MAIN_FCU + 0.02, Z_MAIN_FCU + h, dia), C_CHROME)
    for lref in ("L1", "L2", "L3"):
        fp = mb_fps[lref]
        lx, ly = ox_mb + pcbnew.ToMM(fp.GetPosition().x), oy_mb - pcbnew.ToMM(fp.GetPosition().y)
        solids[lref] = (box_xyz(lx - 2.7, lx + 2.7, ly - 2.6, ly + 2.6,
                                Z_MAIN_FCU + 0.02, Z_MAIN_FCU + 3.00), C_BLACK)
    for kref in ("K1", "K2"):
        fp = mb_fps[kref]
        kx, ky = ox_mb + pcbnew.ToMM(fp.GetPosition().x), oy_mb - pcbnew.ToMM(fp.GetPosition().y)
        solids[kref] = (box_xyz(kx - 5.0, kx + 5.0, ky - 3.25, ky + 3.25,
                                Z_MAIN_FCU + 0.02, Z_MAIN_FCU + 5.20), C_BLACK)
    opto_pads = [(ox_mb + pcbnew.ToMM(p.GetPosition().x), oy_mb - pcbnew.ToMM(p.GetPosition().y))
                 for p in mb_fps["U_OPTO"].Pads()]
    opx = (min(x for x, _ in opto_pads) + max(x for x, _ in opto_pads)) / 2.0
    opy = (min(y for _, y in opto_pads) + max(y for _, y in opto_pads)) / 2.0
    solids["U_OPTO_H11L1"] = (box_xyz(opx - 3.30, opx + 3.30, opy - 3.80, opy + 3.80,
                                      Z_MAIN_FCU + 0.02, Z_MAIN_FCU + 7.50), C_BLACK)

    # 12. All 18x M3 Brass Heat-Set Inserts (OD=4.60mm, ID=3.06mm, L=4.00mm) + All 18x M3 Bolts!
    def add_brass_insert(name: str, cx: float, cy: float, z1: float, z2: float) -> None:
        ins = (cyl_z(cx, cy, z1, z2, 4.60) - cyl_z(cx, cy, z1 - 0.5, z2 + 0.5, 3.08)).solids()[0]
        solids[name] = (ins, C_BRASS)

    # 12a. 8x Doepfer 3U Rail Inserts + 8x M3x6mm Knurled Eurorack Bolts ("Knurlies")
    for iname, ix, iy, iz in DOEPFER_INSERTS:
        add_brass_insert(iname, ix, iy, iz - 4.02, iz - 0.02)
        bname = iname.replace("INS_", "BOLT_")
        bolt = (
            cyl_z(ix, iy, 0.02, 3.20, 6.00)            # Knurled thumb/hex head above panel (Z=0)
            + cyl_z(ix, iy, iz - 4.20, 0.02, 2.98)     # M3 shank through panel into insert
        ).solids()[0]
        solids[bname] = (bolt, C_CHROME)

    # 12b. 4x South Apron Lid Inserts + 4x M3x8mm Countersunk Machine Screws
    for iname, lx, ly, lz in SOUTH_LID_INSERTS:
        add_brass_insert(iname, lx, ly, lz + 0.02, lz + 4.02)
        bname = iname.replace("INS_", "BOLT_")
        bolt = (
            cone_z(lx, ly, Z_BOTTOM + 0.02, Z_BOTTOM + 1.65, 2.95, 1.48)
            + cyl_z(lx, ly, Z_BOTTOM + 1.65, lz + 4.20, 2.98)
        ).solids()[0]
        solids[bname] = (bolt, C_CHROME)

    # 12c. 6x main_board Inserts (MH101..106) + 3x M3x5mm Low-Head PCB Screws + 3x M3x10mm North Lid/PCB Screws
    mhs_map = {m["ref"]: (m["x"], m["y"]) for m in CONTRACT["boards"]["main_board"]["mounting_holes_world_mm"]}
    for mref in ("MH101", "MH102", "MH103"):
        mx, my = mhs_map[mref]
        add_brass_insert(f"INS_{mref}", mx, my, Z_MAIN_FCU + 0.02, Z_MAIN_FCU + 4.02)
        # Low-profile M3x5mm screw (1.4mm head at Z=[-41.42, -40.02], clearing Z=-42.00 bottom_lid by 0.58mm!)
        bolt = (
            cyl_z(mx, my, Z_MAIN_BCU - 1.42, Z_MAIN_BCU - 0.02, 5.40)
            + cyl_z(mx, my, Z_MAIN_BCU - 0.02, Z_MAIN_FCU + 3.80, 2.98)
        ).solids()[0]
        solids[f"BOLT_{mref}"] = (bolt, C_CHROME)

    for mref in ("MH104", "MH105", "MH106"):
        mx, my = mhs_map[mref]
        add_brass_insert(f"INS_{mref}", mx, my, Z_MAIN_FCU + 0.02, Z_MAIN_FCU + 4.02)
        # Countersunk M3x10mm screw through bottom_lid + integral collar + MH104..106 into upper insert
        bolt = (
            cone_z(mx, my, Z_BOTTOM + 0.02, Z_BOTTOM + 1.65, 2.95, 1.48)
            + cyl_z(mx, my, Z_BOTTOM + 1.65, Z_MAIN_FCU + 3.80, 2.98)
        ).solids()[0]
        solids[f"BOLT_{mref}"] = (bolt, C_CHROME)

    return solids


# ==============================================================================
# High-Resolution Z-Buffered Phong Studio Mesh Renderer & Technical Diagrams
# ==============================================================================
def load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = (
        ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
         "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"]
        if bold else
        ["/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
         "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"]
    )
    for p in candidates:
        if pathlib.Path(p).exists():
            return ImageFont.truetype(p, size=size)
    return ImageFont.load_default()


def tessellate_scene(
    solids: Dict[str, Tuple[bd.Solid, Tuple[float, float, float]]],
    exclude: set[str] | None = None,
    offsets: Dict[str, Tuple[float, float, float]] | None = None,
    tol: float = 0.25,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Extract world-space triangle vertices (N,3,3), normals (N,3), and base RGB colors (N,3)."""
    exclude = exclude or set()
    offsets = offsets or {}
    tris_list = []
    cols_list = []
    for name, (solid, rgb) in solids.items():
        if name in exclude:
            continue
        verts_v, faces = solid.tessellate(tol)
        if not faces:
            continue
        v = np.array([[p.X, p.Y, p.Z] for p in verts_v], dtype=np.float64)
        if name in offsets:
            v = v + np.array(offsets[name], dtype=np.float64)
        f = np.array(faces, dtype=np.int32)
        t = v[f]  # (M, 3, 3)
        tris_list.append(t)
        cols_list.append(np.tile(np.array(rgb, dtype=np.float64), (len(f), 1)))
    all_tris = np.concatenate(tris_list, axis=0)
    all_cols = np.concatenate(cols_list, axis=0)
    e1 = all_tris[:, 1] - all_tris[:, 0]
    e2 = all_tris[:, 2] - all_tris[:, 0]
    norms = np.cross(e1, e2)
    lens = np.linalg.norm(norms, axis=1, keepdims=True)
    norms = norms / np.maximum(lens, 1e-12)
    return all_tris, norms, all_cols


def render_studio_view(
    solids: Dict[str, Tuple[bd.Solid, Tuple[float, float, float]]],
    out_path: pathlib.Path,
    cam_pos: Tuple[float, float, float],
    look_at: Tuple[float, float, float],
    up_vec: Tuple[float, float, float] = (0.0, 0.0, 1.0),
    fov_deg: float = 34.0,
    title: str = "",
    subtitle: str = "",
    callouts: List[Tuple[Tuple[float, float, float], Tuple[int, int], str]] | None = None,
    exclude: set[str] | None = None,
    offsets: Dict[str, Tuple[float, float, float]] | None = None,
    img_wh: Tuple[int, int] = (1600, 1100),
) -> None:
    """Render a 2x-supersampled TRUE per-pixel Z-buffered Phong studio PNG."""
    ss = 2
    W, H = img_wh[0] * ss, img_wh[1] * ss

    tris, norms, base_cols = tessellate_scene(solids, exclude=exclude, offsets=offsets, tol=0.20)

    cam = np.array(cam_pos, dtype=np.float64)
    tgt = np.array(look_at, dtype=np.float64)
    up = np.array(up_vec, dtype=np.float64)

    fwd = tgt - cam
    fwd /= np.linalg.norm(fwd)
    right = np.cross(fwd, up)
    right /= np.linalg.norm(right)
    true_up = np.cross(right, fwd)

    rel = tris - cam[None, None, :]
    cx = np.einsum("nij,j->ni", rel, right)
    cy = np.einsum("nij,j->ni", rel, true_up)
    cz = np.einsum("nij,j->ni", rel, fwd)

    valid = np.all(cz > 5.0, axis=1)
    tris, norms, base_cols = tris[valid], norms[valid], base_cols[valid]
    cx, cy, cz = cx[valid], cy[valid], cz[valid]

    focal = (H * 0.48) / math.tan(math.radians(fov_deg * 0.5))
    sx = (W * 0.50) + (cx / cz) * focal
    sy = (H * 0.53) - (cy / cz) * focal

    # Studio 3-point Phong lighting
    centroids = tris.mean(axis=1)
    view_dir = cam[None, :] - centroids
    view_dir /= np.maximum(np.linalg.norm(view_dir, axis=1, keepdims=True), 1e-9)
    flip = np.sum(norms * view_dir, axis=1, keepdims=True) < 0
    n_oriented = np.where(flip, -norms, norms)

    l_key = np.array([-0.42, -0.50, 0.76])
    l_key /= np.linalg.norm(l_key)
    l_fill = np.array([0.62, 0.35, 0.70])
    l_fill /= np.linalg.norm(l_fill)
    l_rim = np.array([0.10, 0.85, 0.52])
    l_rim /= np.linalg.norm(l_rim)

    d_key = np.clip(n_oriented @ l_key, 0.0, 1.0)[:, None]
    d_fill = np.clip(n_oriented @ l_fill, 0.0, 1.0)[:, None]
    d_rim = np.clip(n_oriented @ l_rim, 0.0, 1.0)[:, None]

    h_vec = l_key[None, :] + view_dir
    h_vec /= np.maximum(np.linalg.norm(h_vec, axis=1, keepdims=True), 1e-9)
    spec = (np.clip(np.sum(n_oriented * h_vec, axis=1), 0.0, 1.0) ** 28.0)[:, None]

    lit = base_cols * (0.28 + 0.62 * d_key + 0.24 * d_fill + 0.14 * d_rim) + 0.18 * spec
    lit_u8 = np.clip(lit * 255.0, 0, 255).astype(np.uint8)

    # Studio gradient background + true floating-point Z-buffer
    grad = np.linspace(244, 224, H, dtype=np.uint8)[:, None]
    bg = np.repeat(grad, W, axis=1)
    fb = np.stack([bg, np.minimum(bg.astype(np.uint16) + 2, 255).astype(np.uint8),
                   np.minimum(bg.astype(np.uint16) + 6, 255).astype(np.uint8)], axis=-1)
    zbuf = np.full((H, W), np.inf, dtype=np.float64)

    # Exact per-pixel barycentric Z-buffer rasterization
    x0, y0, z0 = sx[:, 0], sy[:, 0], cz[:, 0]
    x1, y1, z1 = sx[:, 1], sy[:, 1], cz[:, 1]
    x2, y2, z2 = sx[:, 2], sy[:, 2], cz[:, 2]
    denom = (y1 - y2) * (x0 - x2) + (x2 - x1) * (y0 - y2)

    xmin_arr = np.maximum(0, np.floor(np.minimum(np.minimum(x0, x1), x2)).astype(np.int32))
    xmax_arr = np.minimum(W - 1, np.ceil(np.maximum(np.maximum(x0, x1), x2)).astype(np.int32))
    ymin_arr = np.maximum(0, np.floor(np.minimum(np.minimum(y0, y1), y2)).astype(np.int32))
    ymax_arr = np.minimum(H - 1, np.ceil(np.maximum(np.maximum(y0, y1), y2)).astype(np.int32))

    for i in range(len(sx)):
        den = denom[i]
        if abs(den) < 1e-6:
            continue
        ix0, ix1 = xmin_arr[i], xmax_arr[i]
        iy0, iy1 = ymin_arr[i], ymax_arr[i]
        if ix0 > ix1 or iy0 > iy1:
            continue
        gx = np.arange(ix0, ix1 + 1, dtype=np.float64)[None, :] + 0.5
        gy = np.arange(iy0, iy1 + 1, dtype=np.float64)[:, None] + 0.5
        inv_d = 1.0 / den
        w0 = ((y1[i] - y2[i]) * (gx - x2[i]) + (x2[i] - x1[i]) * (gy - y2[i])) * inv_d
        w1 = ((y2[i] - y0[i]) * (gx - x2[i]) + (x0[i] - x2[i]) * (gy - y2[i])) * inv_d
        w2 = 1.0 - w0 - w1
        inside = (w0 >= -1e-5) & (w1 >= -1e-5) & (w2 >= -1e-5)
        if not np.any(inside):
            continue
        # Perspective-correct depth 1/z interpolation
        inv_z = w0 / z0[i] + w1 / z1[i] + w2 / z2[i]
        z_pix = 1.0 / np.maximum(inv_z, 1e-9)
        sub_z = zbuf[iy0:iy1 + 1, ix0:ix1 + 1]
        win = inside & (z_pix < sub_z)
        if np.any(win):
            sub_z[win] = z_pix[win]
            fb[iy0:iy1 + 1, ix0:ix1 + 1][win] = lit_u8[i]

    # Subtle screen-space depth-discontinuity edge enhancement for crisp CAD silhouette lines
    dz_x = np.abs(np.diff(np.where(np.isfinite(zbuf), zbuf, 9999.0), axis=1, prepend=9999.0))
    dz_y = np.abs(np.diff(np.where(np.isfinite(zbuf), zbuf, 9999.0), axis=0, prepend=9999.0))
    sil = ((dz_x > 2.8) | (dz_y > 2.8)) & np.isfinite(zbuf)
    fb[sil] = (fb[sil].astype(np.uint16) * 55 // 100).astype(np.uint8)

    img = Image.fromarray(fb, mode="RGB").resize(img_wh, resample=Image.Resampling.LANCZOS)
    draw_f = ImageDraw.Draw(img)

    # Header banner
    f_title = load_font(26, bold=True)
    f_sub = load_font(16, bold=False)
    f_call = load_font(14, bold=True)

    draw_f.rectangle([(0, 0), (img_wh[0], 74)], fill=(20, 24, 31))
    draw_f.text((28, 13), title, fill=(248, 250, 252), font=f_title)
    draw_f.text((28, 46), subtitle, fill=(172, 186, 206), font=f_sub)

    # Project 3D callout anchors
    if callouts:
        for world_pt, label_xy, text in callouts:
            wp = np.array(world_pt, dtype=np.float64) - cam
            px_c = float(wp @ right)
            py_c = float(wp @ true_up)
            pz_c = float(wp @ fwd)
            if pz_c <= 5.0:
                continue
            ax = (img_wh[0] * 0.50) + (px_c / pz_c) * (focal / ss)
            ay = (img_wh[1] * 0.53) - (py_c / pz_c) * (focal / ss)
            lx, ly = label_xy
            draw_f.line([(ax, ay), (lx, ly)], fill=(220, 58, 38), width=2)
            draw_f.ellipse([(ax - 4, ay - 4), (ax + 4, ay + 4)], fill=(220, 58, 38), outline=(255, 255, 255))
            bbox = draw_f.textbbox((lx, ly), text, font=f_call)
            pad = 5
            draw_f.rounded_rectangle(
                [(bbox[0] - pad, bbox[1] - pad), (bbox[2] + pad, bbox[3] + pad)],
                radius=5, fill=(24, 28, 36), outline=(220, 58, 38), width=2,
            )
            draw_f.text((lx, ly), text, fill=(250, 250, 252), font=f_call)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(str(out_path))


def render_cross_section_and_wiring_diagrams(out_dir: pathlib.Path) -> None:
    """Render true mechanical Y-Z cross-section & full labeled user wiring/assembly guide."""
    # 1. True-to-scale Mechanical Y-Z Cross-Section Diagram
    W, H = 1700, 980
    img = Image.new("RGB", (W, H), (248, 250, 252))
    d = ImageDraw.Draw(img)
    f_h1 = load_font(25, bold=True)
    f_h2 = load_font(16, bold=True)
    f_b = load_font(14, bold=False)

    d.rectangle([(0, 0), (W, 74)], fill=(20, 24, 31))
    d.text((28, 13), "BEADS PEDALBOARD SKIFF — TRUE MECHANICAL Y–Z STACKUP CROSS-SECTION", fill=(255, 255, 255), font=f_h1)
    d.text((28, 46), "Scale Z-datum audit: Z=0.0mm Flush 3U Top | -1.6mm FR4 Shelf | -2.0mm Beads Shelf | -11.6mm UI Mezzanine | -12.0mm Stomp Apron | -38.4mm Main Board | -45.0mm Base", fill=(175, 190, 210), font=f_b)

    # Map Y=[0..190] -> px=[130..1530] (scale = 7.2 px/mm), Z=[-46..+22] -> py=[800..200] (scale = 8.5 px/mm)
    def yz(y_mm: float, z_mm: float) -> Tuple[float, float]:
        return (130.0 + y_mm * 7.2, 490.0 - z_mm * 8.5)

    def rect_yz(y1: float, y2: float, z1: float, z2: float, fill, outline=(30, 35, 42), width: int = 2) -> None:
        x1, py2 = yz(y1, z1)
        x2, py1 = yz(y2, z2)
        d.rectangle([(x1, py1), (x2, py2)], fill=fill, outline=outline, width=width)

    # Reference Z=0.00mm and Z=-45.00mm datum lines
    d.line([yz(-6, 0.0), yz(194, 0.0)], fill=(37, 99, 235), width=2)
    d.text((yz(187, 1.8)[0] - 110, yz(187, 1.8)[1]), "Z = 0.00 mm (Flush 3U Plane)", fill=(37, 99, 235), font=f_h2)
    d.line([yz(-6, -45.0), yz(194, -45.0)], fill=(100, 116, 139), width=2)
    d.text((yz(187, -45.0)[0] - 110, yz(187, -45.0)[1] + 6), "Z = -45.00 mm (Pedalboard Floor)", fill=(71, 85, 105), font=f_h2)

    # PETG-HF Enclosure cross-section
    c_petg = (55, 65, 81)
    rect_yz(0.0, 3.6, -45.0, -12.0, c_petg)             # South wall
    rect_yz(3.6, 39.0, -16.0, -12.0, c_petg)            # Stepped stomp apron deck
    rect_yz(17.5, 24.5, -42.0, -16.0, (75, 85, 99))     # Stomp load-transfer pillar
    rect_yz(39.0, 42.85, -16.0, 0.0, c_petg)            # 12mm step riser wall
    rect_yz(42.85, 52.60, -6.0, -1.6, c_petg)           # South 3U rail lip + M3 boss
    rect_yz(161.10, 171.35, -6.0, -1.6, c_petg)         # North 3U rail lip + M3 boss
    rect_yz(171.35, 182.00, -4.0, 0.0, c_petg)          # 14mm North bezel roof
    rect_yz(182.00, 185.60, -45.0, 0.0, c_petg)         # North I/O wall
    # North NMJ4HCD2 bore + spotface
    rect_yz(182.00, 185.60, -36.01, -24.51, (248, 250, 252), outline=(248, 250, 252), width=1)
    rect_yz(184.50, 185.60, -38.51, -22.01, (248, 250, 252), outline=(248, 250, 252), width=1)

    # Flush 3.0mm Bottom Service Lid
    rect_yz(2.45, 183.15, -45.0, -42.0, (90, 102, 118))

    # main_board (Y=[35.0, 181.6], Z=[-40.0, -38.4])
    rect_yz(35.0, 181.6, -40.0, -38.4, (22, 128, 61))
    # Neutrik NMJ4HCD2 at North edge (Y=[161.19, 181.80], Z=[-38.4, -22.2] + ferrule nose to 187.59)
    rect_yz(161.19, 181.80, -38.4, -22.2, (38, 38, 42))
    rect_yz(181.80, 187.59, -35.81, -24.71, (180, 188, 198))
    # Shrouded 2x5 Eurorack Header + Ribbon (Y=[70, 90], Z=[-38.4, -27.2])
    rect_yz(72.6, 86.6, -38.4, -29.5, (40, 40, 46))
    rect_yz(74.0, 105.0, -28.8, -27.2, (220, 50, 50))
    # 2x8 Tall BTB Stacker + Socket (Y=[80, 100], Z=[-38.4, -13.2])
    rect_yz(80.0, 100.0, -38.4, -21.7, (50, 50, 58))
    rect_yz(80.0, 100.0, -21.7, -13.2, (30, 30, 36))

    # ui_mezzanine (Y=[52.85, 160.85], Z=[-13.2, -11.6]) + Thonkiconn + Pots/Encoder (+8.4mm shaft!)
    rect_yz(52.85, 160.85, -13.2, -11.6, (22, 128, 61))
    rect_yz(62.0, 72.5, -11.6, -1.6, (45, 45, 52))
    rect_yz(64.0, 70.0, -1.6, 1.9, (190, 196, 204))
    # Encoder/Dual Pot with >=8.40mm shaft protrusion!
    rect_yz(115.0, 124.5, -11.6, -1.6, (70, 75, 85))
    rect_yz(116.8, 122.8, -1.6, 8.4, (196, 202, 210))
    # SSD1306 OLED behind milled window
    rect_yz(131.0, 158.0, -5.5, -2.4, (14, 116, 178))

    # faceplate_14hp (Z=[-1.6, 0.0]) & Beads rear PCB dashed outline (Y=[54.6, 159.6], Z=[-27.0, -2.0])
    rect_yz(42.85, 171.35, -1.6, 0.0, (24, 24, 28))
    bx1, by2 = yz(54.6, -27.0)
    bx2, by1 = yz(159.6, -2.0)
    d.rectangle([(bx1, by1), (bx2, by2)], outline=(180, 83, 9), width=3)

    # Footswitch FS1 on Stepped Apron (Y=21.0, Z_apron=-12.0)
    rect_yz(15.0, 27.0, -34.5, -16.0, (148, 163, 184))
    rect_yz(16.0, 26.0, -12.0, -2.4, (203, 213, 225))

    # Clear callout annotations
    notes = [
        ((21.0, -5.0), (150, 240), "FS1 / FS2 Soft-Touch Momentary\nZ=-12mm Stepped Apron + Load Pillars"),
        ((67.0, 1.0), (490, 130), "12x Thonkiconn + Faceplate (Z=0.0mm)\n-1.6mm Left Shelf / -2.0mm Beads Shelf"),
        ((120.0, 8.4), (860, 125), "EC11 & Dual-Gang Pots: +8.40 mm\nShaft Protrusion (>= 8.0 mm Spec!)"),
        ((145.0, -3.5), (1180, 195), "0.96\" SSD1306 OLED on SLW-104\nLow-Profile Socket Behind Window"),
        ((172.0, -30.26), (1250, 825), "4x Neutrik NMJ4HCD2 (Y=161.19..181.80)\n100% North of Beads Rear PCB (Y<=159.6)!"),
        ((82.0, -28.0), (620, 835), "11.4mm Clear Ribbon Bay Under Beads\n(Z=-27.0..-38.4mm) RED STRIPE = -12V"),
        ((90.0, -26.0), (240, 835), "2x8 Board-to-Board Stackers\n0.000 mm XY Congruence, 25.2mm Span"),
    ]
    for (wy, wz), (lx, ly), txt in notes:
        ax, ay = yz(wy, wz)
        d.line([(ax, ay), (lx, ly)], fill=(220, 38, 38), width=2)
        d.ellipse([(ax - 4, ay - 4), (ax + 4, ay + 4)], fill=(220, 38, 38))
        bb = d.textbbox((lx, ly), txt, font=f_b)
        d.rounded_rectangle([(bb[0] - 7, bb[1] - 5), (bb[2] + 7, bb[3] + 5)],
                            radius=5, fill=(255, 255, 255), outline=(220, 38, 38), width=2)
        d.text((lx, ly), txt, fill=(15, 23, 42), font=f_b)

    out_dir.mkdir(parents=True, exist_ok=True)
    img.save(str(out_dir / "render_side_cross_section.png"))

    # 2. Labeled Top-Down Installation, Off-Board Wiring & Polarity Diagram
    W2, H2 = 1700, 1180
    img2 = Image.new("RGB", (W2, H2), (248, 250, 252))
    d2 = ImageDraw.Draw(img2)
    d2.rectangle([(0, 0), (W2, 76)], fill=(20, 24, 31))
    d2.text((28, 13), "BEADS PEDALBOARD SKIFF — INSTALLATION, POLARITY & OFF-BOARD WIRING GUIDE", fill=(255, 255, 255), font=f_h1)
    d2.text((28, 47), "Zero Flying Audio Wires! Only 5 short 2-pin panel jumpers + 10-pin RED-STRIPE Eurorack power ribbon + 2x8 BTB headers.", fill=(175, 190, 210), font=f_b)

    # Top-down scale map: X=[0..152] -> [120..880] (scale=5.0 px/mm), Y=[0..185.6] -> [1060..132] (scale=5.0 px/mm)
    def xy(x_mm: float, y_mm: float) -> Tuple[float, float]:
        return (120.0 + x_mm * 5.0, 1060.0 - y_mm * 5.0)

    def box_2d(x1: float, x2: float, y1: float, y2: float, fill, outline=(30, 41, 59), w: int = 2, label: str = "") -> None:
        px1, py2 = xy(x1, y1)
        px2, py1 = xy(x2, y2)
        d2.rectangle([(px1, py1), (px2, py2)], fill=fill, outline=outline, width=w)
        if label:
            d2.text((px1 + 8, py1 + 8), label, fill=(15, 23, 42), font=f_h2)

    # Enclosure outline, Stepped Apron, Main Board, Left Mezzanine, Right Beads Bay
    box_2d(0.0, 152.0, 0.0, 185.6, (226, 232, 240), outline=(30, 41, 59), w=3)
    box_2d(3.6, 148.4, 3.6, 39.0, (203, 213, 225))
    d2.text((xy(46.0, 9.5)[0], xy(46.0, 9.5)[1]), "STEPPED STOMP APRON (Z = -12.0 mm)", fill=(15, 23, 42), font=f_b)
    box_2d(5.0, 147.0, 35.0, 181.6, (209, 250, 229), outline=(5, 150, 105), w=2, label="main_board (142 x 146.6 mm, Z = -38.4 mm)")
    box_2d(5.0, 75.8, 42.85, 171.35, (224, 242, 254), outline=(2, 132, 199), w=2)
    d2.text((xy(7.5, 168.0)[0], xy(7.5, 168.0)[1]), "LEFT 14 HP:\nfaceplate_14hp + ui_mezzanine", fill=(15, 23, 42), font=f_h2)
    box_2d(76.2, 147.0, 42.85, 171.35, (241, 245, 249), outline=(100, 116, 139), w=2)
    d2.text((xy(78.5, 168.0)[0], xy(78.5, 168.0)[1]), "RIGHT 14 HP:\nMutable Instruments Beads", fill=(15, 23, 42), font=f_h2)

    # North wall connectors
    n_labels = [
        (15.5, "OUT R"), (35.5, "OUT L/M"), (55.5, "IN R"), (75.5, "IN L/M"),
        (93.0, "THRU"), (105.0, "A|B"), (117.0, "IN"), (129.5, "USB-C"), (140.4, "DC"),
    ]
    for nx, nl in n_labels:
        px, py = xy(nx, 183.8)
        d2.ellipse([(px - 9, py - 9), (px + 9, py + 9)], fill=(30, 41, 59))
        d2.text((px - 16, py - 30), nl, fill=(15, 23, 42), font=f_b)

    # Wiring callouts inside diagram:
    # 1. DC Jack (140.4, 183.8) -> J_PWR_IN (141.5, 167.6)
    p_dc = xy(140.4, 180.0)
    p_jpwr = xy(141.5, 167.6)
    d2.line([p_dc, p_jpwr], fill=(220, 38, 38), width=4)
    d2.ellipse([p_jpwr[0] - 6, p_jpwr[1] - 6, p_jpwr[0] + 6, p_jpwr[1] + 6], fill=(220, 38, 38))

    # 2. J_EURO_PWR (132.3, 75.0) -> Beads 2x5 Power Header
    p_euro = xy(132.3, 75.0)
    p_beads_pwr = xy(105.0, 75.0)
    d2.rectangle([p_euro[0] - 16, p_euro[1] - 32, p_euro[0] + 16, p_euro[1] + 32], fill=(30, 41, 59))
    d2.line([(p_euro[0] - 18, p_euro[1] - 28), (p_euro[0] + 18, p_euro[1] - 28)], fill=(220, 38, 38), width=5)
    d2.line([p_euro, p_beads_pwr], fill=(220, 38, 38), width=5)
    d2.text((p_beads_pwr[0] - 75, p_beads_pwr[1] + 12), "2x5 IDC Ribbon\nRED STRIPE = -12V (Pins 1-2!)", fill=(185, 28, 28), font=f_h2)

    # 3. 2x8 BTB Headers (staggered vertical label offsets so zero overlap!)
    for bx, lbl, dy_lbl in [(29.65, "J_BTB_AUDIO_CV", 44), (52.65, "J_BTB_UI_DIG", 64)]:
        pb = xy(bx, 89.96)
        d2.rectangle([pb[0] - 12, pb[1] - 38, pb[0] + 12, pb[1] + 38], fill=(30, 64, 175))
        d2.text((pb[0] - 48, pb[1] + dy_lbl), lbl, fill=(30, 64, 175), font=f_b)

    # 4. Stepped Apron FS1/FS2 & LEDs -> J_FS1/2 & J_LED_FS1/2
    for fx, jx_fs, jx_led, name in [(30.0, 30.3, 42.3, "FS1 (BYPASS)"), (122.0, 120.3, 132.3, "FS2 (FREEZE/TAP)")]:
        pfs = xy(fx, 18.5)
        pled = xy(fx, 32.0)
        pjfs = xy(jx_fs, 41.6)
        pjled = xy(jx_led, 41.6)
        d2.ellipse([pfs[0] - 18, pfs[1] - 18, pfs[0] + 18, pfs[1] + 18], fill=(71, 85, 105), outline=(15, 23, 42), width=2)
        d2.ellipse([pled[0] - 8, pled[1] - 8, pled[0] + 8, pled[1] + 8], fill=(220, 38, 38))
        d2.line([pfs, pjfs], fill=(37, 99, 235), width=3)
        d2.line([pled, pjled], fill=(220, 38, 38), width=3)
        d2.text((pfs[0] - 45, pfs[1] + 22), name, fill=(15, 23, 42), font=f_h2)

    # Right-hand Legend & Safety Checklist Panel
    rx1, rx2 = 930, 1665
    d2.rounded_rectangle([(rx1, 115), (rx2, 1125)], radius=12, fill=(255, 255, 255), outline=(148, 163, 184), width=2)
    checklist = [
        ("1. CENTER-NEGATIVE 9-18V DC INPUT (CRITICAL!)", (185, 28, 28), [
            "• Panel DC Jack: Tensility 54-00401 (Insulated LCP, M11x1 D-bore).",
            "• OUTER SLEEVE (+9V..+18V)  -->  J_PWR_IN Pin 1 (+V_SLEEVE).",
            "• CENTER PIN (0V GND)       -->  J_PWR_IN Pin 2 (GND_CENTER).",
            "• Protected on-board by 1.1A 33V PTC + SMBJ20CA + AO3401A RPP.",
        ]),
        ("2. EURORACK 2x5 POWER HEADER (J_EURO_PWR)", (185, 28, 28), [
            "• Pins 1 & 2 (NORTH / SILKSCREEN BAR) = -12.0V EUR (RED STRIPE!).",
            "• Pins 3..8 = GND   |   Pins 9 & 10 (SOUTH) = +12.0V EUR.",
            "• Verify RED STRIPE matches -12V marking on Mutable Instruments Beads!",
        ]),
        ("3. REVERSIBLE 0.96\" SSD1306 OLED JUMPER (JP_OLED_PWR)", (2, 132, 199), [
            "• Check your 4-pin OLED pin order BEFORE plugging into J_OLED:",
            "  - Mode A (GND-VCC-SCL-SDA): bridge 1-2 & 4-5 on JP_OLED_PWR.",
            "  - Mode B (VCC-GND-SCL-SDA): bridge 2-3 & 5-6 on JP_OLED_PWR.",
            "• Mount on Samtec SLW-104-01-G-S (4.57mm low-profile female socket).",
        ]),
        ("4. STEPPED APRON FOOTSWITCH & LED HEADERS", (30, 64, 175), [
            "• FS1 (Left, X=30mm): E-Switch FS5700SPMT2B2M1QEH lugs 1 & 2 -> J_FS1.",
            "• FS2 (Right, X=122mm): E-Switch FS5700SPMT2B2M1QEH lugs 1 & 2 -> J_FS2.",
            "• Apron 3mm LEDs: Pin 1 = Anode (+3V3), Pin 2 = Cathode -> J_LED_FS1/2.",
        ]),
        ("5. 18x M3 BRASS HEAT-SET INSERTS (M3 x L4.0 x OD4.6 mm @ 240°C)", (15, 23, 42), [
            "• 8x Top 3U Eurorack rail bosses (4x Left @ Z=-1.6mm, 4x Right @ Z=-2.0mm).",
            "• 6x Internal main_board bosses MH101..MH106 (at Z=-38.40mm).",
            "• 4x South apron bottom-lid bosses (at Z=-42.00mm).",
            "• Fasten faceplate & Beads with 8x M3x6mm Knurlies (dead-flush at Z=0!).",
        ]),
        ("6. HEADERLESS USB-C UF2 FIRMWARE FLASHING", (5, 150, 105), [
            "• Fresh RP2040 mounts automatically as RPI-RP2 over USB-C (<1 uA isolated).",
            "• Drag-and-drop firmware/build/beads_bridge.uf2 — zero SWD pins needed!",
            "• Future updates: OLED Menu -> SYSTEM -> USB FIRMWARE UPDATE (or 1200bps).",
        ]),
    ]
    cy_txt = 138
    for hdr, col, lines in checklist:
        d2.text((rx1 + 22, cy_txt), hdr, fill=col, font=f_h2)
        cy_txt += 28
        for ln in lines:
            d2.text((rx1 + 30, cy_txt), ln, fill=(30, 41, 59), font=f_b)
            cy_txt += 23
        cy_txt += 16

    img2.save(str(out_dir / "diagram_wiring_and_assembly.png"))


def main() -> int:
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)

    print("[1/4] Building print-ready Bambu Lab X2D PETG-HF enclosure_shell & bottom_lid...")
    raw_shell = build_enclosure_shell(installed_inserts=False)
    lid = build_bottom_lid()

    bd.export_stl(raw_shell, str(EXPORT_DIR / "beads_enclosure_shell.stl"))
    bd.export_step(raw_shell, str(EXPORT_DIR / "beads_enclosure_shell.step"))
    bd.export_stl(lid, str(EXPORT_DIR / "beads_bottom_lid.stl"))
    bd.export_step(lid, str(EXPORT_DIR / "beads_bottom_lid.step"))
    print(f"      Exported STLs & STEPs -> {EXPORT_DIR}")

    print("[2/4] Building full 90+ solid populated assembly STEP...")
    solids = build_populated_solids()
    assy = bd.Compound(children=[s for s, _ in solids.values()])
    bd.export_step(assy, str(EXPORT_DIR / "beads_full_assembly.step"))
    print(f"      Exported {len(solids)} un-grouped solids -> beads_full_assembly.step")

    print("[3/4] Rendering multi-angle studio PNG views...")
    # View 1: Hero 3/4 Front-South Isometric Studio Render
    render_studio_view(
        solids,
        EXPORT_DIR / "render_iso_front.png",
        cam_pos=(-135.0, -165.0, 175.0),
        look_at=(76.0, 92.0, -16.0),
        fov_deg=32.0,
        title="BEADS PEDALBOARD SKIFF & DRIFT WORKSTATION — 3/4 FRONT STUDIO VIEW",
        subtitle="Bambu Lab X2D PETG-HF Unibody (152.0 x 185.6 x 45.0 mm) | Left 14HP Drift Bridge + Right 14HP Mutable Instruments Beads",
        callouts=[
            ((30.0, 18.5, -4.0), (85, 860), "FS1: Popless PhotoMOS True Bypass"),
            ((122.0, 18.5, -4.0), (1090, 920), "FS2: Freeze / Seed Tap Tempo (92mm Span)"),
            ((26.4, 143.8, 0.0), (65, 220), "0.96\" SSD1306 OLED + ENC + BACK"),
            ((41.4, 96.2, 1.5), (60, 520), "SEND/RET + 8x +-8V Bezier/MIDI CV Jacks"),
            ((111.6, 122.0, 14.0), (1130, 240), "Mutable Instruments Beads (Flush Z=0.0mm)"),
        ],
    )

    # View 2: North-Wall Pedalboard I/O & Spotfaces Studio View
    render_studio_view(
        solids,
        EXPORT_DIR / "render_north_io.png",
        cam_pos=(76.0, 415.0, 62.0),
        look_at=(76.0, 150.0, -24.0),
        fov_deg=28.0,
        title="NORTH-WALL PEDALBOARD I/O — ALL CABLES EXIT TOP EDGE",
        subtitle="4x Neutrik NMJ4HCD2 1/4\" (Ø16.5mm Spotfaces) | TRS MIDI IN + Type A/B Switch + Hardware THRU | Isolated USB-C | 9-18V DC",
        callouts=[
            ((15.5, 186.5, -30.26), (1150, 860), "OUT R & OUT L/M (Neutrik NMJ4HCD2)"),
            ((75.5, 186.5, -30.26), (760, 920), "IN R (L->R Normalled) & IN L/Mono"),
            ((105.0, 185.6, -36.50), (430, 900), "MIDI THRU | TYPE A<->B | TRS MIDI IN"),
            ((129.5, 185.6, -36.80), (110, 845), "USB-C (MIDI + Headerless UF2, <1uA Iso)"),
            ((140.4, 187.5, -28.00), (65, 620), "9-18V DC Center-Neg (Insulated D-Bore)"),
        ],
    )

    # View 3: Exploded Interior Stackup View (Bottom Lid Dropped + Panels Lifted to Reveal Internal Architecture!)
    exp_offsets: Dict[str, Tuple[float, float, float]] = {"bottom_lid": (0.0, 0.0, -34.0)}
    for k in solids:
        if k.startswith("BOLT_LID") or k in ("BOLT_MH104", "BOLT_MH105", "BOLT_MH106"):
            exp_offsets[k] = (0.0, 0.0, -44.0)
        elif k in ("faceplate_14hp", "beads_module") or k.startswith("BOLT_RAIL") or k.endswith("_nut") and k.startswith(("J_SEND", "J_RET", "J_CV", "SW_ENC", "RV_")):
            exp_offsets[k] = (0.0, 0.0, 38.0)
    render_studio_view(
        solids,
        EXPORT_DIR / "render_bottom_interior.png",
        cam_pos=(-155.0, -150.0, -135.0),
        look_at=(76.0, 95.0, -22.0),
        up_vec=(0.0, 0.0, 1.0),
        fov_deg=36.0,
        offsets=exp_offsets,
        title="EXPLODED UNDERSIDE & INTERNAL MULTI-BOARD ARCHITECTURE",
        subtitle="Flush 3mm Service Lid | 2-Layer main_board (Z=-38.4mm) | 18x M3 Brass Heat-Set Inserts | Stomp Load Pillars | 2x5 Red-Stripe Header",
        callouts=[
            ((76.0, 95.0, -76.0), (960, 915), "Flush 3.0mm PETG-HF Bottom Service Lid"),
            ((76.0, 100.0, -39.2), (90, 560), "main_board (Top-Side JLCPCB SMT + >89% GND)"),
            ((132.3, 75.0, -32.0), (1080, 560), "Shrouded 2x5 Eurorack Header + Ribbon"),
            ((16.5, 21.0, -28.0), (95, 790), "4x Full-Height Stomp Force Pillars"),
        ],
    )

    print("[4/4] Generating mechanical Y-Z cross-section & wiring/installation diagrams...")
    render_cross_section_and_wiring_diagrams(EXPORT_DIR)
    print("[OK] All 3D STLs, STEPs, Studio PNG Renders & Wiring Diagrams generated successfully!")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
