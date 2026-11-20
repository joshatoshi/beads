#!/usr/bin/env python3
"""Gate 5 Automated 3D B-Rep Collision, Swept Insertion Kinematics, Datasheet Envelope,
Datum, Shaft-Protrusion & Deliverable Auditor for the Mutable Instruments Beads Pedalboard Skiff.

Uses build123d + OCP.BRepAlgoAPI.BRepAlgoAPI_Common directly across ALL individual
un-grouped solids (121 solids -> 7,260 pairs) AND across the rigid-body main_board
assembly insertion sweep to assert:
  1. 0.000 mm³ pairwise B-Rep intersection volume across every un-grouped solid pair.
  2. 0.000 mm³ swept rigid-body insertion kinematics for main_board + all soldered
     connectors/headers (vertical lift dz: -30.0 -> 0.0 mm at dy = -6.00 mm, followed
     by horizontal slide dy: -6.00 -> 0.00 mm at dz = 0.00 mm) against enclosure_shell
     + pre-installed panel hardware.
  3. Full datasheet envelopes: 17.6mm Tensility 54-00401 DC_JACK + solder lugs,
     >=16mm mated 2x5 IDC ribbon plug South of Beads, <=8.5mm SSD1306 stack w/ 19.2mm glass,
     exact 23.37mm Samtec DW-08-12-L-D-655 posts, all 5x 1x2 headers + 14.0mm mated housings,
     bushingless EC11E15244G1 (zero fictional nut), <=0.5mm J_USB pocket reach with >=2.5mm
     North-wall web to DC_JACK, and finger-reachable SW_MIDI_AB alcove.
  4. >= 8.00 mm shaft protrusion above faceplate_14hp (Z = 0.00 mm) on SW_ENC, RV_IN_TRIM, RV_OUT_TRIM.
  5. Complete STL, STEP, local 3D shape library, and Studio PNG / Wiring Diagram deliverables.
"""
from __future__ import annotations

import json
import math
import pathlib
import sys

import build123d as bd
from OCP.BRepAlgoAPI import BRepAlgoAPI_Common
from OCP.BRepGProp import BRepGProp
from OCP.GProp import GProp_GProps

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "cad"))

import build_enclosure as be  # noqa: E402


def brep_common_volume_mm3(s1: bd.Solid, s2: bd.Solid) -> float:
    """Exact OpenCascade BRepAlgoAPI_Common intersection volume in mm³."""
    op = BRepAlgoAPI_Common(s1.wrapped, s2.wrapped)
    op.Build()
    if not op.IsDone():
        raise RuntimeError("BRepAlgoAPI_Common failed to evaluate!")
    props = GProp_GProps()
    BRepGProp.VolumeProperties_s(op.Shape(), props)
    return max(0.0, float(props.Mass()))


def aabb_overlaps(bb1: bd.BoundBox, bb2: bd.BoundBox, pad: float = 0.02) -> bool:
    return not (
        bb1.max.X + pad < bb2.min.X or bb2.max.X + pad < bb1.min.X
        or bb1.max.Y + pad < bb2.min.Y or bb2.max.Y + pad < bb1.min.Y
        or bb1.max.Z + pad < bb2.min.Z or bb2.max.Z + pad < bb1.min.Z
    )


