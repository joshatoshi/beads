#!/usr/bin/env python3
"""Deterministic Build123d STEP generator for hardware/beads_custom.3dshapes/.

Generates worktree-portable, datasheet-accurate 3D STEP models in KiCad footprint local
3D coordinates (X_3d = +X_fp, Y_3d = -Y_fp, Z_3d = height above F.Cu) and links them via
${KIPRJMOD}/../beads_custom.3dshapes/*.step inside hardware/beads_custom.pretty/*.kicad_mod.
"""
from __future__ import annotations

import pathlib
import re
import build123d as bd

ROOT = pathlib.Path(__file__).resolve().parents[1]
SHAPES_DIR = ROOT / "hardware" / "beads_custom.3dshapes"
PRETTY_DIR = ROOT / "hardware" / "beads_custom.pretty"


def export_model(name: str, part: bd.Part | bd.Solid | bd.Compound) -> pathlib.Path:
    SHAPES_DIR.mkdir(parents=True, exist_ok=True)
    out = SHAPES_DIR / f"{name}.step"
    bd.export_step(part, str(out))
    return out


def build_all_custom_3dshapes() -> list[pathlib.Path]:
    exported: list[pathlib.Path] = []

    # 1. Neutrik NMJ4HCD2 Horizontal 1/4" Jack (ST-NMJ4HCD2: T/TN rear X=0, S/SN front X=+12.70,
    #    front shoulder X=+16.70, threaded chrome ferrule X=+16.70..+22.49, rear tab X=-6.83..-3.91)
    body = bd.Pos((16.70 - 3.91) / 2.0, -8.115, 8.10) * bd.Box(20.61, 18.20, 16.20)
    nose = bd.Pos(16.70 + 2.895, -8.115, 8.14) * bd.Rot(0, 90, 0) * bd.Cylinder(5.55, 5.79)
    rear_tab = bd.Pos(-3.91 - 1.46, -8.115, 8.14) * bd.Box(2.92, 8.70, 5.60)
    pins = [
        bd.Pos(px, -py, -1.75) * bd.Cylinder(0.60, 3.50)
        for px, py in [(0.0, 0.0), (0.0, 16.23), (12.7, 0.0), (12.7, 16.23)]
    ]
    nmj = body + nose + rear_tab
    for p in pins:
        nmj = nmj + p
    exported.append(export_model("Jack_6.35mm_Neutrik_NMJ4HCD2", nmj))

    # 2. Same Sky / CUI SJ1-3523N Horizontal 3.5mm TRS Jack
    #    KiCad rot=0: S=(0,0), T=(+5,-5)->Y_3d=+5, R=(-5,-5)->Y_3d=+5, front shoulder Y_fp=+3.50 -> Y_3d=-3.50
    sj_body = bd.Pos(0.0, 2.10, 2.50) * bd.Box(12.00, 11.20, 5.00)
    # Front Ø6.0mm collar extends from Y_3d=-3.50 to -6.50, centered at Z=+2.50 (steps to Z=-0.50 below F.Cu!)
    sj_collar = bd.Pos(0.0, -5.00, 2.50) * bd.Rot(90, 0, 0) * bd.Cylinder(3.00, 3.00)
    exported.append(export_model("Jack_3.5mm_CUI_SJ1-3523N", sj_body + sj_collar))

    # 3. C&K JS202011AQN Right-Angle DPDT Slide Switch
    #    KiCad rot=0: Pad1=(0,0), Pad2=(2.5,0), Pad3=(5,0), front Y_fp=+3.65 -> Y_3d=-3.65, actuator to Y_3d=-5.65
    js_body = bd.Pos(2.50, -1.65, 1.90) * bd.Box(9.00, 4.00, 3.50)
    js_act = bd.Pos(2.50, -4.65, 1.75) * bd.Box(1.50, 2.00, 1.50)
    exported.append(export_model("SW_CK_JS202011AQN_DPDT_Angled", js_body + js_act))

    # 4. HRO TYPE-C-31-M-12 USB-C Receptacle
    #    KiCad rot=0: front lip Y_fp=+3.65 -> Y_3d=-3.65, body 8.94 x 7.30 x 3.20 mm
    usbc = bd.Pos(0.0, 0.0, 1.60) * bd.Box(8.94, 7.30, 3.20)
    exported.append(export_model("USB_C_Receptacle_HRO_TYPE-C-31-M-12", usbc))

    # 5. QingPu WQP-PJ398SM ("Thonkiconn") Vertical 3.5mm Jack
    #    KiCad rot=0: S=(0,0), TN=(0,3.1), T=(0,11.4), bushing center (0, 6.50) -> Y_3d=-6.50
    #    10.0mm body height + 3.5mm M6x0.75 bushing
    th_body = bd.Pos(0.0, -7.20, 5.00) * bd.Box(9.00, 10.50, 10.00)
    th_bush = bd.Pos(0.0, -6.50, 11.75) * bd.Cylinder(3.00, 3.50)
    exported.append(export_model("Jack_3.5mm_QingPu_WQP-PJ398SM_Vertical", th_body + th_bush))

    # 6. Alps EC11E15244G1 Rotary Encoder w/ Switch (H=20mm total above PCB)
    #    KiCad rot=0: shaft center at (+7.50, +2.50) -> (7.50, -2.50)
    ec_body = bd.Pos(7.50, -2.50, 3.25) * bd.Box(12.00, 11.60, 6.50)
    ec_bush = bd.Pos(7.50, -2.50, 10.00) * bd.Cylinder(3.40, 7.00)
    ec_shaft = bd.Pos(7.50, -2.50, 16.75) * bd.Cylinder(3.00, 6.50)
    exported.append(export_model("RotaryEncoder_Alps_EC11E_H20mm", ec_body + ec_bush + ec_shaft))

    # 7. Dual-Gang 9mm Vertical Potentiometer (Alpha RD902F-20 / Bourns PTD902-2020K-B103)
    #    KiCad rot=0: shaft center at (+7.50, +2.50) -> (7.50, -2.50), shoulder Z=10.0, total Z=20.0
    pot_body = bd.Pos(6.65, -2.50, 5.00) * bd.Box(11.30, 9.50, 10.00)
    pot_bush = bd.Pos(7.50, -2.50, 12.50) * bd.Cylinder(3.40, 5.00)
    pot_shaft = bd.Pos(7.50, -2.50, 17.50) * bd.Cylinder(3.00, 5.00)
    exported.append(export_model("Potentiometer_Dual_9mm_Vertical", pot_body + pot_bush + pot_shaft))

    # 8. Tactile BACK Pushbutton 6x6mm H=13.0mm
    sw_b = bd.Pos(3.25, -2.25, 1.75) * bd.Box(6.00, 6.00, 3.50)
    sw_s = bd.Pos(3.25, -2.25, 8.25) * bd.Cylinder(1.75, 9.50)
    exported.append(export_model("SW_PUSH_6mm_H13mm", sw_b + sw_s))

    # 9. Custom SMD & BTB Footprints in hardware/beads_custom.pretty/
    exported.append(export_model("QFN-56_RP2040_7x7mm", bd.Pos(0.0, 0.0, 0.45) * bd.Box(7.00, 7.00, 0.90)))
    exported.append(export_model("VQFN-24_TPS65131_4x4mm", bd.Pos(0.0, 0.0, 0.45) * bd.Box(4.00, 4.00, 0.90)))
    exported.append(export_model("SOIC-8_TPS5430", bd.Pos(0.0, 0.0, 0.80) * bd.Box(3.90, 4.90, 1.60)))
    exported.append(export_model("SOP-4_TLP172AM", bd.Pos(0.0, 0.0, 1.05) * bd.Box(3.90, 4.40, 2.10)))
    exported.append(export_model("SW_Push_TS-1088_4x3mm", bd.Pos(0.0, 0.0, 1.00) * bd.Box(4.00, 3.00, 2.00)))

    # BTB Socket 2x08 Bottom-Mate (mounted on B.Cu of ui_mezzanine, hangs -8.51mm in -Z_3d!)
    # KiCad rot=0: Pin1=(0,0), Pin2=(2.54,0) ... Pin16=(2.54, 17.78) -> center (1.27, -8.89)
    btb_sock = bd.Pos(1.27, -8.89, -1.60 - 4.255) * bd.Box(5.08, 20.50, 8.51)
    exported.append(export_model("BTB_Socket_2x08_BottomMate", btb_sock))

    # SolderJumper_OLED_RevPWR (flat copper feature)
    exported.append(export_model("SolderJumper_OLED_RevPWR", bd.Pos(0.0, 0.0, 0.05) * bd.Box(4.20, 3.80, 0.10)))

    return exported


