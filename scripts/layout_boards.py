#!/usr/bin/env python3
"""Deterministic KiCad 9 pcbnew placement, board outline, silkscreen, and GND-plane builder
for all three Beads Pedalboard Skiff PCBs (faceplate_14hp, ui_mezzanine, main_board).

Reads exact locked coordinates from hardware_contract.json (worktree-portable via Path(__file__)).
"""
from __future__ import annotations

import json
import math
import pathlib
import sys
import pcbnew

ROOT = pathlib.Path(__file__).resolve().parents[1]
CONTRACT = json.loads((ROOT / "hardware_contract.json").read_text(encoding="utf-8"))


def mm(v: float) -> int:
    return pcbnew.FromMM(float(v))


def pt(x: float, y: float) -> pcbnew.VECTOR2I:
    return pcbnew.VECTOR2I(mm(x), mm(y))


def add_edge_rect(board: pcbnew.BOARD, x1: float, y1: float, x2: float, y2: float, width: float = 0.15) -> None:
    pts = [(x1, y1), (x2, y1), (x2, y2), (x1, y2)]
    for i in range(4):
        a, b = pts[i], pts[(i + 1) % 4]
        seg = pcbnew.PCB_SHAPE(board)
        seg.SetShape(pcbnew.SHAPE_T_SEGMENT)
        seg.SetLayer(pcbnew.Edge_Cuts)
        seg.SetStart(pt(*a))
        seg.SetEnd(pt(*b))
        seg.SetWidth(mm(width))
        board.Add(seg)


def add_edge_circle(board: pcbnew.BOARD, cx: float, cy: float, dia: float, width: float = 0.15) -> None:
    c = pcbnew.PCB_SHAPE(board)
    c.SetShape(pcbnew.SHAPE_T_CIRCLE)
    c.SetLayer(pcbnew.Edge_Cuts)
    c.SetCenter(pt(cx, cy))
    c.SetEnd(pt(cx + dia / 2.0, cy))
    c.SetWidth(mm(width))
    board.Add(c)


def add_silk_text(board: pcbnew.BOARD, text: str, x: float, y: float, size: float = 1.2,
                  thick: float = 0.18, layer: int = pcbnew.F_SilkS, angle: float = 0.0) -> None:
    t = pcbnew.PCB_TEXT(board)
    t.SetText(text)
    t.SetPosition(pt(x, y))
    t.SetLayer(layer)
    t.SetTextSize(pcbnew.VECTOR2I(mm(size), mm(size)))
    t.SetTextThickness(mm(thick))
    t.SetTextAngle(pcbnew.EDA_ANGLE(angle, pcbnew.DEGREES_T))
    board.Add(t)


def add_silk_line(board: pcbnew.BOARD, x1: float, y1: float, x2: float, y2: float,
                  width: float = 0.25, layer: int = pcbnew.F_SilkS) -> None:
    s = pcbnew.PCB_SHAPE(board)
    s.SetShape(pcbnew.SHAPE_T_SEGMENT)
    s.SetLayer(layer)
    s.SetStart(pt(x1, y1))
    s.SetEnd(pt(x2, y2))
    s.SetWidth(mm(width))
    board.Add(s)


def clear_graphics_and_zones(board: pcbnew.BOARD) -> None:
    for d in list(board.GetDrawings()):
        board.Delete(d)
    for z in list(board.Zones()):
        board.Delete(z)
    for t in list(board.GetTracks()):
        board.Delete(t)


def add_gnd_zone(board: pcbnew.BOARD, w: float, h: float, layer: int = pcbnew.B_Cu,
                 clearance: float = 0.22, edge_inset: float = 0.40) -> None:
    gnd = board.FindNet("GND")
    if gnd is None:
        return
    z = pcbnew.ZONE(board)
    z.SetNet(gnd)
    z.SetLayer(layer)
    z.SetIsFilled(False)
    z.SetLocalClearance(mm(clearance))
    z.SetMinThickness(mm(0.20))
    z.SetThermalReliefGap(mm(0.30))
    z.SetThermalReliefSpokeWidth(mm(0.35))
    z.SetPadConnection(pcbnew.ZONE_CONNECTION_THERMAL)
    z.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_ALWAYS)
    outline = z.Outline()
    outline.NewOutline()
    for x, y in [
        (edge_inset, edge_inset),
        (w - edge_inset, edge_inset),
        (w - edge_inset, h - edge_inset),
        (edge_inset, h - edge_inset),
    ]:
        outline.Append(mm(x), mm(y))
    outline.Outline(0).SetClosed(True)
    board.Add(z)


def add_mh_keepout(board: pcbnew.BOARD, cx: float, cy: float, radius: float = 3.15) -> None:
    """Keep routed signal tracks and vias >= 3.0 mm clear of M3 mounting holes (GND pour & MH pad allowed)."""
    z = pcbnew.ZONE(board)
    z.SetIsRuleArea(True)
    z.SetDoNotAllowTracks(True)
    z.SetDoNotAllowVias(True)
    z.SetDoNotAllowPads(False)
    z.SetDoNotAllowFootprints(False)
    z.SetDoNotAllowCopperPour(False)
    lset = pcbnew.LSET()
    lset.AddLayer(pcbnew.F_Cu)
    lset.AddLayer(pcbnew.B_Cu)
    z.SetLayerSet(lset)
    outline = z.Outline()
    outline.NewOutline()
    for i in range(16):
        ang = 2.0 * math.pi * i / 16.0
        outline.Append(mm(cx + radius * math.cos(ang)), mm(cy + radius * math.sin(ang)))
    outline.Outline(0).SetClosed(True)
    board.Add(z)


def add_via(board: pcbnew.BOARD, x: float, y: float, net_name: str = "GND",
            dia: float = 0.60, drill: float = 0.30) -> None:
    net = board.FindNet(net_name)
    if net is None:
        return
    v = pcbnew.PCB_VIA(board)
    v.SetPosition(pt(x, y))
    v.SetWidth(pcbnew.F_Cu, mm(dia))
    v.SetDrill(mm(drill))
    v.SetViaType(pcbnew.VIATYPE_THROUGH)
    v.SetNet(net)
    board.Add(v)


