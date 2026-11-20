#!/usr/bin/env python3
"""Normalize KiCad 10 tokens emitted by Konnect MCP back to KiCad 9.0.2 schematic syntax.

Konnect MCP may emit KiCad 10 schema fields ((version 20260101), (body_style N),
(in_pos_files yes|no), (show_name yes|no), (do_not_autoplace yes|no), and top-level
(hide yes) on properties) while kicad-cli 9.0.2 expects KiCad 9 schematic schema
(version 20250114) with (hide yes) inside (effects ...).
"""
from __future__ import annotations

import pathlib
import re
import sys


def normalize_sch_text(txt: str) -> str:
    txt = txt.replace("(version 20260101)", "(version 20250114)")
    txt = txt.replace('(generator_version "10.0")', '(generator_version "9.0")')
    txt = re.sub(r"\(body_style\s+\d+\)\s*", "", txt)
    txt = re.sub(r"\(in_pos_files\s+(?:yes|no)\)\s*", "", txt)
    txt = re.sub(r"\s*\(show_name\s+(?:yes|no)\)", "", txt)
    txt = re.sub(r"\s*\(do_not_autoplace\s+(?:yes|no)\)", "", txt)
    # Move standalone (hide yes) immediately preceding (effects ...) into (effects ...)
    txt = re.sub(
        r"\n([ \t]*)\(hide yes\)\n([ \t]*)\(effects\b",
        r"\n\2(effects\n\2\t(hide yes)",
        txt,
    )
    # Also handle inline/single-line property (hide yes) before (effects if any
    txt = re.sub(
        r"\(hide yes\)\s*\(effects\b",
        "(effects (hide yes)",
        txt,
    )
    return txt


def sync_child_sheet_instances(sch_path: pathlib.Path, txt: str) -> str:
    """Ensure Konnect-added symbols on child sheets carry the parent project's hierarchical instance path."""
    stem = sch_path.stem
    parent_dir = sch_path.parent
    root_sch = parent_dir / f"{parent_dir.name}.kicad_sch"
    if not root_sch.exists() or root_sch.resolve() == sch_path.resolve():
        return txt
    root_txt = root_sch.read_text(encoding="utf-8")
    m_root = re.search(r'\(uuid\s+"([^"]+)"\)', root_txt)
    if not m_root:
        return txt
    root_uuid = m_root.group(1)
    # Find the sheet block in root_sch referencing sch_path.name
    sheet_uuid = None
    for m_sh in re.finditer(r'\(sheet\s+\(at\b.*?\(uuid\s+"([^"]+)"\).*?\)', root_txt, re.S):
        blk = m_sh.group(0)
        if f'"{sch_path.name}"' in blk:
            sheet_uuid = m_sh.group(1)
            break
    if not sheet_uuid:
        # Fallback: locate property "Sheetfile" "<name>" and nearest preceding/following (uuid "...")
        idx = root_txt.find(f'"{sch_path.name}"')
        if idx >= 0:
            s_start = root_txt.rfind("(sheet", 0, idx)
            m_u = re.search(r'\(uuid\s+"([^"]+)"\)', root_txt[s_start:idx + 400])
            if m_u:
                sheet_uuid = m_u.group(1)
    if not sheet_uuid:
        return txt

    root_proj = root_sch.stem
    pat = re.compile(
        r'\(project\s+"' + re.escape(stem) + r'"\s*\n([ \t]*)\(path\s+"([^"]+)"\s*\n'
        r'([ \t]*)\(reference\s+"([^"]+)"\)\s*\n([ \t]*)\(unit\s+(\d+)\)\)\)',
        re.M,
    )

    def repl(m: re.Match[str]) -> str:
        ind_p, child_path, ind_r, ref, ind_u, unit = m.groups()
        hier_path = f"/{root_uuid}/{sheet_uuid}"
        return (
            f'(project "{root_proj}"\n'
            f'{ind_p}(path "{child_path}"\n'
            f'{ind_r}(reference "{ref}")\n'
            f'{ind_u}(unit {unit}))\n'
            f'{ind_p}(path "{hier_path}"\n'
            f'{ind_r}(reference "{ref}")\n'
            f'{ind_u}(unit {unit})))'
        )

    return pat.sub(repl, txt)


def _split_lib_symbols(txt: str) -> tuple[str, str, str]:
    """Split a .kicad_sch file into (prefix, lib_symbols_block, body_after_lib_symbols)."""
    ls_idx = txt.find("(lib_symbols")
    if ls_idx == -1:
        return "", "", txt
    depth = 0
    i = ls_idx
    while i < len(txt):
        if txt[i] == "(":
            depth += 1
        elif txt[i] == ")":
            depth -= 1
            if depth == 0:
                return txt[:ls_idx], txt[ls_idx : i + 1], txt[i + 1 :]
        i += 1
    return "", "", txt


