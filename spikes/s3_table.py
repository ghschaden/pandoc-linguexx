#!/usr/bin/env python3
"""S3 — glossed-example table: merged translation row, injected column styles,
and absolute-cm vs relative-% width behaviour when the page geometry changes.

Four ODTs are produced: {abs,rel} x {A4 2cm margins (17cm text),
A4 5cm margins (11cm text)}.  Each is rendered to PDF and the right-most ink
position is compared with the right text margin.  The width mode that keeps
the table inside the margins after the geometry change wins and becomes the
emitter default.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from xml.etree import ElementTree as ET

sys.path.insert(0, str(Path(__file__).parent))
import odtzip  # noqa: E402

HERE = Path(__file__).parent
OUT = odtzip.fresh(HERE / "_out" / "s3")

# Wide on purpose: at build width the table must nearly fill the 17cm text
# block, so that squeezing the page to 11cm genuinely stresses the layout.
OBJ = ["esto", "es", "un", "ejemplo", "glosado", "bastante", "largo", "para",
       "llenar", "la", "linea", "entera"]
GLOSS = ["this", "is", "a", "example", "glossed", "rather", "long", "to",
         "fill", "the", "whole", "line"]
TRANS = "'This is a rather long glossed example filling the whole line.'"

NUM_W = 1.1  # cm, the number column
TEXT_W = 17.0  # cm, text width at build time


def widths() -> list[float]:
    """Crude 'optimal-ish' sizing: 0.55em per char at 12pt (~0.42cm/char)."""
    per_char = 0.55 * 12 / 72 * 2.54
    cols = [
        max(1.0, min(6.0, per_char * max(len(o), len(g))))
        for o, g in zip(OBJ, GLOSS)
    ]
    scale = (TEXT_W - NUM_W) / sum(cols)
    if scale < 1:
        cols = [c * scale for c in cols]
    return cols


def styles(mode: str) -> str:
    cols = widths()
    total = NUM_W + sum(cols)
    if mode == "absleft":
        table_props = f'<style:table-properties style:width="{total:.3f}cm" table:align="left"/>'
    elif mode == "abs":
        table_props = f'<style:table-properties style:width="{total:.3f}cm" table:align="margins"/>'

    if mode in ("abs", "absleft"):
        def col(w: float) -> str:
            return f'<style:table-column-properties style:column-width="{w:.3f}cm"/>'
    else:
        table_props = '<style:table-properties style:rel-width="100%" table:align="margins"/>'
        units = [round(w / total * 10000) for w in [NUM_W] + cols]

        def col(w: float, _it=iter(units)) -> str:
            return f'<style:table-column-properties style:rel-column-width="{next(_it)}*"/>'

    out = [
        f'<style:style style:name="LxExTable" style:family="table">{table_props}</style:style>',
        '<style:style style:name="LxExCell" style:family="table-cell">'
        '<style:table-cell-properties fo:padding="0cm" fo:border="none"/></style:style>',
    ]
    for i, w in enumerate([NUM_W] + cols):
        name = "LxExCol." + chr(ord("A") + i)
        out.append(
            f'<style:style style:name="{name}" style:family="table-column">{col(w)}</style:style>'
        )
    return "".join(out)


def table_xml() -> str:
    ncols = 1 + len(OBJ)
    cols = "".join(
        f'<table:table-column table:style-name="LxExCol.{chr(ord("A") + i)}"/>'
        for i in range(ncols)
    )

    def cell(content: str, span: int = 1) -> str:
        sp = f' table:number-columns-spanned="{span}"' if span > 1 else ""
        covered = "<table:covered-table-cell/>" * (span - 1)
        return (
            f'<table:table-cell table:style-name="LxExCell"{sp} office:value-type="string">'
            f"<text:p>{content}</text:p></table:table-cell>{covered}"
        )

    num = (
        '(<text:sequence text:ref-name="refNumEx0" text:name="NumEx"'
        ' text:formula="ooow:NumEx+1" style:num-format="1">99</text:sequence>)'
    )
    r1 = "<table:table-row>" + cell(num) + "".join(cell(w) for w in OBJ) + "</table:table-row>"
    r2 = "<table:table-row>" + cell("") + "".join(cell(g) for g in GLOSS) + "</table:table-row>"
    r3 = "<table:table-row>" + cell("") + cell(TRANS, span=len(OBJ)) + "</table:table-row>"
    return (
        f'<table:table table:name="LxEx1" table:style-name="LxExTable">{cols}{r1}{r2}{r3}</table:table>'
    )


A4 = (
    'fo:margin-bottom="2cm" fo:margin-left="{m}cm" fo:margin-right="{m}cm"'
    ' fo:margin-top="2cm" fo:page-height="29.7cm" fo:page-width="21cm"'
)


def set_page(styles_xml: str, margin: float) -> str:
    return re.sub(
        r'fo:margin-bottom="[^"]*" fo:margin-left="[^"]*" fo:margin-right="[^"]*"'
        r' fo:margin-top="[^"]*" fo:page-height="[^"]*" fo:page-width="[^"]*"',
        A4.format(m=margin),
        styles_xml,
    )


def build(mode: str, margin: float) -> Path:
    doc = {
        "pandoc-api-version": [1, 23, 1],
        "meta": {},
        "blocks": [
            {"t": "Para", "c": [{"t": "Str", "c": "Prose."}]},
            {"t": "RawBlock", "c": ["opendocument", table_xml()]},
        ],
    }
    name = f"{mode}_{margin:g}cm"
    src = OUT / f"{name}.json"
    src.write_text(json.dumps(doc), encoding="utf-8")
    raw = OUT / f"{name}_raw.odt"
    subprocess.run(["pandoc", "-f", "json", str(src), "-o", str(raw)], check=True)

    content = odtzip.inject_automatic_styles(
        odtzip.inject_sequence_decls(odtzip.read_member(raw, "content.xml")), styles(mode)
    )
    st = set_page(odtzip.read_member(raw, "styles.xml"), margin)
    odt = OUT / f"{name}.odt"
    odtzip.patch(raw, odt, {"content.xml": content, "styles.xml": st})
    return odt


def right_edge(pdf: Path) -> tuple[float, float]:
    """Return (rightmost ink x, page width) in pt from pdftotext -bbox."""
    xml = subprocess.run(
        ["pdftotext", "-bbox", str(pdf), "-"], check=True, capture_output=True, text=True
    ).stdout
    root = ET.fromstring(xml)
    ns = {"x": "http://www.w3.org/1999/xhtml"}
    page = root.find(".//x:page", ns)
    return (
        max(float(w.get("xMax")) for w in page.findall(".//x:word", ns)),
        float(page.get("width")),
    )


CM = 72 / 2.54


def main() -> int:
    rows = []
    for mode in ("abs", "absleft", "rel"):
        for margin in (2.0, 5.0):
            odt = build(mode, margin)
            pdf = odtzip.soffice_convert(odt, "pdf", OUT)
            ink, pw = right_edge(pdf)
            limit = pw - margin * CM
            text = odtzip.pdf_text(pdf)
            rows.append(
                (
                    mode,
                    margin,
                    ink / CM,
                    limit / CM,
                    ink <= limit + 2,
                    "(1)" in text and TRANS.strip("'") in text.replace("’", "'"),
                )
            )

    print(f"table build width: {NUM_W + sum(widths()):.2f}cm")
    print(f"{'mode':7} {'margin':>7} {'ink→cm':>8} {'limit cm':>9} {'inside':>7} {'content ok':>11}")
    for mode, margin, ink, limit, inside, ok in rows:
        print(f"{mode:7} {margin:6}cm {ink:8.2f} {limit:9.2f} {str(inside):>7} {str(ok):>11}")

    bad = [r for r in rows if not r[5]]
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
