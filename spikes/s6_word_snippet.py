#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""S6: a Script Lab snippet that puts the converter's own .docx examples
into Word through Office.js `insertOoxml`, and reports what Word made of
them.

    PYTHONPATH=src python3 spikes/s6_word_snippet.py OUT.yaml

Converts tests/e2e/word-sample.tex with `--to docx`, takes its five
example tables, the cross-reference paragraph and styles.xml, and packs
them as the flat OPC package `insertOoxml` takes.  A second package
holds a copy of example (1), bookmark renamed, to insert in front of the
rest and see whether numbers and references follow.  Import OUT.yaml in
Script Lab (Import > paste) and press the buttons in order.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PKG = "http://schemas.microsoft.com/office/2006/xmlPackage"
REL = "http://schemas.openxmlformats.org/package/2006/relationships"
OFFDOC = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"


def convert() -> tuple[str, str]:
    """(document.xml, styles.xml) of the converted word-sample."""
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "sample.docx"
        subprocess.run(
            [sys.executable, "-m", "linguexx2odt",
             str(ROOT / "tests/e2e/word-sample.tex"), "--to", "docx",
             "-o", str(out)],
            check=True, env={"PYTHONPATH": str(ROOT / "src"), "PATH": "/usr/bin:/bin"})
        z = zipfile.ZipFile(out)
        return z.read("word/document.xml").decode(), z.read("word/styles.xml").decode()


def strip_decl(xml: str) -> str:
    return re.sub(r"^<\?xml[^>]*\?>\s*", "", xml)


def package(document: str, body: str, styles: str | None) -> str:
    """A flat OPC package: document.xml holding `body`, plus styles.xml."""
    root = re.match(r"(<w:document[^>]*>)", strip_decl(document)).group(1)
    doc = f"{root}<w:body>{body}</w:body></w:document>"
    parts = [
        ("/_rels/.rels", "application/vnd.openxmlformats-package.relationships+xml",
         f'<Relationships xmlns="{REL}"><Relationship Id="rId1" '
         f'Type="{OFFDOC}/officeDocument" Target="word/document.xml"/></Relationships>'),
        ("/word/_rels/document.xml.rels",
         "application/vnd.openxmlformats-package.relationships+xml",
         f'<Relationships xmlns="{REL}">'
         + (f'<Relationship Id="rId1" Type="{OFFDOC}/styles" Target="styles.xml"/>'
            if styles is not None else "")
         + "</Relationships>"),
        ("/word/document.xml",
         "application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml",
         doc),
    ]
    if styles is not None:
        parts.append(("/word/styles.xml",
                      "application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml",
                      strip_decl(styles)))
    inner = "".join(
        f'<pkg:part pkg:name="{name}" pkg:contentType="{ctype}">'
        f"<pkg:xmlData>{xml}</pkg:xmlData></pkg:part>"
        for name, ctype, xml in parts)
    return (f'<?xml version="1.0" standalone="yes"?>'
            f'<pkg:package xmlns:pkg="{PKG}">{inner}</pkg:package>')