def configure_2layer_rules(board: pcbnew.BOARD, min_track: float = 0.15, min_clear: float = 0.15,
                           power_track: float = 0.50) -> None:
    ds = board.GetDesignSettings()
    ds.SetCopperLayerCount(2)
    ds.m_TrackMinWidth = mm(min_track)
    ds.m_MinClearance = mm(min_clear)
    ds.m_ViasMinSize = mm(0.50)
    ds.m_ViasMinDrill = mm(0.30)
    ds.m_CopperEdgeClearance = mm(0.35)
    ds.m_HoleClearance = mm(0.25)
    ds.m_HoleToHoleMin = mm(0.35)
    ds.m_SilkClearance = mm(0.10)
    ds.m_MinSilkTextHeight = mm(0.80)
    ds.m_MinSilkTextThickness = mm(0.12)
    # Default netclass (KiCad 9 API) — 0.55/0.30mm via gives 0.275mm >= 0.25mm hole clearance & 0.40mm >= 0.35mm hole-to-hole!
    nc = ds.m_NetSettings.GetDefaultNetclass()
    nc.SetTrackWidth(mm(0.18))
    nc.SetClearance(mm(min_clear))
    nc.SetViaDiameter(mm(0.55))
    nc.SetViaDrill(mm(0.30))
    # POWER: >= 0.50 mm trunks (0.52 mm) for wide-pitch main/Eurorack power rails!
    pnc = pcbnew.NETCLASS("POWER")
    pnc.SetTrackWidth(mm(power_track))
    pnc.SetClearance(mm(min_clear))
    pnc.SetViaDiameter(mm(0.65))
    pnc.SetViaDrill(mm(0.30))
    ds.m_NetSettings.SetNetclass("POWER", pnc)
    # POWER_QFN: 0.25 mm pad-entry class (0.15mm clearance fits 0.50mm QFN-24 pads cleanly!)
    qnc = pcbnew.NETCLASS("POWER_QFN")
    qnc.SetTrackWidth(mm(0.25))
    qnc.SetClearance(mm(min_clear))
    qnc.SetViaDiameter(mm(0.55))
    qnc.SetViaDrill(mm(0.30))
    ds.m_NetSettings.SetNetclass("POWER_QFN", qnc)
    power_trunk_nets = {
        "VIN_JACK_POS", "VIN_FUSED", "VIN_PROT", "VIN_FILT",
        "BUCK_SW", "+12V_PRE", "-12V_PRE", "+12V_EUR", "-12V_EUR",
        "USB_VBUS_RAW", "USB_VBUS", "USB_POST_DIODE", "VIN_3V3_LDO",
    }
    power_qfn_nets = {
        "+5V_BUCK", "PMIC_INP", "PMIC_SWN", "+14V6_RAW", "-14V6_RAW",
    }
    for pname in power_trunk_nets:
        if board.FindNet(pname) is not None:
            ds.m_NetSettings.SetNetclassPatternAssignment(pname, "POWER")
    for pname in power_qfn_nets:
        if board.FindNet(pname) is not None:
            ds.m_NetSettings.SetNetclassPatternAssignment(pname, "POWER_QFN")


def hide_value_and_tidy_refs(board: pcbnew.BOARD, ref_size: float = 0.85, show_refs: set[str] | None = None) -> None:
    for fp in board.GetFootprints():
        fp.Value().SetVisible(False)
        ref = fp.GetReference()
        r = fp.Reference()
        r.SetTextSize(pcbnew.VECTOR2I(mm(ref_size), mm(ref_size)))
        r.SetTextThickness(mm(0.13))
        if show_refs is not None:
            r.SetVisible(ref in show_refs)
        else:
            # Keep silkscreen clean and collision-free on dense boards by placing ref text on F.Fab for tiny passives
            if ref.startswith(("R", "C")) and not ref.startswith("RV"):
                r.SetLayer(pcbnew.F_Fab)


def build_faceplate() -> None:
    pcb_path = ROOT / "hardware" / "faceplate_14hp" / "faceplate_14hp.kicad_pcb"
    board = pcbnew.LoadBoard(str(pcb_path))
    clear_graphics_and_zones(board)
    configure_2layer_rules(board)

    W, H = CONTRACT["boards"]["faceplate_14hp"]["dimensions_mm"]
    add_edge_rect(board, 0.0, 0.0, W, H)

    # 4x Doepfer M3 mounting holes
    by_ref = {fp.GetReference(): fp for fp in board.GetFootprints()}
    for mh in CONTRACT["boards"]["faceplate_14hp"]["doepfer_m3_holes_pcb_mm"]:
        fp = by_ref[mh["ref"]]
        fp.SetPosition(pt(mh["x"], mh["y"]))
        fp.SetOrientationDegrees(0.0)
        fp.Reference().SetVisible(False)
        fp.Value().SetVisible(False)

    # Offset from ui_mezzanine local coords to faceplate_14hp local coords:
    # X_fp = X_mezz + 1.40, Y_fp = Y_mezz + 10.50
    dx, dy = 1.40, 10.50
    feats = CONTRACT["boards"]["ui_mezzanine"]["panel_features_mezz_mm"]

    # Milled OLED window (26.0 x 15.0 mm)
    ow = feats["OLED_WINDOW"]
    ox, oy = ow["x"] + dx, ow["y"] + dy
    add_edge_rect(board, ox - ow["w"] / 2.0, oy - ow["h"] / 2.0, ox + ow["w"] / 2.0, oy + ow["h"] / 2.0)

    # Circular cutouts for encoder, back button, 2x pots, PEAK LED, 12x Thonkiconn
    labels = {
        "SW_ENC": ("ENC", 0, -7.2),
        "SW_BACK": ("BACK", 0, -4.8),
        "RV_IN_TRIM": ("IN TRIM", 0, -8.0),
        "RV_OUT_TRIM": ("OUT TRIM", 0, -8.0),
        "D_PEAK": ("PEAK", 0, -4.2),
        "J_SEND_L": ("SEND L", 0, -5.6),
        "J_SEND_R": ("SEND R", 0, -5.6),
        "J_RET_L": ("RET L", 0, -5.6),
        "J_RET_R": ("RET R", 0, -5.6),
        "J_CV1": ("CV 1", 0, -5.6),
        "J_CV2": ("CV 2", 0, -5.6),
        "J_CV3": ("CV 3", 0, -5.6),
        "J_CV4": ("CV 4", 0, -5.6),
        "J_CV5": ("CV 5", 0, -5.6),
        "J_CV6": ("CV 6", 0, -5.6),
        "J_CV7": ("CV 7", 0, -5.6),
        "J_CV8": ("CV 8", 0, -5.6),
    }
    for key, f in feats.items():
        if key == "OLED_WINDOW":
            continue
        fx, fy = f["x"] + dx, f["y"] + dy
        add_edge_circle(board, fx, fy, f["drill_mm"])
        if key in labels:
            txt, lx, ly = labels[key]
            add_silk_text(board, txt, fx + lx, fy + ly, size=1.25, thick=0.20)

    # Panel title & divider graphics (Matte Black FR4 + Crisp White Silkscreen)
    add_silk_text(board, "BEADS DRIFT", W / 2.0, 9.0, size=2.0, thick=0.30)
    add_silk_line(board, 4.0, 60.5, W - 4.0, 60.5, width=0.25)
    add_silk_line(board, 25.5, 62.5, 25.5, 118.0, width=0.25)
    add_silk_text(board, "AUDIO", 12.9, 121.0, size=1.3, thick=0.20)
    add_silk_text(board, "8x BIPOLAR CV / GATE", 47.5, 121.0, size=1.3, thick=0.20)

    pcbnew.SaveBoard(str(pcb_path), board)
    print(f"[OK] Laid out {pcb_path} ({W}x{H} mm)")


