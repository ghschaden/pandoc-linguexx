#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Gerhard Schaden
"""Check (or --write) the converter XML used by the editor's 1.5 tests.

Source and expected typed lines are reviewed fixtures; only XML is generated.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from linguexx2odt.emit_base import emitter_for  # noqa: E402
from linguexx2odt.extract import parse  # noqa: E402
from linguexx2odt.styles import Layout  # noqa: E402
from linguexx2odt.styles_docx import styles_fragment  # noqa: E402


def package(case):
    parsed = parse(case['source'])
    emitter = emitter_for('docx', layout=Layout(text_width_cm=case.get('width', 17)))
    emitter.prepare(parsed.examples)
    return (
        '<pkg:package xmlns:pkg="http://schemas.microsoft.com/office/2006/xmlPackage" '
        'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        '<pkg:part pkg:name="/word/document.xml"><pkg:xmlData><w:document><w:body>'
        + emitter.example(parsed.examples[0])
        + '</w:body></w:document></pkg:xmlData></pkg:part>'
        '<pkg:part pkg:name="/word/styles.xml"><pkg:xmlData><w:styles>'
        + styles_fragment(Layout())
        + '</w:styles></pkg:xmlData></pkg:part></pkg:package>')


def main():
    path = ROOT / 'tests/fixtures/linguexx15-untypeset.json'
    cases = json.loads(path.read_text())
    stale = []
    for name, case in cases.items():
        xml = package(case)
        if xml != case['xml']:
            stale.append(name)
            case['xml'] = xml
    if '--write' in sys.argv:
        path.write_text(json.dumps(cases, ensure_ascii=False, indent=2) + '\n')
        return 0
    if stale:
        print(f"Stale editor gloss fixtures: {stale}; run tools/editor_gloss_oracle.py --write")
        return 1
    print('Editor gloss fixtures match the converter')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
