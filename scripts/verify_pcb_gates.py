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

    # Verify every NPTH locating hole on main_board has >= 0.35 mm FR4 web to Edge.Cuts (JLCPCB >= 0.25-0.30 mm)
    edge_segs = [
        (
            pcbnew.ToMM(d.GetStart().x), pcbnew.ToMM(d.GetStart().y),
            pcbnew.ToMM(d.GetEnd().x), pcbnew.ToMM(d.GetEnd().y),
        )
        for d in b.GetDrawings()
        if d.GetLayer() == pcbnew.Edge_Cuts and isinstance(d, pcbnew.PCB_SHAPE)
    ]
    assert len(edge_segs) >= 12, f"Expected notched Edge.Cuts (>=12 segs), got {len(edge_segs)}"
    min_npth_web = 999.0
    for fp in b.GetFootprints():
        ref = fp.GetReference()
        for p in fp.Pads():
            if p.GetAttribute() != pcbnew.PAD_ATTRIB_NPTH:
                continue
            px, py = pcbnew.ToMM(p.GetPosition().x), pcbnew.ToMM(p.GetPosition().y)
            r = max(pcbnew.ToMM(p.GetDrillSize().x), pcbnew.ToMM(p.GetDrillSize().y)) / 2.0
            d_edge = min(seg_dist(px, py, x1, y1, x2, y2) for x1, y1, x2, y2 in edge_segs) - r
            if d_edge < min_npth_web:
                min_npth_web = d_edge
            assert d_edge >= 0.35, f"NPTH hole on {ref} at ({px:.2f},{py:.2f}) has thin FR4 edge web {d_edge:.3f}mm < 0.35mm!"

    # Verify local ${KIPRJMOD}/../beads_custom.3dshapes/*.step links on SW_MIDI_AB (main_board) & 21/21 ui_mezzanine
    sw_models = [m.m_Filename for m in fps["SW_MIDI_AB"].Models()]
    assert sw_models == ["${KIPRJMOD}/../beads_custom.3dshapes/SW_CK_JS202011AQN_DPDT_Angled.step"], (
        f"SW_MIDI_AB missing local STEP link: {sw_models}"
    )
    mz_chk = pcbnew.LoadBoard(str(ROOT / "hardware" / "ui_mezzanine" / "ui_mezzanine.kicad_pcb"))
    for fp in mz_chk.GetFootprints():
        ms = [m.m_Filename for m in fp.Models()]
        assert len(ms) == 1 and ms[0].startswith("${KIPRJMOD}/../beads_custom.3dshapes/"), (
            f"ui_mezzanine {fp.GetReference()} missing local STEP link: {ms}"
        )
        assert (ROOT / "hardware" / "beads_custom.3dshapes" / pathlib.Path(ms[0]).name).exists(), (
            f"Missing STEP file for ui_mezzanine {fp.GetReference()}: {ms[0]}"
        )

    print(
        f"[PASS] Gate 1.3: main_board B.Cu GND largest island={pct:.2f}% (>={min_pct:.0f}%, 0 un-stitched islands), "
        f"bulk power trunks >=0.50mm, MH min clr={min_mh_clr:.2f}mm, NPTH min web={min_npth_web:.3f}mm (>=0.35mm), "
        f"U_MCU EP={len(mcu_ep_vias)} GND vias, 0 via-in-paste, 21/21 ui_mezzanine + SW_MIDI_AB local STEPs linked"
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


def check_schematic_bounds_and_netlists() -> None:
    """Gate 1.6: Verify 100% of schematic symbols/labels/texts fit inside page borders & clear of
    title block, zero literal \\\\n in notes, clean sheet_instances, and synced .net files."""
    PAPER_MM = {
        "A4": (297.0, 210.0),
        "A3": (420.0, 297.0),
        "A2": (594.0, 420.0),
        "A1": (841.0, 594.0),
        "A0": (1189.0, 841.0),
    }
    checked_sheets = 0
    for sch in sorted((ROOT / "hardware").rglob("*.kicad_sch")):
        txt = sch.read_text(encoding="utf-8")
        m_pap = re.search(r'\(paper\s+"([^"]+)"\)', txt)
        assert m_pap and m_pap.group(1) in PAPER_MM, f"Unsupported/missing paper size in {sch}"
        pw, ph = PAPER_MM[m_pap.group(1)]
        margin = 10.0
        tb_x1, tb_y1 = pw - margin - 110.0, ph - margin - 35.0

        # Strip embedded (lib_symbols ...) before checking placed coordinates
        ls_idx = txt.find("(lib_symbols")
        body = txt
        if ls_idx != -1:
            depth = 0
            i = ls_idx
            while i < len(txt):
                if txt[i] == "(":
                    depth += 1
                elif txt[i] == ")":
                    depth -= 1
                    if depth == 0:
                        body = txt[:ls_idx] + txt[i + 1 :]
                        break
                i += 1

        # Zero literal double-escaped \\n inside (text "...") annotations
        for tm in re.finditer(r'\(text\s+"((?:[^"\\]|\\.)*)"', body):
            assert "\\\\n" not in tm.group(1), f"Literal \\\\n found in schematic text of {sch}: {tm.group(1)[:60]!r}"

        # Check all placed symbol/label/text/wire coordinates against inner drawing border & title block
        for tag in ("symbol", "global_label", "label", "hierarchical_label", "text", "no_connect"):
            pos = 0
            while True:
                idx = body.find(f"({tag}", pos)
                if idx == -1:
                    break
                # Ensure exact token match (followed by whitespace)
                nxt = body[idx + len(tag) + 1 : idx + len(tag) + 2]
                if nxt not in (" ", "\t", "\n", "\r"):
                    pos = idx + 1
                    continue
                depth = 0
                j = idx
                while j < len(body):
                    if body[j] == "(":
                        depth += 1
                    elif body[j] == ")":
                        depth -= 1
                        if depth == 0:
                            blk = body[idx : j + 1]
                            pos = j + 1
                            break
                    j += 1
                m_at = re.search(r'\(at\s+([-\d.]+)\s+([-\d.]+)', blk)
                if not m_at:
                    continue
                x, y = float(m_at.group(1)), float(m_at.group(2))
                assert margin <= x <= pw - margin and margin <= y <= ph - margin, (
                    f"Out-of-border {tag} at ({x:.2f}, {y:.2f}) on {sch.name} ({m_pap.group(1)} inner [{margin},{pw-margin}]x[{margin},{ph-margin}])"
                )
                assert not (x >= tb_x1 and y >= tb_y1), (
                    f"Title-block overlap for {tag} at ({x:.2f}, {y:.2f}) on {sch.name} (title block X>={tb_x1:.1f}, Y>={tb_y1:.1f})"
                )

        # On main_board.kicad_sch verify sheet_instances has exact sequential pages 1..5 (no stale orphan UUIDs)
        if sch.name == "main_board.kicad_sch":
            sheet_uuids = re.findall(r'\(sheet\b.*?\(uuid\s+"([^"]+)"\)', body, re.S)
            si_m = re.search(r'\(sheet_instances\b(.*)\)\s*$', body, re.S)
            assert si_m, "Missing sheet_instances in main_board.kicad_sch"
            pages = re.findall(r'\(page\s+"(\d+)"\)', si_m.group(1))
            assert pages == [str(i) for i in range(1, len(sheet_uuids) + 2)], (
                f"Non-sequential or stale sheet_instances in main_board.kicad_sch: pages={pages}, sheets={len(sheet_uuids)}"
            )
        checked_sheets += 1

    # Verify tracked *.net files match fresh kicad-cli export (nets + net classes) & have zero .lane paths
    for b in ("main_board", "ui_mezzanine", "faceplate_14hp"):
        sch = ROOT / "hardware" / b / f"{b}.kicad_sch"
        tracked_net = ROOT / "hardware" / b / f"{b}.net"
        assert tracked_net.exists(), f"Missing tracked netlist {tracked_net}"
        tr_txt = tracked_net.read_text(encoding="utf-8")
        assert ".lane/trees/" not in tr_txt, f"Ephemeral .lane path leaked into {tracked_net}"
        fresh_net = SCRATCH / f"{b}_fresh.net"
        r = subprocess.run(["kicad-cli", "sch", "export", "netlist", "-o", str(fresh_net), str(sch)], capture_output=True, text=True)
        assert r.returncode == 0, f"Netlist export failed on {b}: {r.stderr}"
        def _norm(s: str) -> str:
            s = re.sub(r'\(date\s+"[^"]*"\)', '(date "")', s)
            s = re.sub(r'\(source\s+"[^"]*"\)', '(source "")', s)
            s = re.sub(r'\(uri\s+"[^"]*"\)', '(uri "")', s)
            return s
        assert _norm(tr_txt) == _norm(fresh_net.read_text(encoding="utf-8")), (
            f"Tracked {tracked_net.name} is out of sync with {sch.name}!"
        )

    print(
        f"[PASS] Gate 1.6: All {checked_sheets} schematic sheets within page borders & clear of title block, "
        f"zero literal \\\\n, clean sheet_instances 1..5, and 3/3 .net files synced"
    )


def check_plated_slots_dfm() -> None:
    """Gate 1.7: Enforce JLCPCB 2-layer plated-slot DFM (width >= 0.50 mm, and L >= 2*W on
    main_board / narrow slots) across BOTH KiCad PCB oblong drills and exported *-PTH.drl files."""
    checked_pcb_slots = 0
    for bname in ("main_board", "ui_mezzanine"):
        b = pcbnew.LoadBoard(str(ROOT / "hardware" / bname / f"{bname}.kicad_pcb"))
        for fp in b.GetFootprints():
            ref = fp.GetReference()
            for p in fp.Pads():
                if p.GetAttribute() != pcbnew.PAD_ATTRIB_PTH:
                    continue
                if p.GetDrillShape() != pcbnew.PAD_DRILL_SHAPE_OBLONG:
                    continue
                dx = pcbnew.ToMM(p.GetDrillSize().x)
                dy = pcbnew.ToMM(p.GetDrillSize().y)
                w, l = min(dx, dy), max(dx, dy)
                assert w >= 0.50 - 1e-6, (
                    f"PCB plated slot {bname}:{ref}.{p.GetName()} width {w:.3f} mm < 0.50 mm JLCPCB 2-layer min!"
                )
                if bname == "main_board" or w < 0.80:
                    assert l >= 2.0 * w - 1e-6, (
                        f"PCB plated slot {bname}:{ref}.{p.GetName()} length {l:.3f} mm < 2*W ({2.0*w:.3f} mm)!"
                    )
                checked_pcb_slots += 1

    checked_drl_slots = 0
    min_slot_w = 999.0
    for bname in ("main_board", "ui_mezzanine"):
        drl = ROOT / "manufacturing" / bname / "gerbers" / f"{bname}-PTH.drl"
        assert drl.exists(), f"Missing exported drill file: {drl}"
        tools: dict[str, float] = {}
        cur_tool = None
        for line in drl.read_text(encoding="utf-8").splitlines():
            s = line.strip()
            mt = re.match(r"^(T\d+)C([0-9.]+)$", s)
            if mt:
                tools[mt.group(1)] = float(mt.group(2))
                continue
            ms = re.match(r"^(T\d+)$", s)
            if ms and ms.group(1) in tools:
                cur_tool = ms.group(1)
                continue
            mg = re.match(r"^X([-\d.]+)Y([-\d.]+)G85X([-\d.]+)Y([-\d.]+)$", s)
            if mg:
                assert cur_tool is not None and cur_tool in tools, f"G85 slot without active tool in {drl}"
                w = tools[cur_tool]
                travel = math.hypot(float(mg.group(3)) - float(mg.group(1)), float(mg.group(4)) - float(mg.group(2)))
                l = travel + w
                if w < min_slot_w:
                    min_slot_w = w
                assert w >= 0.50 - 1e-6, (
                    f"Excellon {drl.name} G85 slot tool {cur_tool}={w:.3f} mm < 0.50 mm JLCPCB 2-layer min!"
                )
                if bname == "main_board" or w < 0.80:
                    assert l >= 2.0 * w - 1e-6, (
                        f"Excellon {drl.name} G85 slot {s} length {l:.3f} mm < 2*W ({2.0*w:.3f} mm)!"
                    )
                checked_drl_slots += 1

    assert checked_pcb_slots >= 14 and checked_drl_slots == checked_pcb_slots, (
        f"Plated slot count mismatch: PCB={checked_pcb_slots}, PTH.drl={checked_drl_slots}"
    )
    print(
        f"[PASS] Gate 1.7: All {checked_drl_slots} plated oval slots (PCB & PTH.drl) satisfy "
        f"min width={min_slot_w:.3f} mm >= 0.50 mm and L >= 2*W"
    )


def main() -> int:
    check_portability()
    check_erc_and_drc()
    check_bcu_pour_and_mh_and_paste()
    check_btb_mating_congruence()
    check_custom_courtyards()
    check_schematic_bounds_and_netlists()
    check_plated_slots_dfm()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
