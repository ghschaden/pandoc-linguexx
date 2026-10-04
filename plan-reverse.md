# Plan: the way back — `.docx`/`.odt` → LaTeX with linguexx

Status, 2026-10-04: **tier A built**: `docx2linguexx` and `odt2linguexx`
(`untypeset.py`, `reverse.py`, `tests/test_reverse.py`). See *Built* at
the end, which records where the build departed from this plan. Tier B is
not built. The decisions are recorded at the end: tier A only for now,
generated labels, two commands.

## What "the way back" can mean

Two problems hide under one name, and they differ by an order of
magnitude in difficulty:

- **A. Round trip.** The document's examples were made by this project:
  the converter (`--to odt`/`--to docx`), the Writer macro, or an add-in.
  Each example cell names its role by paragraph style (`Lx*`), the number
  is a field with a bookmark, references are `REF`/`sequence-ref` fields,
  and a tree carries its source as alt text. Reading it back is
  **deterministic**. The use case is a co-author who edits in Word, and an
  author who wants their LaTeX back afterwards.
- **B. Foreign documents.** These are articles typed freehand in Word or
  Writer. Their examples are borderless tables, tab-aligned lines or
  lines aligned with non-breaking spaces. Numbers are typed by hand, and so
  are references. Reading them is **heuristic**. linguex-peren found the
  hard limit (F13): *no reliable marker separates a gloss from a data
  table.*

The prior art is not in this repository:

- **For B:** linguex-peren's `pandoc-test/` already takes Lexique articles
  to linguexx. Its input is Lodel HTML, which descends from the authors'
  Word and Writer files. `prepare.py` (1,010 lines) and `lexique.lua` (948)
  do the following:
  - detect examples;
  - read labels per row (F129);
  - recover hand alignment from word positions (F125);
  - map sources to `\exsource` (F126) and Leipzig labels to `\lpzg`
    (F139–F140).

  This is proof that B is possible on one journal's corpus. It cannot be
  reused as code: it walks a BeautifulSoup DOM, and its tolerances were
  tuned on a single article (1910).
- **For A:** this repository already reads its own tables back. The
  macro's `LxReadTable` does it, and so does its port `addin/core/
  untypeset.js` (*Untypeset*). Both rely on style names alone ("nothing is
  inferred from what a cell happens to contain").

## Spikes run for this evaluation [observed]

These were run on 2026-10-04 with pandoc 3.10.2, on `tests/cases/gloss.tex`
and `labels.tex` converted by the current tool. The outputs are in the
session scratchpad and were not kept.

| # | Question | Answer |
|---|---|---|
| S1 | Does `pandoc -f docx+styles` keep the `Lx*` cell styles? | **Yes.** Each cell paragraph arrives as `Div custom-style="LxExampleCell"` (etc.) inside an ordinary `Table`. |
| S2 | What becomes of a `SEQ` number and a `REF` in `.docx`? | The number arrives as its **cached text** ("(", "1)"), next to an empty anchor span `#NumEx0`. The field itself is gone. A `REF` arrives as a **link** to that anchor: `[1](#NumEx0)`. Both the numbers and the references can be recovered. |
| S3 | Does `pandoc -f odt` do the same? | **No.** The ODT reader has no `styles` extension, and it **drops the `sequence-ref` fields entirely**: "Refs: (), (a), c." This is the same failure as the deleted-text case in CLAUDE.md: text vanishes with nothing to show it. |
| S4 | Does `soffice --convert-to docx` preserve what S3 lost? | **Yes.** Read with `docx+styles`, it gives the same cell styles, anchors renamed `Ref_NumEx0_number_only`, and links to them. |
| S5 | Do tab-aligned glosses survive pandoc? | **No**, in both readers: `<text:tab/>` and `<w:tab/>` become `Space`. A typed gloss cannot be told from prose through pandoc. |

What follows from the spikes:

- **Use one reader.** `.odt` goes through LibreOffice to `.docx` first,
  then everything is read as `docx+styles`. LibreOffice is already a
  dependency (the rendering half).
- **Do not use pandoc's ODT reader.** Reading `content.xml` directly would
  be the alternative, and it would mean a second reader to keep honest.
