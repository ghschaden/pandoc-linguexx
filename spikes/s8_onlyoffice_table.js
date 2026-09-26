(function () {
  // S8: the "il mio libro" example of tests/e2e/word-sample.tex, built
  // through the builder API with the converter's column widths.  Paste
  // into OnlyOffice Desktop's macro editor in a blank document.
  var doc = Api.GetDocument();
  var log = [];
  var W = [624, 189, 391, 472, 582, 7380];
  var st = {};
  ["LxExampleCell", "LxJudgmentCell", "LxTranslation", "LxExampleSpaceAbove", "LxExampleSpaceBelow"].forEach(function (n) { st[n] = doc.CreateStyle(n, "paragraph"); });
  var rows = [
    [["LxExampleSpaceAbove", "", 6]],
    [["LxExampleCell", "#NUM"], ["LxJudgmentCell", ""], ["LxExampleCell", "il"], ["LxExampleCell", "mio"], ["LxExampleCell", "libro"], ["LxExampleCell", ""]],
    [["LxExampleCell", ""], ["LxJudgmentCell", ""], ["LxExampleCell", "the"], ["LxExampleCell", "my"], ["LxExampleCell", "book"], ["LxExampleCell", ""]],
    [["LxExampleCell", ""], ["LxJudgmentCell", ""], ["LxTranslation", "‘my book’", 4]],
    [["LxExampleSpaceBelow", "", 6]]
  ];
  doc.GetElement(0).AddText("Prose before.");
  var t = Api.CreateTable(rows.length, W.length);
  doc.Push(t);
  t.SetWidth("twips", 9638);
  t.SetTableLayout("fixed");
  t.SetTableCellMarginTop(0); t.SetTableCellMarginBottom(0);
  t.SetTableCellMarginLeft(0); t.SetTableCellMarginRight(0);
  for (var r = rows.length - 1; r >= 0; r--) {
    var col = 0, spec = rows[r];
    for (var k = 0; k < spec.length; k++) {
      var span = spec[k][2] || 1;
      if (span > 1) {
        var cells = [];
        for (var q = 0; q < span; q++) cells.push(t.GetRow(r).GetCell(col + q));
        t.MergeCells(cells);
      }
      col += span;
    }
  }
  var j = JSON.parse(t.ToJSON(false, false));
  log.push("tblStyle before FromJSON: " + JSON.stringify(j.tblPr.tblStyle));
  j.tblGrid = W.map(function (w) { return {w: w, type: "gridCol"}; });
  j.content.forEach(function (row) {
    var col = 0;
    row.content.forEach(function (cell) {
      var pr = cell.tcPr || (cell.tcPr = {});
      var span = pr.gridSpan || 1, w = 0;
      for (var q = 0; q < span; q++) w += W[col + q];
      pr.tcW = {type: "dxa", w: w};
      col += span;
    });
  });
  var t2 = Api.FromJSON(JSON.stringify(j));
  t.ReplaceByElement(t2);
  t = t2;
  t.SetTableBorderAll("none", 0, 0, 0, 0, 0);
  for (var r = 0; r < rows.length; r++) {
    var spec = rows[r];
    for (var k = 0; k < spec.length; k++) {
      var par = t.GetRow(r).GetCell(k).GetContent().GetElement(0);
      par.SetStyle(st[spec[k][0]]);
      if (spec[k][1] == "#NUM") {
        par.AddText("(");
        par.AddText("0").GetRange().AddField('SEQ NumEx \\* ARABIC');
        par.AddText(")");
        var n = par.GetElementsCount(), open = -1, close = -1;
        for (var i = 0; i < n; i++) { var s = par.GetElement(i).GetText(); if (s == "(" && open < 0) open = i; if (s == ")") close = i; }
        par.GetElement(open + 1).GetRange().ExpandTo(par.GetElement(close - 1).GetRange()).AddBookmark("exGloss");
      } else if (spec[k][1]) par.AddText(spec[k][1]);
    }
  }
  var after = Api.CreateParagraph(); doc.Push(after);
  after.AddText("Prose after, see ("); after.AddText("9").GetRange().AddField('REF exGloss \\h'); after.AddText(").");
  doc.UpdateAllFields();
})();