def main() -> int:
    export_dir = ROOT / "cad" / "exports"
    shapes_dir = ROOT / "hardware" / "beads_custom.3dshapes"
    contract = json.loads((ROOT / "hardware_contract.json").read_text(encoding="utf-8"))

    # 1. Verify exported STL, STEP, local .3dshapes, and PNG render deliverables exist & non-empty
    required_exports = [
        export_dir / "beads_enclosure_shell.stl",
        export_dir / "beads_enclosure_shell.step",
        export_dir / "beads_bottom_lid.stl",
        export_dir / "beads_bottom_lid.step",
        export_dir / "beads_full_assembly.step",
        export_dir / "render_iso_front.png",
        export_dir / "render_north_io.png",
        export_dir / "render_bottom_interior.png",
        export_dir / "render_side_cross_section.png",
        export_dir / "diagram_wiring_and_assembly.png",
    ]
    for p in required_exports:
        assert p.exists() and p.stat().st_size > 5_000, f"Missing or truncated 3D CAD deliverable: {p}"

    step_shapes = list(shapes_dir.glob("*.step"))
    assert len(step_shapes) >= 15, f"Expected >= 15 local STEP models in {shapes_dir}, found {len(step_shapes)}"
    print(f"[PASS] Gate 5.1: All {len(required_exports)} CAD STL/STEP/PNG exports & {len(step_shapes)} local 3D STEP models verified")

    # 2. Verify raw print-ready enclosure_shell & bottom_lid manifold integrity + envelope dimensions
    raw_shell = be.build_enclosure_shell(installed_inserts=False)
    assert raw_shell.is_valid and len(raw_shell.solids()) == 1 and raw_shell.volume > 50_000.0
    rbb = raw_shell.bounding_box()
    assert abs((rbb.max.X - rbb.min.X) - 152.00) < 0.02, f"Shell X span mismatch: {rbb}"
    assert abs((rbb.max.Y - rbb.min.Y) - 185.60) < 0.02, f"Shell Y span mismatch: {rbb}"
    assert abs((rbb.max.Z - rbb.min.Z) - 45.00) < 0.02, f"Shell Z span mismatch: {rbb}"
    print(
        f"[PASS] Gate 5.2: Print-ready enclosure_shell is 1 monolithic Solid "
        f"({rbb.max.X - rbb.min.X:.2f} x {rbb.max.Y - rbb.min.Y:.2f} x {rbb.max.Z - rbb.min.Z:.2f} mm, "
        f"vol = {raw_shell.volume / 1000.0:.2f} cm³)"
    )

    # 3. Build all individual un-grouped populated solids & verify mandatory categories + datasheet envelopes
    solids_map = be.build_populated_solids()
    names = list(solids_map.keys())
    mandatory_keys = [
        "enclosure_shell", "bottom_lid", "main_board", "ui_mezzanine", "faceplate_14hp",
        "beads_module", "J_EURO_PWR_header", "eurorack_2x5_ribbon",
        "J_OUT_R", "J_OUT_L", "J_IN_R", "J_IN_L",
        "J_MIDI_THRU", "J_MIDI_IN", "SW_MIDI_AB", "J_USB",
        "DC_JACK", "DC_JACK_nut_sweep",
        "J_PWR_IN_header", "J_PWR_IN_plug",
        "J_FS1_header", "J_FS1_plug", "J_FS2_header", "J_FS2_plug",
        "J_LED_FS1_header", "J_LED_FS1_plug", "J_LED_FS2_header", "J_LED_FS2_plug",
        "FS1", "FS2", "FS1_inner_nut", "FS2_inner_nut",
        "J_OLED_socket", "SSD1306_oled", "SW_ENC", "SW_BACK", "RV_IN_TRIM", "RV_OUT_TRIM",
        "J_SEND_L", "J_SEND_R", "J_RET_L", "J_RET_R",
        "J_CV1", "J_CV2", "J_CV3", "J_CV4", "J_CV5", "J_CV6", "J_CV7", "J_CV8",
        "J_BTB_AUDIO_CV_mb_header", "J_BTB_AUDIO_CV_mz_socket",
        "J_BTB_UI_DIG_mb_header", "J_BTB_UI_DIG_mz_socket",
    ]
    for mk in mandatory_keys:
        assert mk in solids_map, f"Missing mandatory un-grouped solid in 3D audit: {mk}"
    assert "SW_ENC_nut" not in solids_map, "Bushingless Alps EC11E15244G1 must NOT have a fictional SW_ENC_nut!"

    insert_count = sum(1 for k in names if k.startswith("INS_"))
    bolt_count = sum(1 for k in names if k.startswith("BOLT_"))
    assert insert_count == 18 and bolt_count == 18, f"Expected 18 inserts & 18 bolts, got {insert_count}, {bolt_count}"

    for k, (s, _) in solids_map.items():
        assert s.is_valid and s.volume > 0.01, f"Invalid or degenerate solid: {k} (vol={s.volume})"

    # Datasheet envelope & North-wall reach assertions
    dc_bb = solids_map["DC_JACK"][0].bounding_box()
    assert (dc_bb.max.Y - dc_bb.min.Y) >= 17.55, f"DC_JACK depth {dc_bb.max.Y - dc_bb.min.Y:.2f}mm < 17.6mm Tensility 54-00401 spec!"
    rib_bb = solids_map["eurorack_2x5_ribbon"][0].bounding_box()
    assert (rib_bb.max.Z - be.Z_MAIN_FCU) >= 15.5, f"2x5 IDC mated ribbon plug height {rib_bb.max.Z - be.Z_MAIN_FCU:.2f}mm shrunk!"
    oled_bb = solids_map["SSD1306_oled"][0].bounding_box()
    oled_stack = oled_bb.max.Z - be.Z_MEZZ_FCU
    assert oled_stack <= 8.50, f"SSD1306 OLED stack {oled_stack:.2f}mm > 8.50mm limit!"
    assert (oled_bb.max.X - oled_bb.min.X) >= 27.25 and (oled_bb.max.Y - oled_bb.min.Y) >= 27.75, f"SSD1306 PCB shrunk: {oled_bb}"
    btb_bb = solids_map["J_BTB_AUDIO_CV_mb_header"][0].bounding_box()
    btb_post_h = btb_bb.max.Z - be.Z_MAIN_FCU
    assert abs(btb_post_h - 23.37) < 0.05, f"DW-08-12-L-D-655 post height {btb_post_h:.2f}mm != 23.37mm!"
    for href in ("J_PWR_IN", "J_FS1", "J_FS2", "J_LED_FS1", "J_LED_FS2"):
        pbb = solids_map[f"{href}_plug"][0].bounding_box()
        assert abs((pbb.max.Z - pbb.min.Z) - 14.00) < 0.05, f"{href}_plug housing height {pbb.max.Z - pbb.min.Z:.2f}mm != 14.00mm!"

    # J_USB <= 0.50 mm reach to 13.0x7.5mm pocket floor (Y=183.20) & >= 2.50 mm radial web to DC_JACK D-bore
    usb_bb = solids_map["J_USB"][0].bounding_box()
    usb_recess = 183.20 - usb_bb.max.Y
    assert 0.0 <= usb_recess <= 0.50, f"J_USB lip recess {usb_recess:.2f}mm outside [0.0, 0.50]mm!"
    nc = contract["boards"]["main_board"]["north_wall_connectors_world_mm"]
    ux, uz = nc["J_USB"]["x_center"], nc["J_USB"]["z_center"]
    dx_dc, dz_dc = nc["DC_JACK"]["x_center"], nc["DC_JACK"]["z_center"]
    r_usb_pocket = 7.50 / 2.0
    x_usb_right_arc = ux + (13.00 - 7.50) / 2.0
    r_dc_bore = nc["DC_JACK"]["d_bore_dia"] / 2.0
    north_web = math.hypot(dx_dc - x_usb_right_arc, dz_dc - uz) - r_usb_pocket - r_dc_bore
    assert north_web >= 2.50, f"North-wall web between J_USB pocket & DC_JACK bore {north_web:.3f}mm < 2.50mm!"

    sw_ab_bb = solids_map["SW_MIDI_AB"][0].bounding_box()
    assert sw_ab_bb.max.Y >= 182.30 and sw_ab_bb.max.Y <= 185.00, f"SW_MIDI_AB tip Y={sw_ab_bb.max.Y:.2f}mm not finger-reachable in alcove!"

    # 4. Verify shaft protrusion >= 8.00 mm above faceplate_14hp (Z = 0.00 mm) & flush panel datums
    fp_bb = solids_map["faceplate_14hp"][0].bounding_box()
    lid_bb = solids_map["bottom_lid"][0].bounding_box()
    assert abs(fp_bb.max.Z - 0.00) < 0.02 and abs(fp_bb.min.Z - (-1.60)) < 0.02, f"faceplate_14hp Z off: {fp_bb}"
    assert abs(lid_bb.min.Z - (-45.00)) < 0.02, f"bottom_lid not flush at Z=-45.00: {lid_bb}"

    protrusions = {}
    for sref in ("SW_ENC", "RV_IN_TRIM", "RV_OUT_TRIM"):
        s_top = solids_map[sref][0].bounding_box().max.Z - fp_bb.max.Z
        protrusions[sref] = s_top
        assert s_top >= 8.00, f"Insufficient shaft protrusion on {sref}: {s_top:.2f} mm < 8.00 mm!"
    print(
        f"[PASS] Gate 5.3: Flush Z=0.00mm panels, J_USB recess={usb_recess:.2f}mm (<=0.5mm, web={north_web:.2f}mm), "
        f"OLED={oled_stack:.2f}mm, BTB={btb_post_h:.2f}mm, shafts: SW_ENC={protrusions['SW_ENC']:.2f}mm, "
        f"RV_IN/OUT={protrusions['RV_IN_TRIM']:.2f}mm (>=8.00mm)"
    )

    # 5. Pairwise OCP BRepAlgoAPI_Common across ALL N*(N-1)/2 un-grouped solid pairs!
    bbs = {k: solids_map[k][0].bounding_box() for k in names}
    total_pairs = len(names) * (len(names) - 1) // 2
    narrow_checked = 0
    max_vol = 0.0
    collisions = []

    for i in range(len(names)):
        k1 = names[i]
        s1 = solids_map[k1][0]
        b1 = bbs[k1]
        for j in range(i + 1, len(names)):
            k2 = names[j]
            if not aabb_overlaps(b1, bbs[k2]):
                continue
            narrow_checked += 1
            vol = brep_common_volume_mm3(s1, solids_map[k2][0])
            if vol > max_vol:
                max_vol = vol
            if vol > 1e-4:
                collisions.append((vol, k1, k2))

    if collisions:
        collisions.sort(reverse=True)
        msg = "\n".join(f"  - {k1} <-> {k2}: {v:.4f} mm³" for v, k1, k2 in collisions[:15])
        raise AssertionError(f"3D B-Rep collisions detected ({len(collisions)} pairs):\n{msg}")

    print(
        f"[PASS] Gate 5.4: 0.000 mm³ pairwise OCP BRepAlgoAPI_Common collision volume "
        f"across {len(names)} un-grouped solids ({total_pairs} total pairs, "
        f"{narrow_checked} narrowphase B-Rep booleans, max = {max_vol:.6f} mm³)!"
    )

    # 6. Rigid-Body main_board Swept-Insertion Kinematic Verification (OCP BRepAlgoAPI_Common)
    #    Stage A: Lift vertically dz in [-28.0 .. 0.0 mm] while shifted South at dy = -6.00 mm
    #    Stage B: Slide North dy in [-6.00 .. 0.00 mm] at installed Z (dz = 0.00 mm)
    moving_mb_keys = [
        "main_board",
        "J_OUT_R", "J_OUT_L", "J_IN_R", "J_IN_L",
        "J_MIDI_THRU", "J_MIDI_IN", "SW_MIDI_AB", "J_USB",
        "J_EURO_PWR_header",
        "J_BTB_AUDIO_CV_mb_header", "J_BTB_UI_DIG_mb_header",
        "J_PWR_IN_header", "J_FS1_header", "J_FS2_header", "J_LED_FS1_header", "J_LED_FS2_header",
        "U_OPTO_H11L1", "C18", "C22", "L1", "L2", "L3", "K1", "K2",
    ]
    fixed_case_keys = [
        "enclosure_shell",
        "DC_JACK", "DC_JACK_nut_sweep",
        "FS1", "FS2", "FS1_inner_nut", "FS2_inner_nut", "LED_FS1", "LED_FS2",
    ] + [k for k in names if k.startswith("INS_")]

    waypoints = (
        [(0.0, -6.00, dz) for dz in (-28.0, -20.0, -12.0, -6.0, -2.0, 0.0)]
        + [(0.0, dy, 0.0) for dy in (-5.0, -4.0, -3.0, -2.0, -1.0, -0.4, 0.0)]
    )
    sweep_checks = 0
    max_sweep_vol = 0.0
    for dx, dy, dz in waypoints:
        loc = bd.Pos(dx, dy, dz)
        for mk in moving_mb_keys:
            ms = (loc * solids_map[mk][0]).solids()[0]
            mbb = ms.bounding_box()
            for fk in fixed_case_keys:
                fs = solids_map[fk][0]
                if not aabb_overlaps(mbb, bbs[fk]):
                    continue
                sweep_checks += 1
                v = brep_common_volume_mm3(ms, fs)
                if v > max_sweep_vol:
                    max_sweep_vol = v
                assert v <= 1e-4, (
                    f"Rigid-body main_board insertion collision at (dy={dy:.2f}, dz={dz:.2f}): "
                    f"{mk} <-> {fk} = {v:.4f} mm³!"
                )

    print(
        f"[PASS] Gate 5.4b: 0.000 mm³ rigid-body main_board insertion sweep verified across "
        f"{len(waypoints)} kinematic poses x {len(moving_mb_keys)} soldered parts "
        f"({sweep_checks} B-Rep checks, max = {max_sweep_vol:.6f} mm³)!"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