def link_models_into_custom_footprints() -> None:
    mapping = {
        "Jack_6.35mm_Neutrik_NMJ4HCD2_TightCrtYd.kicad_mod": "Jack_6.35mm_Neutrik_NMJ4HCD2.step",
        "Jack_3.5mm_CUI_SJ1-3523N_Clean.kicad_mod": "Jack_3.5mm_CUI_SJ1-3523N.step",
        "QFN-56-1EP_7x7mm_RP2040_SegPaste.kicad_mod": "QFN-56_RP2040_7x7mm.step",
        "VQFN-24-1EP_4x4mm_TPS65131_SegPaste.kicad_mod": "VQFN-24_TPS65131_4x4mm.step",
        "SOIC-8-1EP_TPS5430_SegPaste.kicad_mod": "SOIC-8_TPS5430.step",
        "SOP-4_TLP172AM_P2.54mm.kicad_mod": "SOP-4_TLP172AM.step",
        "SW_Push_TS-1088_4.0x3.0mm.kicad_mod": "SW_Push_TS-1088_4x3mm.step",
        "BTB_Socket_2x08_P2.54mm_BottomMate.kicad_mod": "BTB_Socket_2x08_BottomMate.step",
        "SolderJumper_OLED_RevPWR.kicad_mod": "SolderJumper_OLED_RevPWR.step",
    }
    for mod_name, step_name in mapping.items():
        mod_path = PRETTY_DIR / mod_name
        txt = mod_path.read_text(encoding="utf-8")
        uri = f"${{KIPRJMOD}}/../beads_custom.3dshapes/{step_name}"
        model_block = (
            f'  (model "{uri}"\n'
            f'    (offset (xyz 0 0 0))\n'
            f'    (scale (xyz 1 1 1))\n'
            f'    (rotate (xyz 0 0 0))\n'
            f'  )\n'
        )
        # Remove any existing (model ...) block before closing ')'
        txt = re.sub(r'\s*\(model\s+"[^"]+".*?\n\s*\)\n', "\n", txt, flags=re.S)
        idx = txt.rfind(")")
        assert idx != -1
        new_txt = txt[:idx] + model_block + ")\n"
        mod_path.write_text(new_txt, encoding="utf-8")


def main() -> int:
    exported = build_all_custom_3dshapes()
    link_models_into_custom_footprints()
    print(f"[OK] Generated {len(exported)} STEP models in {SHAPES_DIR} and linked ${'{KIPRJMOD}'} URIs")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
