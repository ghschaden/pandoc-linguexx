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

It appears as a **LinguExx ▸ Typeset example** menu entry in Writer. An installed extension raises
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
  by −7% to +28% in practice. Here the actual font is available, so
  columns are exactly as wide as their contents.
- **Reads the real page.** The available text width comes from the page
  style in front of you, not from a `--text-width` flag — so it is right
  for the document you are actually in.
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
- **Items may be glossed or not, in the same paradigm.** An unglossed item
  is running text in one merged cell, not one word per column: splitting it
  would align words that have nothing to do with each other.
- **Each item may carry its own judgment mark**, which hangs left as usual.
- A translation belongs to its own item.

If a letter appears part-way through the selection but the selection does
not start with one, it refuses rather than guess.

## Differences from `linguexx2odt`

| | converter | macro |
|---|---|---|
| column widths | estimated | measured |
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

It needs `soffice`, `pdftotext` and python-uno. It checks that the number
field evaluates, that every gloss sits under its word, that `{braces}`
group, that an overlong example still aligns, and that a judgment mark
hangs left without shifting the text block of a neighbouring unjudged
example. Six sub-example cases cover glossed, unglossed, mixed, judged,
roman-numeral and marker-on-its-own-line paradigms, and one pins the
letter against a main example's text — the invariant
`test_sub_example_letters_align_with_main_example_text` pins for the
converter.

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
