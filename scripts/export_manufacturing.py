#!/usr/bin/env python3
"""Worktree-portable JLCPCB Manufacturing Exporter & jlcpcb_parts.db / CPL Parity Verifier.

Generates for all 3 boards (main_board, ui_mezzanine, faceplate_14hp):
  - KiCad 9 Gerbers + Excellon PTH/NPTH drill files + ZIP archive
  - KiCad 9 Schematic PDFs
  - main_board JLCPCB Top-Side SMT BOM + EasyEDA-verified Pin-1/centroid CPL CSV (zero THT!)
  - Hand-solder THT BOM CSVs for main_board & ui_mezzanine
Validates 100% of SMT BOM lines directly against /home/yerbaadmin/.local/share/kicad-mcp/jlcpcb_parts.db.
"""
from __future__ import annotations

import csv
import json
import math
import pathlib
import re
import sqlite3
import subprocess
import sys
import zipfile
import pcbnew

ROOT = pathlib.Path(__file__).resolve().parents[1]
CONTRACT = json.loads((ROOT / "hardware_contract.json").read_text(encoding="utf-8"))
DB_PATH = pathlib.Path("/home/yerbaadmin/.local/share/kicad-mcp/jlcpcb_parts.db")
MFG_DIR = ROOT / "manufacturing"

