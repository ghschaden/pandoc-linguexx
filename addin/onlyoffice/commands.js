// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 Gerhard Schaden
//
// This file is part of pandoc-linguexx.

/**
 * What runs INSIDE the editor, through Asc.plugin.callCommand.
 *
 * callCommand sends a function's source text to the editor and runs it
 * there with the builder API's `Api`, so every function here is
 * self-contained: no imports, no helpers from outside itself, input only
 * through Asc.scope, output only through its return value.  A reference to
 * anything else works under Node and fails in the editor.
 *
 * Document Builder runs the same API headless, so these same functions are
 * what tools/run_onlyoffice_test.mjs drives there -- the editor half is
 * tested, not only the pure half (plan-addins.md, S9).
 *
 * The insertion follows what S7 and S8 measured, in their order: styles;
 * the table and its merges; the grid, which the API cannot set, written
 * through ToJSON/FromJSON (S8 facts 1-3); borders set to none, which the
 * rebuild adds (fact 4); then the cells' content, the number field and the
 * bookmark round the WHOLE field (S7 facts 3-5); a paragraph after the
 * table, which Word would otherwise join to the next one (S7 fact 8,
 * S6 fact 3); and UpdateAllFields, which in OnlyOffice renumbers
 * everything and rewrites the caches (S7 fact 2).
 */

/* global Api, Asc */

/**
 * The selection as data: its paragraphs' runs and formats, the text
 * block's width, the default face, and the bookmarks already taken.
 */
export function readSelection() {
  var doc = Api.GetDocument();
  var out = { paragraphs: [], bookmarks: doc.GetAllBookmarksNames() || [],
              widthTwips: 0, font: "", error: "" };
  var range = doc.GetRangeBySelect();
  var paras = range ? range.GetAllParagraphs() : [];
  if (!paras || !paras.length) {
    out.error = "Select the lines of an example first.";
    return out;
  }
  function runsOf(container, into) {
    var n = container.GetElementsCount();
    for (var i = 0; i < n; i++) {
      var el = container.GetElement(i);
      var type = el.GetClassType();
      if (type === "run") {
        var st = el.GetStyle();
        into.push({
          text: el.GetText(), bold: !!el.GetBold(), italic: !!el.GetItalic(),
          smallCaps: !!el.GetSmallCaps(), underline: !!el.GetUnderline(),
          vertAlign: el.GetVertAlign() || "", style: st ? st.GetName() : "",
        });
      } else if (el.GetElementsCount) {
        runsOf(el, into);               // a hyperlink, a content control
      }
    }
  }
  for (var k = 0; k < paras.length; k++) {
    var runs = [];
    runsOf(paras[k], runs);
    out.paragraphs.push({ inTable: !!paras[k].GetParentTable(), runs: runs });
  }
  // An example number in the selection -- a bookmark round a bare number,
  // outside any table -- is reported by its bookmark, to be TAKEN OVER
  // (the Writer macro's LxTakeNumber): the builder API does not show where
  // a field begins, but the bookmark round the whole field says which it is.
  var at = paras.map(function (p) { return p.GetParentTable() ? -1 : p.GetPosInParent(); });
  out.numbers = [];
  for (var b = 0; b < out.bookmarks.length; b++) {
    var br = doc.GetBookmarkRange(out.bookmarks[b]);
    if (!br || !/^\s*\d+\s*$/.test(br.GetText())) continue;
    var bp = br.GetParagraph(0);
    if (!bp || bp.GetParentTable()) continue;
    var k2 = at.indexOf(bp.GetPosInParent());
    if (k2 >= 0) out.numbers.push({ bookmark: out.bookmarks[b], shown: br.GetText().trim(), paragraph: k2 });
  }
  var sec = paras[0].GetSection ? paras[0].GetSection() : doc.GetFinalSection();
  if (sec) out.widthTwips = sec.GetPageWidth() - sec.GetPageMarginLeft() - sec.GetPageMarginRight();
  var def = doc.GetDefaultTextPr();
  out.font = def ? def.GetFontFamily() || "" : "";
  // half-points, as the builder reports sizes
  out.sizeHalfPt = def && def.GetFontSize ? def.GetFontSize() || 0 : 0;
  return out;
}

/**
 * Replace the selected paragraphs with the example Asc.scope.job
 * describes (onlyoffice/job.js).  Returns {bookmark, number} or {error}.
 */
