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
- **Python ≥ 3.10**, standard library only
- LibreOffice is *not* needed to convert, only to read the result (and to
  run the rendering half of the test suite)

## Install

Arch/Manjaro (and most current distros) mark the system Python as
externally managed, so `pip install -e .` into it is refused. Use a
virtual environment:

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
  each band a group of tier rows starting back at the left edge, all
  sharing one column grid — the pattern item 4 of the reference document
  specifies. The number appears on the first band only, and the
  translation once, at the end. `--no-split` squeezes it into a single
  band instead, wrapping words inside their cells;
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
judgments · `\label` / `\sublabel` / `\ref` / `\pref` · `\lpzg{…}`.

Example bodies end where linguexx ends them: at a blank line, at `\z.`,
at an environment boundary, or at a closing brace.

### What it does not, and says so

The converter never fails silently. Anything it cannot render faithfully
produces a warning naming the construct and the line, and degrades to
readable output rather than to nothing:

| construct | what happens |
|---|---|
| `\ex.` inside `itemize`, `enumerate`, `footnote`, `exe`/`xlist` | left as LaTeX, untouched |
| `\ex.[(4′)]` custom labels | printed literally; the counter is not stepped |
| `\exsource{…}` | rendered inline at the end, not flush right |
| `\refrange`, `\Last`, `\Next`, relative references | left as LaTeX |
| `\altn`, `\altg` | left as LaTeX |
| gb4e `exe`/`xlist` syntax, `[legacy]` mode | out of scope |
| math inside examples | handed to pandoc; may not survive |
| anything else unknown | handed to `pandoc -f latex -t opendocument` |

## Things you will want to fix by hand

Two of these are inherent to the table method, not defects:

1. **Column widths are guesses.** Real font metrics are not available to
   the converter, so widths are estimated from per-character advance
   widths for a Times-like face at 12 pt, erring slightly wide. Drag the
   column edges in Writer if a column looks wrong, or set `--font-pt` if
   your body text is not 12 pt. The Writer macro below does not have this
   limitation — it measures.

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
estimate is off by −7% to +28%), and it reads the **actual page style**
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
below it. A second
command draws the tree with no number at all, for a footnote or a figure.

Formatting you applied by hand comes through — small caps on a Leipzig
gloss, italics, bold, superscripts — and each run is measured in the font
it will be drawn in, which matters more than it sounds: small caps are
capitals at 80% of the size, so 10–20% *wider* than the lowercase they
stand in for, and a column measured as lowercase is too narrow for them.

Install it as a LibreOffice extension:

```
python3 tools/build_oxt.py && unopkg add dist/linguexx-0.1.0.oxt
```

or paste the source in by hand — it ships with the package, so
`linguexx2odt --print-macro` prints it.

See [`docs/macro.md`](docs/macro.md) for the details and the trade-offs.

## Checking the renumbering

Open the output in Writer, put the cursor before an example, insert a new
one (Insert ▸ Field ▸ More Fields ▸ Variables ▸ Number range, `NumEx`),
then Tools ▸ Update ▸ Fields (F9). Every later number and every
cross-reference shifts.

## Development

```
.venv/bin/pytest            # parser goldens, corpus, and end-to-end
LINGUEXX_UPDATE_GOLDEN=1 .venv/bin/pytest tests/test_extract.py   # re-snapshot
python3 spikes/s1_passthrough.py   # re-run if the pandoc version changes
```

The end-to-end tests build a real `.odt`, render it headlessly, and
measure the PDF: that numbers evaluate (with every cached value corrupted
first, so echoing cannot pass), that cross-references resolve, that
glosses sit above their words, that judgment marks do not shift the text,
and that nothing overflows the margin. They skip cleanly where `soffice`
is absent.

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
  build_oxt.py       package the macro as a LibreOffice extension
  run_macro_test.py  drive the macro in a real LibreOffice and measure it
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
