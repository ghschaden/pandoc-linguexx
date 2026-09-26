# pandoc-linguexx

`linguexx2odt` converts a LaTeX document containing
[linguexx](../linguexx) examples into a LibreOffice Writer file in which
**every example number is a live field**. Insert an example in Writer and
everything after it renumbers; cross-references follow.

The rest of the document — sections, prose, emphasis, footnotes,
citations — is converted by pandoc as usual.

```
linguexx2odt paper.tex -o paper.odt
```

**Documentation en français :** [`docs/guide-fr.md`](docs/guide-fr.md)
couvre les deux outils ; [`docs/manuel-extension-fr.md`](docs/manuel-extension-fr.md)
est un manuel autonome pour la seule extension LibreOffice, avec les
instructions d'installation sous Windows, macOS et Linux.

## Requirements

- **pandoc ≥ 3.0** (developed and tested against 3.6.1)
- **Python ≥ 3.10** and `fonttools` (the only dependency; `pip` brings it)
- LibreOffice is *not* needed to convert, only to read the result (and to
  run the rendering half of the test suite)

## Install

No install is needed to run it. From a checkout:

```
PYTHONPATH=src python3 -m linguexx2odt paper.tex -o paper.odt
```

The `PYTHONPATH` is not optional — this is a src-layout project, so a bare
`python3 -m linguexx2odt` from the repository root does not find the
package. What it buys is needing no virtualenv, which is the quickest way
past a `.venv` that has gone stale — or, if this checkout is synced by a
service that does not preserve the executable bit, past a
`.venv/bin/linguexx2odt` that exists and will not run.

(The test suite needs no `PYTHONPATH`: `pyproject.toml` sets it for pytest.
The two are different, and conflating them cost an afternoon.)

For the `linguexx2odt` command itself: Arch/Manjaro (and most current
distros) mark the system Python as externally managed, so `pip install -e .`
into it is refused. Use a virtual environment:

```
python -m venv .venv
.venv/bin/pip install -e .
.venv/bin/linguexx2odt paper.tex
```

Put it on `PATH` if you want the bare command:

```
export PATH="$PWD/.venv/bin:$PATH"     # or: ln -s "$PWD/.venv/bin/linguexx2odt" ~/.local/bin/
```

With `pipx` (`pacman -S python-pipx`) the whole thing is one line, and
the command lands on `PATH` for you:

```
pipx install -e .
```

Or skip installing altogether — there are no dependencies beyond the
standard library:

```
PYTHONPATH=src python3 -m linguexx2odt.cli paper.tex
```

## What the output looks like

Each example becomes one borderless table, so the columns line up:

| | | |
|---|---|---|
| (3) | a. | \*First subexample |
| | b. | Second subexample |

