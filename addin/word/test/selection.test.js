// SPDX-License-Identifier: GPL-3.0-or-later
//
// Reading a Word selection into the core's tagged lines, and the numbering
// arithmetic -- both pure, so tested here without Word.  The package below
// is shaped like Range.getOoxml()'s: rsids, proofErr, lang, a hyperlink, a
// tracked insertion and deletion, a field, a line break, the section.

import { test } from "node:test";
import assert from "node:assert/strict";

import { parseLines, strip } from "../../core/parse.js";
import { readSelection } from "../selection.js";
import { audit, freshBookmark, numberAt, refTarget, staleMessage } from "../numbering.js";

const W = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"';
function pkg(body, styles = "") {
  const part = (name, xml) =>
    `<pkg:part pkg:name="${name}" pkg:contentType="x"><pkg:xmlData>${xml}</pkg:xmlData></pkg:part>`;
  return '<?xml version="1.0" standalone="yes"?>' +
    '<?mso-application progid="Word.Document"?>' +
    '<pkg:package xmlns:pkg="http://schemas.microsoft.com/office/2006/xmlPackage">' +
    part("/word/document.xml", `<w:document ${W}><w:body>${body}</w:body></w:document>`) +
    (styles ? part("/word/styles.xml", `<w:styles ${W}>${styles}</w:styles>`) : "") +
    "</pkg:package>";
}
const r = (text, rpr = "") =>
  `<w:r w:rsidRPr="00A1B2C3">${rpr ? `<w:rPr>${rpr}</w:rPr>` : ""}<w:t xml:space="preserve">${text}</w:t></w:r>`;
const p = (...runs) => `<w:p w:rsidR="00D4E5F6"><w:pPr><w:rPr><w:lang w:val="de-DE"/></w:rPr></w:pPr>${runs.join("")}</w:p>`;
const SECT = '<w:sectPr><w:pgSz w:w="11906" w:h="16838"/>' +
  '<w:pgMar w:top="1417" w:right="1134" w:bottom="1134" w:left="1134" w:header="708" w:footer="708" w:gutter="0"/></w:sectPr>';
const STYLES = '<w:docDefaults><w:rPrDefault><w:rPr><w:rFonts w:asciiTheme="minorHAnsi" w:hAnsiTheme="minorHAnsi"/>' +
  '<w:sz w:val="24"/></w:rPr></w:rPrDefault></w:docDefaults>' +
  '<w:style w:type="character" w:styleId="Gloss"><w:name w:val="Gloss"/><w:rPr><w:smallCaps/></w:rPr></w:style>' +
  '<w:style w:type="character" w:styleId="GlossChild"><w:name w:val="GlossChild"/><w:basedOn w:val="Gloss"/></w:style>';

test("paragraphs and line breaks are lines; proofing marks and languages are nothing", () => {
  const sel = readSelection(pkg(
    p(r("Ich "), '<w:proofErr w:type="spellStart"/>', r("habe"), '<w:proofErr w:type="spellEnd"/>',
      r(" geschlafen"), '<w:r><w:br/></w:r>', r("I have slept")) +
    p(r("‘I slept.’")) + SECT, STYLES));
  assert.equal(sel.refusal, "");
  assert.deepEqual(sel.lines.map(strip), ["Ich habe geschlafen", "I have slept", "‘I slept.’"]);
  const parsed = parseLines(sel.lines);
  assert.deepEqual(parsed.items[0].tiers.map((t) => t.map(strip)), [["Ich", "habe", "geschlafen"], ["I", "have", "slept"]]);
  assert.equal(strip(parsed.items[0].translation), "‘I slept.’");
});

test("the text block is the page less its margins", () => {
  const sel = readSelection(pkg(p(r("x")) + SECT));
  assert.ok(Math.abs(sel.textWidthCm - 17.0) < 0.01, String(sel.textWidthCm));
  assert.equal(readSelection(pkg(p(r("x")))).textWidthCm, null);
});