# Authoritative verified LCSC catalog (100% verified against jlcpcb_parts.db)
# Key = (value, footprint_substring) -> (lcsc, comment_str, top_rot_offset_deg, local_centroid_dx_dy_mm, expected_pkg_tokens)
SMT_LCSC_MAP: dict[str, tuple[str, str, float, tuple[float, float], tuple[str, ...]]] = {
    # Active ICs, Relays, PhotoMOS, Power, Semiconductors, Connectors, Inductors
    "RP2040":           ("C2040",     "RP2040",                       0.0,   (0.0,  0.0),  ("QFN-56", "LQFN-56")),
    "W25Q128JVSIQ":     ("C97521",    "W25Q128JVSIQ",               270.0,   (0.0,  0.0),  ("SOIC-8",)),
    "12MHz_20pF":       ("C9002",     "X322512MSB4SI 12MHz 20pF",     0.0,   (0.0,  0.0),  ("3225",)),
    "MCP4822-E/SN":     ("C16040",    "MCP4822-E/SN",               270.0,   (0.0,  0.0),  ("SOIC-8",)),
    "TL072CDT":         ("C6961",     "TL072CDT",                   270.0,   (0.0,  0.0),  ("SO-8", "SOIC-8")),
    "NE5532DR":         ("C7426",     "NE5532DR",                   270.0,   (0.0,  0.0),  ("SOIC-8",)),
    "OP07CDR":          ("C7433",     "OP07CDR",                    270.0,   (0.0,  0.0),  ("SOIC-8",)),
    "CJ431":            ("C3113",     "CJ431",                      180.0,   (0.0,  0.0),  ("SOT-23",)),
    "MCP6002T-I/SN":    ("C7377",     "MCP6002T-I/SN",              270.0,   (0.0,  0.0),  ("SOIC-8",)),
    "74HC14D,653":      ("C5605",     "74HC14D,653",                270.0,   (0.0,  0.0),  ("SOIC-14",)),
    "G6K-2F-Y-TR_DC5":  ("C47190",    "G6K-2F-Y-TR DC5",            270.0,   (0.0,  0.0),  ("SMD", "G6K")),
    "TLP172AM":         ("C2152276",  "TLP172AM(TPL,E",             270.0,   (0.0,  0.0),  ("SOP-4",)),
    "TPS5430DDAR":      ("C9864",     "TPS5430DDAR",                  0.0,   (0.0,  0.0),  ("SOIC-8",)),
    "TPS65131RGER":     ("C87663",    "TPS65131RGER",                 0.0,   (0.0,  0.0),  ("QFN-24",)),
    "LM317AG-TN3-R":    ("C75510",    "LM317AG-TN3-R",                0.0,   (-1.20, 0.0), ("TO-252",)),
    "79M12(TP)":        ("C53477637", "79M12(TP)",                  180.0,   (-1.20, 0.0), ("TO-252",)),
    "AMS1117-3.3":      ("C6186",     "AMS1117-3.3",                180.0,   (0.0,  0.0),  ("SOT-223",)),
    "10uH_3.5A":        ("C177248",   "FXL0530-100-M 10uH 3.5A",      0.0,   (0.0,  0.0),  ("SMD", "5.4")),
    "BLM18PG121SN1D":   ("C14709",    "BLM18PG121SN1D 120R 2A",       0.0,   (0.0,  0.0),  ("0603",)),
    "1.1A_33V_PTC":     ("C269134",   "SMD1812B110TF/33 1.1A 33V",    0.0,   (0.0,  0.0),  ("1812",)),
    "500mA_30V_PTC":    ("C720075",   "JK-nSMD050-30 500mA 30V",      0.0,   (0.0,  0.0),  ("1206",)),
    "SMBJ20CA":         ("C19077576", "SMBJ20CA 20V 600W TVS",        0.0,   (0.0,  0.0),  ("DO-214AA", "SMB")),
    "BZX84-C9V1":       ("C96231",    "BZX84-C9V1,215 9.1V",        180.0,   (0.0,  0.0),  ("SOT-23",)),
    "SRV05-4-P-T7":     ("C85364",    "SRV05-4-P-T7",               180.0,   (0.0,  0.0),  ("SOT-23-6",)),
    "TYPE-C-31-M-12":   ("C165948",   "TYPE-C-31-M-12",               0.0,   (0.0, -1.50), ("SMD",)),
    "AO3401A":          ("C15127",    "AO3401A",                    180.0,   (0.0,  0.0),  ("SOT-23",)),
    "AO3400A":          ("C20917",    "AO3400A",                    180.0,   (0.0,  0.0),  ("SOT-23",)),
    "SS34":             ("C8678",     "SS34 40V 3A Schottky",         0.0,   (0.0,  0.0),  ("SMA",)),
    "1N5819WS":         ("C191023",   "1N5819WS 40V 1A Schottky",     0.0,   (0.0,  0.0),  ("SOD-323",)),
    "1N4148W":          ("C81598",    "1N4148W 75V 150mA",            0.0,   (0.0,  0.0),  ("SOD-123",)),
    "BAV99":            ("C2500",     "BAV99,215",                  180.0,   (0.0,  0.0),  ("SOT-23",)),
    "TS-1088":          ("C720477",   "TS-1088-AR02016",              0.0,   (0.0,  0.0),  ("SMD", "4")),
    # Resistors (0603 1% & 0805 0.47R)
    "0.47R":            ("C382278",   "0.47R 1% 0805",                0.0,   (0.0,  0.0),  ("0805",)),
    "20R":              ("C22950",    "20R 1% 0603",                  0.0,   (0.0,  0.0),  ("0603",)),
    "27R":              ("C25190",    "27R 1% 0603",                  0.0,   (0.0,  0.0),  ("0603",)),
    "33R":              ("C23140",    "33R 1% 0603",                  0.0,   (0.0,  0.0),  ("0603",)),
    "51R":              ("C23197",    "51R 1% 0603",                  0.0,   (0.0,  0.0),  ("0603",)),
    "100R":             ("C22775",    "100R 1% 0603",                 0.0,   (0.0,  0.0),  ("0603",)),
    "220R":             ("C22962",    "220R 1% 0603",                 0.0,   (0.0,  0.0),  ("0603",)),
    "240R":             ("C23350",    "240R 1% 0603",                 0.0,   (0.0,  0.0),  ("0603",)),
    "270R":             ("C22966",    "270R 1% 0603",                 0.0,   (0.0,  0.0),  ("0603",)),
    "470R":             ("C23179",    "470R 1% 0603",                 0.0,   (0.0,  0.0),  ("0603",)),
    "1k":               ("C21190",    "1k 1% 0603",                   0.0,   (0.0,  0.0),  ("0603",)),
    "1.5k":             ("C22843",    "1.5k 1% 0603",                 0.0,   (0.0,  0.0),  ("0603",)),
    "2k":               ("C22975",    "2k 1% 0603",                   0.0,   (0.0,  0.0),  ("0603",)),
    "2.2k":             ("C4190",     "2.2k 1% 0603",                 0.0,   (0.0,  0.0),  ("0603",)),
    "4.7k":             ("C23162",    "4.7k 1% 0603",                 0.0,   (0.0,  0.0),  ("0603",)),
    "5.1k":             ("C23186",    "5.1k 1% 0603",                 0.0,   (0.0,  0.0),  ("0603",)),
    "10k":              ("C25804",    "10k 1% 0603",                  0.0,   (0.0,  0.0),  ("0603",)),
    "13k":              ("C22797",    "13k 1% 0603",                  0.0,   (0.0,  0.0),  ("0603",)),
    "15k":              ("C22809",    "15k 1% 0603",                  0.0,   (0.0,  0.0),  ("0603",)),
    "18k":              ("C25810",    "18k 1% 0603",                  0.0,   (0.0,  0.0),  ("0603",)),
    "22k":              ("C31850",    "22k 1% 0603",                  0.0,   (0.0,  0.0),  ("0603",)),
    "24k":              ("C23352",    "24k 1% 0603",                  0.0,   (0.0,  0.0),  ("0603",)),
    "30k":              ("C22984",    "30k 1% 0603",                  0.0,   (0.0,  0.0),  ("0603",)),
    "33k":              ("C4216",     "33k 1% 0603",                  0.0,   (0.0,  0.0),  ("0603",)),
    "47k":              ("C25819",    "47k 1% 0603",                  0.0,   (0.0,  0.0),  ("0603",)),
    "68k":              ("C23231",    "68k 1% 0603",                  0.0,   (0.0,  0.0),  ("0603",)),
    "75k":              ("C23242",    "75k 1% 0603",                  0.0,   (0.0,  0.0),  ("0603",)),
    "100k":             ("C25803",    "100k 1% 0603",                 0.0,   (0.0,  0.0),  ("0603",)),
    "1M":               ("C22935",    "1M 1% 0603",                   0.0,   (0.0,  0.0),  ("0603",)),
    "2.2M":             ("C22938",    "2.2M 1% 0603",                 0.0,   (0.0,  0.0),  ("0603",)),
    # Capacitors (verified dielectric & voltage derating!)
    "22pF_50V_C0G":     ("C1653",     "22pF 50V C0G 0603",            0.0,   (0.0,  0.0),  ("0603",)),
    "30pF_50V_C0G":     ("C1658",     "30pF 50V C0G 0603",            0.0,   (0.0,  0.0),  ("0603",)),
    "47pF_50V_C0G":     ("C1671",     "47pF 50V C0G 0603",            0.0,   (0.0,  0.0),  ("0603",)),
    "1nF_50V_C0G":      ("C106246",   "1nF 50V NP0/C0G 0603",         0.0,   (0.0,  0.0),  ("0603",)),
    "4.7nF_50V_X7R":    ("C53987",    "4.7nF 50V X7R 0603",           0.0,   (0.0,  0.0),  ("0603",)),
    "10nF_50V_X7R":     ("C57112",    "10nF 50V X7R 0603",            0.0,   (0.0,  0.0),  ("0603",)),
    "47nF_50V_X7R":     ("C1622",     "47nF 50V X7R 0603",            0.0,   (0.0,  0.0),  ("0603",)),
    "100nF_50V_X7R":    ("C14663",    "100nF 50V X7R 0603",           0.0,   (0.0,  0.0),  ("0603",)),
    "220nF_25V_X7R":    ("C21120",    "220nF 25V X7R 0603",           0.0,   (0.0,  0.0),  ("0603",)),
    "470nF_25V_X7R":    ("C1623",     "470nF 25V X7R 0603",           0.0,   (0.0,  0.0),  ("0603",)),
    "1uF_50V_X7R":      ("C28323",    "1uF 50V X7R 0805",             0.0,   (0.0,  0.0),  ("0805",)),
    "10uF_50V_X7R":     ("C89632",    "10uF 50V X7R 1206",            0.0,   (0.0,  0.0),  ("1206",)),
    "10uF_25V_X5R":     ("C15850",    "10uF 25V X5R 0805",            0.0,   (0.0,  0.0),  ("0805",)),
    "22uF_25V_X5R":     ("C12891",    "22uF 25V X5R 1206",            0.0,   (0.0,  0.0),  ("1206",)),
    "47uF_50V":         ("C72523",    "47uF 50V 105C D6.3x7.7 Elec",  0.0,   (0.0,  0.0),  ("6.3", "SMD")),
}

