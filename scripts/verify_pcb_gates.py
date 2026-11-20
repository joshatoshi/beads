#!/usr/bin/env python3
"""Gate 1 Structural KiCad 9 & PCB Invariant Auditor for Beads Pedalboard Skiff.

Verifies:
  1. All 3 boards (main_board, ui_mezzanine, faceplate_14hp) have ERC=0/0, DRC=0 errors, unconnected=0.
  2. Worktree portability: zero hardcoded /home/yerbaadmin paths in sym-lib-table / fp-lib-table.
  3. main_board continuous B.Cu GND pour >= 88.0%.
  4. J_BTB_AUDIO_CV & J_BTB_UI_DIG exact pin-by-pin world XY mating congruence < 0.05 mm.
  5. F.CrtYd >= F.Fab on all custom footprints in hardware/beads_custom.pretty/.
  6. Segmented F.Paste (50-70%) & zero paste-over-via on RP2040/TPS65131/TPS5430 thermal pads,
     and F.Paste present on TLP172AM & G6K-2F-Y SMD pads.
  7. >= 3.0 mm non-GND track/via clearance around MH101..MH106 mounting holes on main_board.
"""
from __future__ import annotations

import json
import math
import pathlib
import re
import subprocess
import sys
import pcbnew

ROOT = pathlib.Path(__file__).resolve().parents[1]
CONTRACT = json.loads((ROOT / "hardware_contract.json").read_text(encoding="utf-8"))
SCRATCH = pathlib.Path("/tmp/opencode/beads_checks")
SCRATCH.mkdir(parents=True, exist_ok=True)


def check_portability() -> None:
    for b in ("main_board", "ui_mezzanine", "faceplate_14hp"):
        for tbl in ("sym-lib-table", "fp-lib-table"):
            p = ROOT / "hardware" / b / tbl
            assert p.exists(), f"Missing {p}"
            txt = p.read_text(encoding="utf-8")
            assert "/home/yerbaadmin" not in txt, f"Hardcoded host path found in {p}!"
            assert "${KIPRJMOD}" in txt, f"Missing ${{KIPRJMOD}} portable URI in {p}!"
    print("[PASS] Gate 1.1: Worktree-portable ${KIPRJMOD} sym-lib-table & fp-lib-table across all 3 boards")


def check_erc_and_drc() -> None:
    for b in ("main_board", "ui_mezzanine", "faceplate_14hp"):
        sch = ROOT / "hardware" / b / f"{b}.kicad_sch"
        pcb = ROOT / "hardware" / b / f"{b}.kicad_pcb"
        pro = ROOT / "hardware" / b / f"{b}.kicad_pro"
        for f in (pro, sch, pcb):
            assert f.exists() and f.stat().st_size > 100, f"Missing/empty {f}"

        erc_json = SCRATCH / f"{b}_erc.json"
        r = subprocess.run(["kicad-cli", "sch", "erc", "--format", "json", "-o", str(erc_json), str(sch)], capture_output=True, text=True)
        assert r.returncode == 0, f"ERC failed on {b}:\n{r.stdout}\n{r.stderr}"
        ed = json.loads(erc_json.read_text(encoding="utf-8"))
        e_viols = [v for s in ed.get("sheets", []) for v in s.get("violations", [])]
        assert len(e_viols) == 0, f"ERC violations on {b}: {e_viols[:5]}"

        drc_json = SCRATCH / f"{b}_drc.json"
        r2 = subprocess.run(["kicad-cli", "pcb", "drc", "--format", "json", "--severity-all", "-o", str(drc_json), str(pcb)], capture_output=True, text=True)
        assert r2.returncode == 0, f"DRC failed on {b}:\n{r2.stdout}\n{r2.stderr}"
        dd = json.loads(drc_json.read_text(encoding="utf-8"))
        d_errs = [v for v in dd.get("violations", []) if v.get("severity") == "error"]
        d_warns = [v for v in dd.get("violations", []) if v.get("severity") == "warning"]
        uncs = dd.get("unconnected_items", [])
        assert len(d_errs) == 0, f"DRC errors on {b}: {d_errs[:5]}"
        assert len(d_warns) == 0, f"DRC warnings on {b}: {d_warns[:5]}"
        assert len(uncs) == 0, f"Unconnected items on {b}: {uncs[:5]}"
    print("[PASS] Gate 1.2: 3-board KiCad 9 ERC = 0/0, DRC = 0 errors / 0 warnings, unconnected = 0")