export function insertExample() {
  var job = Asc.scope.job;
  var doc = Api.GetDocument();

  // Styles first: a paragraph can only take a style that exists.  The job
  // lists parents before children, as the converter's fragment does.
  for (var s = 0; s < job.styles.length; s++) {
    var sd = job.styles[s];
    if (doc.GetStyle(sd.name)) continue;
    var st = doc.CreateStyle(sd.name, sd.type);
    if (sd.basedOn && doc.GetStyle(sd.basedOn)) st.SetBasedOn(doc.GetStyle(sd.basedOn));
    if (sd.type === "paragraph") {
      var pp = st.GetParaPr();
      if (sd.para.before !== undefined) pp.SetSpacingBefore(sd.para.before);
      if (sd.para.after !== undefined) pp.SetSpacingAfter(sd.para.after);
      if (sd.para.line !== undefined) pp.SetSpacingLine(sd.para.line, sd.para.lineRule);
      if (sd.para.firstLine !== undefined) pp.SetIndFirstLine(sd.para.firstLine);
      if (sd.para.jc) pp.SetJc(sd.para.jc);
    }
    var tp = st.GetTextPr();
    if (sd.run.size) tp.SetFontSize(sd.run.size);
    if (sd.run.smallCaps) tp.SetSmallCaps(true);
  }

  var range = doc.GetRangeBySelect();
  var paras = range ? range.GetAllParagraphs() : [];
  if (!paras || !paras.length) return { error: "Select the lines of an example first." };
  var pos = paras[0].GetPosInParent();
  // A number taken over: the old bookmark goes first, so that at no moment
  // do two claim its name -- the macro's order.  Its field goes with the
  // selected paragraphs, below.
  if (job.takeOver) doc.DeleteBookmark(job.bookmark);

  var nRows = job.rows.length, nCols = job.grid.length;
  var t = Api.CreateTable(nRows, nCols);
  doc.AddElement(pos, t);
  t.SetWidth("twips", job.widthTwips);
  t.SetTableLayout("fixed");
  t.SetTableCellMarginTop(0); t.SetTableCellMarginBottom(0);
  t.SetTableCellMarginLeft(0); t.SetTableCellMarginRight(0);

  // Merges, right to left within a row so the indices still to merge hold.
  var r, k, col;
  for (r = 0; r < nRows; r++) {
    var spans = [];
    col = 0;
    for (k = 0; k < job.rows[r].length; k++) {
      if (job.rows[r][k].span > 1) spans.push([col, job.rows[r][k].span]);
      col += job.rows[r][k].span;
    }
    for (var m = spans.length - 1; m >= 0; m--) {
      var cells = [];
      for (var q = 0; q < spans[m][1]; q++) cells.push(t.GetRow(r).GetCell(spans[m][0] + q));
      t.MergeCells(cells);
    }
  }

  // The grid: the API leaves six default columns, which LibreOffice and
  // Word lay out from (S8 fact 2).  Written through JSON, and each cell's
  // width with it.
  var j = JSON.parse(t.ToJSON(false, false));
  j.tblGrid = job.grid.map(function (w) { return { w: w, type: "gridCol" }; });
  for (r = 0; r < nRows; r++) {
    for (k = 0; k < j.content[r].content.length; k++) {
      var tc = j.content[r].content[k];
      tc.tcPr = tc.tcPr || {};
      tc.tcPr.tcW = { type: "dxa", w: job.rows[r][k].widthTwips };
    }
  }
  var t2 = Api.FromJSON(JSON.stringify(j));
  t.ReplaceByElement(t2);
  t = t2;
  t.SetTableBorderAll("none", 0, 0, 0, 0, 0);

  // Each run made fresh and added, never par.AddText: AddText's new run
  // INHERITS the previous run's formatting (probed 2026-09-26), so a plain
  // word after a small-caps one came out in small caps -- the macro's style
  // leak (79e155f) again, in another API.
  function put(par, runs) {
    for (var i = 0; i < runs.length; i++) {
      var run = Api.CreateRun();
      run.AddText(runs[i].text);
      par.AddElement(run);
      var f = runs[i].fmt || {};
      var style = f.rStyle ? doc.GetStyle(f.rStyle) : null;
      if (style) run.SetStyle(style);
      if (f.bold) run.SetBold(true);
      if (f.italic) run.SetItalic(true);
      if (f.smallCaps && !style) run.SetSmallCaps(true);
      if (f.underline) run.SetUnderline(true);
      if (f.vertAlign) run.SetVertAlign(f.vertAlign);
    }
  }

  var numberAt = null;
  for (r = 0; r < nRows; r++) {
    for (k = 0; k < job.rows[r].length; k++) {
      var cell = job.rows[r][k];
      var par = t.GetRow(r).GetCell(k).GetContent().GetElement(0);
      par.SetStyle(doc.GetStyle(cell.style));
      if (cell.content.kind === "text") put(par, cell.content.runs);
      else if (cell.content.kind === "number") numberAt = par;
    }
  }

  // The number: a SEQ field, then a bookmark round the whole field -- its
  // runs strictly between "(" and ")" -- since AddField deletes whatever
  // its range held, a bookmark included (S7 facts 3 and 4).
  if (numberAt) {
    numberAt.AddText(job.brackets.left || "(");
    numberAt.AddText("0").GetRange().AddField("SEQ NumEx \\* ARABIC");
    numberAt.AddText(job.brackets.right || ")");
    var n = numberAt.GetElementsCount(), first = -1, last = -1;
    for (var e = 0; e < n; e++) {
      var txt = numberAt.GetElement(e).GetText();
      if (txt === (job.brackets.left || "(") && first < 0) first = e;
      if (txt === (job.brackets.right || ")")) last = e;
    }
    numberAt.GetElement(first + 1).GetRange()
      .ExpandTo(numberAt.GetElement(last - 1).GetRange()).AddBookmark(job.bookmark);
  }

  // The typed lines go; a paragraph must follow the table.
  for (var d = 0; d < paras.length; d++) paras[d].Delete();
  var next = doc.GetElement(t.GetPosInParent() + 1);
  if (!next || next.GetClassType() === "table") doc.AddElement(t.GetPosInParent() + 1, Api.CreateParagraph());

  doc.UpdateAllFields();
  var mark = doc.GetBookmarkRange(job.bookmark);
  return { bookmark: job.bookmark, number: mark ? mark.GetText() : "" };
}