- **Tier B cannot run on the pandoc AST alone.** The tabs are gone by then,
  so it has to read `document.xml`.

## Architecture (tier A)

The IR is the pivot. The forward path is `tex → IR → markup`; the way
back is `markup → IR → tex`. The IR (`ir.py`) already holds LaTeX source
in its cells, so the way back needs two pieces:

1. a **table reader**: example table → `Example`;
2. a **linguexx writer**: `Example` → `\ex. \gll … \\ … \\ \glt …`.

Nothing in `measure` or `emit_base` is involved: geometry is not read
back, because linguexx sets its own.

```
in.odt ──soffice──┐
in.docx ──────────┴→ pandoc -f docx+styles -t json
                      └ untypeset.py   for each Table whose first/last rows carry
                                       LxExampleSpaceAbove/Below (isExampleTable):
                                       cells by style → ir.Example → RawBlock latex
                                       anchors → \label, links to them → \ref/\pref
                                       LxExampleGap paragraphs → deleted
                    → pandoc -t latex --template reverse.latex  (linguexx, babel, biblatex)
                    → out.tex
```

- **`untypeset.py`** is the macro's `LxReadTable`, a third time, in
  Python. It keeps the same rule: style names decide, never contents. It
  is held to the same oracle, `UNTYPESET_CASES` and the typed-example
  fixtures, compared exactly. CLAUDE.md's rule ("the core is held to
  oracles, exactly") applies unchanged. Node stays test-only, so the JS
  core cannot simply be called.
- **Inline markup in cells:**
  - italics, bold and small caps come back as pandoc inlines and go out
    through pandoc's LaTeX writer;
  - the converter's character styles map back to their commands, for
    instance a Leipzig small-caps run → `\lpzg{…}`;
  - the mapping is the inverse of `inline.DECLARATIONS`/`WRAPPERS`, and a
    test should hold the two in step.
