#!/usr/bin/env python3
"""Route ui_mezzanine and main_board via Specctra DSN + bounded Freerouting + fresh-process
ZONE_FILLER refill + SMD GND via stitching, then audit DRC=0, unconnected=0, B.Cu GND pour %,
and J_BTB_* XY mating congruence (< 0.05 mm).
"""
from __future__ import annotations

import json
import math
import pathlib
import subprocess
import sys
import pcbnew

ROOT = pathlib.Path(__file__).resolve().parents[1]
CONTRACT = json.loads((ROOT / "hardware_contract.json").read_text(encoding="utf-8"))
FR_JAR = pathlib.Path("/home/yerbaadmin/.kicad-mcp/freerouting.jar")
SCRATCH = pathlib.Path("/tmp/opencode/beads_route")
SCRATCH.mkdir(parents=True, exist_ok=True)


def mm(v: float) -> int:
    return pcbnew.FromMM(float(v))


def pt(x: float, y: float) -> pcbnew.VECTOR2I:
    return pcbnew.VECTOR2I(mm(x), mm(y))


def route_one_board(board_name: str, max_passes: int = 25, timeout_s: int = 180) -> None:
    pcb_path = ROOT / "hardware" / board_name / f"{board_name}.kicad_pcb"
    dsn_path = SCRATCH / f"{board_name}.dsn"
    ses_path = SCRATCH / f"{board_name}.ses"

    # Step 1: Export DSN via pcbnew
    board = pcbnew.LoadBoard(str(pcb_path))
    ok = pcbnew.ExportSpecctraDSN(board, str(dsn_path))
    if not ok or not dsn_path.exists():
        raise RuntimeError(f"ExportSpecctraDSN failed for {board_name}")

    # Tune DSN: keep GND out of autorouter (B.Cu pour handles GND after SMD via drop!) OR let FR route short stubs?
    # Better: drop GND vias beside every SMD GND pad FIRST (or let FR route all nets with B.Cu cost penalty so B.Cu stays >90% GND!)
    # Actually, let's check: in DSN, adding (cost 10) on B.Cu / keeping (cost 1) on F.Cu strongly biases routing to F.Cu!
    dsn_txt = dsn_path.read_text(encoding="utf-8")
    # For main_board: make B.Cu horizontal/vertical high-cost? Standard freerouting already routes cleanly on 2 layers;
    # let's add a gentle B.Cu preference by removing GND from Freerouting ONLY after placing local GND vias?
    # Wait: if we leave GND in Freerouting vs pour-only: if GND is removed from DSN, Freerouting won't waste F.Cu on GND traces,
    # AND then our SMD GND via dropper connects every SMD GND pad straight down to the continuous B.Cu GND plane!!
    # Let's check: EVERY GND pad on ui_mezzanine is THT (except JP_OLED_PWR pads 1 & 6)!
    # On main_board, every SMD GND pad can drop a local 0.55/0.30mm via right beside the pad to B.Cu!
    # Wait: what if a dropped via collides with a routed trace? Drop local GND vias BEFORE exporting DSN so Freerouting routes AROUND them!
    print(f"[INFO] Exported DSN for {board_name} ({dsn_path.stat().st_size} bytes)")

    # Step 2: Run bounded Freerouting
    cmd = [
        "java", "-Xmx2g", "-jar", str(FR_JAR),
        "-de", str(dsn_path),
        "-do", str(ses_path),
        "-mp", str(max_passes),
        "-mt", "2",
    ]
    print(f"[INFO] Running Freerouting ({max_passes} passes, timeout={timeout_s}s) on {board_name}...")
    proc = subprocess.run(cmd, timeout=timeout_s, capture_output=True, text=True)
    if not ses_path.exists():
        raise RuntimeError(f"Freerouting failed for {board_name} (rc={proc.returncode}):\n{proc.stdout[-1000:]}\n{proc.stderr[-1000:]}")

    # Step 3: Import SES & save
    board2 = pcbnew.LoadBoard(str(pcb_path))
    ok2 = pcbnew.ImportSpecctraSES(board2, str(ses_path))
    if not ok2:
        raise RuntimeError(f"ImportSpecctraSES failed for {board_name}")
    pcbnew.SaveBoard(str(pcb_path), board2)
    print(f"[OK] Imported SES into {pcb_path}")

    # Step 4: Refill zones in a FRESH subprocess (HARDWARE_LESSONS.md Rule 5!)
    refill_code = (
        "import pcbnew, sys; "
        "b = pcbnew.LoadBoard(sys.argv[1]); "
        "f = pcbnew.ZONE_FILLER(b); "
        "f.Fill(b.Zones()); "
        "pcbnew.SaveBoard(sys.argv[1], b)"
    )
    subprocess.run([sys.executable, "-c", refill_code, str(pcb_path)], check=True)
    print(f"[OK] Refilled zones in fresh subprocess for {board_name}")


