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


def main(argv: list[str]) -> int:
    root = pathlib.Path(__file__).resolve().parents[1]
    targets = [pathlib.Path(a) for a in argv[1:]] if len(argv) > 1 else sorted(
        (root / "hardware").rglob("*.kicad_sch")
    )
    changed = 0
    for p in targets:
        raw = p.read_text(encoding="utf-8")
        fixed = sync_child_sheet_instances(p, normalize_sch_text(raw))
        if fixed != raw:
            p.write_text(fixed, encoding="utf-8")
            changed += 1
            print(f"Normalized KiCad 9 syntax: {p}")
    print(f"Done ({changed}/{len(targets)} updated).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