/**
 * The document's examples, in order: every bookmark round a bare number
 * inside a table -- which is how both this plugin and the converter mark
 * one -- with its row's words as a preview.
 */
export function listExamples() {
  var doc = Api.GetDocument();
  var names = doc.GetAllBookmarksNames() || [];
  var out = [];
  for (var i = 0; i < names.length; i++) {
    var rng = doc.GetBookmarkRange(names[i]);
    if (!rng) continue;
    var shown = rng.GetText();
    if (!/^\s*\d+\s*$/.test(shown)) continue;
    var para = rng.GetParagraph(0);
    var cell = para ? para.GetParentTableCell() : null;
    if (!cell) continue;
    var row = cell.GetParentRow();
    var words = [];
    for (var c = 1; c < row.GetCellsCount(); c++) {
      var text = row.GetCell(c).GetContent().GetElement(0).GetText();
      if (text && text.trim()) words.push(text.trim());
    }
    out.push({ bookmark: names[i], number: shown.trim(), pos: rng.GetStartPos(),
               preview: words.join(" ").slice(0, 60) });
  }
  out.sort(function (a, b) { return a.pos - b.pos; });
  return out;
}

/**
 * Turn the placeholder the plugin pasted at the cursor into a REF field:
 * Asc.scope.ref = {placeholder, bookmark}.  Pasting is the plugin API's
 * way of writing at the cursor; Search and AddField are the builder's way
 * of making a field of what is there (probed 2026-09-26).
 */
export function completeReference() {
  var ref = Asc.scope.ref;
  var doc = Api.GetDocument();
  var found = doc.Search(ref.placeholder, true);
  if (!found || !found.length) return { error: "The reference's placeholder was not found." };
  found[0].AddField("REF " + ref.bookmark + " \\h");
  doc.UpdateAllFields();
  return { ok: true };
}

/**
 * The example the cursor is in, as data: its rows' cells -- the paragraph
 * style's name and the runs -- its number's bookmark, and where it sits.
 * core/untypeset.js reads it (by way of job.untypesetJob).
 */