- the number is a Number Range field named `NumEx`, wrapped in literal
  parentheses — the construction described in
  [Gerhard Schaden's note on Writer for linguists](http://gerhard.schaden.free.fr/blog/libreoffice-writer-for-linguists-and-linguistics/index.html);
- object-language words sit in individual cells with their glosses in the
  cells directly beneath;
- an example too wide for the text block is **split into stacked bands**,
  each band a group of tier rows starting back at the left edge — the
  pattern item 4 of the reference document specifies. The number appears
  on the first band only, and the translation once, at the end.
  `--no-split` squeezes it into a single band instead, wrapping words
  inside their cells;
- a sub-example paradigm shares one table but **not one set of widths**:
  each item is measured and banded on its own words, and the table's
  column grid is the union of every boundary the items and their bands
  produce, each word spanning the columns it covers;
- the free translation occupies a final row of merged cells;
- `\label`/`\ref` become cross-reference fields that track renumbering,
  including forward references and references to sub-examples — `(9a)`;
- judgment marks (`*`, `??`, `\#`, `\jdg{…}`) **hang to the left of the
  text**, in a column carved out of the one before them rather than
  inserted, so they consume no horizontal space in the text block. A
  judged and an unjudged example begin at exactly the same x, and a
  sub-example letter sits where a main example's text begins — linguexx's
  own geometry, measured from a pdflatex build.

Nothing uses direct formatting: everything is a **named style**
(`LxLeipzig`, `LxItalic`, `LxJudgment`, `LxExampleCell`, …), so you can
restyle every example in the document from the Writer sidebar.

### The space above and below an example

That includes the vertical spacing, which is set at conversion time with
`--example-spacing` / `--space-above` / `--space-below` and is afterwards
adjustable from the sidebar through three paragraph styles:

| style | what it does |
|---|---|
| `LxExampleSpace` | the height of both gaps — **edit this to move both at once** |
| `LxExampleSpaceAbove` | inherits it; give it a line spacing of its own to change only the gap above |
| `LxExampleSpaceBelow` | likewise, for the gap below |

Change the height under *Indents & Spacing ▸ Line spacing ▸ Fixed*: the
gap is the height of an empty spacer row at the top and bottom of each
example table, and a fixed line spacing sets it exactly (0 cm really is
0). Every example in the document follows immediately.

It is done this way rather than with a table margin because a table
margin cannot be a named style at all — LibreOffice ignores
`style:parent-style-name` on table styles, so table spacing can only ever
be per-table direct formatting. See `notes/findings.md`.

## Options

```
linguexx2odt input.tex [-o out.odt]
             [--text-width CM]     column widths are computed for this
                                   text block (default 17, = A4/2cm margins)
             [--font-pt PT]        body font size assumed when estimating
                                   column widths (default 12)
             [--example-spacing CM]  space above and below each example
                                   (default 0.18); later editable as the
                                   LxExampleSpace paragraph style
             [--space-above CM]    override it above only
             [--space-below CM]    override it below only
             [--no-split]          do not break overlong examples into bands
             [--page a4|a4-wide|letter|keep]
                                   page geometry written into the ODT
                                   (default a4; pandoc's own default is Letter)
             [--bibliography BIB]  a .bib for the citations; repeatable.
                                   Default: the ones the document names
             [--csl STYLE]         CSL style for citations and the
                                   reference list (default: Chicago
                                   author-date, which reads like natbib's
                                   author-year mode)
             [--no-citeproc]       do not resolve citations; print the keys
             [--reference-doc REF.odt]   base styles for pandoc
             [--keep-intermediates DIR]  residue.tex, ast.json, unpatched odt
             [-q] [-v]
```

## What it converts

The **lazy** syntax:

`\ex.` · `\a. \b. \c.` sub-examples (two levels: letters, then romans) ·
`\z.` early termination and level popping · `\gll` / `\glll` /
`\gl … \endgl` glosses · `\glt` translations · `\exg.` / `\ag.` / `\bg.`
shorthands · `{braced groups}` as single columns · unequal tiers ·
judgments · `\label` / `\sublabel` / `\ref` / `\pref` · `\lpzg{…}` ·
`\ExLBr` / `\ExRBr` and the sub-example pairs, so a document that asks for
`[1]` gets `[1]` · `\exannot{…}` structural labels, in a column at
`.75` of the text block — where `\ExAnnotColumn` puts them.

The Writer macro knows the construct too: it builds the same column from
`\exannot{…}` typed in Writer, and *Untypeset* gives the wrapper back
rather than leaving the label as a stray word — so a converted example
survives the trip out and back.

`\exannot` differs from linguexx in one case, deliberately. linguexx keeps
an example that reaches the column full width and drops its annotation to
the next line; this converter bands the example instead, which is what it
already does to anything too wide for the block, so the column stays a
column at every length rather than the rule changing at one. The optional
spoken argument is dropped — it is what a PDF screen reader says, and an
ODT has nowhere to put it.

## The second target: `--to docx`

```
linguexx2odt paper.tex --to docx -o paper.docx
```

A Word file whose example numbers are live `SEQ` fields and whose
cross-references are `REF` fields, so inserting an example renumbers the
rest there too. It lays out the gloss grid, judgments, sub-examples, bands
and `\exannot`, with the columns held to the same rendered-geometry
assertions as the `.odt` target, and it carries the same named styles, so a
Word user can restyle every example from the Styles pane.

Two things are worth knowing.

**Every field is written with its correct value already in it**, so the
document reads right whether or not your reader recalculates fields on
open. They differ about that: LibreOffice recalculates, OnlyOffice 9.4 does
not. The field stays live either way, which is what makes editing renumber.

**It reads correctly in Word 365, LibreOffice and OnlyOffice 9.4.** Word
does not offer to repair it, and inserting an example there renumbers the
rest, references included (`WORD-TESTS-TODO.md` has the tests and how to
repeat them). It is also validated against the ECMA-376 transitional
schemas (`make schemas`, then `tools/validate_docx.py`). OnlyOffice lays a
table out from its cells' widths where Word and LibreOffice use the column
grid, and until 2026-09-26 a banded or paradigm example's cell widths
disagreed with its grid — invisible in the other two, letters in slivers in
OnlyOffice. They agree now, and a test holds them to it.

The `.odt` target remains the reference one: it is what the Writer macro,
the reference document and the French manual are about.

**Targets linguexx 1.3.2.** Worth stating, because the gap is otherwise
invisible: this converter was written against 1.2 and silently kept
emitting 1.2's output for a month after 1.3 changed it. If you are on a
newer linguexx, check this table before trusting the result.

Example bodies end where linguexx ends them: at a blank line, at `\z.`,
at an environment boundary, or at a closing brace.

### What it does not, and says so

The converter never fails silently. Anything it cannot render faithfully
produces a warning naming the construct and the line, and degrades to
readable output rather than to nothing:

Unless a row says otherwise, this is true of both targets.

| construct | what happens |
|---|---|
| `\ex.` inside `itemize`, `enumerate`, `footnote`, `exe`/`xlist` | left as LaTeX, untouched |
| `\ex.[(4′)]` custom labels | printed literally; the counter is not stepped |
| `\exsource{…}` | rendered inline at the end, not flush right |
| `forest` / `\Tree` trees | kept as bracket notation, ready for the Writer macro to draw |
| `\refrange` | left as LaTeX |
| `\Next`, `\Last`, `\NNext`, `\LLast` and their `p` forms | resolved by position and rewritten as live cross-references |
| `\altn`, `\altg` | left as LaTeX |
| `\GlossTransSide` | warns; converted as an ordinary example, with the translation below. Deliberate — see below |
| `[phantomalign]`, `\GlossPhantomAlign` | warns; judgment marks get their own column instead of a gutter |
| `\GlossTierFont`, `\SetLeipzig`, `\DeclareJudgment` | warn; the reference document's styles and the literal marks are used |
| `[langsci]`, the `\ea … \z` front-end | warns; those examples are left as LaTeX |
| `\SetAltSpoken`, `\SetAnnotSpoken`, `\SetJudgmentSpoken` | ignored — they describe what a PDF screen reader says, which has no ODT counterpart |
| gb4e `exe`/`xlist` syntax, `[legacy]` mode | out of scope |
| `\citet`, `\citep`, `\citealt`, `\citeauthor` | resolved with citeproc against the document's `.bib`, with a reference list; the keys are printed if no `.bib` is found |
| `\citeauthor`, `\citealt`, `\citeyear` | resolved, but printed as `Author (Year)` — pandoc has one author-in-text mode, so the parentheses and the year come back; the run says how many |
| an example inside an environment pandoc does not know (`multicols`, …) | the example is recovered; the surrounding markup is not |
| math inside examples | handed to pandoc; may not survive |
| consecutive examples, `.docx` only | kept apart by a 1 pt paragraph in its own style, `LxExampleGap`: Word joins tables that touch, and without it a run of examples was one table in Word. Each step between consecutive examples is 1 pt taller than in the `.odt`, and nothing else moves (measured). A file converted before 2026-09-26 still has them touching; reconvert it |
| anything else unknown | handed to pandoc, as `opendocument` or `openxml` |

### Why `\GlossTransSide` is normalised rather than reproduced

A side translation is the same material in a different place, so setting it
below loses nothing a reader needs. Reproducing it would mean deciding what
that column does when an example is too wide and splits into bands — repeat
beside every band, sit beside the first only, or suppress the split. linguexx
never faces the question because it reflows; an ODT table does not, and
answering it in passing would turn an accident into a promise.

So the converter says what it did and moves on. If you want the side layout
in the `.odt`, it is a column drag in Writer, once, per example.

### Citations

natbib and biblatex citations are resolved, and a reference list is added at
the end. Nothing needs saying on the command line: the document already
declares its bibliography with `\addbibresource` or `\bibliography`, so that
is what gets used.

```
linguexx2odt paper.tex                       # uses \addbibresource{mabiblio.bib}
linguexx2odt paper.tex --bibliography ~/refs.bib    # or name one yourself
linguexx2odt paper.tex --csl unified-style-sheet.csl
```

`\citet` comes out author-in-text, `\citep` parenthetical, and an optional
locator (`\citep[786]{fruyt2011}` → "Fruyt 2011, 786") survives. `\citealt`,
`\citeauthor` and `\citeyear` resolve too, but pandoc's reader has a single
author-in-text mode, so they all print `Author (Year)`; the run says how many
of each, since `\citeauthor` in particular asked for the author *without* the
year.

**If no `.bib` is found the keys are printed** — `[vincent1982]` — and the run
says so twice, once for the missing file and once for the count. This is not
politeness: a `Cite` that citeproc has not resolved carries only the raw LaTeX
the reader kept, and both writers drop that, so before this an unresolved
citation was not degraded but *deleted*, closing the sentence over the hole
("According to authors like , the Latin construction…"). Printing the key is
what makes the gap visible.

### Choosing the face: `--font`

```
linguexx2odt paper.tex --font "EB Garamond"
```

The column widths are computed from real per-character metrics, so the face
the document is set in and the face it is measured for have to be the same
one. `--font` sets both, in either target.

Times New Roman is the default, and Times-metric faces — Liberation Serif,
Nimbus Roman, Tinos — use a table measured once and shipped, reading no
files. Any other face is measured off its own font file with `fonttools`,
which takes milliseconds and needs no LibreOffice. A name no installed font
answers to is an error rather than a silent substitution: fontconfig always
returns *something*, and measuring its guess would size the columns for a
font nobody chose.

`--reference-doc` wins over `--font`. Supplying a reference document is
choosing a typeface, and overriding it to keep the columns exact would be
answering a question you already answered — the columns may then drift a
little, which is the honest price.

## Things you will want to fix by hand

Two of these are inherent to the table method, not defects:

1. **Column widths are estimated.** Real font metrics are not available
   at conversion time, so widths come from a table of per-character
   advances measured from Liberation Serif — metric-compatible with Times
   New Roman — and err slightly wide: −2% to +9% of the rendered width
   before `width_safety`. Drag the column edges in Writer if a column
   looks wrong, or set `--font-pt` if your body text is not 12 pt. The
   Writer macro below does not have this limitation — it measures.
   `python3 tools/measure_advances.py` checks the table against the font.

   Text is estimated as it is *drawn*, not as it is spelled: `\lpzg{…}`
   and `\textsc{…}` set small capitals, which are the capitals at 80% of
   the size and so wider than the lowercase they replace for most letters.
   A gloss column measured from the lowercase would be too narrow for its
   own contents.

2. **Tables do not reflow.** Where a band breaks is computed from
   `--text-width` at conversion time and then frozen — the reference
   document fixes the band *pattern*, never the break points. If you
   change the page geometry later, reconvert from the `.tex` with the new
   `--text-width` rather than fighting the existing file. (Thanks to
   `table:align="margins"`, a squeezed table rescales and wraps internally
   instead of running off the page — ugly, never wrong.) The Writer macro
   below can re-band against the current page at any time.

## Writing examples in Writer

The Writer macro (`linguexx2odt --print-macro`) turns selected
lines into an aligned example without going through LaTeX at all. Select

```
Esto es un ejemplo glosado
this is a example glossed
'This is a glossed example.'
```

press your shortcut, and get the same object this converter emits — same
named styles, same `NumEx` field, same hanging judgment marks.

It exists because a macro can do two things the converter cannot: it
**measures the real font** instead of estimating column widths (the
estimate is off by −2% to +9%), and it reads the **actual page style**
instead of taking `--text-width` on trust. Since it shares the style
names, it also works as a post-processor on converted documents.

Sub-example paradigms (`a. … b. …`) work too, glossed or not, with the
letters in their own column and one number for the paradigm.

It also draws **syntax trees** from bracket notation: select
`[DP [D the] [NP [N tree]]]`, press the shortcut, and get a numbered
example whose content is the tree — built from Writer draw shapes, in the
same table as any other example, so trees and glossed examples line up and
renumber together. `{braced}` labels, `, roof` triangles, judgment marks and
movement arrows all work — movement is written by naming two nodes and
adding `move t -> wh` under the tree, and the arrow is routed in a gutter
below it. *Typeset numbered tree* takes a whole `a. … b. …` paradigm of them, and
*Typeset unnumbered tree* draws one with no number at all. Which command
you run is the whole of the decision: *Typeset example* never draws a tree,
so labelled bracketing like `[TP [DP John] [VP left]]` stays the text you
typed.

*Untypeset example* is the way back: put the cursor in a built example and
it becomes the lines it was built from again, with its number — the live
field every cross-reference points at — at the head of the first one. Edit
the text, select it, typeset it again, and it is the same example with the
same number, so **an example can be changed without breaking a single
`\ref` to it**. Any of the building commands will take the text back, so a
glossed example can come back as a tree or as a paradigm. Drawn trees come
back too: the group of shapes carries the bracket notation it was drawn
from in its alt text, since shapes have positions and not structure.

Formatting you applied by hand comes through — small caps on a Leipzig
gloss, italics, bold, superscripts — and each run is measured in the font
it will be drawn in, which matters more than it sounds: small caps are
capitals at 80% of the size, so 10–20% *wider* than the lowercase they
stand in for, and a column measured as lowercase is too narrow for them.

*Example layout…* sets the five lengths that are house style rather than
measurement: how far in the example number sits, how far from it the
sub-example letter sits, how far from that the sub-example's text sits, and
the space above and below. They belong to the document, like the styles.
The two spacings *are* the `LxExampleSpace*` styles, so changing them
restyles every example at once; the indents apply to examples built
afterwards.

Install it as a LibreOffice extension:

```
python3 tools/build_oxt.py && unopkg add dist/linguexx-0.1.0.oxt
```

or paste the source in by hand — it ships with the package, so
`linguexx2odt --print-macro` prints it.

See [`docs/macro.md`](docs/macro.md) for the details and the trade-offs.

## Writing examples in Word and OnlyOffice

Two add-ins do in Word and in OnlyOffice what the Writer macro does in
Writer. Select the lines of an example and they become a numbered example
with a live number — the same table the converter writes, the same named
styles, the same `NumEx` sequence — so a converted document, a macro
document and an add-in document hold the same kind of object. Both are one
JavaScript core under two thin layers: the core parses as the macro parses
and lays out as the converter lays out, and tests hold it to both exactly
(`plan-addins.md` says how).

- **Typeset selection.** Lines typed as for the macro: the object line,
  the gloss lines, a quoted translation last; `a.`, `b.` for sub-examples;
  a leading `*` or `?` for a judgment; `{braces}` to keep words in one
  column; `\exannot{…}` for a label in its column.
- **Insert reference…** lists the document's examples; pick one and a live
  cross-reference goes in at the cursor, `(3)` — or `3` with *bare
  number*.
- **Untypeset example** turns the example the cursor is in back into its
  lines, with its number — the same field every reference points at — at
  the head of the first. Edit, select, typeset again: same example, same
  number, references intact.
- Formatting typed by hand comes through (small caps, italic, bold,
  underline, raised and lowered text, character styles) and is measured as
  drawn.
- **The example is set in the document's face and measured for it.**
  Times-metric faces and Aptos, Word's default, have measured metrics;
  another face is estimated from Times's, and the pane says so.

### What they do not, and say so

| | Word | OnlyOffice |
|---|---|---|
| renumbering after an insertion | Word for the desktop: Ctrl+A, F9. **Word on the web never renumbers fields** and will not let an add-in do it: the new example is numbered right, and the pane says which numbers and references are stale | at once — and every other field in the document is refreshed with them |
| trees | not drawn; bracket notation stays text — use the Writer macro | the same |
| the layout dialog | none: the lengths are the converter's, and the space around an example is the `LxExampleSpace*` styles | the same |
| several examples in one table — a file converted before 2026-09-26 | *Untypeset* refuses it; reconvert the file (see the `.docx` row above) | does not arise: OnlyOffice keeps touching tables apart |
| a document an earlier add-in build wrote into | its `LxExampleCell` may carry Times New Roman: Styles ▸ LxExampleCell ▸ Modify ▸ the document's face | — |
| where it has run | Word on the web. **Word for the desktop has not been tried** | OnlyOffice Desktop 9.4 |

Word on the web is slow — every question an add-in asks is a round trip —
and a click can take a few seconds; the pane disables its buttons while
Word works.

### Installing them

Neither is published. **Word:** the add-in has to be served over HTTPS,
and for now that is a server on your own machine:

```
python3 tools/serve_addin.py      # https://localhost:3000, certificate made once
```

Open <https://localhost:3000/word/taskpane.html> once and accept the
certificate, then in Word: Home ▸ Add-ins ▸ More Add-ins ▸ My Add-ins ▸
*Upload My Add-in*, and choose `addin/word/manifest.xml`. A **LinguExx ▸
Examples** button appears on the Home tab. The server has to run while the
add-in is used; `--manifest-only --base URL` writes a manifest for serving
`addin/` from anywhere else.

**OnlyOffice:** `make onlyoffice` builds the plugin into
`dist/onlyoffice/{D71895BD-806D-4964-ACA4-0A531FE92454}/`. Copy that folder
into OnlyOffice Desktop's user plugin folder and restart; **LinguExx**
appears on the Plugins tab. For the Flatpak build that folder is
`~/.var/app/org.onlyoffice.desktopeditors/data/onlyoffice/desktopeditors/sdkjs-plugins/`
— the one place this has been tried. `dist/linguexx-onlyoffice.plugin` is
the same folder zipped, for OnlyOffice's plugin manager.

## Checking the renumbering

Open the output in Writer, put the cursor before an example, insert a new
one (Insert ▸ Field ▸ More Fields ▸ Variables ▸ Number range, `NumEx`),
then Tools ▸ Update ▸ Fields (F9). Every later number and every
cross-reference shifts.

## Development

```
make check                  # lint and the suite: what CI runs
make test                   # the suite alone
make lint                   # ruff over src/, tests/ and tools/
make js-test                # the add-ins' suite (Node >= 22, nothing to install)
make onlyoffice-test        # the OnlyOffice plugin's editor half, in Document Builder
LINGUEXX_UPDATE_GOLDEN=1 pytest tests/test_extract.py   # re-snapshot
python3 spikes/s1_passthrough.py   # re-run if the pandoc version changes
```

Plain `pytest` is enough — `pyproject.toml` sets `pythonpath = ["src"]`, so
no `PYTHONPATH` and no activated virtualenv are required. A regenerated
golden is **read before it is committed**; regenerating without reading
records whatever the code now does, bug included.

The end-to-end tests build a real `.odt`, render it headlessly, and
measure the PDF: that numbers evaluate (with every cached value corrupted
first, so echoing cannot pass), that cross-references resolve, that
glosses sit above their words, that judgment marks do not shift the text,
and that nothing overflows the margin.

They need `pandoc`, `soffice` and `pdftotext`, and their absence is a
**failure, not a skip**: without them 28 of the tests — every end-to-end
one — step aside and the run still exits 0, which is how a contributor
without LibreOffice sees green and ships. `tests/test_tooling.py` names
what is missing, and checks that CI still installs it. To run a partial
suite deliberately:

```
LINGUEXX2ODT_ALLOW_MISSING=1 make test
```

If a rendering test seems to sit there for ever rather than fail,
suspect OpenCL: LibreOffice probes it at startup, and a broken entry in
`/etc/OpenCL/vendors` hangs the probe. `clinfo -l` hanging too confirms
it, and `SAL_DISABLE_OPENCL=1` gets the suite moving. Fixing the ICD is
the better cure — the workaround is per-run, and everything else that
uses OpenCL stays broken. It applies to `tools/run_macro_test.py` too.

`notes/findings.md` records what was measured and why each design
decision was taken — read it before revisiting one.

## Layout

```
src/linguexx2odt/
  extract.py      .tex  -> IR + residue with placeholders
  ir.py           the dataclasses the golden tests snapshot
  latexutil.py    brace/comment/verbatim-aware scanning
  emit_odt.py     IR   -> raw opendocument tables
  inline.py       LaTeX inline fragments -> ODT spans (pandoc fallback)
  styles.py       named styles, all layout constants, and the subset the
                  Writer macro must agree with
  inject.py       placeholder Paras -> raw blocks; \ref -> fields
  postprocess.py  zip surgery on the .odt pandoc produced
  cli.py
  writermacro/    the Writer macro, shipped as package data
    LinguExx.bas
tools/
  sync_macro.py      regenerate/check the constants shared with the macro
                     and the add-ins
  build_oxt.py       package the macro as a LibreOffice extension
  run_macro_test.py  drive the macro in a real LibreOffice and measure it
  addin_oracle.py    the converter's plans and .docx markup, which the
                     add-in core is held to
  serve_addin.py     serve the Word add-in on localhost over HTTPS
  build_onlyoffice.py         build the OnlyOffice plugin
  run_onlyoffice_test.mjs     run it headless in Document Builder
  measure_face.py    measure a face (Aptos) into measure.py
addin/
  core/           parse, plan, table, untypeset: shared by both add-ins
  word/           the Word add-in: OOXML, the task pane, the manifest
  onlyoffice/     the OnlyOffice plugin: builder-API commands, the panel
docs/
  macro.md        the Writer macro
  guide-fr.md     guide complet en français
```

The converter and the macro live in one repository on purpose: what they
share is a *specification* — six style names, seven layout lengths, the
`NumEx` sequence, and the geometry rules — not code. Splitting them would
make that contract implicit, and it had already started to drift.
`tools/sync_macro.py` and `tests/test_macro_sync.py` make it explicit
instead.

## License

Copyright © 2026 Gerhard Schaden.

This program is free software: you can redistribute it and/or modify it
under the terms of the GNU General Public License as published by the
Free Software Foundation, either version 3 of the License, or (at your
option) any later version. See [LICENSE](LICENSE).

Note that [linguexx](../linguexx) itself is under the LaTeX Project
Public License 1.3c — a different licence for a different kind of work.
This converter only reads linguexx documents; it includes none of the
package's code.
