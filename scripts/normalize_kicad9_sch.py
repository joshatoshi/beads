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


def main(argv: list[str]) -> int:
    root = pathlib.Path(__file__).resolve().parents[1]
    targets = [pathlib.Path(a) for a in argv[1:]] if len(argv) > 1 else sorted(
        (root / "hardware").rglob("*.kicad_sch")
    )
    changed = 0
    for p in targets:
        raw = p.read_text(encoding="utf-8")
        fixed = normalize_sch_text(raw)
        if fixed != raw:
            p.write_text(fixed, encoding="utf-8")
            changed += 1
            print(f"Normalized KiCad 9 syntax: {p}")
    print(f"Done ({changed}/{len(targets)} updated).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