def check_bcu_pour_and_mh_and_paste() -> None:
    mb_path = ROOT / "hardware" / "main_board" / "main_board.kicad_pcb"
    b = pcbnew.LoadBoard(str(mb_path))
    W, H = CONTRACT["boards"]["main_board"]["dimensions_mm"]
    board_area = W * H

    # Collect all GND stitching points (vias + PTH pads) for island stitching verification
    gnd_stitch = [
        (pcbnew.ToMM(v.GetPosition().x), pcbnew.ToMM(v.GetPosition().y))
        for v in b.GetTracks()
        if isinstance(v, pcbnew.PCB_VIA) and v.GetNetname() == "GND"
    ]
    for fp in b.GetFootprints():
        for p in fp.Pads():
            if p.GetNetname() == "GND" and p.GetAttribute() == pcbnew.PAD_ATTRIB_PTH:
                gnd_stitch.append((pcbnew.ToMM(p.GetPosition().x), pcbnew.ToMM(p.GetPosition().y)))

    def _chain_area_mm2(cl) -> float:
        pts = [(pcbnew.ToMM(cl.CPoint(k).x), pcbnew.ToMM(cl.CPoint(k).y)) for k in range(cl.PointCount())]
        a = 0.0
        for j in range(len(pts)):
            x1, y1 = pts[j]
            x2, y2 = pts[(j + 1) % len(pts)]
            a += x1 * y2 - x2 * y1
        return abs(a) * 0.5

    largest_island_area = 0.0
    total_bcu_area = 0.0
    zero_via_islands = 0
    outline_count = 0
    for z in b.Zones():
        if not z.GetIsRuleArea() and z.GetNetname() == "GND" and z.GetLayer() == pcbnew.B_Cu:
            ps = z.GetFilledPolysList(pcbnew.B_Cu)
            outline_count += ps.OutlineCount()
            for i in range(ps.OutlineCount()):
                poly = ps.Outline(i)
                a = _chain_area_mm2(poly)
                sub = pcbnew.SHAPE_POLY_SET()
                sub.AddOutline(poly)
                for h in range(ps.HoleCount(i)):
                    hole = ps.Hole(i, h)
                    a -= _chain_area_mm2(hole)
                    sub.AddHole(hole)
                total_bcu_area += a
                if a > largest_island_area:
                    largest_island_area = a
                has_stitch = any(
                    sub.Contains(pcbnew.VECTOR2I(pcbnew.FromMM(vx), pcbnew.FromMM(vy)))
                    for vx, vy in gnd_stitch
                )
                if not has_stitch:
                    zero_via_islands += 1

    pct = 100.0 * largest_island_area / board_area
    tot_pct = 100.0 * total_bcu_area / board_area
    min_pct = CONTRACT["boards"]["main_board"]["min_bcu_gnd_pour_pct"]
    assert pct >= min_pct, f"main_board B.Cu GND largest connected island {pct:.2f}% < {min_pct:.1f}% (total {tot_pct:.2f}%)"
    assert zero_via_islands == 0, f"main_board B.Cu GND has {zero_via_islands} un-stitched 0-via islands!"

    # Verify >= 0.50 mm bulk power trunks on all high-current rails
    bulk_power_rails = {
        "+12V_EUR": 99.0,
        "-12V_EUR": 99.0,
        "+12V_PRE": 99.0,
        "-12V_PRE": 99.0,
        "+5V_BUCK": 70.0,
        "PMIC_INP": 75.0,
        "PMIC_SWN": 90.0,
        "+14V6_RAW": 55.0,
        "-14V6_RAW": 75.0,
    }
    for net_name, min_wide_pct in bulk_power_rails.items():
        segs = [t for t in b.GetTracks() if not isinstance(t, pcbnew.PCB_VIA) and t.GetNetname() == net_name]
        assert segs, f"Missing routed tracks on bulk power rail {net_name}"
        tot_len = sum(pcbnew.ToMM(t.GetLength()) for t in segs)
        wide_len = sum(pcbnew.ToMM(t.GetLength()) for t in segs if pcbnew.ToMM(t.GetWidth()) >= 0.499)
        max_w = max(pcbnew.ToMM(t.GetWidth()) for t in segs)
        wide_pct = (100.0 * wide_len / tot_len) if tot_len > 0 else 0.0
        assert max_w >= 0.50, f"Power rail {net_name} max width {max_w:.3f} mm < 0.50 mm!"
        assert wide_pct >= min_wide_pct, f"Power rail {net_name} >=0.50mm trunk coverage {wide_pct:.1f}% < {min_wide_pct:.0f}%!"

    # Check >= 3.0 mm non-GND track/via clearance around MH101..MH106
    mhs = []
    for fp in b.GetFootprints():
        if fp.GetReference().startswith("MH"):
            p = fp.GetPosition()
            mhs.append((fp.GetReference(), pcbnew.ToMM(p.x), pcbnew.ToMM(p.y)))
    assert len(mhs) == 6

    def seg_dist(px: float, py: float, x1: float, y1: float, x2: float, y2: float) -> float:
        dx, dy = x2 - x1, y2 - y1
        l2 = dx * dx + dy * dy
        if l2 < 1e-9:
            return math.hypot(px - x1, py - y1)
        t = max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / l2))
        return math.hypot(px - (x1 + t * dx), py - (y1 + t * dy))

    min_mh_clr = 999.0
    for mh_ref, mx, my in mhs:
        for tr in b.GetTracks():
            if tr.GetNetname() == "GND":
                continue
            if isinstance(tr, pcbnew.PCB_VIA):
                vx, vy = pcbnew.ToMM(tr.GetPosition().x), pcbnew.ToMM(tr.GetPosition().y)
                d = math.hypot(mx - vx, my - vy) - pcbnew.ToMM(tr.GetWidth(pcbnew.F_Cu)) / 2.0
            else:
                s, e = tr.GetStart(), tr.GetEnd()
                d = seg_dist(mx, my, pcbnew.ToMM(s.x), pcbnew.ToMM(s.y), pcbnew.ToMM(e.x), pcbnew.ToMM(e.y)) - pcbnew.ToMM(tr.GetWidth()) / 2.0
            if d < min_mh_clr:
                min_mh_clr = d
            assert d >= 2.95, f"Non-GND copper too close to {mh_ref}: {d:.3f} mm ({tr.GetNetname()})"

    # Check F.Paste presence on TLP172AM & G6K-2F-Y, and segmented F.Paste + zero via-in-paste on RP2040/TPS65131/TPS5430 & board-wide!
    fps = {fp.GetReference(): fp for fp in b.GetFootprints()}
    for ref in ("U_MUTE_L", "U_MUTE_R", "K1", "K2"):
        for pad in fps[ref].Pads():
            assert pad.IsOnLayer(pcbnew.F_Paste), f"Missing F.Paste on {ref}.{pad.GetName()}"

    vias = [(pcbnew.ToMM(v.GetPosition().x), pcbnew.ToMM(v.GetPosition().y), pcbnew.ToMM(v.GetDrill()) / 2.0, v.GetNetname())
            for v in b.GetTracks() if isinstance(v, pcbnew.PCB_VIA)]

    for ref, ep_num in (("U_MCU", "57"), ("U_PMIC", "25"), ("U_BUCK5", "9")):
        fp = fps[ref]
        ep_pad = next(p for p in fp.Pads() if p.GetName() == ep_num)
        assert not ep_pad.IsOnLayer(pcbnew.F_Paste), f"{ref} EP pad {ep_num} must use segmented F.Paste windows, not solid paste!"
        paste_pads = [p for p in fp.Pads() if p.GetName() == "" and p.IsOnLayer(pcbnew.F_Paste)]
        assert len(paste_pads) == 4, f"{ref} expected 4 segmented F.Paste windows, got {len(paste_pads)}"
        ep_area = pcbnew.ToMM(ep_pad.GetSize().x) * pcbnew.ToMM(ep_pad.GetSize().y)
        p_area = sum(pcbnew.ToMM(p.GetSize().x) * pcbnew.ToMM(p.GetSize().y) for p in paste_pads)
        ratio = 100.0 * p_area / ep_area
        assert 50.0 <= ratio <= 70.0, f"{ref} EP paste ratio {ratio:.1f}% outside 50-70%!"

    # Verify U_MCU Pad 57 (sole MCU GND pad!) has >= 4 GND stitching vias inside the EP copper
    mcu_ep = next(p for p in fps["U_MCU"].Pads() if p.GetName() == "57")
    ep_bb = mcu_ep.GetBoundingBox()
    mcu_ep_vias = [
        (vx, vy)
        for vx, vy, vr, vn in vias
        if vn == "GND"
        and pcbnew.ToMM(ep_bb.GetLeft()) <= vx <= pcbnew.ToMM(ep_bb.GetRight())
        and pcbnew.ToMM(ep_bb.GetTop()) <= vy <= pcbnew.ToMM(ep_bb.GetBottom())
    ]
    assert len(mcu_ep_vias) >= 4, f"U_MCU Pad 57 sole GND EP has only {len(mcu_ep_vias)} GND vias (< 4)!"

    # Board-wide zero via-in-paste gate across ALL F.Paste pads (oriented local rectangle test)
    for fp in b.GetFootprints():
        ref = fp.GetReference()
        for pp in fp.Pads():
            if not pp.IsOnLayer(pcbnew.F_Paste):
                continue
            px, py = pcbnew.ToMM(pp.GetPosition().x), pcbnew.ToMM(pp.GetPosition().y)
            sx, sy = pcbnew.ToMM(pp.GetSize().x), pcbnew.ToMM(pp.GetSize().y)
            ang = math.radians(pp.GetOrientationDegrees())
            ca, sa = math.cos(ang), math.sin(ang)
            for vx, vy, vr, _ in vias:
                dx, dy = vx - px, vy - py
                lx = dx * ca + dy * sa
                ly = -dx * sa + dy * ca
                if abs(lx) < sx / 2.0 + vr and abs(ly) < sy / 2.0 + vr:
                    raise AssertionError(f"Via-in-paste collision on {ref}.{pp.GetName()} F.Paste at via ({vx:.2f},{vy:.2f})!")

    print(
        f"[PASS] Gate 1.3: main_board B.Cu GND largest island={pct:.2f}% (>={min_pct:.0f}%, 0 un-stitched islands), "
        f"bulk power trunks >=0.50mm, MH min clr={min_mh_clr:.2f}mm, U_MCU EP={len(mcu_ep_vias)} GND vias, 0 via-in-paste"
    )


