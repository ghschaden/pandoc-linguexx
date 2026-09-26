(function () {
  var doc = Api.GetDocument();
  function example(pos, label) {
    var t = Api.CreateTable(1, 2);
    if (pos < 0) doc.Push(t); else doc.AddElement(pos, t);
    var par = t.GetRow(0).GetCell(0).GetContent().GetElement(0);
    par.AddText("(");
    par.AddText("0").GetRange().AddField('SEQ NumEx \\* ARABIC');
    par.AddText(")");
    t.GetRow(0).GetCell(1).GetContent().GetElement(0).AddText(label);
    var n = par.GetElementsCount(), open = -1, close = -1;
    for (var i = 0; i < n; i++) {
      var s = par.GetElement(i).GetText();
      if (s == "(" && open < 0) open = i;
      if (s == ")") close = i;
    }
    par.GetElement(open + 1).GetRange()
       .ExpandTo(par.GetElement(close - 1).GetRange())
       .AddBookmark("ex" + label);
  }
  doc.GetElement(0).AddText("Prose before.");
  example(-1, "A");
  example(-1, "B");
  example(-1, "C");
  var pr = Api.CreateParagraph();
  doc.Push(pr);
  pr.AddText("See (");
  pr.AddText("9").GetRange().AddField('REF exC \\h');
  pr.AddText(") and (");
  pr.AddText("9").GetRange().AddField('REF exA \\h');
  pr.AddText(").");
  doc.UpdateAllFields();
  example(1, "NEW");
  doc.UpdateAllFields();
})();
