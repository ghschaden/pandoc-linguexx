# LinguExx.bas — glossed examples inside Writer

A LibreOffice Basic macro that turns selected lines into an aligned
linguistic example. It is the companion to `linguexx2odt`, not a
replacement: the converter handles LaTeX documents, this handles examples
you are writing in Writer.

Select the lines and run it:

```
Esto es un ejemplo glosado
this is a example glossed
'This is a glossed example.'
```

becomes

```
(1)   Esto    es   un   ejemplo   glosado
      this    is   a    example   glossed
      'This is a glossed example.'
```

with the number a live `NumEx` field, so inserting an example above
renumbers everything below it on F9.

French documentation: [`guide-fr.md`](guide-fr.md) covers both tools;
[`manuel-extension-fr.md`](manuel-extension-fr.md) is a standalone manual
for the extension alone, with per-platform install instructions.

## Install

### As an extension (recommended)

```
python3 tools/build_oxt.py
unopkg add dist/linguexx-0.1.0.oxt
```

It appears as a **LinguExx** menu in Writer, with three entries:
*Typeset example*, *Typeset numbered tree* and *Typeset unnumbered
tree*. An installed extension raises
no macro-security warning, and it is the only sensible thing to hand to
someone who is not going to paste Basic into an IDE.

To remove it: `unopkg remove net.schaden.linguexx`.

Close LibreOffice first — `unopkg` will not register into a profile that is
in use. To replace an already-installed copy, use `unopkg add -f`.

### By hand

The macro source ships with the Python package:

```
linguexx2odt --print-macro > LinguExx.bas
```

Then: **Tools ▸ Macros ▸ Edit Macros…**, right-click **My Macros ▸
Standard** → **Insert ▸ BASIC Module**, paste, save. Bind a shortcut under
**Tools ▸ Customize ▸ Keyboard** by picking `GlossSelection` — the
Basic entry point keeps that name; only the menu label reads *Typeset
example*.

## What it does

- **Measures the real font.** The converter has no font metrics and
  estimates column widths from per-character advance widths, which is off
  by −2% to +9% in practice. Here the actual font is available, so
  columns are exactly as wide as their contents.
- **Reads the real page.** The available text width comes from the page
  style in front of you, not from a `--text-width` flag — so it is right
  for the document you are actually in.