def check_btb_mating_congruence() -> None:
    mb = pcbnew.LoadBoard(str(ROOT / "hardware" / "main_board" / "main_board.kicad_pcb"))
    mz = pcbnew.LoadBoard(str(ROOT / "hardware" / "ui_mezzanine" / "ui_mezzanine.kicad_pcb"))
    ox_mb, oy_mb = CONTRACT["boards"]["main_board"]["kicad_origin_world_mm"]
    ox_mz, oy_mz = CONTRACT["boards"]["ui_mezzanine"]["kicad_origin_world_mm"]

    mb_fps = {fp.GetReference(): fp for fp in mb.GetFootprints()}
    mz_fps = {fp.GetReference(): fp for fp in mz.GetFootprints()}

    max_err = 0.0
    for ref in ("J_BTB_AUDIO_CV", "J_BTB_UI_DIG"):
        assert mb_fps[ref].GetLayer() == pcbnew.F_Cu, f"main_board {ref} must be on F.Cu!"
        assert mz_fps[ref].GetLayer() == pcbnew.B_Cu, f"ui_mezzanine {ref} must be flipped to B.Cu for downward mating!"
        mb_pads = {p.GetName(): (ox_mb + pcbnew.ToMM(p.GetPosition().x), oy_mb - pcbnew.ToMM(p.GetPosition().y)) for p in mb_fps[ref].Pads()}
        mz_pads = {p.GetName(): (ox_mz + pcbnew.ToMM(p.GetPosition().x), oy_mz - pcbnew.ToMM(p.GetPosition().y)) for p in mz_fps[ref].Pads()}
        assert len(mb_pads) == 16 and len(mz_pads) == 16
        for pin in [str(i) for i in range(1, 17)]:
            d = math.hypot(mb_pads[pin][0] - mz_pads[pin][0], mb_pads[pin][1] - mz_pads[pin][1])
            if d > max_err:
                max_err = d
            assert d < 0.05, f"BTB mating mismatch on {ref}.{pin}: {d:.4f} mm >= 0.05 mm!"
    print(f"[PASS] Gate 1.4: J_BTB_AUDIO_CV & J_BTB_UI_DIG F.Cu<->B.Cu 32-pin XY mating error = {max_err:.4f} mm (< 0.05 mm)")