export function readExampleTable() {
  var doc = Api.GetDocument();
  var range = doc.GetRangeBySelect();
  var para = range ? range.GetParagraph(0) : doc.GetCurrentParagraph();
  var table = para ? para.GetParentTable() : null;
  if (!table) return { error: "Put the cursor in the example you want back as text." };
  function runsOf(container, into) {
    var n = container.GetElementsCount();
    for (var i = 0; i < n; i++) {
      var el = container.GetElement(i);
      if (el.GetClassType() === "run") {
        var st = el.GetStyle();
        into.push({
          text: el.GetText(), bold: !!el.GetBold(), italic: !!el.GetItalic(),
          smallCaps: !!el.GetSmallCaps(), underline: !!el.GetUnderline(),
          vertAlign: el.GetVertAlign() || "", style: st ? st.GetName() : "",
        });
      } else if (el.GetElementsCount) runsOf(el, into);
    }
  }
  var rows = [];
  for (var r = 0; r < table.GetRowsCount(); r++) {
    var row = table.GetRow(r), cells = [];
    for (var c = 0; c < row.GetCellsCount(); c++) {
      var content = row.GetCell(c).GetContent();
      var style = "", runs = [];
      for (var e = 0; e < content.GetElementsCount(); e++) {
        var p = content.GetElement(e);
        if (p.GetClassType() !== "paragraph") continue;
        if (!style && p.GetStyle()) style = p.GetStyle().GetName();
        if (runs.length) runs.push({ text: " " });
        runsOf(p, runs);
      }
      cells.push({ style: style, runs: runs });
    }
    rows.push(cells);
  }
  var pos = table.GetPosInParent();
  var number = null, names = doc.GetAllBookmarksNames() || [];
  for (var b = 0; b < names.length && !number; b++) {
    var br = doc.GetBookmarkRange(names[b]);
    if (!br || !/^\s*\d+\s*$/.test(br.GetText())) continue;
    var bp = br.GetParagraph(0), bt = bp ? bp.GetParentTable() : null;
    if (bt && bt.GetPosInParent() === pos) number = { bookmark: names[b], shown: br.GetText().trim() };
  }
  return { rows: rows, number: number, pos: pos };
}

/**
 * Replace the example table at Asc.scope.back.pos with its lines, the
 * number -- the same bookmark's name -- at the head of the first, as the
 * macro writes it: "(", the field, ")", a tab.  The table goes first, so
 * the name is never claimed twice.
 */
export function writeLines() {
  var back = Asc.scope.back;
  var doc = Api.GetDocument();
  var table = doc.GetElement(back.pos);
  if (!table || table.GetClassType() !== "table") return { error: "The example has moved; try again." };
  // Deleting the table would take the bookmark with it; it is removed first
  // all the same, so the order -- old identity gone, then the new claim -- is
  // stated rather than left to a side effect (a mutation test showed the
  // line changes nothing today).
  if (back.number) doc.DeleteBookmark(back.number.bookmark);
  table.Delete();
  for (var i = 0; i < back.lines.length; i++) {
    var par = Api.CreateParagraph();
    doc.AddElement(back.pos + i, par);
    if (i === 0 && back.number) {
      par.AddText("(");
      par.AddText("0").GetRange().AddField("SEQ NumEx \\* ARABIC");
      par.AddText(")");
      var n = par.GetElementsCount(), first = -1, last = -1;
      for (var e = 0; e < n; e++) {
        var t = par.GetElement(e).GetText();
        if (t === "(" && first < 0) first = e;
        if (t === ")") last = e;
      }
      par.GetElement(first + 1).GetRange().ExpandTo(par.GetElement(last - 1).GetRange())
        .AddBookmark(back.number.bookmark);
      var tab = Api.CreateRun(); tab.AddText("\t"); par.AddElement(tab);
    }
    var runs = back.lines[i];
    for (var k = 0; k < runs.length; k++) {
      var run = Api.CreateRun();
      run.AddText(runs[k].text);
      par.AddElement(run);
      var f = runs[k].fmt || {};
      var style = f.rStyle ? doc.GetStyle(f.rStyle) : null;
      if (style) run.SetStyle(style);
      if (f.bold) run.SetBold(true);
      if (f.italic) run.SetItalic(true);
      if (f.smallCaps && !style) run.SetSmallCaps(true);
      if (f.underline) run.SetUnderline(true);
      if (f.vertAlign) run.SetVertAlign(f.vertAlign);
    }
  }
  doc.UpdateAllFields();
  return { ok: true, lines: back.lines.length };
}