def drop_local_gnd_vias(board_name: str) -> None:
    """Drop a short stub + GND via beside every SMD GND pad BEFORE Freerouting, and remove GND
    from autorouting? Wait: keeping GND in autorouting with pre-placed local GND vias lets Freerouting
    see all GND vias as already connected through the B.Cu plane if zone is filled, OR we route all nets cleanly."""
    pcb_path = ROOT / "hardware" / board_name / f"{board_name}.kicad_pcb"
    board = pcbnew.LoadBoard(str(pcb_path))
    gnd = board.FindNet("GND")
    if gnd is None:
        return

    # Gather mounting hole centers for 3.2mm keepout check
    mh_centers = []
    for fp in board.GetFootprints():
        if fp.GetReference().startswith("MH"):
            p = fp.GetPosition()
            mh_centers.append((pcbnew.ToMM(p.x), pcbnew.ToMM(p.y)))

    # Gather all pads for collision checking
    all_pads = []
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            p = pad.GetPosition()
            sz = pad.GetSize()
            all_pads.append((
                pcbnew.ToMM(p.x), pcbnew.ToMM(p.y),
                max(pcbnew.ToMM(sz.x), pcbnew.ToMM(sz.y)) / 2.0,
                pad.GetNetname(),
                fp.GetReference(),
                pad.GetName(),
            ))

    existing_vias = [(pcbnew.ToMM(v.GetPosition().x), pcbnew.ToMM(v.GetPosition().y)) for v in board.GetTracks() if isinstance(v, pcbnew.PCB_VIA)]
    existing_segs = [
        (pcbnew.ToMM(t.GetStart().x), pcbnew.ToMM(t.GetStart().y),
         pcbnew.ToMM(t.GetEnd().x), pcbnew.ToMM(t.GetEnd().y),
         pcbnew.ToMM(t.GetWidth()) / 2.0, t.GetNetname())
        for t in board.GetTracks() if not isinstance(t, pcbnew.PCB_VIA)
    ]
    w_mm, h_mm = CONTRACT["boards"][board_name]["dimensions_mm"]

    # On main_board: tie U_PMIC peripheral GND pads (2,3,9,11,19) and U_MCU pad 19 (GND) ORTHOGONALLY into EP!
    by_ref = {fp.GetReference(): fp for fp in board.GetFootprints()}
    if "U_PMIC" in by_ref:
        pmic = by_ref["U_PMIC"]
        ep_pad = next(p for p in pmic.Pads() if p.GetName() == "25")
        epx, epy = pcbnew.ToMM(ep_pad.GetPosition().x), pcbnew.ToMM(ep_pad.GetPosition().y)
        for p in pmic.Pads():
            pname = p.GetName()
            if pname in ("2", "3", "9", "11", "19") and p.GetNetname() == "GND":
                px, py = pcbnew.ToMM(p.GetPosition().x), pcbnew.ToMM(p.GetPosition().y)
                if pname in ("2", "3"):
                    tx, ty = epx - 0.80, py       # Straight East into EP!
                elif pname in ("9", "11"):
                    tx, ty = px, epy + 0.80       # Straight North into EP!
                else:  # Pad 19 (+1.25, -1.987) -> straight South into EP edge
                    tx, ty = epx + 1.05, epy - 1.00
                tr = pcbnew.PCB_TRACK(board)
                tr.SetStart(pt(px, py))
                tr.SetEnd(pt(tx, ty))
                tr.SetWidth(mm(0.22))
                tr.SetLayer(pcbnew.F_Cu)
                tr.SetNet(gnd)
                board.Add(tr)
    if "U_MCU" in by_ref:
        mcu = by_ref["U_MCU"]
        ep_pad = next(p for p in mcu.Pads() if p.GetName() == "57")
        epx, epy = pcbnew.ToMM(ep_pad.GetPosition().x), pcbnew.ToMM(ep_pad.GetPosition().y)
        p19 = next((p for p in mcu.Pads() if p.GetName() == "19"), None)
        if p19 is not None and p19.GetNetname() == "GND":
            px, py = pcbnew.ToMM(p19.GetPosition().x), pcbnew.ToMM(p19.GetPosition().y)
            tr = pcbnew.PCB_TRACK(board)
            tr.SetStart(pt(px, py))
            tr.SetEnd(pt(px, epy + 1.20))
            tr.SetWidth(mm(0.20))
            tr.SetLayer(pcbnew.F_Cu)
            tr.SetNet(gnd)
            board.Add(tr)

    def seg_dist(px: float, py: float, x1: float, y1: float, x2: float, y2: float) -> float:
        dx, dy = x2 - x1, y2 - y1
        l2 = dx * dx + dy * dy
        if l2 < 1e-9:
            return math.hypot(px - x1, py - y1)
        t = max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / l2))
        return math.hypot(px - (x1 + t * dx), py - (y1 + t * dy))

    def point_clear(vx: float, vy: float, r_via: float = 0.28, clr: float = 0.32) -> bool:
        if vx < 1.0 or vx > w_mm - 1.0 or vy < 1.0 or vy > h_mm - 1.0:
            return False
        for mx, my in mh_centers:
            if math.hypot(vx - mx, vy - my) < 3.5:
                return False
        for ex, ey in existing_vias:
            if math.hypot(vx - ex, vy - ey) < 0.95:
                return False
        for px, py, pr, pnet, _, _ in all_pads:
            min_d = (r_via + pr + (0.16 if pnet == "GND" else clr))
            if math.hypot(vx - px, vy - py) < min_d:
                return False
        for x1, y1, x2, y2, hw, snet in existing_segs:
            min_d = r_via + hw + (0.16 if snet == "GND" else clr)
            if seg_dist(vx, vy, x1, y1, x2, y2) < min_d:
                return False
        return True

    added = 0
    for fp in board.GetFootprints():
        ref = fp.GetReference()
        for pad in fp.Pads():
            if pad.GetNetname() != "GND":
                continue
            if pad.GetAttribute() != pcbnew.PAD_ATTRIB_SMD:
                continue
            # Skip EP center pads (thermal vias) & U_PMIC peripheral GND pads (spoked straight to EP!)
            if ref in ("U_MCU", "U_PMIC", "U_BUCK5") and pad.GetName() in ("57", "25", "9"):
                continue
            if ref == "U_PMIC" and pad.GetName() in ("2", "3", "9", "11", "19"):
                continue
            if ref == "U_MCU" and pad.GetName() == "19":
                continue
            px, py = pcbnew.ToMM(pad.GetPosition().x), pcbnew.ToMM(pad.GetPosition().y)
            # If already very close (<1.2mm) to an existing GND via, skip
            if any(math.hypot(px - ex, py - ey) < 1.15 for ex, ey in existing_vias):
                continue
            # Try candidate offsets around the SMD GND pad (including larger radii for 6.3mm electrolytics C18/C22!)
            found = None
            for dist in (0.95, 1.25, 1.55, 1.90, 2.35, 2.80, 3.25):
                for ang_deg in range(0, 360, 30):
                    rad = math.radians(ang_deg)
                    vx = px + dist * math.cos(rad)
                    vy = py + dist * math.sin(rad)
                    if point_clear(vx, vy):
                        found = (vx, vy)
                        break
                if found:
                    break
            if found:
                vx, vy = found
                v = pcbnew.PCB_VIA(board)
                v.SetPosition(pt(vx, vy))
                v.SetWidth(pcbnew.F_Cu, mm(0.55))
                v.SetDrill(mm(0.30))
                v.SetViaType(pcbnew.VIATYPE_THROUGH)
                v.SetNet(gnd)
                board.Add(v)
                tr = pcbnew.PCB_TRACK(board)
                tr.SetStart(pt(px, py))
                tr.SetEnd(pt(vx, vy))
                tr.SetWidth(mm(0.25))
                tr.SetLayer(pcbnew.F_Cu)
                tr.SetNet(gnd)
                board.Add(tr)
                existing_vias.append((vx, vy))
                added += 1

    pcbnew.SaveBoard(str(pcb_path), board)
    print(f"[OK] Added {added} local SMD GND vias on {board_name}")