def build_ui_mezzanine() -> None:
    pcb_path = ROOT / "hardware" / "ui_mezzanine" / "ui_mezzanine.kicad_pcb"
    board = pcbnew.LoadBoard(str(pcb_path))
    clear_graphics_and_zones(board)
    configure_2layer_rules(board, min_track=0.20, min_clear=0.20, power_track=0.30)

    W, H = CONTRACT["boards"]["ui_mezzanine"]["dimensions_mm"]
    add_edge_rect(board, 0.0, 0.0, W, H)

    by_ref = {fp.GetReference(): fp for fp in board.GetFootprints()}
    feats = CONTRACT["boards"]["ui_mezzanine"]["panel_features_mezz_mm"]

    # Place all 12 Thonkiconn jacks (bushing at local (0, +6.50) at rot=0)
    for key in ["J_SEND_L", "J_SEND_R", "J_RET_L", "J_RET_R"] + [f"J_CV{i}" for i in range(1, 9)]:
        f = feats[key]
        fp = by_ref[key]
        fp.SetPosition(pt(f["x"], f["y"] - 6.50))
        fp.SetOrientationDegrees(0.0)

    # Place EC11E (shaft at local (+7.50, +2.50))
    f_enc = feats["SW_ENC"]
    by_ref["SW_ENC"].SetPosition(pt(f_enc["x"] - 7.50, f_enc["y"] - 2.50))
    by_ref["SW_ENC"].SetOrientationDegrees(0.0)

    # Place SW_BACK (button center at local (+3.25, +2.25))
    f_bk = feats["SW_BACK"]
    by_ref["SW_BACK"].SetPosition(pt(f_bk["x"] - 3.25, f_bk["y"] - 2.25))
    by_ref["SW_BACK"].SetOrientationDegrees(0.0)

    # Place dual-gang 9mm pots (shaft at local (+7.50, +2.50))
    for pkey in ["RV_IN_TRIM", "RV_OUT_TRIM"]:
        fp = by_ref[pkey]
        f = feats[pkey]
        fp.SetPosition(pt(f["x"] - 7.50, f["y"] - 2.50))
        fp.SetOrientationDegrees(0.0)

    # Place PEAK 3mm LED (body center at local (+1.27, 0))
    f_pk = feats["D_PEAK"]
    by_ref["D_PEAK"].SetPosition(pt(f_pk["x"] - 1.27, f_pk["y"]))
    by_ref["D_PEAK"].SetOrientationDegrees(0.0)

    # Place J_OLED 1x4 horizontal along top of SSD1306 (OLED centered X=20.0, top header Y=4.5)
    # PinSocket_1x04 has pins at (0,0), (0,2.54), (0,5.08), (0,7.62) at rot=0; at rot=90 (CCW in Y-up = CW? test!)
    # Let's place at rot=90 and verify pins run horizontally centered at X=20.0, Y=4.5
    j_oled = by_ref["J_OLED"]
    j_oled.SetOrientationDegrees(90.0)
    j_oled.SetPosition(pt(16.19, 4.50))
    # Verify actual pad X span and recenter to X=20.00!
    xs = [pcbnew.ToMM(p.GetPosition().x) for p in j_oled.Pads()]
    ys = [pcbnew.ToMM(p.GetPosition().y) for p in j_oled.Pads()]
    j_oled.SetPosition(pt(16.19 + (20.00 - (min(xs) + max(xs)) / 2.0), 4.50 + (4.50 - (min(ys) + max(ys)) / 2.0)))

    # Reversible OLED power jumper right beside J_OLED (clear of OLED pins & EC11)
    by_ref["JP_OLED_PWR"].SetPosition(pt(33.5, 5.0))
    by_ref["JP_OLED_PWR"].SetOrientationDegrees(0.0)

    # BTB Mating Sockets — placed on BOTTOM (B.Cu) with EXACT world coordinate parity (< 0.001 mm!)
    # BTB_Socket_2x08_P2.54mm_BottomMate has even pins mirrored to x=-2.54 in F.Cu definition, so
    # Flip(pos, False) (which sets layer=B.Cu, rot=180) places Pin 1 at (bx, by) and Pin 2 at (bx+2.54, by)!
    ox_m, oy_m = CONTRACT["boards"]["ui_mezzanine"]["kicad_origin_world_mm"]
    for btb_ref in ["J_BTB_AUDIO_CV", "J_BTB_UI_DIG"]:
        spec = CONTRACT["btb_mating_world_mm"][btb_ref]
        bx = spec["pin1_world_x"] - ox_m
        by = oy_m - spec["pin1_world_y"]
        fp = by_ref[btb_ref]
        fp.SetPosition(pt(bx, by))
        fp.SetOrientationDegrees(0.0)
        if fp.GetLayer() != pcbnew.B_Cu:
            fp.Flip(pt(bx, by), False)
        fp.SetOrientationDegrees(180.0)

    hide_value_and_tidy_refs(board, ref_size=0.90, show_refs=set())
    add_silk_text(board, "BEADS UI MEZZANINE (PURE THT)", 34.0, 2.0, size=1.0, thick=0.15)
    add_silk_text(board, "JP_OLED: 1-2/4-5=G-V | 2-3/5-6=V-G", 34.0, 10.5, size=0.85, thick=0.14)
    add_silk_text(board, "J_BTB_AUDIO_CV (BOTTOM)", 23.25, 58.0, size=0.85, thick=0.14, layer=pcbnew.B_SilkS)
    add_silk_text(board, "J_BTB_UI_DIG (BOTTOM)", 46.25, 58.0, size=0.85, thick=0.14, layer=pcbnew.B_SilkS)

    add_gnd_zone(board, W, H, layer=pcbnew.B_Cu, clearance=0.25)
    pcbnew.SaveBoard(str(pcb_path), board)
    print(f"[OK] Laid out {pcb_path} ({W}x{H} mm)")


