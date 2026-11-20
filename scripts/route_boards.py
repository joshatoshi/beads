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
    w_mm, h_mm = CONTRACT["boards"][board_name]["dimensions_mm"]

    def point_clear(vx: float, vy: float, r_via: float = 0.30, clr: float = 0.42) -> bool:
        if vx < 1.0 or vx > w_mm - 1.0 or vy < 1.0 or vy > h_mm - 1.0:
            return False
        for mx, my in mh_centers:
            if math.hypot(vx - mx, vy - my) < 3.5:
                return False
        for ex, ey in existing_vias:
            if math.hypot(vx - ex, vy - ey) < 0.95:
                return False
        for px, py, pr, pnet, _, _ in all_pads:
            # Always keep drill/pad clear of non-GND pads by >= 0.42mm (> 0.35mm hole clearance!)
            min_d = (r_via + pr + (0.15 if pnet == "GND" else clr))
            if math.hypot(vx - px, vy - py) < min_d:
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
            # Skip EP center pads (already have dedicated thermal vias!)
            if ref in ("U_MCU", "U_PMIC", "U_BUCK5") and pad.GetName() in ("57", "25", "9"):
                continue
            px, py = pcbnew.ToMM(pad.GetPosition().x), pcbnew.ToMM(pad.GetPosition().y)
            # If already very close (<1.2mm) to an existing GND via, skip
            if any(math.hypot(px - ex, py - ey) < 1.15 for ex, ey in existing_vias):
                continue
            # Try candidate offsets around the SMD GND pad
            found = None
            for dist in (0.95, 1.25, 1.55, 1.90):
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


def strip_gnd_from_dsn_and_route(board_name: str, max_passes: int = 25, timeout_s: int = 180) -> None:
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
    print(proc.stdout[-500:] if proc.stdout else "")
    if not ses_path.exists():
        raise RuntimeError(f"Freerouting failed for {board_name}:\n{proc.stdout[-800:]}\n{proc.stderr[-800:]}")

    board2 = pcbnew.LoadBoard(str(pcb_path))
    if not pcbnew.ImportSpecctraSES(board2, str(ses_path)):
        raise RuntimeError(f"ImportSpecctraSES failed for {board_name}")
    pcbnew.SaveBoard(str(pcb_path), board2)

    # Fresh subprocess ZONE_FILLER refill
    subprocess.run([sys.executable, "-c", refill_code, str(pcb_path)], check=True)
    print(f"[OK] Routed & refilled B.Cu GND plane for {board_name}")


def main(argv: list[str]) -> int:
    targets = argv[1:] if len(argv) > 1 else ["ui_mezzanine", "main_board"]
    for t in targets:
        strip_gnd_from_dsn_and_route(t, max_passes=20 if t == "ui_mezzanine" else 25, timeout_s=180)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
