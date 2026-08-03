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

## Options

```
linguexx2odt input.tex [-o out.odt]
             [--text-width CM]     column widths are computed for this
                                   text block (default 17, = A4/2cm margins)
             [--font-pt PT]        body font size assumed when estimating
                                   column widths (default 12)
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
   your body text is not 12 pt.

2. **Tables do not reflow.** Where a band breaks is computed from
   `--text-width` at conversion time and then frozen — the reference
   document fixes the band *pattern*, never the break points. If you
   change the page geometry later, reconvert from the `.tex` with the new
   `--text-width` rather than fighting the existing file. (Thanks to
   `table:align="margins"`, a squeezed table rescales and wraps internally
   instead of running off the page — ugly, never wrong.)

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
  styles.py       named styles and all layout constants
  inject.py       placeholder Paras -> raw blocks; \ref -> fields
  postprocess.py  zip surgery on the .odt pandoc produced
  cli.py
```

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