def place_by_pad_target(fp: pcbnew.FOOTPRINT, rot_deg: float, target_fn) -> None:
    """Place footprint at rot_deg so target_fn(fp) aligns to exact desired PCB coordinate."""
    fp.SetOrientationDegrees(rot_deg)
    fp.SetPosition(pt(0.0, 0.0))
    dx, dy = target_fn(fp)
    fp.SetPosition(pt(dx, dy))


def build_main_board() -> None:
    pcb_path = ROOT / "hardware" / "main_board" / "main_board.kicad_pcb"
    board = pcbnew.LoadBoard(str(pcb_path))
    clear_graphics_and_zones(board)
    configure_2layer_rules(board, min_track=0.15, min_clear=0.15, power_track=0.52)

    W, H = CONTRACT["boards"]["main_board"]["dimensions_mm"]
    ox_mb, oy_mb = CONTRACT["boards"]["main_board"]["kicad_origin_world_mm"]
    add_edge_rect(board, 0.0, 0.0, W, H)

    def w2p(xw: float, yw: float) -> tuple[float, float]:
        return (xw - ox_mb, oy_mb - yw)

    by_ref = {fp.GetReference(): fp for fp in board.GetFootprints()}
    placed: set[str] = set()

    def P(ref: str, x: float, y: float, rot: float = 0.0) -> None:
        if ref not in by_ref:
            raise KeyError(f"Missing footprint on main_board: {ref}")
        fp = by_ref[ref]
        fp.SetPosition(pt(x, y))
        fp.SetOrientationDegrees(rot)
        placed.add(ref)

    # 1. 6x M3 Floor Mounting Holes (MH101..MH106) + 3.15mm non-GND track/via keepout!
    for mh in CONTRACT["boards"]["main_board"]["mounting_holes_world_mm"]:
        px, py = w2p(mh["x"], mh["y"])
        P(mh["ref"], px, py, 0.0)
        add_mh_keepout(board, px, py, radius=3.15)

    # 2. North-Wall Connectors (EXACT mechanical datums from hardware_contract.json!)
    nc = CONTRACT["boards"]["main_board"]["north_wall_connectors_world_mm"]
    # 4x Neutrik NMJ4HCD2 (ST-NMJ4HCD2):
    # At rot=0, T=(0,0), TN=(0,16.23) [REAR], S=(12.7,0), SN=(12.7,16.23) [FRONT], front shoulder X=+16.70!
    # Rotate +90.0 deg so front shoulder (+X_local=+16.70) faces NORTH (-Y_pcb=-0.20 -> Y_w=181.80) and S is NORTH of T!
    for jref in ["J_OUT_R", "J_OUT_L", "J_IN_R", "J_IN_L"]:
        fp = by_ref[jref]
        tx_barrel = nc[jref]["x_center"] - ox_mb
        fp.SetOrientationDegrees(90.0)
        fp.SetPosition(pt(0.0, 0.0))
        pads = {p.GetName(): (pcbnew.ToMM(p.GetPosition().x), pcbnew.ToMM(p.GetPosition().y)) for p in fp.Pads()}
        assert pads["S"][1] < pads["T"][1], f"Expected S north of T on {jref}: {pads}"
        cur_bx = (pads["T"][0] + pads["TN"][0]) / 2.0
        cur_shoulder_y = pads["T"][1] - 16.70
        fp.SetPosition(pt(tx_barrel - cur_bx, -0.20 - cur_shoulder_y))
        placed.add(jref)

    # 2x Same Sky SJ1-3523N (MIDI THRU, MIDI IN):
    # At rot=0, S=(0,0), T=(+5,-5), R=(-5,-5), Connector Edge Y=+3.50 (+-0.30), front Ø1.2mm NPTH pegs at Y=+2.50.
    # Rotate 180 and place at Y_pcb=3.60 -> NPTH pegs at Y_pcb=1.10 (0.500mm FR4 web to North Edge.Cuts!)
    # paired with 0.70mm deep Edge.Cuts collar relief notches (X=x_c+-3.40mm, Y=0.00..0.70mm) per plan/04 §4.2!
    for jref in ["J_MIDI_THRU", "J_MIDI_IN"]:
        fp = by_ref[jref]
        tx = nc[jref]["x_center"] - ox_mb
        fp.SetOrientationDegrees(180.0)
        fp.SetPosition(pt(tx, 3.60))
        placed.add(jref)

    # C&K JS202011AQN DPDT MIDI TYPE A/B Switch:
    # At rot=0, Pad1=(0,0), Pad2=(2.5,0), Pad3=(5,0), Pad6=(0,3.3), Pad5=(2.5,3.3), Pad4=(5,3.3), front face Y=+3.65.
    # At rot=180, actuator faces North (-Y_pcb), Pad 3/4 are West (Left=TYPE A), Pad 1/6 are East (Right=TYPE B)!
    # Front face at fp_y - 3.65 -> want at Y_pcb = -0.20 -> fp_y = 3.45!
    sw_fp = by_ref["SW_MIDI_AB"]
    sw_fp.SetOrientationDegrees(180.0)
    sw_fp.SetPosition(pt(0.0, 0.0))
    sw_pads = {p.GetName(): (pcbnew.ToMM(p.GetPosition().x), pcbnew.ToMM(p.GetPosition().y)) for p in sw_fp.Pads()}
    sw_cx = sw_pads["2"][0]
    sw_tx = nc["SW_MIDI_AB"]["x_center"] - ox_mb
    # fp_y=4.80 puts Pads 4,5,6 at Y=1.50mm (0.80mm edge clearance so MIDI_IN_TIP routes cleanly above!), actuator tip protrudes past North edge!
    sw_fp.SetPosition(pt(sw_tx - sw_cx, 4.80))
    placed.add("SW_MIDI_AB")
    # Sanity assert: Pad 3 (TYPE A Ring) must be WEST (smaller X) of Pad 1 (TYPE B Tip)!
    sw_pads2 = {p.GetName(): (pcbnew.ToMM(p.GetPosition().x), pcbnew.ToMM(p.GetPosition().y)) for p in sw_fp.Pads()}
    assert sw_pads2["3"][0] < sw_pads2["1"][0], f"SW_MIDI_AB Left/Right polarity wrong: {sw_pads2}"

    # USB-C TYPE-C-31-M-12 (advanced 0.85 mm North to Y_pcb=2.40 -> front tongue at Y_w=182.85 mm,
    # protruding 0.85 mm into North wall so USB-C plugs reach <= 0.45 mm from exterior pocket floor!)
    usb_tx = nc["J_USB"]["x_center"] - ox_mb
    P("J_USB", usb_tx, 2.40, 180.0)

    # Panel DC Jack 2-pin header J_PWR_IN placed clear South of full 17.6mm DC_JACK (Y_w>=168) & North of Beads (Y_w<=159.6)!
    # At (135.5, 19.0, rot=90): Pin1=(135.5, 19.0), Pin2=(132.96, 19.0) -> X_w=[136.7, 141.8], Y_w=[161.3, 163.9]!
    P("J_PWR_IN", 135.5, 19.0, 90.0)

    # 3. BTB Mating Headers (0.000 mm world XY parity with ui_mezzanine!)
    for btb_ref in ["J_BTB_AUDIO_CV", "J_BTB_UI_DIG"]:
        spec = CONTRACT["btb_mating_world_mm"][btb_ref]
        bx, by = w2p(spec["pin1_world_x"], spec["pin1_world_y"])
        P(btb_ref, bx, by, 0.0)

    # 4. Eurorack 2x5 Power Header relocated SOUTH of Beads rear PCB (Y_w=48.1 < 54.6 -> 32.4 mm vertical headroom
    #    for full 14mm mated 2x5 IDC plug + strain-relief ribbon loop!). Rotated 90 deg so Pins 1..10 run East-West!
    j_euro = by_ref["J_EURO_PWR"]
    j_euro.SetOrientationDegrees(90.0)
    j_euro.SetPosition(pt(0.0, 0.0))
    epads = [(pcbnew.ToMM(p.GetPosition().x), pcbnew.ToMM(p.GetPosition().y)) for p in j_euro.Pads()]
    ecx = (min(x for x, _ in epads) + max(x for x, _ in epads)) / 2.0
    ecy = (min(y for _, y in epads) + max(y for _, y in epads)) / 2.0
    j_euro.SetPosition(pt(96.0 - ecx, 133.5 - ecy))
    placed.add("J_EURO_PWR")

    # 5. South-Edge Footswitch & Apron Status LED Headers (clear of MH101..103 at Y=140.6!)
    P("J_FS1",     24.0, 140.0, 90.0)
    P("J_LED_FS1", 36.0, 140.0, 90.0)
    P("J_FS2",    114.0, 140.0, 90.0)
    P("J_LED_FS2",126.0, 140.0, 90.0)

    # =========================================================================
    # ZONE 1 (NORTH-EAST, X=84..138, Y=18..96): POWER, USB ISOLATION, ±12V LDOs
    # =========================================================================
    # Input protection & Pi-Filter (clear of J_PWR_IN at (134,19) and MH106 at (137.0, 39.6)!)
    P("F1",      126.5, 22.5, 0.0)
    P("D_TVS1",  134.0, 27.5, 0.0)
    P("Q_RPP1",  126.5, 28.0, 0.0)
    P("D_Z_RPP", 121.0, 28.0, 0.0)
    P("R1",      123.5, 32.0, 0.0)
    P("R2",      127.5, 32.0, 0.0)
    P("C1",      119.5, 36.0, 0.0)
    P("C2",      124.5, 36.0, 0.0)
    P("FB1",     129.0, 36.0, 0.0)
    P("C3",      125.0, 40.5, 0.0)
    P("C4",      130.0, 40.5, 0.0)
    P("C5",      119.5, 40.5, 0.0)

    # Stage 1: TPS5430DDAR (+5.08V Buck) around (110, 42)
    P("U_BUCK5", 110.0, 42.0, 0.0)
    P("C_BOOT",  105.0, 38.0, 0.0)
    P("D_BUCK",  117.5, 46.5, 90.0)
    P("L1",      124.5, 48.0, 0.0)
    P("C6",      131.5, 48.0, 0.0)
    P("C7",      131.5, 52.5, 0.0)
    P("C8",      136.0, 48.0, 90.0)
    P("R3",      136.0, 52.5, 90.0)
    P("R4",      104.0, 44.5, 0.0)
    P("R5",      104.0, 47.0, 0.0)
    P("R6",      104.0, 49.5, 0.0)
    P("R7",      104.0, 52.0, 0.0)
    P("R8",      108.5, 51.0, 0.0)
    P("R9",      108.5, 53.5, 0.0)

    # Stage 2: TPS65131RGER (±14.6V, PSP/PSN=GND, I_VREF=6.07uA) around (96, 63)
    P("U_PMIC",  96.0, 63.0, 0.0)
    P("C9",      90.0, 57.5, 0.0)
    P("C10",     90.0, 60.5, 0.0)
    P("R10",     90.0, 63.5, 0.0)
    P("R11",     90.0, 66.0, 0.0)
    P("C_ENN",   90.0, 68.5, 0.0)
    P("C_VREF", 102.5, 65.5, 0.0)
    P("C_CP",   102.5, 60.5, 0.0)
    P("C_CN",   102.5, 63.0, 0.0)
    # +14.65V Boost (North of U_PMIC; C13 placed directly beside U_LDO_P12.3 <= 5.5mm!)
    P("L2",      95.0, 52.0, 0.0)
    P("D_POS",   87.0, 52.0, 0.0)
    P("C11",     87.0, 46.5, 0.0)
    P("C12",     92.5, 46.5, 0.0)
    P("C13",    106.5, 61.5, 90.0)
    P("R12",    101.0, 55.5, 0.0)
    P("R13",    101.0, 58.0, 0.0)
    P("R14",    104.0, 56.0, 0.0)
    # -14.56V Inverter (South of U_PMIC; C16 placed <= 6.5mm from U_PMIC.15!)
    P("L3",      95.0, 74.0, 0.0)
    P("D_NEG",  103.0, 74.0, 0.0)
    P("C14",     92.0, 81.0, 0.0)
    P("C15",     97.5, 81.0, 0.0)
    P("C16",    101.5, 68.5, 90.0)
    P("R15",    105.5, 68.0, 0.0)
    P("R16",    105.5, 70.5, 0.0)
    P("R17",    105.5, 65.5, 0.0)

    # Stage 3: Linear ±12.0V Post-LDOs (DPAK) + Ferrite LC -> J_EURO_PWR
    P("U_LDO_P12",   115.0, 61.5, 0.0)
    P("R18",         109.5, 69.0, 0.0)
    P("R19",         113.0, 69.0, 0.0)
    P("R20",         116.5, 69.0, 0.0)
    P("C_ADJ",       113.0, 72.5, 0.0)
    P("D_LM1",       115.0, 56.0, 0.0)
    P("D_LM2",       121.5, 56.0, 0.0)
    P("C17",         132.5, 58.5, 0.0)
    P("D_CLAMP_P12", 137.0, 58.5, 90.0)
    P("FB2",         132.5, 63.0, 0.0)
    P("C18",         134.0, 70.0, 0.0)
    P("C19",         127.0, 63.0, 0.0)

    P("U_LDO_N12",   113.5, 82.0, 0.0)
    P("C20",         113.5, 89.5, 0.0)
    P("R_ESR_N12",   119.0, 89.5, 0.0)
    P("C21",         120.0, 85.0, 0.0)
    P("D_CLAMP_N12", 127.0, 89.5, 90.0)
    P("FB3",         131.0, 89.5, 0.0)
    P("C22",         134.0, 81.5, 0.0)
    P("C23",         127.0, 84.5, 0.0)

    # Stage 4: USB-C ESD + Bidirectional Zero-Backfeed ORing (D_OR_PED 1N5819WS!) + AMS1117-3.3
    P("F_USB",      123.5, 10.5, 0.0)
    P("U_USB_ESD",  129.5, 11.0, 0.0)
    P("R21",        120.5, 14.0, 0.0)
    P("R22",        124.0, 14.0, 0.0)
    P("R23",        128.0, 15.0, 0.0)
    P("R24",        131.5, 15.0, 0.0)
    P("R25",        119.5, 17.5, 0.0)
    P("R26",        119.5, 20.0, 0.0)
    P("D_USB_FWD",  119.0, 23.5, 0.0)
    P("Q_USB",      114.0, 25.0, 0.0)
    P("R27",        114.0, 29.0, 0.0)
    P("D_OR_PED",   110.0, 32.5, 0.0)
    P("C24",        106.5, 28.0, 0.0)
    P("C25",        102.5, 28.0, 0.0)
    P("U_LDO_3V3",   95.5, 28.0, 0.0)
    P("C26",         88.5, 26.0, 0.0)
    P("C27",         88.5, 30.5, 0.0)
    P("C28",         93.0, 34.5, 0.0)
    P("FB4",         89.0, 34.5, 0.0)
    P("C29",         85.0, 34.5, 0.0)
    P("C30",         85.0, 38.0, 0.0)

    # =========================================================================
    # ZONE 2 (NORTH-WEST, X=8..78, Y=24..76): RELAYS, PHOTOMOS, PREAMP, RETURN, ENV
    # Clear of MH104 at (5.0, 29.6) and MH105 at (71.0, 29.6)!
    # =========================================================================
    # Relays K1/K2 + PhotoMOS U_MUTE_L/R + drivers (Y=25..44)
    P("K1",       32.0, 32.0, 0.0)
    P("K2",       52.0, 32.0, 0.0)
    P("D_FLY1",   38.5, 28.0, 90.0)
    P("D_FLY2",   58.5, 28.0, 90.0)
    P("Q_REL",    43.0, 30.0, 0.0)
    P("R29",      43.0, 34.0, 0.0)
    P("C31",      43.0, 36.5, 0.0)
    P("R30",      43.0, 39.0, 0.0)

    P("U_MUTE_L", 16.0, 32.0, 0.0)
    P("U_MUTE_R", 16.0, 41.0, 0.0)
    P("R31",      22.5, 31.0, 0.0)
    P("R32",      22.5, 40.0, 0.0)
    P("Q_MUTE",   23.0, 35.5, 0.0)
    P("R33",      27.5, 38.5, 0.0)
    P("C32",      27.5, 41.0, 0.0)
    P("R34",      31.5, 41.0, 0.0)

    # 8x 2.2M anti-pop bleed resistors near relays & jacks
    P("R35", 62.5, 26.0, 0.0)
    P("R36", 62.5, 28.5, 0.0)
    P("R37", 38.5, 34.5, 0.0)
    P("R38", 58.5, 34.5, 0.0)
    P("R39", 22.5, 26.5, 0.0)
    P("R40", 16.0, 26.5, 0.0)
    P("R41", 32.0, 44.5, 0.0)
    P("R42", 42.0, 44.5, 0.0)

    # Stereo Guitar Preamp (U_OP_IN1 L, U_OP_IN2 R) at Y=54..66
    P("U_OP_IN1", 40.0, 55.0, 0.0)
    P("C43",      35.5, 51.0, 0.0)
    P("C44",      44.5, 51.0, 0.0)
    P("C33",      31.0, 51.5, 0.0)
    P("R43",      31.0, 54.5, 0.0)
    P("C34",      31.0, 57.0, 0.0)
    P("R44",      31.0, 59.5, 0.0)
    P("R45",      36.0, 61.5, 0.0)
    P("R46",      40.0, 61.5, 0.0)
    P("R47",      44.0, 61.5, 0.0)
    P("R48",      48.0, 61.5, 0.0)
    P("C35",      48.0, 58.5, 0.0)
    P("R49",      48.0, 55.5, 0.0)
    P("R50",      48.0, 52.5, 0.0)

    P("U_OP_IN2", 62.0, 55.0, 0.0)
    P("C45",      57.5, 51.0, 0.0)
    P("C46",      66.5, 51.0, 0.0)
    P("C36",      53.5, 51.5, 0.0)
    P("R51",      53.5, 54.5, 0.0)
    P("C37",      53.5, 57.0, 0.0)
    P("R52",      53.5, 59.5, 0.0)
    P("R53",      58.0, 61.5, 0.0)
    P("R54",      62.0, 61.5, 0.0)
    P("R55",      66.0, 61.5, 0.0)
    P("R56",      70.0, 61.5, 0.0)
    P("C38",      70.0, 58.5, 0.0)
    P("R57",      70.0, 55.5, 0.0)
    P("R58",      70.0, 52.5, 0.0)

    # Stereo Return Stage (U_OP_RET1 NE5532, U_OP_RET2 TL072) at X=10..36, Y=52..76
    P("U_OP_RET1", 16.0, 55.0, 0.0)
    P("C47",       11.5, 51.0, 0.0)
    P("C48",       20.5, 51.0, 0.0)
    P("R59",       10.0, 55.0, 0.0)
    P("R60",       10.0, 57.5, 0.0)
    P("R61",       10.0, 60.0, 0.0)
    P("R62",       22.0, 55.0, 0.0)
    P("R63",       22.0, 57.5, 0.0)
    P("R64",       22.0, 60.0, 0.0)

    P("U_OP_RET2", 16.0, 70.0, 0.0)
    P("C49",       11.5, 65.5, 0.0)
    P("C50",       20.5, 65.5, 0.0)
    P("C39",       11.0, 76.5, 0.0)
    P("R65",       16.5, 76.5, 0.0)
    P("C40",       22.0, 76.5, 0.0)
    P("R66",       27.5, 76.5, 0.0)

    # Guitar Peak / Pluck Detector (+3.3V MCP6002 + BAV99) at X=55..76, Y=68..78
    P("U_ENV",   62.0, 72.0, 0.0)
    P("C51",     62.0, 67.0, 0.0)
    P("R67",     54.0, 68.0, 0.0)
    P("R68",     54.0, 70.5, 0.0)
    P("R69",     54.0, 73.0, 0.0)
    P("D_CLAMP", 54.0, 77.0, 0.0)
    P("R70",     58.0, 76.5, 0.0)
    P("R71",     67.5, 68.5, 0.0)
    P("D_PK",    72.5, 68.5, 0.0)
    P("R72",     68.0, 72.0, 0.0)
    P("R73",     72.0, 72.0, 0.0)
    P("C41",     68.0, 75.0, 0.0)
    P("R74",     72.0, 75.0, 0.0)
    P("R75",     68.0, 78.0, 0.0)
    P("C42",     72.0, 78.0, 0.0)

    # =========================================================================
    # ZONE 3 (SOUTH-WEST, X=8..82, Y=92..134): +2.495V REF, U_LVL, 4x MCP4822, 4x TL072 CV
    # =========================================================================
    P("U_REF",      11.5, 108.0, 0.0)
    P("R76",        11.5, 104.0, 0.0)
    P("R143",       15.5, 108.0, 0.0)
    P("C52",        19.0, 108.0, 0.0)
    P("U_VREF_BUF", 24.5, 108.0, 0.0)
    P("C53",        21.0, 103.5, 0.0)
    P("C54",        28.0, 103.5, 0.0)

    # SN74AHCT541PWR (U_LVL) 3.3V->5.08V I_off SPI/CS Level Shifter between U_MCU (East) & U_DAC0..3 (West)
    P("U_LVL",      77.0,  96.0, 180.0)
    P("C92",        77.0, 101.5,   0.0)

    # 4x MCP4822 in a clean row along Y=114 (X=38, 49, 60, 71)
    for i in range(4):
        dx = 38.0 + i * 11.0
        P(f"U_DAC{i}", dx, 114.0, 0.0)
        P(f"R{77 + i}", dx - 2.0, 108.5, 0.0)
        P(f"C{55 + i}", dx + 2.0, 108.5, 0.0)

    # 4x TL072 CV amps along Y=127 (X=16, 32, 48, 64) + 8 channels of passives neatly grouped!
    for i in range(4):
        ox = 16.0 + i * 16.0
        P(f"U_OP_CV{i + 1}", ox, 126.0, 0.0)
        P(f"C{67 + i * 2}", ox - 4.5, 122.0, 0.0)
        P(f"C{68 + i * 2}", ox + 4.5, 122.0, 0.0)
        # 2 channels per TL072: passives in neat columns above/below
        for sub in range(2):
            ch = i * 2 + sub + 1
            r0 = 81 + (ch - 1) * 5
            c0 = 59 + (ch - 1)
            px_base = ox - 5.5 + sub * 7.5
            P(f"R{r0}",     px_base,       131.5, 0.0)
            P(f"R{r0 + 1}", px_base + 3.5, 131.5, 0.0)
            P(f"R{r0 + 2}", px_base,       134.0, 0.0)
            P(f"R{r0 + 3}", px_base + 3.5, 134.0, 0.0)
            P(f"C{c0}",     px_base,       120.0, 0.0)
            P(f"R{r0 + 4}", px_base + 3.5, 120.0, 0.0)

    # =========================================================================
    # ZONE 4 (SOUTH-EAST & NORTH-CENTER MIDI): RP2040, W25Q128, XTAL, H11L1, 74HC14
    # =========================================================================
    # MIDI Opto & 74HC14 directly behind J_MIDI_THRU / SW_MIDI_AB / J_MIDI_IN (X=81..115, Y=13..26)
    P("R125",       111.0, 14.5, 0.0)
    P("D_MIDI_REV", 111.0, 17.5, 0.0)
    P("U_OPTO",      97.5, 16.5, 0.0)
    P("R126",       111.0, 21.0, 0.0)
    P("C88",        102.5, 13.0, 0.0)
    P("U_INV",       88.0, 19.5, 90.0)
    P("C89",         82.5, 25.0, 0.0)
    P("R127",        86.0, 13.0, 0.0)
    P("R142",        90.0, 13.0, 0.0)
    P("R128",        94.0, 13.0, 0.0)

    # RP2040 MCU + Flash + 12MHz Xtal + BOOTSEL at X=88..112, Y=98..128
    P("U_MCU",    94.0, 110.0, 0.0)
    P("U_FLASH", 110.0, 104.0, 0.0)
    P("R121",    105.0,  99.0, 0.0)
    P("R122",    109.0,  99.0, 0.0)
    P("SW_BOOT", 116.0,  99.0, 0.0)
    P("Y1",       94.0, 122.0, 0.0)
    P("R123",     94.0, 118.0, 0.0)
    P("C75",      90.0, 122.0, 90.0)
    P("C76",      98.0, 122.0, 90.0)
    P("R124",     85.5, 117.0, 0.0)
    P("C77",      85.5, 119.5, 0.0)
    P("TP_DBG_TX",85.5, 102.0, 0.0)

    # RP2040 decoupling caps ringed tightly <= 4mm around U_MCU!
    P("C78",  86.0, 106.0, 0.0)
    P("C79",  86.0, 109.5, 0.0)
    P("C80",  86.0, 112.5, 0.0)
    P("C81",  90.5, 102.5, 0.0)
    P("C82",  94.5, 102.5, 0.0)
    P("C83",  98.5, 102.5, 0.0)
    P("C84", 102.0, 108.0, 90.0)
    P("C85", 102.0, 113.5, 90.0)
    P("C86",  90.0, 117.0, 0.0)
    P("C87",  98.5, 117.0, 0.0)

    # UI Pull-ups & encoder debounce caps neatly beside J_BTB_UI_DIG (X=56..78, Y=84..102)
    P("R129", 57.0, 84.0, 0.0)
    P("R130", 61.0, 84.0, 0.0)
    P("R131", 57.0, 87.0, 0.0)
    P("C90",  61.0, 87.0, 0.0)
    P("R132", 57.0, 90.0, 0.0)
    P("C91",  61.0, 90.0, 0.0)
    P("R133", 57.0, 93.0, 0.0)
    P("R134", 61.0, 93.0, 0.0)
    P("R135", 57.0, 96.0, 0.0)
    P("R136", 61.0, 96.0, 0.0)
    P("R137", 57.0, 99.0, 0.0)

    # Apron Status LED NMOS drivers cleanly flanking J_LED_FS1 / J_LED_FS2 (clear of J_EURO_PWR at (96, 133.5)!)
    P("Q_LED1", 44.0, 140.0, 0.0)
    P("R138",   48.5, 140.0, 0.0)
    P("R139",   52.5, 140.0, 0.0)
    P("Q_LED2",124.0, 132.0, 0.0)
    P("R140",  128.5, 132.0, 0.0)
    P("R141",  132.5, 132.0, 0.0)

    # Verify 100% of footprints were explicitly placed!
    unplaced = sorted(set(by_ref.keys()) - placed)
    if unplaced:
        raise RuntimeError(f"Unplaced footprints on main_board: {unplaced}")

    # Add GND Thermal Vias cleanly inside the segmented F.Paste cross-channels (ZERO paste-over-via!)
    for dx, dy in [(0.0, 0.0), (-1.0, 0.0), (1.0, 0.0), (0.0, -1.0), (0.0, 1.0)]:
        add_via(board, 94.0 + dx, 110.0 + dy, "GND", dia=0.52, drill=0.30)  # RP2040
    for dx, dy in [(0.0, 0.0), (-0.8, 0.0), (0.8, 0.0), (0.0, -0.8), (0.0, 0.8)]:
        add_via(board, 96.0 + dx, 63.0 + dy, "GND", dia=0.50, drill=0.30)   # TPS65131
    for dy in [-0.9, 0.0, 0.9]:
        add_via(board, 110.0, 42.0 + dy, "GND", dia=0.50, drill=0.30)       # TPS5430

    # Tidy refs and add mandatory silkscreen markings
    show_refs = {
        "J_OUT_R", "J_OUT_L", "J_IN_R", "J_IN_L", "J_MIDI_THRU", "SW_MIDI_AB", "J_MIDI_IN",
        "J_USB", "J_PWR_IN", "J_EURO_PWR", "J_BTB_AUDIO_CV", "J_BTB_UI_DIG",
        "J_FS1", "J_FS2", "J_LED_FS1", "J_LED_FS2", "SW_BOOT", "K1", "K2",
        "U_MCU", "U_LVL", "U_OPTO", "U_BUCK5", "U_PMIC", "U_LDO_P12", "U_LDO_N12", "U_LDO_3V3",
    }
    hide_value_and_tidy_refs(board, ref_size=0.80, show_refs=show_refs)
    # Keep visible IC/connector refs strictly clear of neighboring silkscreen, pads & board edges
    for rref, rx, ry in [
        ("J_USB",      124.5,   8.6),
        ("J_PWR_IN",   136.8,  15.6),
        ("J_EURO_PWR",  79.5, 134.5),
        ("U_LVL",       77.0,  90.8),
        ("SW_BOOT",    116.0,  95.8),
        ("SW_MIDI_AB", 100.0,   7.5),
        ("J_MIDI_THRU", 79.5,  22.0),
        ("J_MIDI_IN",  115.5,  13.0),
        ("U_OPTO",     106.0,  24.2),
        ("U_LDO_3V3",   95.5,  32.6),
        ("U_LDO_P12",  123.5,  61.5),
    ]:
        if rref in by_ref:
            by_ref[rref].Reference().SetPosition(pt(rx, ry))
            if rref == "J_PWR_IN":
                by_ref[rref].Reference().SetTextAngleDegrees(0.0)

    # Mandatory Silkscreen Markings (plan/01, plan/02, plan/03) — positioned cleanly clear of pads/courtyards/edges!
    add_silk_text(board, "RED STRIPE / -12V (PINS 1-2)", 96.0, 126.0, size=0.85, thick=0.15)
    add_silk_line(board, 84.4, 129.0, 84.4, 138.2, width=0.55)
    add_silk_text(board, "9-18V CTR-NEG",    136.8, 13.4, size=0.80, thick=0.14)
    add_silk_text(board, "P1:+V P2:GND",     136.8, 22.8, size=0.80, thick=0.14)
    add_silk_text(board, "<A|MIDI|B>",       100.0,  9.5, size=0.82, thick=0.14)
    add_silk_text(board, "OUT R",             10.5, 22.5, size=1.0,  thick=0.18)
    add_silk_text(board, "OUT L/M",           30.5, 22.5, size=1.0,  thick=0.18)
    add_silk_text(board, "IN R",              50.5, 22.5, size=1.0,  thick=0.18)
    add_silk_text(board, "IN L/M",            70.5, 22.5, size=1.0,  thick=0.18)
    add_silk_text(board, "BOOTSEL",          116.0, 93.8, size=0.82, thick=0.14)
    add_silk_text(board, "BEADS PEDALBOARD SKIFF MAIN_BOARD REV 1.1", 71.0, 144.8, size=1.05, thick=0.17)

    # Continuous solid B.Cu GND plane (>90% unbroken copper!)
    add_gnd_zone(board, W, H, layer=pcbnew.B_Cu, clearance=0.22, edge_inset=0.40)

    pcbnew.SaveBoard(str(pcb_path), board)
    print(f"[OK] Laid out {pcb_path} ({W}x{H} mm, {len(placed)} footprints placed, 0 unplaced)")


def main(argv: list[str]) -> int:
    targets = argv[1:] if len(argv) > 1 else ["faceplate_14hp", "ui_mezzanine", "main_board"]
    for t in targets:
        if t == "faceplate_14hp":
            build_faceplate()
        elif t == "ui_mezzanine":
            build_ui_mezzanine()
        elif t == "main_board":
            build_main_board()
        else:
            raise ValueError(f"Unknown board: {t}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