- **Keeps the formatting you applied.** Italic, bold, small caps (and the
  other case maps), sub- and superscript, underline, and character styles
  such as `LxLeipzig` all come through the transform unchanged, in any
  combination. Each run is also *measured* in the font it will be drawn
  in — bold is wider than roman, a superscript smaller, and small caps are
  capitals at 80% of the size, which is 10–20% **wider** than the lowercase
  they stand in for, so a column measured as lowercase would be too narrow
  for what goes in it. See [What is not carried](#what-is-not-carried).
- **Splits overlong examples into bands**, each starting back at the left
  edge, and can redo it at any time: nothing is frozen at conversion time.
- **Hangs judgment marks.** A leading `*`, `??`, `#`, `%` or `!` goes into
  its own column, carved out of the number column, so a judged and an
  unjudged example begin at exactly the same x.
- **`{braced groups}`** count as one column, as in linguexx.
- **One undo step.** Ctrl+Z takes the whole example back at once.
- **Uses the same named styles as `linguexx2odt`** — `LxExampleCell`,
  `LxTranslation`, `LxJudgmentCell`, `LxExampleSpace{,Above,Below}` — so a
  converted document and a hand-built example are the same object, and the
  spacing styles described in the main README govern both. Existing styles
  are never overwritten.

### What is not carried

**Font family and size are deliberately dropped**, and the example is set
in whatever `LxExampleCell` says. Carrying them would mean writing them
back as direct formatting on every cell, and then editing the style would
no longer change the example — which is the point of having the style. The
consequence to know about: an example typed in a font other than the body
font is measured, and set, in the body font.

Everything else outside the list above is dropped too — text colour,
highlighting, strikeout, letter spacing, the run's language. They are
dropped because nobody asked for them, not for any deeper reason: each is
one more entry in `LxFormatIndex` and `LxApplyFmt`, and none of them
changes a column width.

The character style goes on first and each direct property only if the
style did not already supply it, so a run that carried `LxLeipzig` still
answers to `LxLeipzig` afterwards rather than being frozen into hard small
caps, and text nobody formatted by hand arrives with no direct formatting
at all.

The last selected line is treated as a free translation when it opens with
a quote character — straight, curly, guillemets, or the backtick of LaTeX's
`` `like this' `` convention. Otherwise it is another gloss tier.

### Unglossed examples

A single line is an example too — the commonest kind:

```
A simple example.
```

becomes `(1)  A simple example.`, numbered like any other. It stays running
text in one cell rather than being split one word per column. Add a quoted
line under it and that becomes the translation.

## Trees

Three commands, and which one you run is the whole of the decision:

| menu entry | Basic | what it makes |
|---|---|---|
| **Typeset example** | `GlossSelection` | an example — **never** a tree, whatever brackets are in it |
| **Typeset numbered tree** | `TreeSelection` | a numbered tree, or a paradigm of them |
| **Typeset unnumbered tree** | `TreeSelectionBare` | one tree, no table and no number |

`TreeSelection` turns bracket notation into a drawn syntax tree. Select

```
[DP [D the] [NP [N tree]]]
```

and you get a numbered example whose content is the tree, in the same table
as any other example — same number field, same spacing styles, same
alignment, so a document that mixes trees and glossed examples keeps them
all starting at the same x.

The notation is the one qtree and forest share: the first token after a `[`
is the label, everything after it is a child, and a bare word is a leaf.
`[D the]` and `[D [the]]` mean the same thing.

- **`{braced groups}`** are one label even with spaces in them, as in
  glossed examples.
- **A leaf marked `, roof`** is drawn under a triangle:
  `[S [NP {the big tree, roof}] [VP [V slept]]]`.
- **`name=`** labels a node so a `move` line can refer to it — see
  [Movement](#movement).
- **A judgment mark** leads the tree as it leads an example —
  `*[S [NP him] [VP [V left]]]` — and hangs in the same column.
- **Node labels keep their formatting.** Italicise a terminal or set a
  feature in small caps before running it and that is how it is drawn.
- The bracket expression may be typed over **several lines**; select them
  all and they are read as one expression.

### Movement

Name the two nodes and put a `move` line under the tree:

```
[CP [DP,name=wh what] [C' [C did] [TP [DP John] [VP [V see] [DP,name=t __]]]]]
move t -> wh
```

The arrow runs out from under the node it moved from, along its own lane in
a gutter beneath the tree, and up to the node it moved to, with a filled
head. Both ends sit at the **underside of the whole subtree**, not at the
node's own baseline: a node almost always has something below it, and an
arrow aimed at the baseline would go straight through it. An arrow points
at a constituent; it never crosses one. Several arrows get separate lanes: two may share one only if
their spans do not overlap, and the narrower span goes in the shallower
lane, so a movement nested inside another sits above it — which is how the
same configuration is drawn by hand.

`name=` is a node option like `roof`, so it goes inside the brackets after
a comma. A `move` line is recognised by starting with `move`; everything
else in the selection is the tree.

**This is not TikZ, on purpose.** forest writes the same thing as
`\draw[->] (t) to[out=south west,in=south] (wh);`, and supporting a subset
of TikZ is a trap: the moment `move` looked like `\draw`, the next thing
asked for would be bend angles, edge labels and node anchors, and wherever
the subset ended would read as a bug rather than a boundary. A line that is
plainly not TikZ promises only what it delivers. Anything with a backslash
in it is still refused, and the message points here.

Refused by name: a `move` line with no `->`, a name no node carries, a node
moving to itself, and move lines with no tree above them.

**Nothing needs routing around.** An arrow crosses no node, no branch and
no roof, in any tree — not by luck but by construction: it leaves and
arrives at the underside of a whole subtree, so it never enters one, and
sibling subtrees are laid out horizontally disjoint, so nothing sits at a
riser's x over the span it travels. `check_arrow_clearance` pins it across
seven awkward shapes — a landing site mid-tree, a target whose sibling is
far deeper, rightward movement, two arrows with overlapping spans, a roof
in the way, and a target that dominates its own source.

Arrows above the tree and edge labels remain out of scope.

### Trees in a paradigm

**Typeset numbered tree** takes a paradigm too:

```
a. [DP [D the] [NP [N tree]]]
b. [DP [D a] [NP [N cat]]]
c. [VP [V sang] [AdvP [Adv loudly]]]
```

One number, the letters in their own column, and each tree in the merged
cell an unglossed item would have taken. Judgment marks, translations and
`move` lines all belong to their own item.

Every item is a tree, because that is what the command means. An item that
is not one is refused **by letter** — "Sub-example b. is not a tree" — so a
paradigm never builds half-drawn. To put a tree beside a glossed example,
make them two examples.

**Typeset example never draws a tree.** Bracket notation is not a signal
and is not treated as one, because labelled bracketing is how constituent
structure is shown inside an ordinary example:

```
[TP [DP John] [VP left]]
[CP [C that] [TP she left]] is grammatical
Mary saw [DP the [AP very big] cat]
```

Every one of those stays exactly as typed. There is nothing in the string
that separates "draw this" from "show this", so the macro does not try to
tell — and narrowing the guess does not rescue it: requiring the root to
have children keeps `[ˈkæt]` safe and still swallows every fully bracketed
sentence.

A real tree typed into *Typeset example* stays text too. An earlier attempt
to guess narrowly — requiring the root to have children — kept `[ˈkæt]`
safe and still swallowed every fully bracketed sentence.

### Trees that came from LaTeX

`linguexx2odt` cannot draw a tree — that needs draw shapes, and it has no
Writer to make them in. What it does instead is keep one: a
`\begin{forest}…\end{forest}` environment (or qtree's `\Tree`) arrives in
the converted document as its **bracket notation**, inside the example it
belongs to, with a warning saying so.

Select those brackets and run **Typeset unnumbered tree** — unnumbered,
because the example around them already supplies the number. The tree is
drawn in place and the numbering is untouched.

Before this, the environment went to pandoc and the example came out as
`]]]`.

### Trees without a number

Not every tree should spend an example number — one in a footnote, a figure
or a slide should not. **LinguExx ▸ Typeset unnumbered tree**
(`TreeSelectionBare`) draws the same tree with no table, no number and no
example styles: the shapes replace the brackets where they stand, anchored
as a character in that paragraph.

It is a separate command rather than one that works out whether a number is
wanted. Guessing from context is the kind of inference this macro refuses
everywhere else, and it would be wrong in silence.

**Give a bare tree a line of its own.** A shape group anchored as a
character reserves vertical room in the line but not horizontal — measured,
a 38 pt-wide tree between two words leaves a 31 pt gap, which is the width
of the words alone. So the tree is drawn where the line's text ends. Text
*before* it is fine, and is exactly how the judgment mark works (with no
table there is no hanging column, so `*` is set as the text it would have
been). Text still to come on the line would end up beside the tree rather
than after it, and the macro says so when it finds any.

The vertical half does work: a bare tree pushes the paragraph after it down
by its full height.

### What it draws with, and what that means

The tree is a group of Writer draw shapes — a text shape per node, a line
per branch — anchored as a character. So it is a real object in the
document: it prints, it exports to PDF, its labels are selectable text, and
you can drag a node afterwards. Nothing re-runs the layout if you do, in
exactly the way a built example does not re-align itself; run it again on
the source instead.

Node labels are the one thing in this macro not governed by a paragraph
style, because Writer has no style family for draw-shape text (there is no
`graphics` family in a text document — only `ParagraphStyles`,
`CharacterStyles`, `FrameStyles` and friends). The label font is therefore
the document's, applied directly.

Widths are not estimated at all here: each label is measured **by being
set** into a scratch shape that grows to fit, so what the layout gets is
what Writer will draw, formatting included. That is exact where
`getStringWidth` is 2–5% out — enough to wrap a long label inside its own
node box.

Layout keeps every parent centred over its children and no two subtrees
overlapping. It is not Reingold–Tilford: it tracks one leftmost-free-x per
tier and shifts a subtree right when its parent would collide. That packs
marginally looser than the linear algorithm and is a great deal easier to
be sure of.

### What it refuses

- **Backslash commands.** This does not read LaTeX; the message points at
  the `move` line instead.
- **Node options other than `roof` and `name=`** — edge labels, per-node
  styling. Refused by name, so adding one later is a small change rather
  than a silent behaviour shift.
- Unbalanced brackets, text after the end of the tree, and a selection
  that does not begin with `[`.

A tree wider than the text block is still built, with a warning saying how
wide it came out — shorten a label or group words with `{braces}`.

## Sub-examples

`a. … b. …` paradigms work, glossed or not. Select the whole thing:

```
a. Esto es un ejemplo
   this is a example
   'This is an example.'
b. Otro ejemplo aqui
   another example here
   'Another example here.'
```

The letters go in their own column, the paradigm carries **one** number,
and every item shares one column grid. A letter may lead the object
language as above or stand alone on its line.

- **Markers** are a single letter or a roman numeral followed by `.` or
  `)` — `a.`, `(b)`, `iii.`. Deliberately narrow, so `Dr.` and `no.` are
  not mistaken for one.
- **A sub-example letter sits exactly where a main example's text
  begins** — linguexx's own geometry. That is why the judgment column is
  carved out of the column to its left rather than inserted after it.
- **Items may be glossed or not, in the same paradigm** — or be trees. An
  unglossed item is running text in one merged cell, not one word per
  column: splitting it would align words that have nothing to do with each
  other. Under *Typeset numbered tree* every item is a tree instead, each
  in that same merged cell.
- **Each item may carry its own judgment mark**, which hangs left as usual.
- A translation belongs to its own item.

If a letter appears part-way through the selection but the selection does
not start with one, it refuses rather than guess.

## Differences from `linguexx2odt`

| | converter | macro |
|---|---|---|
| syntax trees | no | yes, from bracket notation, numbered or bare |
| column widths | estimated | measured |
| inline formatting | from the LaTeX (`\lpzg`, `\textsc`, …) | from the text you selected |
| small caps | estimated at `sc_ratio` of the capital | measured, by rendering them |
| text width | `--text-width` | the actual page style |
| band grid | union of the bands' boundaries | the same |
| judgment column | reserved only if the document judges something | always reserved |
| sub-examples | yes | yes — one marker column, as the converter has |

The judgment row is a deliberate simplification: the column is always
reserved because a macro sees one selection where the converter sees the
whole document first, and the cost is a few millimetres of indent in a
document that never judges anything.

The band grid used to differ — the macro shared one rectangular grid
between the bands, which coupled them: the fifth column of band 2 had to
be as wide as the fifth column of band 1, so one long word stretched an
unrelated column in another line. It now builds the union of the bands'
boundaries and spans each word across the columns it covers, exactly as
the converter does, so each band lays itself out freely.

## Testing

`tools/run_macro_test.py` installs `LinguExx.bas` into a throwaway
LibreOffice profile, drives it over UNO, renders the result and measures
the PDF — so what is tested is the file that ships, not a
re-implementation of it.

```
python3 tools/run_macro_test.py [OUTDIR]
```

It needs `soffice`, `unopkg`, `pdftotext` and python-uno. Each run picks a
free port and shuts its LibreOffice down at the end: a fixed port lets a
stray instance from an earlier run answer instead, and the suite then
drives whatever library *that* one holds — which has produced a false
failure at least once. It checks that the number
field evaluates, that every gloss sits under its word, that `{braces}`
group, that an overlong example still aligns, and that a judgment mark
hangs left without shifting the text block of a neighbouring unjudged
example. Six sub-example cases cover glossed, unglossed, mixed, judged,
roman-numeral and marker-on-its-own-line paradigms, and one pins the
letter against a main example's text — the invariant
`test_sub_example_letters_align_with_main_example_text` pins for the
converter.

Two cases cover formatting. `check_small_caps` builds the same example
three times — glosses in small caps, in lowercase, and in real capitals —
and pins both halves of what formatting has to do: the file still spells
the gloss in lowercase, the PDF renders it as capitals, and exactly one
column, the one holding it, comes out *between* the lowercase and the
capitals width. `check_formatting_round_trip` types one word in each of
italic, bold, both, underline, sub- and superscript, small caps and a
character style, and compares each word's character properties before and
after against the document itself — not against an expectation written
into the test, which could be wrong in the same direction as the code.

Four more cover trees. `check_trees` builds six shapes of tree and pins
that every node got a shape and every parent-child pair a branch, and that
five malformed selections are refused rather than drawn. `check_tree_geometry`
asks *where* the shapes are, which counting cannot: the nodes must sit on as
many tiers as the tree is deep, and every branch must run from the underside
of one node to the top of another. Both failures it exists for leave the
shape count untouched — a polygon positioned before its `PolyPolygon` is
still a branch, just 2501 units away, and a collapsed tier spacing still has
every node. `check_tree_alignment` puts a tree and a glossed example in one
document and pins that they start at the same x, and that a long braced
label is on one line rather than wrapped inside its node.
`check_tree_formatting` pins that a small-caps label is still lowercase in
the file and still small caps in the shape. `check_bare_tree` pins the
unnumbered form: no table, the group anchored as a character, the next
paragraph pushed down by the tree's height, a judgment mark set as text,
and the warning when something is left on the line after it.

`check_undo` pins what the docs promise about Ctrl+Z: one step takes back
an example, a tree, a tree with movement or a bare tree, and no style
creation is left outside the undo context to be unwound separately.

`check_extension` builds the `.oxt`, checks every command the menu offers
names a Sub that exists, installs it with `unopkg` into a throwaway profile
and drives all three commands *from the package* rather than from the loose
`.bas`. Everything else in the suite loads the macro straight into a Basic
library, which skips the package — and that has hidden a real bug before.

`check_tree_items` covers trees inside a paradigm — beside a glossed item,
beside a plain one, judged, with movement — and pins that each keeps its
own letter while the paradigm keeps one number. Seven bracketings are
pinned to stay text under *Typeset example* — labelled bracketing with and
without prose around it, two bare constituents, a partial bracketing, a
transcription, an optional element, and a genuine tree typed into the wrong
command. Three more pin that a non-tree item is refused by letter.

`check_moves`, `check_move_geometry` and `check_arrow_clearance` cover
movement. The geometry one
tells the shapes apart by type rather than by order — a branch is a
`LineShape`, an arrow a `PolyLineShape`, a filled `PolyPolygonShape` a
head — and pins that every arrow runs below the deepest node, that two
arrows take different lanes, that the heads are centred on the nodes moved
*to* (the source node is never a target, so an arrow drawn backwards is
caught), that each arrow's top meets the foot of its own head, and that no
part of an arrow passes through a node box. That last one reads the shapes'
own polygons back and tests each segment against each node, so it is the
real invariant rather than a proxy for it — aim an arrow at a node's
baseline instead of its subtree's underside and it fails.

`check_arrow_clearance` widens that to branches and roofs, which a
box test cannot see because a branch is a diagonal. Aiming arrows at node
baselines again fails all seven of its trees. That
last one exists because getting the polygon's box origin wrong sinks the
arrow away from its head while leaving something that still looks like an
arrow and still counts as one.

`GlossSelectionQuiet()` is the entry point the harness uses: it does the
same work with dialogs suppressed and returns the message instead
(`""` on success). A modal dialog in a headless LibreOffice blocks for
ever, so anything non-interactive should call that one.

## Staying in step with the converter

The macro is Basic and can import nothing from Python, so the style names
and layout lengths exist twice. `src/linguexx2odt/styles.py` owns them and
`tools/sync_macro.py` writes the generated block at the top of
`LinguExx.bas`:

```
python3 tools/sync_macro.py            # check; exit 1 on drift
python3 tools/sync_macro.py --write    # regenerate the block
```

`tests/test_macro_sync.py` runs the check as part of the ordinary suite —
no LibreOffice needed — and also asserts that every shared constant is
actually *used*, not merely declared. That last check exists because the
macro had silently lost `max_col_cm` before any of this was written.