test("formats: what a linguist marks, and the small caps a character style brings", () => {
  const sel = readSelection(pkg(p(
    r("the "), r("dog", "<w:rFonts w:ascii=\"Arial\"/><w:i/><w:sz w:val=\"30\"/>"),
    r(" "), r("nom", '<w:rStyle w:val="GlossChild"/>'), r("-"), r("pl", "<w:smallCaps/>"),
    r("x", '<w:b w:val="0"/><w:vertAlign w:val="subscript"/>'), r("u", '<w:u w:val="single"/>'),
  ), STYLES));
  const byText = {};
  let fmt = null;
  for (const ch of sel.lines[0]) {
    const n = ch.charCodeAt(0) - 0xe000;
    if (n >= 0 && n < 250) fmt = sel.formats[n];
    else byText[ch] = fmt;
  }
  assert.deepEqual(byText.d, { italic: true }, "face and size are not carried");
  assert.deepEqual(byText.n, { rStyle: "GlossChild", smallCaps: true }, "small caps through basedOn");
  assert.deepEqual(byText.p, { smallCaps: true });
  assert.deepEqual(byText.x, { vertAlign: "subscript" }, "w:b w:val=0 is off");
  assert.deepEqual(byText.u, { underline: "single" });
  assert.deepEqual(byText.t, {});
});

test("a field shows its result, not its code; deletions are not text; insertions are", () => {
  const field = '<w:r><w:fldChar w:fldCharType="begin"/></w:r><w:r><w:instrText> DATE </w:instrText></w:r>' +
    '<w:r><w:fldChar w:fldCharType="separate"/></w:r>' + r("today") + '<w:r><w:fldChar w:fldCharType="end"/></w:r>';
  const sel = readSelection(pkg(p(
    r("on "), field, '<w:del w:id="1"><w:r><w:delText>never</w:delText></w:r></w:del>',
    '<w:ins w:id="2">', r(" now"), "</w:ins>", '<w:hyperlink r:id="x" xmlns:r="r">', r(" here"), "</w:hyperlink>")));
  assert.deepEqual(sel.lines.map(strip), ["on today now here"]);
});

// An example number in a selection is TAKEN OVER (LxTakeNumber): an example
// untypeset and typeset again keeps the field its references point at.
const seqField = (shown, name = "LxEx5", id = "7") =>
  `<w:bookmarkStart w:id="${id}" w:name="${name}"/>` +
  '<w:r><w:fldChar w:fldCharType="begin"/></w:r><w:r><w:instrText> SEQ NumEx \\* ARABIC </w:instrText></w:r>' +
  '<w:r><w:fldChar w:fldCharType="separate"/></w:r>' + r(shown) + '<w:r><w:fldChar w:fldCharType="end"/></w:r>' +
  `<w:bookmarkEnd w:id="${id}"/>`;

test("a leading example number is taken over: its bookmark kept, its brackets dropped", () => {
  const sel = readSelection(pkg(p(r("("), seqField("3"), r(")"), '<w:r><w:tab/></w:r>', r("Ich habe")) + p(r("I have"))));
  assert.equal(sel.refusal, "");
  assert.deepEqual(sel.number, { bookmark: "LxEx5", shown: "3" });
  assert.deepEqual(parseLines(sel.lines).items[0].tiers.map((t) => t.map(strip)), [["Ich", "habe"], ["I", "have"]]);
  // the simple-field form a converter or another editor may write
  const simple = readSelection(pkg(p(r("("), '<w:bookmarkStart w:id="1" w:name="NumEx0"/>',
    '<w:fldSimple w:instr=" SEQ NumEx ">', r("1"), "</w:fldSimple>", '<w:bookmarkEnd w:id="1"/>', r(") Ich"))));
  assert.deepEqual(simple.number, { bookmark: "NumEx0", shown: "1" });
  assert.deepEqual(simple.lines.map(strip).map((l) => l.trim()), ["Ich"]);
});

test("two numbers, or one part-way through, are refused -- a number must not move", () => {
  assert.match(readSelection(pkg(p(r("("), seqField("1"), r(") a")) + p(r("("), seqField("2", "LxEx6", "8"), r(") b")))).refusal,
    /two example numbers/);
  assert.match(readSelection(pkg(p(r("Ich habe")) + p(r("("), seqField("2"), r(") b")))).refusal, /part-way/);
  assert.match(readSelection(pkg("<w:tbl><w:tr><w:tc>" + p(r("x")) + "</w:tc></w:tr></w:tbl>")).refusal, /table/);
});

test("the default face is reported, a theme as a theme", () => {
  assert.deepEqual(readSelection(pkg(p(r("x")), STYLES)).fonts, ["theme:minorHAnsi"]);
  const named = STYLES.replace('w:asciiTheme="minorHAnsi"', 'w:ascii="Times New Roman"');
  assert.deepEqual(readSelection(pkg(p(r("x")), named)).fonts, ["Times New Roman"]);
});

// -- numbering ------------------------------------------------------------

const f = (code, shown, bookmarks = []) => ({ code, shown, bookmarks });