SCRIPT = r"""
const ALL = __ALL__;
const NEW = __NEW__;
const NEW_BARE = __NEW_BARE__;
const SEQ_PARA = __SEQ_PARA__;

const out = document.getElementById("out") as HTMLElement;
function say(s: string) { out.textContent += s + "\n"; console.log(s); }

async function step(name: string, fn: (ctx: Word.RequestContext) => Promise<void>) {
  say("=== " + name);
  try { await Word.run(fn); } catch (e: any) {
    say("ERROR " + (e.code || "") + " " + e.message +
        (e.debugInfo ? " " + JSON.stringify(e.debugInfo) : ""));
  }
  await report();
}

async function report() {
  try {
    await Word.run(async (ctx) => {
      const tables = ctx.document.body.tables;
      tables.load("items/rowCount,items/values");
      await ctx.sync();
      say("tables: " + tables.items.length + "  rows: " +
          tables.items.map(t => t.rowCount).join(","));
    });
  } catch (e: any) { say("tables: ERROR " + e.message); }
  try {
    await Word.run(async (ctx) => {
      const fields = ctx.document.body.fields;
      fields.load("items/code,items/result/text");
      await ctx.sync();
      say("fields: " + fields.items.length);
      fields.items.forEach(f => say("  [" + f.code.trim() + "] -> " +
                                    JSON.stringify(f.result.text)));
    });
  } catch (e: any) { say("fields: ERROR " + e.message); }
  try {
    await Word.run(async (ctx) => {
      const names = ctx.document.body.getRange("Whole").getBookmarks(true, true);
      await ctx.sync();
      say("bookmarks: " + names.value.join(" "));
    });
  } catch (e: any) { say("bookmarks: ERROR " + e.message); }
  try {
    await Word.run(async (ctx) => {
      const styles = ctx.document.getStyles();
      styles.load("items/nameLocal,items/builtIn");
      await ctx.sync();
      say("Lx styles: " + styles.items.map(s => s.nameLocal)
                            .filter(n => n.startsWith("Lx")).join(" "));
    });
  } catch (e: any) { say("styles: ERROR " + e.message); }
  try {
    await Word.run(async (ctx) => {
      const body = ctx.document.body;
      body.load("text");
      await ctx.sync();
      say("text: " + JSON.stringify(body.text.replace(/\s+/g, " ").slice(0, 400)));
    });
  } catch (e: any) { say("text: ERROR " + e.message); }
  say("");
}

(document.getElementById("b1") as HTMLElement).onclick = () => step("1 insert examples",
  async (ctx) => { ctx.document.body.insertOoxml(ALL, "End"); await ctx.sync(); });
(document.getElementById("b2a") as HTMLElement).onclick = () => step("2a NEW at Start, no styles part",
  async (ctx) => { ctx.document.body.insertOoxml(NEW_BARE, "Start"); await ctx.sync(); });
(document.getElementById("b2b") as HTMLElement).onclick = () => step("2b NEW before the first paragraph",
  async (ctx) => {
    ctx.document.body.paragraphs.getFirst().insertOoxml(NEW_BARE, "Before");
    await ctx.sync();
  });
(document.getElementById("b2c") as HTMLElement).onclick = () => step("2c NEW at End",
  async (ctx) => { ctx.document.body.insertOoxml(NEW_BARE, "End"); await ctx.sync(); });
(document.getElementById("b2d") as HTMLElement).onclick = () => step("2d one SEQ paragraph at Start",
  async (ctx) => { ctx.document.body.insertOoxml(SEQ_PARA, "Start"); await ctx.sync(); });
(document.getElementById("b3") as HTMLElement).onclick = () => step("3 update every field",
  async (ctx) => {
    const fields = ctx.document.body.fields;
    fields.load("items");
    await ctx.sync();
    fields.items.forEach(f => f.updateResult());
    await ctx.sync();
  });
(document.getElementById("b4") as HTMLElement).onclick = () => report();
(document.getElementById("b5") as HTMLElement).onclick = () => step("4 renumber by hand",
  async (ctx) => {
    // Word on the web does not recalculate, so write the values ourselves:
    // count SEQ NumEx in document order, note which bookmark wraps each,
    // then give every REF the number of its bookmark.
    const fields = ctx.document.body.fields;
    fields.load("items/code");
    await ctx.sync();
    const seqs = fields.items.filter(f => /^\s*SEQ\s+NumEx\b/.test(f.code));
    const refs = fields.items.filter(f => /^\s*REF\s+\S+/.test(f.code));
    const marks = seqs.map(f => f.result.getBookmarks(true, true));
    await ctx.sync();
    const number: { [name: string]: number } = {};
    seqs.forEach((f, i) => {
      f.result.insertText(String(i + 1), "Replace");
      marks[i].value.forEach(b => { number[b] = i + 1; });
    });
    say("bookmark -> number: " + JSON.stringify(number));
    refs.forEach(f => {
      const name = f.code.trim().split(/\s+/)[1];
      if (name in number) f.result.insertText(String(number[name]), "Replace");
      else say("REF to " + name + ": no SEQ found under that bookmark");
    });
    await ctx.sync();
  });
"""