# THT / Mechanical / Non-PCBA footprints strictly excluded from JLCPCB SMT BOM & CPL!
THT_EXCLUDE_REFS = {
    "J_OUT_R", "J_OUT_L", "J_IN_R", "J_IN_L",
    "J_MIDI_IN", "J_MIDI_THRU", "SW_MIDI_AB", "U_OPTO",
    "J_EURO_PWR", "J_PWR_IN", "J_FS1", "J_FS2", "J_LED_FS1", "J_LED_FS2",
    "J_BTB_AUDIO_CV", "J_BTB_UI_DIG", "TP_DBG_TX",
}


def run(cmd: list[str]) -> None:
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"Command failed: {' '.join(cmd)}\n{r.stdout}\n{r.stderr}")


def export_board_gerbers_and_pdf(board_name: str) -> None:
    hw_dir = ROOT / "hardware" / board_name
    out_dir = MFG_DIR / board_name
    gerb_dir = out_dir / "gerbers"
    gerb_dir.mkdir(parents=True, exist_ok=True)

    pcb = hw_dir / f"{board_name}.kicad_pcb"
    sch = hw_dir / f"{board_name}.kicad_sch"

    # 1. Schematic PDF
    run(["kicad-cli", "sch", "export", "pdf", "-o", str(out_dir / f"{board_name}_schematic.pdf"), str(sch)])

    # 2. Gerbers (2-layer + masks + silk + paste + Edge.Cuts)
    layers = "F.Cu,B.Cu,F.Mask,B.Mask,F.SilkS,B.SilkS,F.Paste,B.Paste,Edge.Cuts"
    run([
        "kicad-cli", "pcb", "export", "gerbers",
        "-o", str(gerb_dir),
        "-l", layers,
        "--subtract-soldermask",
        "--use-drill-file-origin",
        str(pcb),
    ])

    # 3. Excellon Drills (Separate PTH + NPTH per JLCPCB standard!)
    run([
        "kicad-cli", "pcb", "export", "drill",
        "-o", str(gerb_dir) + "/",
        "--format", "excellon",
        "--excellon-separate-th",
        "--drill-origin", "absolute",
        "--excellon-units", "mm",
        "--generate-map",
        "--map-format", "gerberx2",
        str(pcb),
    ])

    # 4. Zip all Gerbers + Drills
    zip_path = out_dir / f"{board_name}_gerbers.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in sorted(gerb_dir.iterdir()):
            if f.is_file():
                zf.write(f, f.name)

    # Verify NPTH drill file exists on boards with mounting/locating holes!
    npth_files = list(gerb_dir.glob("*NPTH*.drl"))
    if board_name in ("main_board", "faceplate_14hp"):
        assert npth_files and npth_files[0].stat().st_size > 50, f"Missing/empty NPTH drill file for {board_name}!"
    print(f"[OK] Exported Gerbers, Drills & PDF for {board_name} -> {zip_path.name}")