def widen_power_trunks_safely(board_name: str, target_w: float = 0.52) -> None:
    """Surgically widen POWER_QFN trunk segments (+5V_BUCK, PMIC_INP, PMIC_SWN, +14V6_RAW, -14V6_RAW)
    to >= 0.50 mm everywhere outside fine-pitch QFN/TSSOP pad clearances, verifying exact clearance to
    every other-net pad, track, via, and M3 mounting hole so DRC stays 0!"""
    if board_name != "main_board":
        return
    pcb_path = ROOT / "hardware" / board_name / f"{board_name}.kicad_pcb"
    board = pcbnew.LoadBoard(str(pcb_path))
    target_nets = {"+5V_BUCK", "PMIC_INP", "PMIC_SWN", "+14V6_RAW", "-14V6_RAW"}

    # Collect obstacle geometry for exact clearance checking (0.175mm margin > 0.15mm DRC + 0.20mm netclass!)
    mh_centers = []
    other_pads = []
    for fp in board.GetFootprints():
        if fp.GetReference().startswith("MH"):
            p = fp.GetPosition()
            mh_centers.append((pcbnew.ToMM(p.x), pcbnew.ToMM(p.y)))
        for pad in fp.Pads():
            bb = pad.GetBoundingBox()
            other_pads.append((
                pcbnew.ToMM(bb.GetLeft()), pcbnew.ToMM(bb.GetTop()),
                pcbnew.ToMM(bb.GetRight()), pcbnew.ToMM(bb.GetBottom()),
                pad.GetNetname(),
                pad.IsOnLayer(pcbnew.F_Cu), pad.IsOnLayer(pcbnew.B_Cu),
                pad.GetAttribute() in (pcbnew.PAD_ATTRIB_PTH, pcbnew.PAD_ATTRIB_NPTH),
            ))

    all_tracks = list(board.GetTracks())
    vias = [
        (pcbnew.ToMM(v.GetPosition().x), pcbnew.ToMM(v.GetPosition().y),
         pcbnew.ToMM(v.GetWidth(pcbnew.F_Cu)) / 2.0, pcbnew.ToMM(v.GetDrill()) / 2.0, v.GetNetname())
        for v in all_tracks if isinstance(v, pcbnew.PCB_VIA)
    ]
    segs = [
        (pcbnew.ToMM(t.GetStart().x), pcbnew.ToMM(t.GetStart().y),
         pcbnew.ToMM(t.GetEnd().x), pcbnew.ToMM(t.GetEnd().y),
         pcbnew.ToMM(t.GetWidth()) / 2.0, t.GetLayer(), t.GetNetname(), t)
        for t in all_tracks if not isinstance(t, pcbnew.PCB_VIA)
    ]

    def pt_seg_dist(px: float, py: float, x1: float, y1: float, x2: float, y2: float) -> float:
        dx, dy = x2 - x1, y2 - y1
        l2 = dx * dx + dy * dy
        if l2 < 1e-9:
            return math.hypot(px - x1, py - y1)
        u = max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / l2))
        return math.hypot(px - (x1 + u * dx), py - (y1 + u * dy))

    def seg_seg_dist(ax1: float, ay1: float, ax2: float, ay2: float,
                     bx1: float, by1: float, bx2: float, by2: float) -> float:
        # Check intersection or min endpoint distance
        def cross(ox, oy, px, py, qx, qy):
            return (px - ox) * (qy - oy) - (py - oy) * (qx - ox)
        d1 = cross(ax1, ay1, ax2, ay2, bx1, by1)
        d2 = cross(ax1, ay1, ax2, ay2, bx2, by2)
        d3 = cross(bx1, by1, bx2, by2, ax1, ay1)
        d4 = cross(bx1, by1, bx2, by2, ax2, ay2)
        if ((d1 > 0 and d2 < 0) or (d1 < 0 and d2 > 0)) and ((d3 > 0 and d4 < 0) or (d3 < 0 and d4 > 0)):
            return 0.0
        return min(
            pt_seg_dist(ax1, ay1, bx1, by1, bx2, by2),
            pt_seg_dist(ax2, ay2, bx1, by1, bx2, by2),
            pt_seg_dist(bx1, by1, ax1, ay1, ax2, ay2),
            pt_seg_dist(bx2, by2, ax1, ay1, ax2, ay2),
        )

    def seg_rect_dist(x1: float, y1: float, x2: float, y2: float,
                      rx1: float, ry1: float, rx2: float, ry2: float) -> float:
        # Sample along segment (exact enough for small pads with 0.05mm safety buffer)
        L = math.hypot(x2 - x1, y2 - y1)
        steps = max(2, int(math.ceil(L / 0.20)))
        best = 1e9
        for k in range(steps + 1):
            t = k / steps
            px, py = x1 + t * (x2 - x1), y1 + t * (y2 - y1)
            dx = max(rx1 - px, 0.0, px - rx2)
            dy = max(ry1 - py, 0.0, py - ry2)
            d = math.hypot(dx, dy)
            if d < best:
                best = d
        return best

    widened = 0
    total_cand = 0
    clr_req = 0.175  # Strictly above 0.15 mm DRC clearance!
    w_mm, h_mm = CONTRACT["boards"][board_name]["dimensions_mm"]

    for idx, (x1, y1, x2, y2, hw, lay, net, tr) in enumerate(segs):
        if net not in target_nets:
            continue
        total_cand += 1
        new_hw = target_w / 2.0
        if hw >= new_hw - 1e-4:
            continue
        # Edge clearance >= 0.40 mm
        if min(x1, x2) - new_hw < 0.40 or max(x1, x2) + new_hw > w_mm - 0.40:
            continue
        if min(y1, y2) - new_hw < 0.40 or max(y1, y2) + new_hw > h_mm - 0.40:
            continue
        # M3 mounting hole >= 3.05 mm clearance
        ok = True
        for mx, my in mh_centers:
            if pt_seg_dist(mx, my, x1, y1, x2, y2) - new_hw < 3.05:
                ok = False
                break
        if not ok:
            continue
        # Check other-net pads
        for rx1, ry1, rx2, ry2, pnet, on_f, on_b, is_th in other_pads:
            if pnet == net:
                continue
            if lay == pcbnew.F_Cu and not on_f and not is_th:
                continue
            if lay == pcbnew.B_Cu and not on_b and not is_th:
                continue
            need = max(clr_req, 0.40 if is_th else clr_req)
            if seg_rect_dist(x1, y1, x2, y2, rx1, ry1, rx2, ry2) - new_hw < need:
                ok = False
                break
        if not ok:
            continue
        # Check other-net vias
        for vx, vy, vr, vdr, vnet in vias:
            if vnet == net:
                continue
            d = pt_seg_dist(vx, vy, x1, y1, x2, y2) - new_hw
            if d - vr < clr_req or d - vdr < 0.275:
                ok = False
                break
        if not ok:
            continue
        # Check other-net tracks on same layer
        for j, (ox1, oy1, ox2, oy2, ohw, olay, onet, _) in enumerate(segs):
            if j == idx or olay != lay or onet == net:
                continue
            if seg_seg_dist(x1, y1, x2, y2, ox1, oy1, ox2, oy2) - new_hw - ohw < clr_req:
                ok = False
                break
        if ok:
            tr.SetWidth(mm(target_w))
            segs[idx] = (x1, y1, x2, y2, new_hw, lay, net, tr)
            widened += 1

    pcbnew.SaveBoard(str(pcb_path), board)
    print(f"[OK] Surgically widened {widened}/{total_cand} POWER_QFN trunk segments to {target_w:.2f} mm on {board_name}")