SEQ_PARA = ('<w:p><w:r><w:t xml:space="preserve">SEQ paragraph: (</w:t></w:r>'
            '<w:bookmarkStart w:id="901" w:name="S6Seq"/>'
            '<w:r><w:fldChar w:fldCharType="begin"/></w:r>'
            '<w:r><w:instrText xml:space="preserve"> SEQ NumEx \\* ARABIC </w:instrText></w:r>'
            '<w:r><w:fldChar w:fldCharType="separate"/></w:r>'
            '<w:r><w:t>0</w:t></w:r>'
            '<w:r><w:fldChar w:fldCharType="end"/></w:r>'
            '<w:bookmarkEnd w:id="901"/>'
            '<w:r><w:t>)</w:t></w:r></w:p>')

HTML = """<p>S6 &mdash; 1 once in a blank document; then 2a, 2b, 2c, 2d, pressing 3 after any that inserts. Select the log by hand to copy it.</p>
<button id="b1">1. Insert examples</button>
<button id="b2a">2a. NEW at start, no styles</button>
<button id="b2b">2b. NEW before first paragraph</button>
<button id="b2c">2c. NEW at end</button>
<button id="b2d">2d. one SEQ paragraph at start</button>
<button id="b3">3. Update every field</button>
<button id="b5">4. Renumber by hand</button>
<button id="b4">Report only</button>
<pre id="out" style="white-space:pre-wrap;font-size:11px"></pre>
"""


def indent(s: str) -> str:
    return "".join("    " + line + "\n" if line else "\n" for line in s.splitlines())


def main() -> int:
    document, styles = convert()
    body = document.split("<w:body>", 1)[1].split("<w:sectPr", 1)[0]
    parts = re.findall(r"<w:tbl>.*?</w:tbl>|<w:p[ >].*?</w:p>|<w:p/>", body, re.S)
    tables = [p for p in parts if p.startswith("<w:tbl>")]
    xref = next(p for p in parts if "REF " in p and p.startswith("<w:p"))
    assert len(tables) == 5, len(tables)
    names = re.findall(r'w:bookmarkStart w:id="\d+" w:name="([^"]+)"', tables[0])
    new = tables[0].replace(f'w:name="{names[0]}"', 'w:name="S6New"')
    new = re.sub(r'(<w:t[^>]*>)A plain example', r"\1NEW, inserted in front", new)
    after = "<w:p><w:r><w:t>Paragraph after NEW.</w:t></w:r></w:p>"
    script = (SCRIPT.replace("__ALL__", json.dumps(package(document, "".join(tables) + xref, styles)))
                    .replace("__NEW__", json.dumps(package(document, new + after, styles)))
                    .replace("__NEW_BARE__", json.dumps(package(document, new + after, None)))
                    .replace("__SEQ_PARA__", json.dumps(package(document, SEQ_PARA, None))))
    yaml = ("name: S6 insertOoxml\n"
            "description: linguexx2odt examples through insertOoxml\n"
            "host: WORD\napi_set: {}\n"
            "script:\n  content: |\n" + indent(script) + "  language: typescript\n"
            "template:\n  content: |\n" + indent(HTML) + "  language: html\n"
            "style:\n  content: ''\n  language: css\n"
            "libraries: |\n"
            "  https://appsforoffice.microsoft.com/lib/1/hosted/office.js\n"
            "  @types/office-js\n")
    Path(sys.argv[1]).write_text(yaml, encoding="utf-8")
    stem = Path(sys.argv[1]).with_suffix("")
    Path(f"{stem}-script.ts").write_text(script.lstrip("\n"), encoding="utf-8")
    Path(f"{stem}-html.html").write_text(HTML, encoding="utf-8")
    print(f"also {stem}-script.ts and {stem}-html.html, for pasting into the tabs")
    print(f"{sys.argv[1]}: {len(yaml)} bytes; example bookmark {names[0]} -> S6New")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