def verify_and_export_main_board_pcba() -> None:
    pcb_path = ROOT / "hardware" / "main_board" / "main_board.kicad_pcb"
    out_dir = MFG_DIR / "main_board"
    out_dir.mkdir(parents=True, exist_ok=True)

    board = pcbnew.LoadBoard(str(pcb_path))
    W, H = CONTRACT["boards"]["main_board"]["dimensions_mm"]

    # Check jlcpcb_parts.db
    if not DB_PATH.exists():
        raise FileNotFoundError(f"Missing JLCPCB parts database: {DB_PATH}")
    con = sqlite3.connect(str(DB_PATH))

    bom_groups: dict[tuple[str, str, str], list[str]] = {}
    cpl_rows: list[dict[str, str]] = []
    tht_rows: list[dict[str, str]] = []
    verified_lcsc: dict[str, dict] = {}

    for fp in sorted(board.GetFootprints(), key=lambda f: f.GetReference()):
        ref = fp.GetReference()
        val = fp.GetValue()
        fp_name = fp.GetFPIDAsString()

        if ref.startswith("MH") or ref.startswith("#"):
            continue
        if ref in THT_EXCLUDE_REFS:
            tht_rows.append({"Designator": ref, "Value": val, "Footprint": fp_name})
            continue

        # Must be SMD-only for JLCPCB SMT CPL!
        has_smd = any(p.GetAttribute() == pcbnew.PAD_ATTRIB_SMD for p in fp.Pads())
        assert has_smd, f"Unexpected THT-only footprint not in THT_EXCLUDE_REFS: {ref} ({val}, {fp_name})"

        if val not in SMT_LCSC_MAP:
            raise KeyError(f"Unmapped SMT value in SMT_LCSC_MAP: {ref} val={val!r} fp={fp_name}")

        lcsc, comment, rot_off, (dx_loc, dy_loc), pkg_tokens = SMT_LCSC_MAP[val]

        # Verify against jlcpcb_parts.db once per LCSC code
        if lcsc not in verified_lcsc:
            row = con.execute(
                "SELECT lcsc, mfr_part, package, library_type, stock, description, solder_joints "
                "FROM components WHERE lcsc = ?",
                (lcsc,),
            ).fetchone()
            assert row is not None, f"LCSC {lcsc} ({val}) NOT FOUND in jlcpcb_parts.db!"
            db_lcsc, db_mpn, db_pkg, db_tier, db_stock, db_desc, db_joints = row
            assert db_stock and db_stock > 0, f"LCSC {lcsc} ({db_mpn}) has ZERO stock in jlcpcb_parts.db!"
            pkg_ok = any(tok.upper() in (db_pkg or "").upper() or tok.upper() in (db_desc or "").upper() for tok in pkg_tokens)
            assert pkg_ok, f"Package mismatch for {lcsc}: db_pkg={db_pkg!r}, expected any of {pkg_tokens}"
            verified_lcsc[lcsc] = {
                "mpn": db_mpn, "package": db_pkg, "tier": db_tier,
                "stock": db_stock, "desc": db_desc, "joints": db_joints,
            }

        # Group BOM line
        short_fp = fp_name.split(":")[-1]
        bom_groups.setdefault((comment, short_fp, lcsc), []).append(ref)

        # Compute exact Gerber/JLCPCB centroid & Pin-1 rotation
        # KiCad pcbnew: +X East, +Y South; rotation deg is CCW in Gerber Y-up (+X East, +Y North)
        px = pcbnew.ToMM(fp.GetPosition().x)
        py = pcbnew.ToMM(fp.GetPosition().y)
        k_rot = fp.GetOrientationDegrees() % 360.0
        # Apply local centroid shift (dx_loc, dy_loc in KiCad rot=0 local coords where +Y is down)
        rad = math.radians(k_rot)
        # KiCad CCW rotation transform for (dx_loc, dy_loc) in Y-down PCB coords:
        # x_pcb = px + dx*cos(a) + dy*sin(a), y_pcb = py - dx*sin(a) + dy*cos(a)
        cx_pcb = px + dx_loc * math.cos(rad) + dy_loc * math.sin(rad)
        cy_pcb = py - dx_loc * math.sin(rad) + dy_loc * math.cos(rad)

        # JLCPCB / KiCad pos.csv coordinate sign: Mid X = +cx_pcb, Mid Y = -cy_pcb (matching Edge_Cuts.gm1!)
        mid_x = cx_pcb
        mid_y = -cy_pcb
        jlc_rot = (k_rot + rot_off) % 360.0
        layer = "top" if fp.GetLayer() == pcbnew.F_Cu else "bottom"
        assert layer == "top", f"Expected Top-Side single-sided PCBA on main_board, found {ref} on {layer}!"
        assert 0.0 <= mid_x <= W and -H <= mid_y <= 0.0, (
            f"CPL centroid out of Edge.Cuts bounds for {ref}: ({mid_x:.3f}, {mid_y:.3f}) vs [0,{W}]x[{-H},0]"
        )

        cpl_rows.append({
            "Designator": ref,
            "Val": comment,
            "Package": short_fp,
            "Mid X": f"{mid_x:.4f}mm",
            "Mid Y": f"{mid_y:.4f}mm",
            "Rotation": f"{jlc_rot:.1f}",
            "Layer": layer,
        })

    # Write JLCPCB SMT BOM CSV
    bom_path = out_dir / "main_board_bom.csv"
    with bom_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Comment", "Designator", "Footprint", "LCSC Part #"])
        for (comment, short_fp, lcsc), refs in sorted(bom_groups.items(), key=lambda kv: kv[0][2]):
            w.writerow([comment, ",".join(sorted(refs)), short_fp, lcsc])

    # Write JLCPCB SMT CPL CSV (zero THT!)
    cpl_path = out_dir / "main_board_cpl.csv"
    with cpl_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["Designator", "Val", "Package", "Mid X", "Mid Y", "Rotation", "Layer"])
        w.writeheader()
        w.writerows(cpl_rows)

    # Write THT hand-solder CSV for main_board & ui_mezzanine
    tht_mb_path = out_dir / "main_board_tht_bom.csv"
    with tht_mb_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["Designator", "Value", "Footprint"])
        w.writeheader()
        w.writerows(tht_rows)

    mz_board = pcbnew.LoadBoard(str(ROOT / "hardware" / "ui_mezzanine" / "ui_mezzanine.kicad_pcb"))
    tht_mz_path = MFG_DIR / "ui_mezzanine" / "ui_mezzanine_tht_bom.csv"
    with tht_mz_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["Designator", "Value", "Footprint"])
        w.writeheader()
        for fp in sorted(mz_board.GetFootprints(), key=lambda x: x.GetReference()):
            w.writerow({"Designator": fp.GetReference(), "Value": fp.GetValue(), "Footprint": fp.GetFPIDAsString()})

    # Summary
    tiers = {"Basic": 0, "Preferred": 0, "Extended": 0}
    for info in verified_lcsc.values():
        t = info["tier"]
        if t in tiers:
            tiers[t] += 1
        elif "Basic" in (t or ""):
            tiers["Basic"] += 1
        elif "Preferred" in (t or ""):
            tiers["Preferred"] += 1
        else:
            tiers["Extended"] += 1
    print(
        f"[OK] JLCPCB SMT PCBA Verified: {len(verified_lcsc)} unique LCSC parts "
        f"(100% matched in jlcpcb_parts.db, 0 zero-stock, Basic={tiers['Basic']}, "
        f"Preferred={tiers['Preferred']}, Extended={tiers['Extended']}), "
        f"{len(cpl_rows)} SMD placements (0 THT in CPL), {len(tht_rows)} main_board THT parts."
    )


def main() -> int:
    for b in ["main_board", "ui_mezzanine", "faceplate_14hp"]:
        export_board_gerbers_and_pdf(b)
    verify_and_export_main_board_pcba()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
