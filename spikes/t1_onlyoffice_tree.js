(function () {
  // Trees spike T1: a tree drawn with the builder API -- shapes grouped,
  // their geometry written through ToJSON/FromJSON (the builder ignores
  // positions when grouping), the bracket source as alt text, inline.
  // Paste into OnlyOffice Desktop's macro editor in a blank document.
  var doc = Api.GetDocument();
  var log = [];
  var EMU = 360000;
  var noLine = function () { return Api.CreateStroke(0, Api.CreateNoFill()); };
  var black = function () { return Api.CreateStroke(9525, Api.CreateSolidFill(Api.CreateRGBColor(0, 0, 0))); };
  // geometry in cm: [kind, x, y, w, h, text, flipH]
  var G = [["box", 2.4, 0, 1.2, 0.6, "DP"], ["line", 2.0, 0.6, 1.0, 0.8, "", true], ["line", 3.0, 0.6, 1.0, 0.8],
           ["box", 1.4, 1.4, 1.2, 0.6, "D"], ["box", 3.4, 1.4, 1.2, 0.6, "N"],
           ["line", 2.0, 2.0, 0.0, 0.8], ["line", 4.0, 2.0, 0.0, 0.8],
           ["box", 1.4, 2.8, 1.2, 0.6, "the"], ["box", 3.4, 2.8, 1.2, 0.6, "tree"]];
  var shapes = G.map(function (g) {
    if (g[0] === "box") {
      var s = Api.CreateShape("rect", g[3] * EMU, g[4] * EMU, Api.CreateNoFill(), noLine());
      s.SetPaddings(0, 0, 0, 0);
      // Black, said explicitly: a shape's own style gives its text the
      // colour meant for a filled shape -- white -- and these have no fill.
      // Without it the desktop editor drew the branches and no labels.
      var p = s.GetDocContent().GetElement(0); p.SetJc("center"); p.AddText(g[5]).SetColor(0, 0, 0);
      return s;
    }
    return Api.CreateShape("line", Math.max(1, g[3] * EMU), g[4] * EMU, Api.CreateNoFill(), black());
  });
  var grp = Api.CreateGroup(shapes);
  var par = Api.CreateParagraph(); doc.Push(par); par.AddDrawing(grp); grp.SetWrappingStyle("inline");
  var j = JSON.parse(grp.ToJSON());
  var W = 0, H = 0;
  G.forEach(function (g, i) {
    var x = j.graphic.spTree[i].spPr.xfrm;
    x.off = { x: Math.round(g[1] * EMU), y: Math.round(g[2] * EMU) };
    x.ext = { cx: Math.max(1, Math.round(g[3] * EMU)), cy: Math.round(g[4] * EMU) };
    x.flipH = !!g[6];
    j.graphic.spTree[i].extX = x.ext.cx; j.graphic.spTree[i].extY = x.ext.cy;
    W = Math.max(W, g[1] + g[3]); H = Math.max(H, g[2] + g[4]);
  });
  var gx = j.graphic.spPr.xfrm;
  gx.ext = { cx: Math.round(W * EMU), cy: Math.round(H * EMU) };
  gx.chOffX = 0; gx.chOffY = 0; gx.chExtX = gx.ext.cx; gx.chExtY = gx.ext.cy;
  j.extent = { cx: gx.ext.cx, cy: gx.ext.cy };
  j.docPr.descr = "[DP [D the] [N tree]]";
  var g2 = Api.FromJSON(JSON.stringify(j)); g2.SetWrappingStyle("inline");
  log.push("FromJSON -> " + (g2 && g2.GetClassType()));
  var p2 = Api.CreateParagraph(); doc.Push(p2); p2.AddText("The tree: "); p2.AddDrawing(g2);
  par.Delete();   // the scaffold the geometry was read from
  log.push("rebuilt " + (g2.GetWidth() / EMU).toFixed(2) + " x " + (g2.GetHeight() / EMU).toFixed(2) + " cm");
  log.forEach(function (x) { var p = Api.CreateParagraph(); p.AddText(x); doc.Push(p); });
})();