def normalize_sheet_layout_and_metadata(sch_path: pathlib.Path, txt: str) -> str:
    """Idempotently normalize KiCad 9 paper sizes, multi-line text newlines, SW_MIDI_AB Unit 2 mirror,
    02_audio left-border margin, and main_board sheet_instances page numbers (1..5)."""
    name = sch_path.name

    # 1. Upgrade main_board hierarchical child sheets 01..04 to A2 (594 x 420 mm) so 100% of symbols/labels
    #    fit comfortably inside page borders and clear of the lower-right title block.
    if re.match(r"^0[1-4]_.*\.kicad_sch$", name):
        txt = re.sub(r'\(paper\s+"A4"\)', '(paper "A2")', txt, count=1)

    prefix, lib_blk, body = _split_lib_symbols(txt)

    # 2. Replace double-escaped literal \\n inside (text "...") annotations with real KiCad \n line breaks.
    def _fix_text_block(m: re.Match[str]) -> str:
        inner = m.group(1).replace("\\\\n", "\\n")
        return f'(text "{inner}"'

    body = re.sub(r'\(text\s+"((?:[^"\\]|\\.)*)"', _fix_text_block, body)

    # 3. On 02_audio_bypass_preamp.kicad_sch, shift placed elements +25.40 mm East if any anchor sits
    #    west of the 10.0 mm drawing border (idempotent guard: only runs when min_x < 20.0 mm).
    if name == "02_audio_bypass_preamp.kicad_sch":
        xs = [float(m.group(1)) for m in re.finditer(r'\((?:at|xy)\s+([-\d.]+)\s+[-\d.]+', body)]
        if xs and min(xs) < 20.0:
            shift_x = 25.4
            def _shift_coord(m: re.Match[str]) -> str:
                tag, x_s, rest = m.group(1), m.group(2), m.group(3)
                nx = round(float(x_s) + shift_x, 4)
                nx_s = f"{nx:g}"
                return f"({tag} {nx_s}{rest})"
            body = re.sub(r'\((at|xy)\s+([-\d.]+)(\s+[-\d.]+(?:\s+[-\d.]+)?)\)', _shift_coord, body)

    # 4. On 04_mcu_midi_btb.kicad_sch, visually mirror SW_MIDI_AB Unit 2 vertically ((mirror x)) so
    #    schematic pin ordering matches C&K JS202011AQN's CCW Row-2 pins (6-5-4) with zero net changes.
    if name == "04_mcu_midi_btb.kicad_sch":
        def _mirror_sw_u2(m: re.Match[str]) -> str:
            blk = m.group(0)
            if "(mirror x)" in blk:
                return blk
            return re.sub(
                r'(\(at\s+250\.19\s+64\.77\s+0\))',
                r'\1\n\t\t(mirror x)',
                blk,
                count=1,
            )
        body = re.sub(
            r'\(symbol\s+\(lib_id\s+"Switch:SW_DPDT_x2"\)\s+\(at\s+250\.19\s+64\.77\s+0\)(?:\s+\(mirror\s+[xy]\))?\s+\(unit\s+2\)',
            _mirror_sw_u2,
            body,
            count=1,
        )

    # 5. On main_board.kicad_sch, rebuild (sheet_instances ...) cleanly from live (sheet ...) blocks
    #    ordered 01..04 so pages are strictly 1/5 .. 5/5 with zero stale orphan UUIDs.
    if name == "main_board.kicad_sch":
        m_root = re.search(r'\(uuid\s+"?([0-9a-f-]+)"?\)', prefix or txt)
        if m_root:
            root_uuid = m_root.group(1)
            sheets: list[tuple[str, str]] = []
            pos = 0
            while True:
                s_idx = body.find("(sheet\n", pos)
                if s_idx == -1:
                    s_idx = body.find("(sheet ", pos)
                if s_idx == -1:
                    break
                d = 0
                j = s_idx
                while j < len(body):
                    if body[j] == "(":
                        d += 1
                    elif body[j] == ")":
                        d -= 1
                        if d == 0:
                            sblk = body[s_idx : j + 1]
                            pos = j + 1
                            break
                    j += 1
                mu = re.search(r'\(uuid\s+"([^"]+)"\)', sblk)
                mf = re.search(r'\(property\s+"Sheet file"\s+"([^"]+)"', sblk)
                if mu and mf:
                    sheets.append((mf.group(1), mu.group(1)))
            if sheets:
                sheets.sort(key=lambda item: item[0])
                lines = ['\t(sheet_instances', '\t\t(path "/"', '\t\t\t(page "1")', '\t\t)']
                for pg, (_, suuid) in enumerate(sheets, start=2):
                    lines.append(f'\t\t(path "/{root_uuid}/{suuid}"')
                    lines.append(f'\t\t\t(page "{pg}")')
                    lines.append('\t\t)')
                lines.append('\t)')
                new_si = "\n".join(lines)
                si_idx = body.find("(sheet_instances")
                if si_idx != -1:
                    d = 0
                    j = si_idx
                    while j < len(body):
                        if body[j] == "(":
                            d += 1
                        elif body[j] == ")":
                            d -= 1
                            if d == 0:
                                body = body[:si_idx] + new_si.lstrip("\t") + body[j + 1 :]
                                break
                        j += 1

    return prefix + lib_blk + body


def main(argv: list[str]) -> int:
    root = pathlib.Path(__file__).resolve().parents[1]
    targets = [pathlib.Path(a) for a in argv[1:]] if len(argv) > 1 else sorted(
        (root / "hardware").rglob("*.kicad_sch")
    )
    changed = 0
    for p in targets:
        raw = p.read_text(encoding="utf-8")
        fixed = normalize_sheet_layout_and_metadata(p, sync_child_sheet_instances(p, normalize_sch_text(raw)))
        if fixed != raw:
            p.write_text(fixed, encoding="utf-8")
            changed += 1
            print(f"Normalized KiCad 9 syntax: {p}")
    print(f"Done ({changed}/{len(targets)} updated).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