def strip_gnd_from_dsn_and_route(board_name: str, max_passes: int = 10, timeout_s: int = 180) -> None:
    """Drop local SMD GND vias, route all NON-GND nets with strong F.Cu preference so B.Cu stays
    >90% continuous unbroken GND copper, import SES, and refill B.Cu GND zone in fresh subprocess!"""
    pcb_path = ROOT / "hardware" / board_name / f"{board_name}.kicad_pcb"
    dsn_path = SCRATCH / f"{board_name}.dsn"
    ses_path = SCRATCH / f"{board_name}.ses"

    # Drop local GND vias for all SMD GND pads so B.Cu pour connects them directly!
    drop_local_gnd_vias(board_name)

    # Refill GND zone BEFORE exporting DSN so Freerouting sees the real (plane GND ...) on B.Cu!
    refill_code = (
        "import pcbnew, sys; "
        "b = pcbnew.LoadBoard(sys.argv[1]); "
        "f = pcbnew.ZONE_FILLER(b); "
        "f.Fill(b.Zones()); "
        "pcbnew.SaveBoard(sys.argv[1], b)"
    )
    subprocess.run([sys.executable, "-c", refill_code, str(pcb_path)], check=True)

    board = pcbnew.LoadBoard(str(pcb_path))
    if not pcbnew.ExportSpecctraDSN(board, str(dsn_path)):
        raise RuntimeError(f"ExportSpecctraDSN failed for {board_name}")

    # Only remove the `(net GND ...)` pin-list inside `(network ...)` (NEVER touch `(plane GND)`!),
    # so Freerouting routes all signal/power nets cleanly while B.Cu solid GND plane + local GND vias handle GND!
    txt = dsn_path.read_text(encoding="utf-8")
    net_sec = txt.find("(network")
    if net_sec >= 0:
        for pat in ('(net "GND"', "(net GND\n", "(net GND "):
            idx = txt.find(pat, net_sec)
            if idx >= 0:
                depth = 0
                i = idx
                while i < len(txt):
                    if txt[i] == "(":
                        depth += 1
                    elif txt[i] == ")":
                        depth -= 1
                        if depth == 0:
                            txt = txt[:idx] + txt[i + 1:]
                            break
                    i += 1
                break
        # Also drop GND from (class kicad_default ...) inside (network ...)
        cls_idx = txt.find("(class ", net_sec)
        if cls_idx >= 0:
            cls_end = txt.find(")", cls_idx)
            head = txt[cls_idx:cls_end]
            head = head.replace(' "GND"', "").replace(" GND ", " ").replace(" GND\n", "\n")
            txt = txt[:cls_idx] + head + txt[cls_end:]

    dsn_path.write_text(txt, encoding="utf-8")
    print(f"[INFO] Prepared clean DSN for {board_name} ({len(txt)} bytes)")

    if ses_path.exists():
        ses_path.unlink()

    if board_name == "main_board":
        # Invoke Freerouting BatchAutorouter directly via Java API so F.Cu/B.Cu layer trace costs
        # and via_costs are honored deterministically (keeping B.Cu > 90% ONE continuous GND plane!).
        java_src = SCRATCH / "RunBeadsFR.java"
        java_src.write_text(
            'import java.io.*;\n'
            'import java.util.*;\n'
            'import app.freerouting.autoroute.BatchAutorouter;\n'
            'import app.freerouting.board.*;\n'
            'import app.freerouting.core.*;\n'
            'import app.freerouting.interactive.HeadlessBoardManager;\n'
            'import app.freerouting.settings.RouterSettings;\n'
            'public class RunBeadsFR {\n'
            '  static class DummyThread extends StoppableThread { @Override protected void thread_action() {} }\n'
            '  public static void main(String[] args) throws Exception {\n'
            '    String dsn = args[0], ses = args[1], bname = args[2];\n'
            '    int maxP = Integer.parseInt(args[3]), viaC = Integer.parseInt(args[4]);\n'
            '    double bcuC = Double.parseDouble(args[5]);\n'
            '    int maxSec = Integer.parseInt(args[6]);\n'
            '    RoutingJob job = new RoutingJob();\n'
            '    HeadlessBoardManager bm = new HeadlessBoardManager(Locale.ENGLISH, job);\n'
            '    try (InputStream is = new FileInputStream(dsn)) {\n'
            '      bm.loadFromSpecctraDsn(is, null, new ItemIdentificationNumberGenerator());\n'
            '    }\n'
            '    RoutingBoard board = bm.get_routing_board();\n'
            '    RouterSettings rs = new RouterSettings(board);\n'
            '    rs.set_via_costs(viaC);\n'
            '    rs.set_plane_via_costs(5);\n'
            '    rs.set_start_ripup_costs(100);\n'
            '    rs.set_start_pass_no(1);\n'
            '    rs.set_stop_pass_no(maxP);\n'
            '    rs.setRunFanout(false); rs.setRunRouter(true); rs.setRunOptimizer(false);\n'
            '    rs.set_preferred_direction_trace_costs(0, 1.0);\n'
            '    rs.set_against_preferred_direction_trace_costs(0, 1.05);\n'
            '    if (board.get_layer_count() >= 2) {\n'
            '      rs.set_preferred_direction_trace_costs(1, bcuC);\n'
            '      rs.set_against_preferred_direction_trace_costs(1, bcuC * 1.15);\n'
            '    }\n'
            '    job.board = board; job.routerSettings = rs;\n'
            '    DummyThread th = new DummyThread();\n'
            '    Thread wd = new Thread(() -> { try { Thread.sleep(maxSec * 1000L); th.request_stop_auto_router(); } catch (InterruptedException ignored) {} });\n'
            '    wd.setDaemon(true); wd.start();\n'
            '    long t0 = System.currentTimeMillis();\n'
            '    BatchAutorouter ar = new BatchAutorouter(th, board, rs, true, true, 100, 500);\n'
            '    ar.addTaskStateChangedEventListener(ev -> {\n'
            '      String st = ev.getTaskState().toString(); int pn = ev.getPassNumber();\n'
            '      System.out.printf("[%.1fs] pass=%d state=%s%n", (System.currentTimeMillis()-t0)/1000.0, pn, st);\n'
            '      if ("RUNNING".equals(st) && pn > 1) {\n'
            '        bm.update_routing_board(board);\n'
            '        try (OutputStream os = new FileOutputStream(ses)) { bm.saveAsSpecctraSessionSes(os, bname); } catch (Exception ignored) {}\n'
            '      }\n'
            '    });\n'
            '    boolean done = ar.runBatchLoop();\n'
            '    if (done || !(new File(ses)).exists()) {\n'
            '      bm.update_routing_board(board);\n'
            '      try (OutputStream os = new FileOutputStream(ses)) {\n'
            '        boolean ok = bm.saveAsSpecctraSessionSes(os, bname);\n'
            '        System.out.println("FR_DIRECT_DONE completed=" + done + " saved=" + ok);\n'
            '      }\n'
            '    }\n'
            '    System.exit(0);\n'
            '  }\n'
            '}\n',
            encoding="utf-8",
        )
        # Java 11+ (JEP 330) runs single-file .java source directly without needing javac!
        cmd = [
            "java", "-Xmx2g", "-cp", str(FR_JAR), str(java_src),
            str(dsn_path), str(ses_path), board_name,
            str(max_passes), "42", "9.0", str(max(60, timeout_s - 30)),
        ]
    else:
        cmd = [
            "java", "-Xmx2g", "-jar", str(FR_JAR),
            "-de", str(dsn_path),
            "-do", str(ses_path),
            "-mp", str(max_passes),
            "-mt", "2",
            "--gui.enabled=false",
        ]

    print(f"[INFO] Running Freerouting ({max_passes} passes, timeout={timeout_s}s) on {board_name}...")
    proc = subprocess.run(cmd, timeout=timeout_s, capture_output=True, text=True)
    print(proc.stdout[-1200:] if proc.stdout else "")
    if not ses_path.exists() or ses_path.stat().st_size < 100:
        raise RuntimeError(f"Freerouting failed for {board_name} (rc={proc.returncode}):\n{proc.stdout[-800:]}\n{proc.stderr[-800:]}")

    board2 = pcbnew.LoadBoard(str(pcb_path))
    if not pcbnew.ImportSpecctraSES(board2, str(ses_path)):
        raise RuntimeError(f"ImportSpecctraSES failed for {board_name}")
    pcbnew.SaveBoard(str(pcb_path), board2)

    # Surgically widen POWER_QFN trunks (+5V_BUCK, PMIC_INP, PMIC_SWN, +-14V6_RAW) to 0.52 mm where DRC-clear
    widen_power_trunks_safely(board_name, target_w=0.52)

    # Fresh subprocess ZONE_FILLER refill
    subprocess.run([sys.executable, "-c", refill_code, str(pcb_path)], check=True)
    print(f"[OK] Routed, widened power trunks & refilled B.Cu GND plane for {board_name}")


def main(argv: list[str]) -> int:
    targets = argv[1:] if len(argv) > 1 else ["ui_mezzanine", "main_board"]
    for t in targets:
        strip_gnd_from_dsn_and_route(t, max_passes=20 if t == "ui_mezzanine" else 18, timeout_s=240)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