test("an inserted example is numbered by the example numbers ahead of it", () => {
  assert.equal(numberAt([]), 1);
  assert.equal(numberAt([" SEQ NumEx \\* ARABIC ", " DATE ", " REF LxEx1 \\h ", "SEQ NumEx"]), 3);
  assert.equal(numberAt([" SEQ Figure "]), 1, "another sequence is not ours");
});

test("audit: the right numbers, and exactly what is stale -- S6's own document", () => {
  // After S6's step 2a: NEW inserted in front with its copied cache "1",
  // the SEQ paragraph with its placeholder "0", nothing recalculated.
  const fields = [
    f(" SEQ NumEx \\* ARABIC ", "1", ["S6New"]), f(" SEQ NumEx \\* ARABIC ", "0", ["S6Seq"]),
    f(" REF NumEx0 \\h ", "1"), f(" REF NumEx1 \\h ", "2"), f(" REF NumEx4 \\h ", "5"),
    f(" SEQ NumEx \\* ARABIC ", "1", ["NumEx0"]), f(" SEQ NumEx \\* ARABIC ", "2", ["NumEx1"]),
    f(" SEQ NumEx \\* ARABIC ", "3", ["NumEx2"]), f(" SEQ NumEx \\* ARABIC ", "4", ["NumEx3"]),
    f(" SEQ NumEx \\* ARABIC ", "5", ["NumEx4"]),
  ];
  const { numbers, stale } = audit(fields);
  // the map button 4 computed in Word on the web
  assert.deepEqual(numbers, { S6New: 1, S6Seq: 2, NumEx0: 3, NumEx1: 4, NumEx2: 5, NumEx3: 6, NumEx4: 7 });
  assert.equal(stale.filter((s) => s.kind === "number").length, 6);
  assert.deepEqual(stale.filter((s) => s.kind === "reference").map((s) => [s.shown, s.want]),
    [["1", 3], ["2", 4], ["5", 7]]);
  // many: counted, not listed -- the first live test's pane was a wall of pairs
  assert.match(staleMessage(stale), /^6 example numbers and 3 cross-references \(1 should be 3, 2 should be 4, 5 should be 7\) still/);
  // few: listed
  assert.match(staleMessage(stale.slice(0, 1)), /^1 example number \(0 should be 2\) still/);
  assert.equal(staleMessage([]), "");
});

test("refTarget and freshBookmark", () => {
  assert.equal(refTarget(" REF LxEx9 \\h "), "LxEx9");
  assert.equal(refTarget(" SEQ NumEx "), null);
  const name = freshBookmark([], 1e12);
  assert.match(name, /^LxEx[0-9a-z]+$/);
  assert.equal(freshBookmark([name], 1e12), `${name}_1`);
  assert.ok(name.length <= 40);
});

// Cases the first mutation run showed were missing: each guard below had no
// test that failed without it.

test("a deletion is skipped even where it holds w:t, as a move's source can", () => {
  const sel = readSelection(pkg(p(r("kept"),
    '<w:del w:id="3">', r(" gone"), "</w:del>", '<w:moveFrom w:id="4">', r(" moved"), "</w:moveFrom>")));
  assert.deepEqual(sel.lines.map(strip), ["kept"]);
});

test("text inside a field's code is code: IF with a nested field shows only its result", () => {
  // { IF { MERGEFIELD n } = "1" "yes" "no" } -- the nested field's result
  // lies inside the outer field's code, and is not what the reader sees.
  const fld = (t) => `<w:r><w:fldChar w:fldCharType="${t}"/></w:r>`;
  const instr = (s) => `<w:r><w:instrText xml:space="preserve">${s}</w:instrText></w:r>`;
  const sel = readSelection(pkg(p(
    r("answer: "), fld("begin"), instr(" IF "), fld("begin"), instr(" MERGEFIELD n "), fld("separate"),
    r("1"), fld("end"), instr(' = "1" "yes" "no" '), fld("separate"), r("yes"), fld("end"))));
  assert.deepEqual(sel.lines.map(strip), ["answer: yes"]);
});

test("a reference to some other bookmark is not an example's, and not stale", () => {
  const { stale } = audit([
    f(" SEQ NumEx \\* ARABIC ", "1", ["LxEx1"]),
    f(" REF _Ref123456 \\h ", "Introduction"),   // a heading's cross-reference
    f(" REF LxEx1 \\h ", "1"),
  ]);
  assert.deepEqual(stale, []);
});