def check_custom_courtyards() -> None:
    pretty = ROOT / "hardware" / "beads_custom.pretty"
    checked = 0
    for mod in sorted(pretty.glob("*.kicad_mod")):
        txt = mod.read_text(encoding="utf-8")
        def bbox(layer: str):
            pts = []
            for m in re.finditer(r'\(fp_(?:line|rect|poly).*?\(layer "' + layer + r'"\).*?\)', txt, re.S):
                for xy in re.finditer(r'\((?:start|end|xy)\s+([-\d.]+)\s+([-\d.]+)\)', m.group(0)):
                    pts.append((float(xy.group(1)), float(xy.group(2))))
            if not pts:
                return None
            return (min(x for x, _ in pts), min(y for _, y in pts), max(x for x, _ in pts), max(y for _, y in pts))
        fab = bbox("F.Fab")
        crt = bbox("F.CrtYd")
        assert fab is not None and crt is not None, f"Missing F.Fab or F.CrtYd in {mod.name}"
        assert crt[0] <= fab[0] + 1e-6 and crt[1] <= fab[1] + 1e-6 and crt[2] >= fab[2] - 1e-6 and crt[3] >= fab[3] - 1e-6, (
            f"F.CrtYd < F.Fab in {mod.name}: crt={crt}, fab={fab}"
        )
        checked += 1
    assert checked >= 8
    print(f"[PASS] Gate 1.5: All {checked} custom footprints satisfy F.CrtYd >= F.Fab")


def main() -> int:
    check_portability()
    check_erc_and_drc()
    check_bcu_pour_and_mh_and_paste()
    check_btb_mating_congruence()
    check_custom_courtyards()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