- **Trees:** the drawing's alt text under the title `LinguExx tree` *is*
  the source, so it goes back as the tree environment it came from.
  [inferred: not yet run through pandoc's docx reader; spike S7]

## Phases

### Phase 0: the remaining spikes (half a day)

- **S6 Footnotes, citations, comments, tracked changes.**
  - Footnotes should be fine.
  - Citations: the `docx` reader's `citations` extension reads
    Zotero/Mendeley fields as `Cite`, which `--biblatex` writes as
    `\autocite`. A co-author's Zotero citation therefore comes back as a
    citation, and a citation that is plain text comes back as text.
  - Tracked changes: `--track-changes=accept|reject|all`. The tool should
    refuse a document that still has unresolved changes rather than pick
    a side quietly.
- **S7 Trees:** does the alt text survive `-f docx` (`Image` alt? a
  drawing inside a table cell?) for both hosts' drawings?
- **S8 Edited in Word:** a document converted, opened and *saved* by Word
  (Word on the web, via CDP), with one example inserted through the
  add-in and one reference added. Do the anchors, the links and the
  styles survive Word's rewrite? This is the case that matters, and the
  spikes so far read only files this tool wrote.
- **S9 The fixed point:** `tex → docx → tex → pdflatex` on
  `tests/cases/*.tex` against the original's pdflatex, compared by word
  coordinates (`tests/pdfwords.py`). This measures, before anything is
  built, how much of a document pandoc's own round trip already loses.

### Phase 1: example tables → IR (core of tier A)

- `untypeset.py` and its golden, `tests/golden/reverse/*.json`, are read
  before they are committed.
- **The oracle:** for every `tests/cases/*.tex` and every linguexx corpus
  document, `extract(tex)` must equal `untypeset(convert(tex))`. A
  difference is either a reader bug or a forward-converter bug, and both
  are worth finding.
- The comparison must be modulo LaTeX spelling. `\"a` and `ä`, and
  `{kleine Kind}` and `kleine~Kind`, are the same text. Define the
  normalisation once, and record in the README what it calls equal.

### Phase 2: numbers and references

- An anchor becomes `\label`, and a link to an anchor becomes
  `\ref`/`\pref`/`\exref`.
- A sub-example reference arrives as the link plus a literal letter,
  `([2](#NumEx1)a)`, so it becomes `\ref{…}` with the right sub-label.
- **Label names are lost today.** The forward path names bookmarks
  `NumEx0, NumEx1…`, and the author's `ex:passive` is gone. See
  decision D2.
- Hand-typed numbers in running text ("see (3)") stay text, with a warning
  that counts them. Turning them into references is tier B.

### Phase 3: the document around the examples

- Add a `reverse.latex` template: linguexx, babel from the document's
  language, biblatex when there are citations, and the page size from the
  `.docx` section.
- Prose is pandoc's, and the README says so. Pandoc's LaTeX for a heading,
  a list or a table is what the user gets.
- The repository's rule holds in reverse: **a node pandoc produces but
  cannot render is deleted, not degraded.** Every raw `openxml` or
  `opendocument` block that reaches the LaTeX writer is dropped silently
  unless it is caught, so the run must warn about each one.

### Phase 4: verification and the README

- The fixed point from S9 becomes a test over the corpus. Measure, do not
  reason.
- Add a "What it does not, and says so" table for the way back, in
  English and in `docs/guide-fr.md`.

### Phase 5 (only if D1 says so): foreign documents (tier B)

- Read `document.xml`/`content.xml` directly, because pandoc loses tabs
  (S5).
- Find the examples among tables, tab-aligned paragraphs and paragraphs
  aligned with non-breaking spaces. Use the tab stops, which are real
  positions in the file, unlike F125's estimated widths.
- Port linguex-peren's decisions, not its code:
  - labels per row;
  - sources → `\exsource`;
  - Leipzig labels → `\lpzg`;
  - hand-typed numbers → `\ex.[(n)]` (the author's number, kept);
  - text references matched to them only when unambiguous.
- **What it needs first: a corpus.** That means real authors' `.docx` and
  `.odt` files, not Lodel HTML. Lexique's submissions would be the obvious
  source if they can be used. Without a corpus, the heuristics are tuned
  on whatever is at hand, which is exactly how F125's tolerances came to
  rest on one article.
- **When a guess fails, the lines stay lines.** linguex-peren's rule
  ("if alignment is weak, the lines stay as typed, which is safe") is the
  right one.

## Effort [inferred]

- **Tier A:** Phases 0–4, of the order of the forward `extract.py` plus a
  writer, roughly 1,000–1,500 lines with tests. The oracle comes for free
  because the forward path exists. The risk is concentrated in S8: what
  Word does to the file when it saves it.
- **Tier B:** open-ended. linguex-peren's comparable part took several
  sessions for one journal, and its report flags its own generalisation
  as untested. Do not start it without a corpus and a stopping rule.

## What it will not do

- **Give back the author's original source.** The forward path expands
  the document's own macros (204dd56), normalises `\GlossTransSide`, and
  drops what the README lists. The way back gives *a* linguexx document
  that renders the same examples, not *the* file the author had.
  Re-applying Word edits to the original `.tex` (a three-way merge) is a
  different and harder tool. It is worth naming, and it is not this one.
- **Recover geometry.** Column widths, bands and the gap paragraphs are
  dropped; linguexx sets its own.

## Decisions wanted

- **D1: scope.** Tier A only (recommended to start), or A then B? If B,
  which corpus?
- **D2: label names.** Should the forward path keep the author's `\label`
  key in the document, for example as the bookmark name
  (`NumEx_ex:passive`, within Word's 40-character bookmark limit and its
  character set: a spike), so that the way back restores `ex:passive`?
  This changes forward output and every `.docx`/`.odt` golden. Without
  it, labels come back as generated names (`ex:1`, `ex:2`…), and documents
  converted before the change always will.
- **D3: entry point.** A second command (`docx2linguexx`) or `linguexx2odt
  --reverse`? The package name says one direction. A second console script
  in the same package shares the IR without renaming anything.

**Decided, 2026-10-04 (the user):**
- **D1:** tier A only, for now.
- **D2:** labels are generated (`ex:1`, `ex:2a`). The names do not matter
  as long as they are distinct, so the forward path is unchanged.
- **D3:** two commands, `docx2linguexx` and `odt2linguexx`, both in this
  package.

## Built (2026-10-04)

### Where the build departed from the plan

- **It reads `document.xml`, not pandoc's AST.** Building showed what
  `docx+styles` loses:
  - the paragraph style of an *empty* paragraph, which is every spacer
    row, so an example table cannot be recognised there;
  - the field itself, keeping only its cached text;
  - tabs (S5).

  The XML has all three. Pandoc still converts everything else. Each
  example table is replaced by a paragraph `LXEXAMPLE<n>X`, and each REF
  field whose bookmark is an example's by a word `LXREF<n>X`. Both are
  letters and digits, so pandoc passes them through. They are filled in
  on pandoc's LaTeX output.
- **There is no third port of the macro's `LxReadTable`.** A table is read
  straight into the converter's IR, by the same rule (style names decide).
  The oracle is the stronger one the plan proposed for Phase 1:
  `parse(tex)` must equal `parse(docx2linguexx(linguexx2odt(tex)))`. It
  runs over `tests/cases` and the whole linguexx corpus through `.docx`,
  and over six structural cases through `.odt`.
- **A reference's brackets** decide between `\ref` and `\pref`. "(" + the
  field + ")" is `\ref`, and the field alone is `\pref`. A letter after
  the field that is one of the example's sub-example markers makes it a
  reference to that sub-example. Pandoc writes `[` as `{[}`, and both
  spellings are recognised.

### Measured

- **IR oracle, `.docx`:** all 12 cases and all 110 corpus documents give
  the same examples. `trailing-translation` example 3 was a listed
  exception until the forward fix (below).
- **IR oracle, `.odt`:** the six structural cases pass. Over the whole
  corpus, 71 of 109 pass. Every failure examined was the forward `.odt`
  target deleting LaTeX it cannot render, where the `.docx` target prints
  it as source (`\altn`, `\altg`, `tabular`, `xlist`, `\pause`). The
  README says so for the first two. Not a reverse question.
- **pdflatex, by hand (not in the suite, because CI has no TeX):** the
  original and the round trip were built for every case and each example
  line's words compared, relative to the example number's x. With both
  sides in T1/Latin Modern/microtype, which pandoc's template loads, the
  examples of `gloss`, `exannot`, `judgments`, `shorthand` and `sub` agree
  to 0.3pt. The remaining differences are the forward losses below, the
  documented normalisations (`\GlossTransSide`, `\exsource`), and prose
  set with parskip.
  - A 1.4pt shift of every translation that opens with a quote turned out
    to be microtype's protrusion, not the quote character. It was nearly
    recorded as a fact about quotes.

### Found in the forward path, and fixed

Each one has a test that fails on the code before the fix
(`tests/test_extract.py`, `tests/test_lost_text.py`).

1. **A judged gloss lost its braces.** `\ex. *\gll a {b c}` became three
   words, where linguexx sets two (measured).
2. **Text before a `\gll` was dropped.** The run warned that it was "kept
   as body text", but neither emitter writes `Body.text` when there are
   tiers. It is now the first column of the object line, with nothing
   beneath it. linguexx sets the gloss after free text, 1.65pt nearer
   than after a braced first word (measured), which is within what the
   estimated columns differ by. A judgment mark *and* text before a
   `\gll` glued the text to the first word; they are now kept apart.
3. **The text between `\ex.` and the first `\a.` was dropped, with no
   warning.** It is now `Example.head`, set on the number's row from the
   marker column to the block's edge. That is where linguexx sets it, and
   where it wraps it back to (measured on the `.odt`, the `.docx` and
   pdflatex). The first sub-example starts the next row.
   - The typed-line grammar (the Writer macro and the add-ins' core,
     together) accepts one line before `a.` as that text and builds the
     same row. *Untypeset* gives it back as that line. Fixtures:
     `UNTYPESET_CASES/head`, `head_glossed` and `REFUSE/head_then_b`. The
     macro suite's `check_head` measures that the head starts where "a."
     does, on the number's line.
4. **`\a.\label{x}\sublabel{y}` kept `\label{x}` in the item's text**,
   and the `.docx` showed it to the reader. Both names are now pulled and
   both resolve (`Body.more_labels`).

After these fixes `KNOWN_FORWARD_LOSSES` is empty. Every golden gained
`head` and `more_labels` (read: only those keys, plus `brackets` gaining
its head and `trailing-translation` its first column, without the false
warning).

### S8: files saved by Word itself (2026-10-04)

Run in Word on the web (Chromium driven over CDP). Word's own file was
taken from the add-in pane with `getFileAsync`.

- **Round 1, the converted document, unedited:** Word rewrote the file
  (12,190 bytes against 11,798) and kept every bookmark (`NumEx0`...), every
  `SEQ`/`REF` field and every `Lx*` style. `docx2linguexx` gives LaTeX
  identical to the converter's own file.
- **Round 2, an example typeset and a reference inserted through the Word
  add-in:** this found two add-in bugs, both fixed and re-run.
  - **Styles dropped.** Word on the web drops a `w:pStyle` or `w:rStyle`
    that the inserted package does not define, even when the document has
    the style. The add-in sent the definitions only to a document lacking
    them, so in a converted document a typeset example was "Normal"
    throughout, which no reader recognises as an example. It now always
    sends them. The document's own definition wins, so a style the user
    changed stays changed (measured).
  - **Wrong bookmark.** Pandoc's section bookmark ends after the section,
    so Word reports it around every number. The add-in took the first
    bookmark as each example's, which listed every example as (4) and
    pointed a new reference at the heading. An example's own bookmark is
    now one round exactly one number (`numbering.ownBookmarks`).

  After the fixes, the new example comes back as `ex:1`, the reference to
  it as `\ref{ex:1}`, and every old reference follows its example, though
  Word on the web still shows the old numbers.

### Tables the Writer macro built (2026-10-04)

The converter's round trips never saw the macro's tables. Those always
reserve a judgment column and are merged in Writer rather than spanned.
`check_reverse` in `tools/run_macro_test.py` now typesets every
typed-line fixture in Writer and saves it through LibreOffice's Word
export, the exporter `odt2linguexx` runs. It reads the result back and
requires the macro's own recorded parse of the lines, field for field.

- 38 of 39 match.
- The exception is listed in `REVERSE_KNOWN`: `SUB_CASES/sub_roman`,
  whose sub-examples are typed `i.`, `ii.` at the first level. linguexx
  letters the first level (`\Exalph` is document-wide, and the converter
  does not read it), so they come back as `a.`, `b.`, with a warning.
- The check fails if a known exception starts matching, or stops warning.
- CI runs it in the macro job, which already has pandoc.

### Typeset into a converted paper, in OnlyOffice (2026-10-04)

The Word test's second round, run automatically in Document Builder
(`tools/run_onlyoffice_test.mjs`, "converted"):

- The converter writes `tests/fixtures/converted-paper.tex` as a `.docx`.
- The plugin's own commands typeset an example ahead of the others and
  complete a bracketed reference to it, as its button pastes one.
- `docx2linguexx` then reads every example, label and reference back
  right: the new example as `ex:1`, the old ones renumbered.

Neither Word bug is present here:

- The plugin builds its tables with the builder API, so no styles are
  dropped.
- Its example list only takes a bookmark round a bare number, so the
  section's bookmark doesn't qualify.

One host finding: Document Builder 9.4's `UpdateAllFields` renumbers the
fields made since the document was opened, and none loaded from the file
-- the converter's or the plugin's own, saved and reopened alike. Trimming
the instruction's spaces changes nothing. The old examples go on showing
1, 2, 3 next to the new (1). The test accepts that state and says so if
it ever changes.

OnlyOffice Desktop does renumber them: the same insertion, done by
hand in the Desktop editor, saved the numbers as 1 to 4 and the
references as 2, 2, 3, 3. `docx2linguexx` read it back with four
examples and every reference on its example. So the stale numbers are
Document Builder's, which the suite runs, and not the editor's.

### Not done

- **Trees** come back as a comment holding the macro's bracket notation,
  with a warning. Translating that notation to forest is a question of
  its own: bare leaves and `,name=` options look as if they read
  differently in the two [inferred; not checked against forest].
- **Tier B.**
