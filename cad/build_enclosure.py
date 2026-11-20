#!/usr/bin/env python3
"""Parametric Build123d 3D Enclosure, Populated Assembly, Studio Renderer & Wiring Diagram
Generator for the Mutable Instruments Beads Pedalboard Skiff & Drift Workstation.

Worktree-portable: resolves repo root dynamically via Path(__file__).resolve().parents[1].
Generates:
  - cad/exports/beads_enclosure_shell.stl & .step  (Print-ready Bambu Lab X2D PETG-HF case)
  - cad/exports/beads_bottom_lid.stl & .step       (Flush 3.0mm bottom service lid)
  - cad/exports/beads_full_assembly.step           (Complete 417-solid populated assembly)
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
    # MH104 (10.0, 142.0 -> fused to West wall below Z=-15.50, 2.3mm clear below ui_mezzanine B.Cu=-13.20!)
    mx4, my4 = mhs["MH104"]
    additions.append(cyl_z(mx4, my4, Z_MAIN_FCU, -15.50, 8.00))
    additions.append(box_xyz(WALL - 0.40, mx4, my4 - 3.00, my4 + 3.00, Z_MAIN_FCU, -15.50))
    additions.append(cone_z(mx4, my4, -15.50, -13.50, 4.00, 1.00))  # 45-deg top taper into West wall

    # MH105 (76.0, 142.0 -> relocated South so J_IN_L rear tab Y>=152.27 during dy=-6.0mm entry clears by >6.2mm!)
    mx5, my5 = mhs["MH105"]
    additions.append(cyl_z(mx5, my5, Z_MAIN_FCU, -28.50, 8.00))
    additions.append(box_xyz(74.70, 78.20, my5 - 3.00, my5 + 3.50, Z_MAIN_FCU, -5.50))

    # MH106 (142.0, 142.0 -> Ø8.0mm boss + East wall web below Z=-28.50, 1.5mm clear below Beads Z=-27.00!)
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

    # 7b. 2x Same Sky SJ1-3523N: Ø6.40mm bore + Ø9.80mm exterior TRS plug-shoulder relief (floor at Y=184.20mm,
    #     0.30mm behind SJ1-3523N's Y=184.50mm front bushing lip after the +0.30mm South NPTH-web shift, leaving 2.20mm wall)
    for jref in ("J_MIDI_THRU", "J_MIDI_IN"):
        spec = nc[jref]
        cuts.append(cyl_y(spec["x_center"], spec["z_center"], 181.00, 186.50, spec["bore_dia"]))
        cuts.append(cyl_y(spec["x_center"], spec["z_center"], spec.get("plug_relief_y_floor", 184.20), 186.50, 9.80))

    # 7c. C&K JS202011AQN DPDT MIDI Type A/B Switch:
    #     - 5.4x3.0mm inner through-window (Z=[-38.00, -35.00], strictly above main_board F.Cu Z=-38.40mm)
    #     - 11.6x6.8mm exterior finger/pick alcove stopping at Y=183.00mm (1.00mm 3-perimeter PETG-HF structural wall rim
    #       from Y_inner=182.00mm, eliminating any thin membrane and concealing main_board FR4!)
    #     - Debossed North-wall 'B ◄ ► A' markings (0.60mm deep at Z=-29.80mm per plan/04 §4.3, matching physical throw:
    #       East/+X/North-view-Left = TYPE B, West/-X/North-view-Right = TYPE A!)
    sws = nc["SW_MIDI_AB"]
    sw_w, sw_h = sws["window_wh"]
    sw_alc_w, sw_alc_h = sws["alcove_wh"]
    sw_alc_y = sws["alcove_y_floor"]  # 183.00 mm (>= 1.00 mm inner wall rim)
    cuts.append(box_xyz(sws["x_center"] - sw_w / 2.0, sws["x_center"] + sw_w / 2.0,
                        181.00, 186.50,
                        sws["z_center"] - sw_h / 2.0, sws["z_center"] + sw_h / 2.0))
    cuts.append(oval_slot_y(sws["x_center"], sws["z_center"], sw_alc_y, 186.50, sw_alc_w, sw_alc_h))

    north_plane = bd.Plane(origin=(sws["x_center"], 184.80, -29.60), x_dir=(-1.0, 0.0, 0.0), z_dir=(0.0, 1.0, 0.0))
    with bd.BuildPart() as bp_deboss:
        with bd.BuildSketch(north_plane):
            with bd.Locations((-4.60, 0.0)):
                bd.Text("B", font_size=4.00, font_style=bd.FontStyle.BOLD)
            with bd.Locations((-1.75, 0.0)):
                bd.Polygon([(-0.85, 0.0), (0.85, 1.25), (0.85, -1.25)])
            with bd.Locations((1.75, 0.0)):
                bd.Polygon([(0.85, 0.0), (-0.85, 1.25), (-0.85, -1.25)])
            with bd.Locations((4.60, 0.0)):
                bd.Text("A", font_size=4.00, font_style=bd.FontStyle.BOLD)
        bd.extrude(amount=1.00)
    cuts.extend(bp_deboss.part.solids())

    # 7d. TYPE-C-31-M-12 USB-C: 9.40x3.60mm rounded oval + plan/04 13.00x7.50mm exterior overmold pocket
    #     Pocket floor at Y=183.20mm sits 0.35mm (<= 0.50mm!) ahead of J_USB's Y=182.85mm lip, with 2.69mm web to DC_JACK!
    usbs = nc["J_USB"]
    uw, uh = usbs["oval_wh"]
    cuts.append(oval_slot_y(usbs["x_center"], usbs["z_center"], 181.00, 186.50, uw, uh))
    cuts.append(oval_slot_y(usbs["x_center"], usbs["z_center"], 183.20, 186.50, 13.00, 7.50))

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
    #    Includes the two 0.70 mm North Edge.Cuts SJ1-3523N collar relief notches (X=x_c+-3.40, Y=[180.90, 181.60])
    #    matching hardware/main_board/main_board.kicad_pcb & plan/04 §4.2!
    mb_solid = box_xyz(5.00, 147.00, 35.00, 181.60, Z_MAIN_BCU, Z_MAIN_FCU)
    for mh in CONTRACT["boards"]["main_board"]["mounting_holes_world_mm"]:
        mb_solid = (mb_solid - cyl_z(mh["x"], mh["y"], Z_MAIN_BCU - 0.5, Z_MAIN_FCU + 0.5, mh["drill_mm"])).solids()[0]
    nc_mb = CONTRACT["boards"]["main_board"]["north_wall_connectors_world_mm"]
    for jref in ("J_MIDI_THRU", "J_MIDI_IN"):
        jxc = nc_mb[jref]["x_center"]
        mb_solid = (mb_solid - box_xyz(jxc - 3.40, jxc + 3.40, 180.90, 181.80, Z_MAIN_BCU - 0.5, Z_MAIN_FCU + 0.5)).solids()[0]
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

    # 6. Shrouded 2x5 Eurorack Power Header (J_EURO_PWR at rot=90 deg, South of Beads PCB!) + Full ~16.2mm Mated IDC Plug & Ribbon
    mb_board = pcbnew.LoadBoard(str(ROOT / "hardware/main_board/main_board.kicad_pcb"))
    ox_mb, oy_mb = CONTRACT["boards"]["main_board"]["kicad_origin_world_mm"]
    mb_fps = {fp.GetReference(): fp for fp in mb_board.GetFootprints()}

    jpwr_pads = [(ox_mb + pcbnew.ToMM(p.GetPosition().x), oy_mb - pcbnew.ToMM(p.GetPosition().y))
                 for p in mb_fps["J_EURO_PWR"].Pads()]
    ex_c = (min(x for x, _ in jpwr_pads) + max(x for x, _ in jpwr_pads)) / 2.0   # 101.00
    ey_c = (min(y for _, y in jpwr_pads) + max(y for _, y in jpwr_pads)) / 2.0   # 48.10
    # Würth 61201021621 shrouded 2x5 box header (20.32 x 8.85 x 9.10mm at rot=90 deg, hollowed inside for mated IDC plug)
    euro_hdr = (
        box_xyz(ex_c - 10.16, ex_c + 10.16, ey_c - 4.425, ey_c + 4.425, Z_MAIN_FCU + 0.02, Z_MAIN_FCU + 9.10)
        - box_xyz(ex_c - 8.85, ex_c + 8.85, ey_c - 3.18, ey_c + 3.18, Z_MAIN_FCU + 2.60, Z_MAIN_FCU + 9.50)
        - box_xyz(ex_c - 2.25, ex_c + 2.25, ey_c - 4.50, ey_c - 3.10, Z_MAIN_FCU + 2.60, Z_MAIN_FCU + 9.50)
    ).solids()[0]
    solids["J_EURO_PWR_header"] = (euro_hdr, C_BLACK)
    # Full unshrunk 2x5 IDC female socket + strain-relief cap (17.27 x 6.00mm, reaching Z = F.Cu + 16.20 = -22.20mm!)
    # + 12.70mm 10-conductor flat ribbon curving North into Beads' power bay (Z = [-32.00, -27.05] under Beads Z=-27.00)
    ribbon = (
        box_xyz(ex_c - 8.635, ex_c + 8.635, ey_c - 3.00, ey_c + 3.00, Z_MAIN_FCU + 2.80, Z_MAIN_FCU + 16.20)
        + box_xyz(ex_c - 2.00, ex_c + 2.00, ey_c - 4.10, ey_c - 2.95, Z_MAIN_FCU + 4.00, Z_MAIN_FCU + 13.50)
        + box_xyz(ex_c - 6.35, ex_c + 6.35, ey_c + 2.90, 54.40, Z_MAIN_FCU + 14.80, Z_MAIN_FCU + 16.20)
        + box_xyz(ex_c - 6.35, ex_c + 6.35, 53.10, 54.40, -32.00, Z_MAIN_FCU + 16.20)
        + box_xyz(ex_c - 6.35, ex_c + 6.35, 53.10, 74.00, -32.00, -30.60)
        + box_xyz(ex_c - 8.635, ex_c + 8.635, 68.00, 74.00, -32.00, -27.05)
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

    # 7b. 2x Same Sky SJ1-3523N (including -0.50mm front Ø6.00mm collar step below F.Cu inside 0.70mm PCB relief notch!)
    for jref in ("J_MIDI_THRU", "J_MIDI_IN"):
        fp = mb_fps[jref]
        px = ox_mb + pcbnew.ToMM(fp.GetPosition().x)
        py = oy_mb - pcbnew.ToMM(fp.GetPosition().y)  # Pin 1 (S) at Y_w = 178.00 (Y_pcb = 3.60 -> 0.50mm NPTH web)
        zc = nc[jref]["z_center"]                     # -35.90
        # Main housing: py - 7.70 .. py + 3.50 (170.30 .. 181.50), Z = F.Cu+0.02 .. F.Cu+5.00
        sjb = box_xyz(px - 6.00, px + 6.00, py - 7.70, py + 3.50, Z_MAIN_FCU + 0.02, Z_MAIN_FCU + 5.00)
        # Front Ø6.00mm collar: py + 3.50 .. py + 6.50 (181.50 .. 184.50, clearing Y=[180.90, 181.60] Edge.Cuts notch!)
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

    # 7d. TYPE-C-31-M-12 USB-C Receptacle (exact 8.94 x 7.30 x 3.16mm stainless shell: Y=[175.55, 182.85])
    upx = ox_mb + pcbnew.ToMM(mb_fps["J_USB"].GetPosition().x)
    upy = oy_mb - pcbnew.ToMM(mb_fps["J_USB"].GetPosition().y)
    usbc = oval_slot_y(upx, nc["J_USB"]["z_center"], upy - 3.65, upy + 3.65, 8.94, 3.16)
    solids["J_USB"] = (usbc, C_CHROME)

    # 7e. Tensility 54-00401 Insulated Panel DC Jack (true 17.60mm datasheet depth: 2.5mm flange + 9.5mm thread + 3.1mm rear + 2.5mm solder lugs)
    dcx, dcz = nc["DC_JACK"]["x_center"], nc["DC_JACK"]["z_center"]
    dc_flange = cyl_y(dcx, dcz, 185.62, 188.12, 13.50)
    dc_shank = d_bore_y(dcx, dcz, 176.12, 185.62, 10.85, 9.75)
    dc_rear = cyl_y(dcx, dcz, 173.02, 176.12, 10.40)
    dc_lug_a = box_xyz(dcx - 1.50, dcx + 1.50, 170.52, 173.05, dcz - 0.50, dcz + 0.50)
    dc_lug_b = box_xyz(dcx - 1.50, dcx + 1.50, 170.52, 173.05, dcz - 4.20, dcz - 3.20)
    solids["DC_JACK"] = ((dc_flange + dc_shank + dc_rear + dc_lug_a + dc_lug_b).solids()[0], C_BLACK)
    # 1.1mm lock washer (OD=14.0) + 2.5mm M11 hex nut 360-deg corner sweep (13.0 / cos(30) = 15.011mm) inside Y=178.35..181.95
    dc_nut_sweep = (
        cyl_y(dcx, dcz, 178.35, 181.95, 13.00 / math.cos(math.radians(30.0)))
        - cyl_y(dcx, dcz, 178.00, 182.50, 11.05)
    ).solids()[0]
    solids["DC_JACK_nut_sweep"] = (dc_nut_sweep, C_CHROME)

    # 7f. All 5x 1x2 (2.54mm) Off-Board Headers (J_PWR_IN, J_FS1, J_FS2, J_LED_FS1, J_LED_FS2) + Full 14.0mm Mated Crimp Housings
    for href in ("J_PWR_IN", "J_FS1", "J_FS2", "J_LED_FS1", "J_LED_FS2"):
        hpads = [(ox_mb + pcbnew.ToMM(p.GetPosition().x), oy_mb - pcbnew.ToMM(p.GetPosition().y))
                 for p in mb_fps[href].Pads()]
        hx1, hx2 = min(x for x, _ in hpads), max(x for x, _ in hpads)
        hy1, hy2 = min(y for _, y in hpads), max(y for _, y in hpads)
        hcx, hcy = (hx1 + hx2) / 2.0, (hy1 + hy2) / 2.0
        span_x = max(2.54, (hx2 - hx1) + 2.54)
        span_y = max(2.54, (hy2 - hy1) + 2.54)
        # Samtec TSW-102-07-F-S male header (2.54mm base + 6.00mm square posts = 8.54mm above F.Cu)
        h_base = box_xyz(hcx - span_x / 2.0, hcx + span_x / 2.0,
                         hcy - span_y / 2.0, hcy + span_y / 2.0,
                         Z_MAIN_FCU + 0.02, Z_MAIN_FCU + 2.56)
        for px, py in hpads:
            h_base = (h_base + box_xyz(px - 0.32, px + 0.32, py - 0.32, py + 0.32,
                                       Z_MAIN_FCU + 2.56, Z_MAIN_FCU + 8.54)).solids()[0]
        solids[f"{href}_header"] = (h_base, C_BLACK)
        # Standard unshrunk 14.00mm 1x2 2.54mm female crimp housing (Z = F.Cu+2.60 .. F.Cu+16.60 = -21.80mm)
        h_plug = box_xyz(hcx - span_x / 2.0, hcx + span_x / 2.0,
                         hcy - span_y / 2.0, hcy + span_y / 2.0,
                         Z_MAIN_FCU + 2.60, Z_MAIN_FCU + 16.60)
        for px, py in hpads:
            h_plug = (h_plug - box_xyz(px - 0.42, px + 0.42, py - 0.42, py + 0.42,
                                       Z_MAIN_FCU + 2.50, Z_MAIN_FCU + 9.20)).solids()[0]
        solids[f"{href}_plug"] = (h_plug, C_RED if href == "J_PWR_IN" else C_RIBBON)

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

    # 9b. 0.96" SSD1306 OLED Module + Low-Profile 5.08mm Board-Stacker Header (Samtec DW-04-07-T-S-200: 8.13mm <= 8.50mm total stack!)
    mz_board = pcbnew.LoadBoard(str(ROOT / "hardware/ui_mezzanine/ui_mezzanine.kicad_pcb"))
    mz_fps = {fp.GetReference(): fp for fp in mz_board.GetFootprints()}
    oled_pads = [(ox_mz + pcbnew.ToMM(p.GetPosition().x), oy_mz - pcbnew.ToMM(p.GetPosition().y))
                 for p in mz_fps["J_OLED"].Pads()]
    ocx = (min(x for x, _ in oled_pads) + max(x for x, _ in oled_pads)) / 2.0
    ocy = oled_pads[0][1]
    solids["J_OLED_socket"] = (box_xyz(ocx - 5.08, ocx + 5.08, ocy - 1.27, ocy + 1.27,
                                       Z_MEZZ_FCU + 0.02, Z_MEZZ_FCU + 5.06), C_BLACK)
    # Full 27.30 x 27.80 x 1.60 mm SSD1306 breakout PCB (Z = -6.52 .. -4.92) + true 26.70 x 19.20 x 1.45 mm OLED glass (Z = -4.92 .. -3.47)
    oled_pcb = box_xyz(ow_wx - 13.65, ow_wx + 13.65, ocy - 25.80, ocy + 2.00,
                       Z_MEZZ_FCU + 5.08, Z_MEZZ_FCU + 6.68)
    oled_glass = box_xyz(ow_wx - 13.35, ow_wx + 13.35, ow_wy - 10.60, ow_wy + 8.60,
                         Z_MEZZ_FCU + 6.68, Z_MEZZ_FCU + 8.13)
    solids["SSD1306_oled"] = ((oled_pcb + oled_glass).solids()[0], C_OLED)

    # 9c. Alps EC11E15244G1 Bushingless Rotary Encoder (15 PPR / 30 detents, H=20.0mm above F.Cu -> shaft top Z = +8.40 mm >= +8.00 mm; NO panel nut!)
    ex, ey = ox_mz + feats["SW_ENC"]["x"], oy_mz - feats["SW_ENC"]["y"]
    ec_solid = (
        box_xyz(ex - 6.00, ex + 6.00, ey - 5.80, ey + 5.80, Z_MEZZ_FCU + 0.02, Z_MEZZ_FCU + 6.50)
        + cyl_z(ex, ey, Z_MEZZ_FCU + 6.50, Z_MEZZ_FCU + 13.50, 6.80)
        + cyl_z(ex, ey, Z_MEZZ_FCU + 13.50, Z_MEZZ_FCU + 20.00, 6.00)
    ).solids()[0]
    solids["SW_ENC"] = (ec_solid, C_CHROME)

    # 9d. 2x Taiwan Alpha RD902F-40-15R1-B10K-00D Vertical Dual-Gang Pots (10.0mm body + L=15.0mm -> shaft top Z = +13.40 mm >= +8.00 mm!)
    pot_nut_od = 10.00 / math.cos(math.radians(30.0))  # 11.547 mm 360-deg M7 hex nut corner sweep
    for pkey in ("RV_IN_TRIM", "RV_OUT_TRIM"):
        px, py = ox_mz + feats[pkey]["x"], oy_mz - feats[pkey]["y"]
        pot_solid = (
            box_xyz(px - 6.50, px + 4.80, py - 4.75, py + 4.75, Z_MEZZ_FCU + 0.02, Z_SHELF_LEFT - 0.02)
            + cyl_z(px, py, Z_SHELF_LEFT - 0.02, Z_SHELF_LEFT + 5.00, 6.80)
            + cyl_z(px, py, Z_SHELF_LEFT + 5.00, Z_SHELF_LEFT + 15.00, 6.00)
        ).solids()[0]
        solids[pkey] = (pot_solid, C_CHROME)
        solids[f"{pkey}_nut"] = ((cyl_z(px, py, 0.02, 2.32, pot_nut_od) - cyl_z(px, py, -0.2, 2.6, 7.05)).solids()[0], C_CHROME)

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
                                   Z_MEZZ_BCU - 8.60, Z_MEZZ_BCU - 1.10)).solids()[0]
        solids[f"{btb_ref}_mz_socket"] = (sock, C_BLACK)
        # Tall board-stacker male header on main_board F.Cu (Samtec DW-08-12-L-D-655: 1.030" OAL = 23.37mm above F.Cu -> Z_top = -15.03mm!)
        hdr = box_xyz(bcx - 2.54, bcx + 2.54, bcy - 10.20, bcy + 10.20, Z_MAIN_FCU + 0.02, Z_MAIN_FCU + 16.64)
        for px, py in pads:
            hdr = (hdr + box_xyz(px - 0.32, px + 0.32, py - 0.32, py + 0.32,
                                 Z_MAIN_FCU + 16.64, Z_MAIN_FCU + 23.37)).solids()[0]
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
        # Relay_DPDT_Omron_G6K-2F-Y at rot=0 deg is 6.50mm (X) x 10.00mm (Y) x 5.20mm (Z)
        solids[kref] = (box_xyz(kx - 3.25, kx + 3.25, ky - 5.00, ky + 5.00,
                                Z_MAIN_FCU + 0.02, Z_MAIN_FCU + 5.20), C_BLACK)
    opto_pads = [(ox_mb + pcbnew.ToMM(p.GetPosition().x), oy_mb - pcbnew.ToMM(p.GetPosition().y))
                 for p in mb_fps["U_OPTO"].Pads()]
    opx = (min(x for x, _ in opto_pads) + max(x for x, _ in opto_pads)) / 2.0
    opy = (min(y for _, y in opto_pads) + max(y for _, y in opto_pads)) / 2.0
    solids["U_OPTO_H11L1"] = (box_xyz(opx - 3.30, opx + 3.30, opy - 3.80, opy + 3.80,
                                      Z_MAIN_FCU + 0.02, Z_MAIN_FCU + 7.50), C_BLACK)

    # 11b. All remaining 296 SMD packages & passives on main_board (derived from exact KiCad PCB_SHAPE F.Fab centerlines!)
    smd_heights_mm: Dict[str, float] = {
        "Resistor_SMD:R_0603_1608Metric": 0.55,
        "Resistor_SMD:R_0805_2012Metric": 0.60,
        "Capacitor_SMD:C_0603_1608Metric": 0.80,
        "Capacitor_SMD:C_0805_2012Metric": 1.25,
        "Capacitor_SMD:C_1206_3216Metric": 1.60,
        "Inductor_SMD:L_0603_1608Metric": 0.80,
        "Fuse:Fuse_1206_3216Metric": 1.10,
        "Fuse:Fuse_1812_4532Metric": 1.20,
        "Diode_SMD:D_SOD-323": 1.00,
        "Diode_SMD:D_SOD-123": 1.20,
        "Diode_SMD:D_SMA": 2.20,
        "Diode_SMD:D_SMB": 2.40,
        "Crystal:Crystal_SMD_3225-4Pin_3.2x2.5mm": 0.80,
        "Package_TO_SOT_SMD:SOT-23": 1.10,
        "Package_TO_SOT_SMD:SOT-23-6": 1.25,
        "Package_TO_SOT_SMD:SOT-223-3_TabPin2": 1.70,
        "Package_TO_SOT_SMD:TO-252-2": 2.30,
        "Package_SO:SOIC-8_3.9x4.9mm_P1.27mm": 1.65,
        "Package_SO:SOIC-8_5.3x5.3mm_P1.27mm": 1.90,
        "Package_SO:SOIC-14_3.9x8.7mm_P1.27mm": 1.65,
        "Package_SO:TSSOP-20_4.4x6.5mm_P0.65mm": 1.15,
        "beads_custom:SOIC-8-1EP_TPS5430_SegPaste": 1.65,
        "beads_custom:SOP-4_TLP172AM_P2.54mm": 2.10,
        "beads_custom:QFN-56-1EP_7x7mm_RP2040_SegPaste": 0.90,
        "beads_custom:VQFN-24-1EP_4x4mm_TPS65131_SegPaste": 0.90,
        "beads_custom:SW_Push_TS-1088_4.0x3.0mm": 2.00,
    }
    C_PASSIVE = (0.48, 0.40, 0.28)
    for fp in mb_board.GetFootprints():
        ref = fp.GetReference()
        fpid = fp.GetFPIDAsString()
        if (
            ref in solids
            or f"{ref}_header" in solids
            or ref in ("U_OPTO", "J_BTB_AUDIO_CV", "J_BTB_UI_DIG")
            or ref.startswith(("MH", "TP"))
        ):
            continue
        assert fpid in smd_heights_mm, f"Unhandled SMD footprint on main_board: {ref} ({fpid})"
        fxs: List[float] = []
        fys: List[float] = []
        for item in fp.GraphicalItems():
            if item.GetLayer() == pcbnew.F_Fab and isinstance(item, pcbnew.PCB_SHAPE):
                bb = item.GetBoundingBox()
                hw = item.GetWidth() // 2
                fxs.extend([ox_mb + pcbnew.ToMM(bb.GetLeft() + hw), ox_mb + pcbnew.ToMM(bb.GetRight() - hw)])
                fys.extend([oy_mb - pcbnew.ToMM(bb.GetBottom() - hw), oy_mb - pcbnew.ToMM(bb.GetTop() + hw)])
        col_smd = C_PASSIVE if ref.startswith(("R", "C", "FB", "F")) else C_BLACK
        solids[ref] = (
            box_xyz(min(fxs), max(fxs), min(fys), max(fys), Z_MAIN_FCU + 0.02, Z_MAIN_FCU + smd_heights_mm[fpid]),
            col_smd,
        )

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

    # 12c. 6x main_board Inserts (MH101..106) + 3x M3x5mm ISO 7380 Button-Head Screws + 3x M3x10mm North Lid/PCB Screws
    mhs_map = {m["ref"]: (m["x"], m["y"]) for m in CONTRACT["boards"]["main_board"]["mounting_holes_world_mm"]}
    for mref in ("MH101", "MH102", "MH103"):
        mx, my = mhs_map[mref]
        add_brass_insert(f"INS_{mref}", mx, my, Z_MAIN_FCU + 0.02, Z_MAIN_FCU + 4.02)
        # ISO 7380-1 M3x5mm button-head screw (worst-case k_max=1.65mm, dk_max=5.70mm at Z=[-41.67, -40.02],
        # clearing Z_LID_TOP=-42.00mm bottom_lid by 0.33mm! DIN 9200 k<=1.40mm clears by 0.58mm.)
        bolt = (
            cyl_z(mx, my, Z_MAIN_BCU - 1.67, Z_MAIN_BCU - 0.02, 5.70)
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
    d.text((yz(187, 3.2)[0] - 115, yz(187, 3.2)[1]), "Z = 0.00 mm (Flush 3U Plane)", fill=(37, 99, 235), font=f_h2)
    d.line([yz(-6, -45.0), yz(194, -45.0)], fill=(100, 116, 139), width=2)
    d.text((yz(187, -45.0)[0] - 115, yz(187, -45.0)[1] + 6), "Z = -45.00 mm (Pedalboard Floor)", fill=(71, 85, 105), font=f_h2)

    # PETG-HF Enclosure cross-section
    c_petg = (55, 65, 81)
    rect_yz(0.0, 3.6, -45.0, -12.0, c_petg)             # South wall
    rect_yz(3.6, 39.0, -16.0, -12.0, c_petg)            # Stepped stomp apron deck
    rect_yz(15.0, 22.0, -42.0, -16.0, (75, 85, 99), outline=(100, 116, 139), width=1)  # Flanking X-offset stomp pillar (behind FS1)
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
    # Shrouded 2x5 Eurorack Header + Full 16.2mm Mated IDC Plug & Ribbon (Y=48.1mm South of Beads PCB!)
    rect_yz(43.7, 52.5, -38.4, -29.3, (40, 40, 46))
    rect_yz(45.1, 51.1, -35.6, -22.2, (220, 50, 50))
    rect_yz(51.1, 54.4, -23.6, -22.2, (220, 50, 50))
    rect_yz(53.1, 54.4, -32.0, -22.2, (220, 50, 50))
    rect_yz(53.1, 74.0, -32.0, -30.6, (220, 50, 50))
    rect_yz(68.0, 74.0, -32.0, -27.1, (220, 50, 50))
    # 2x8 Tall BTB Stacker DW-08-12-L-D-655 + B.Cu Socket (Y=[80, 100], Z=[-38.4, -13.2])
    rect_yz(80.0, 100.0, -38.4, -21.76, (50, 50, 58))
    rect_yz(80.0, 100.0, -21.73, -13.2, (30, 30, 36))

    # ui_mezzanine (Y=[52.85, 160.85], Z=[-13.2, -11.6]) + Thonkiconn + Pots/Encoder (+8.4mm / +13.4mm shafts!)
    rect_yz(52.85, 160.85, -13.2, -11.6, (22, 128, 61))
    rect_yz(62.0, 72.5, -11.6, -1.6, (45, 45, 52))
    rect_yz(64.0, 70.0, -1.6, 1.9, (190, 196, 204))
    # Dual Pot RD902F-40-15 (+13.40mm shaft) & EC11E (+8.40mm shaft!)
    rect_yz(115.0, 124.5, -11.6, -1.6, (70, 75, 85))
    rect_yz(116.6, 123.4, -1.6, 3.4, (170, 178, 190))
    rect_yz(117.0, 123.0, 3.4, 13.4, (196, 202, 210))
    # SSD1306 OLED (8.13mm <= 8.50mm stack on DW-04-07-T-S-200) behind milled window
    rect_yz(130.6, 158.3, -6.52, -4.92, (22, 128, 61))
    rect_yz(133.3, 152.5, -4.92, -3.47, (14, 116, 178))

    # faceplate_14hp (Z=[-1.6, 0.0]) & Beads rear PCB dashed outline (Y=[54.6, 159.6], Z=[-27.0, -2.0])
    rect_yz(42.85, 171.35, -1.6, 0.0, (24, 24, 28))
    bx1, by2 = yz(54.6, -27.0)
    bx2, by1 = yz(159.6, -2.0)
    d.rectangle([(bx1, by1), (bx2, by2)], outline=(180, 83, 9), width=3)

    # Footswitch FS1 on Stepped Apron (Y=18.5, Z_apron=-12.0)
    rect_yz(12.5, 24.5, -34.5, -16.0, (148, 163, 184))
    rect_yz(13.5, 23.5, -12.0, -2.4, (203, 213, 225))

    # Clear callout annotations
    notes = [
        ((18.5, -5.0), (145, 235), "FS1 / FS2 Momentary (-M1QEH)\nZ=-12mm Stepped Apron + Load Pillars"),
        ((67.0, 1.0), (470, 130), "12x Thonkiconn + Faceplate (Z=0.0mm)\n-1.6mm Left Shelf / -2.0mm Beads Shelf"),
        ((120.0, 11.5), (850, 115), "RD902F Pots (+13.4mm) & EC11E (+8.4mm)\nShaft Protrusions >= 8.0mm Spec!"),
        ((144.0, -4.2), (1180, 195), "0.96\" SSD1306 + 19.2mm Glass\n8.13mm <= 8.5mm Stack (DW-04-07-T-S-200)"),
        ((172.0, -30.26), (1240, 825), "4x Neutrik NMJ4HCD2 + 17.6mm DC_JACK\n100% North of Beads Rear PCB (Y<=159.6)!"),
        ((48.1, -24.0), (220, 835), "J_EURO_PWR South of Beads (Y=48.1mm)\n32.4mm Headroom for 16.2mm IDC Plug!"),
        ((90.0, -26.0), (740, 835), "Samtec DW-08-12-L-D-655 + B.Cu Sockets\n23.37mm Post inside 25.2mm Gap (0.00mm XY)"),
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
    d2.text((xy(78.0, 169.5)[0], xy(78.0, 169.5)[1]), "RIGHT 14 HP:\nMutable Instruments Beads", fill=(15, 23, 42), font=f_h2)

    # North wall connectors
    n_labels = [
        (15.5, "OUT R", -20), (35.5, "OUT L/M", -28), (55.5, "IN R", -14), (75.5, "IN L/M", -22),
        (93.0, "THRU", -18), (105.0, "<A|B>", -18), (117.0, "IN", -8), (129.5, "USB-C", -24), (140.4, "DC", -8),
    ]
    for nx, nl, dx_lbl in n_labels:
        px, py = xy(nx, 183.8)
        d2.ellipse([(px - 8, py - 8), (px + 8, py + 8)], fill=(30, 41, 59))
        d2.text((px + dx_lbl, py - 30), nl, fill=(15, 23, 42), font=f_b)

    # Wiring callouts inside diagram:
    # 1. DC Jack (140.4, 183.8, 17.6mm deep to Y=170.5) -> J_PWR_IN (141.77, 162.6)
    p_dc = xy(140.4, 180.0)
    p_jpwr = xy(141.77, 162.6)
    d2.line([p_dc, p_jpwr], fill=(220, 38, 38), width=4)
    d2.ellipse([p_jpwr[0] - 6, p_jpwr[1] - 6, p_jpwr[0] + 6, p_jpwr[1] + 6], fill=(220, 38, 38))
    d2.text((p_jpwr[0] - 58, p_jpwr[1] + 12), "J_PWR_IN", fill=(185, 28, 28), font=f_b)

    # 2. J_EURO_PWR (101.0, 48.1, rot=90 deg South of Beads PCB!) -> Beads 2x5 Power Header
    p_euro = xy(101.0, 48.1)
    p_beads_pwr = xy(101.0, 71.0)
    d2.rectangle([p_euro[0] - 48, p_euro[1] - 20, p_euro[0] + 48, p_euro[1] + 20], fill=(30, 41, 59))
    # Thick vertical RED STRIPE bar on WEST/LEFT end (Pins 1 & 2 = -12V_EUR!)
    d2.line([(p_euro[0] - 44, p_euro[1] - 22), (p_euro[0] - 44, p_euro[1] + 22)], fill=(220, 38, 38), width=6)
    d2.line([p_euro, p_beads_pwr], fill=(220, 38, 38), width=5)
    d2.text((p_beads_pwr[0] - 115, p_beads_pwr[1] - 52), "2x5 IDC Ribbon (South of Beads!)\nWEST RED STRIPE = -12V (Pins 1-2)", fill=(185, 28, 28), font=f_h2)

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
        ("2. EURORACK 2x5 POWER HEADER (J_EURO_PWR @ Y=48.1mm)", (185, 28, 28), [
            "• Pins 1 & 2 (WEST / LEFT SILKSCREEN BAR) = -12.0V EUR (RED STRIPE!).",
            "• Pins 3..8 = GND   |   Pins 9 & 10 (EAST / RIGHT) = +12.0V EUR.",
            "• Shroud notch faces SOUTH; match RED STRIPE to -12V mark on Beads!",
        ]),
        ("3. REVERSIBLE 0.96\" SSD1306 OLED JUMPER (JP_OLED_PWR)", (2, 132, 199), [
            "• Check your 4-pin OLED pin order BEFORE soldering/plugging J_OLED:",
            "  - Mode A (GND-VCC-SCL-SDA): bridge 1-2 & 4-5 on JP_OLED_PWR.",
            "  - Mode B (VCC-GND-SCL-SDA): bridge 2-3 & 5-6 on JP_OLED_PWR.",
            "• Mount via Samtec DW-04-07-T-S-200 (5.08mm spacer -> 8.13mm <= 8.5mm stack!).",
        ]),
        ("4. STEPPED APRON FOOTSWITCH & LED HEADERS", (30, 64, 175), [
            "• FS1 (Left, X=30mm): E-Switch FS5700SPMT2B2M1QEH (EG5495-ND) -> J_FS1.",
            "• FS2 (Right, X=122mm): E-Switch FS5700SPMT2B2M1QEH (EG5495-ND) -> J_FS2.",
            "• Apron 3mm LEDs: Pin 1 = Anode (+3V3), Pin 2 = Cathode -> J_LED_FS1/2.",
        ]),
        ("5. 18x M3 HEAT-SET INSERTS & FASTENERS (M3x4.0xOD4.6 @ 240°C)", (15, 23, 42), [
            "• 8x Top 3U Eurorack rail bosses (4x Left @ Z=-1.6mm, 4x Right @ Z=-2.0mm).",
            "• 6x main_board bosses: MH101..103 use M3x5 ISO 7380 button/wafer head (k<=1.65mm)!",
            "• 4x South lid (M3x8 DIN 7991 CSK) + 3x North MH104..106 (M3x10 DIN 7991 CSK).",
            "• Fasten faceplate & Beads with 8x M3x6mm Knurlies (dead-flush at Z=0!).",
        ]),
        ("6. HEADERLESS USB-C UF2 FIRMWARE FLASHING", (5, 150, 105), [
            "• Fresh RP2040 mounts automatically as RPI-RP2 over USB-C (<1 uA isolated).",
            "• Drag-and-drop firmware/build/beads_bridge.uf2 — zero SWD pins needed!",
            "• Future updates: OLED Menu -> SYSTEM -> USB FW UPDATE (or 1200bps CDC).",
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

    print("[2/4] Building full 417-solid populated assembly STEP...")
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
    # Note: Looking South (-Y) at the North wall, +X (East) is on the viewer's LEFT and -X (West) is on the viewer's RIGHT!
    render_studio_view(
        solids,
        EXPORT_DIR / "render_north_io.png",
        cam_pos=(76.0, 415.0, 62.0),
        look_at=(76.0, 150.0, -24.0),
        fov_deg=28.0,
        title="NORTH-WALL PEDALBOARD I/O — ALL CABLES EXIT TOP EDGE",
        subtitle="4x Neutrik NMJ4HCD2 1/4\" (Ø16.5mm Spotfaces) | TRS MIDI IN + Debossed B<->A Switch + Hardware THRU | Isolated USB-C | 9-18V DC",
        callouts=[
            ((15.5, 186.5, -30.26), (1135, 860), "OUT L/M & OUT R (Neutrik NMJ4HCD2)"),
            ((75.5, 186.5, -30.26), (755, 920), "IN L/Mono & IN R (L->R Normalled)"),
            ((105.0, 185.6, -36.50), (420, 900), "TRS MIDI IN | TYPE B<->A | MIDI THRU"),
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
            ((76.0, 100.0, -39.2), (90, 560), "main_board (Top-Side JLCPCB SMT + 92.5% GND)"),
            ((101.0, 48.1, -30.0), (1040, 740), "J_EURO_PWR South of Beads + 16.2mm IDC Plug"),
            ((108.5, 18.5, -41.5), (95, 790), "4x Full-Height Stomp Force Pillars"),
        ],
    )

    print("[4/4] Generating mechanical Y-Z cross-section & wiring/installation diagrams...")
    render_cross_section_and_wiring_diagrams(EXPORT_DIR)
    print("[OK] All 3D STLs, STEPs, Studio PNG Renders & Wiring Diagrams generated successfully!")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
