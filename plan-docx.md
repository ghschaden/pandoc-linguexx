# pandoc-linguexx — assessment: .docx as a second target

**Verdict: feasible, and cheaper than the ODT target was.** Every capability
the tool depends on exists in OOXML and was tested here rather than assumed;
roughly half the existing code is already format-agnostic and moves over
untouched. The work is one new emitter and one new post-processor.

This is an assessment and a plan, not a commitment. Nothing below is built.

## Verified facts (tested 2026-09-25, pandoc 3.10.2, LibreOffice; do not re-litigate)

Each was run as a spike, the way `plan.md`'s own facts were. The `.md`
sources are throwaway; what matters is that the answers are measurements.

1. **Raw OOXML passes through pandoc's docx writer verbatim.** A
   ```` ```{=openxml} ```` block containing a `w:tbl` with `w:tblGrid`,
   `w:tcW` and field runs arrives in `word/document.xml` intact. This is the
   exact analogue of the `RawBlock "opendocument"` decision in `plan.md`,
   and it means the same architecture applies: an example is one opaque
   block this code controls completely.
2. **`SEQ` fields renumber.** Three examples were written with a cached
   value of `1` each; rendered, they read (1), (2), (3). The numbering is
   live, which is the whole premise of the tool.
3. **`REF` gives back just the number**, provided the bookmark wraps only
   the field and not the surrounding text. Bookmarking the paragraph
   returns "(1) ALPHA"; bookmarking the field returns "1". With the second
   form, "See (3) and (1)." came out of a document whose references were
   all cached as 99.
4. **Fixed column widths are honoured.** A three-column table asked for
   1.1 / 9.9 / 6.0 cm rendered with its columns at 0, **1.101** and
   **11.003** cm — 0.003 cm out over 11 cm. `w:tblLayout w:type="fixed"`
   is required; without it Word and Writer are free to re-fit.
5. **Raw OOXML works inline as well as as a block.** An inline `REF` field
   resolved inside an ordinary prose paragraph, with markdown emphasis
   beside it untouched — so cross-references in running text work the way
   `inject.py` already does them for ODT.
6. **A `w:pStyle` reference survives, but the style is not created.**
   `word/styles.xml` has no `LxExampleCell` after conversion; the document
   still renders, because the reference degrades quietly. So the styles
   have to be injected, exactly as `postprocess.inject_named_styles` does
   for ODT, and `styles.xml` is well-formed and patchable.
7. **The Writer macro needs no .docx counterpart — measured, not guessed.**
   A converted `.odt` re-saved as `.docx` by LibreOffice keeps the table and
   all five `Lx*` style names, and the macro reads it: *Untypeset* on that
   file returned `que Pierre est fatigué\exannot{[CP]}`, identical to the
   `.odt`, and re-typesetting inside the same `.docx` put the label back in
   its own cell at 75.00%. `LinguExx.bas` reads styles and cells, not the
   file format. This was listed below as an open question; it is answered
   and the risk is gone.
8. **OOXML cell margins have to be zeroed.** A table cell insets its content
   by 108 twips a side by default, which the width estimate does not know
   about, and the first sample wrapped every word. `w:tblCellMar` at zero
   fixes it. ODT needed no equivalent.
9. **The table must span the text block, with slack in a trailing filler
   column** — the same rule ODT already follows, and for a sharper reason
   here. A narrow table with declared widths rendered at 69% of them; giving
   it the full width and a filler column made every column exact.
10. **The estimator's font baseline does not transfer.** `_ADVANCE` is
    Liberation Serif at 12pt; pandoc's default `reference.docx` is another
    font at another size, and the widths come out too narrow by roughly a
    third. The arithmetic ports, the baseline does not: the docx emitter
    needs either its own measured table or a reference document whose body
    font it sets. Not hard, but it is real work and it is not in the
    "geometry is free" column.
11. **The OOXML this plan proposes is schema-valid.** The sample
    `spikes/s5_docx_sample.py` builds -- tables, fixed grids, `SEQ` and
    `REF` fields, bookmarks -- validates clean against ECMA-376
    **transitional** `wml.xsd`, checked with `tools/validate_docx.py`.
    That is most of the "will Word offer to repair it" risk answered
    without Word. Not all of it: Word enforces relationships, content types
    and part rules the schema does not describe, and has opinions besides.
    Note the flavour. Part 1's 5th edition ships **Strict**
    (`purl.oclc.org/ooxml/...`); pandoc and Word both write **Transitional**
    (`schemas.openxmlformats.org/.../2006/main`), and the Transitional
    schemas are in **Part 4** alone. Validating one against the other fails
    on the namespace before reaching anything real, which looks alarming
    and means nothing.
12. **A reader may not recalculate at all, so the emitter must write the
    cached values correct.** Fact 2 said `SEQ` renumbers, and it does — in
    LibreOffice. Opened in **OnlyOffice 9.4**, the same stale-cache file
    showed **(1) (1)** with both references still reading **99**: the
    numbering did not recalculate and `REF` did not resolve. Two real OOXML
    readers, opposite behaviour, and neither of them Word.

    So the cache is not a hint that gets corrected on open — it is what a
    reader sees. `spikes/s5_docx_sample.py` now writes correct values by
    default (`--stale` restores the old behaviour for probing a new reader),
    and with them LibreOffice still shows (1) (2) while the raw cached text
    is `1, 2, 1, 2`, so both kinds of reader agree.

    **Confirmed in the reader that exposed it**: with correct caches,
    OnlyOffice 9.4 reads (1) and (2) with matching references, and prints
    the same. It also opened the file without offering to repair it —
    a second independent OOXML implementation accepting the markup, which
    is worth as much as the schema validation and is evidence of a
    different kind.

    This does not weaken the target: the field stays live, so inserting an
    example and refreshing still renumbers, which is the feature. It removes
    a dependency on the reader for the document merely being *correct when
    opened*. Phase 2 must compute every number and every reference at build
    time — which it can, since `inject.py` already resolves every label to
    an example index for ODT.
13. **Editing renumbers, and the references follow — the feature works.**
    A copy of the first example pasted above the original, then a refresh,
    in OnlyOffice 9.4: the three examples read (1) (2) (3) and the
    cross-references read **(2) and (3)**.

    Read that second part carefully, because it is the interesting half.
    The bookmarks stayed on the ORIGINAL examples rather than being
    duplicated onto the pasted copy, so `exone` — now example 2 — is what
    its reference resolved to. A duplicated bookmark would have sent the
    reference to the copy, or made it ambiguous, and that was the named
    risk in this test. It did not happen.

    Not Word, so not conclusive for Word. But this is the feature the whole
    target exists for, and it works in a real implementation that is not
    the one the design was developed against.

Consequence: **the ODT architecture transfers whole.** The differences are
smaller than the similarities, and two of them are in docx's favour.

## What moves over unchanged

About half the package, and the half that took the longest to get right:

- `extract.py`, `ir.py`, `latexutil.py` — the parser and the IR know
  nothing about ODF. `Body`, `Item`, `Tier`, `Brackets`, the placeholder
  machinery and every golden test in `tests/golden/` are target-agnostic.
- The **geometry**: `Grid`, `_bands`, `_word_widths`, `_ADVANCE` and
  `Layout`. Band packing and width estimation are arithmetic over cm and do
  not care what XML carries the result. `1 cm = 566.93 dxa` is the only new
  arithmetic.
- `cli.py`, minus a `--to` flag and the choice of emitter.
- The linguexx-tracking work: `scan_brackets`, `_scan_unsupported`, and the
  "What it does not" table, which becomes a table about both targets.

## What is new

- **`emit_docx.py`** — the bulk. The ODT emitter is 607 lines and this is
  its counterpart, not a variation on it: different element names, and a
  different idiom for merging (`w:gridSpan` on the cell rather than
  `table:number-columns-spanned` plus covered cells).
- **`postprocess_docx.py`** — inject the paragraph and character styles into
  `word/styles.xml`, and rezip. Smaller than the ODT one: no
  `text:sequence-decls` (a `SEQ` field declares itself by being used), and
  no automatic column styles (OOXML carries widths inline in `w:tcW`).
- **A target switch** in `inject.py`, which currently hardcodes
  `"opendocument"` in two places.

## Phases

### Phase 1 — the seam — DONE

`measure.py` holds the arithmetic: `_ADVANCE`, the width functions, `Grid`
and `Plan`. `emit_base.py` holds `BaseEmitter` — `prepare()`, `_bands()`,
`_lead_widths()`, `_word_widths()` — plus the `TARGETS` registry and
`emitter_for()`. `emit_odt.Emitter` subclasses it, keeps the XML and its
`auto_styles` (ODF-only: OOXML carries a column's width inline in the
cell), and registers itself as `odt`. `emit_odt.py` went from 671 lines to
379. `cli.py` gained `--to`, with one choice.

The suite reported the same 203 tests throughout, which is what a seam
should cost. `tests/test_targets.py` adds four for the seam itself, one of
which is the invariant worth keeping: **no markup vocabulary in the shared
half**. An emitter reaching for `table:` in format-agnostic code breaks
nothing today and breaks the second target on the day it is written.

Both new tests needed a second attempt, and both failures are the same
shape — a check that could not fail. The leak test first looked for
`'"table:'` and sailed straight past `'"<table:table-cell/>"'`; widened, it
then flagged the module docstrings, which discuss `table:` and `w:`
precisely to promise the code contains neither. It now blanks docstrings
with `ast` before reading, and was mutated in both directions afterwards.

### Phase 2 — numbers and references — DONE

`emit_docx.DocxEmitter`, registered as `docx`: one example as a `w:tbl`,
the number a `SEQ` field bookmarked around the field alone, and `REF`
fields inline for `\ref` and `\pref`. Every cached value written correct,
per fact 12. `--to docx` on the CLI; no post-processing, because OOXML
needs none yet — a `SEQ` field declares itself and a column's width lives
in the cell. Phase 4 adds the styles.

`inject.py` stopped hardcoding `opendocument`: it asks the emitter for
`RAW_FORMAT` and for `reference()`, since what a cross-reference *is* — a
field, an anchor, a span — is the format's business and where it goes is
the inject pass's.

**The two targets render the same document identically**, measured through
LibreOffice: `(1) A first example. (2) A second example. Prose referring to
(1) and (2), and bare 1.` The output is schema-valid.

Six tests in `tests/test_docx.py`, mutation-tested: stale caches and a
bookmark widened to swallow the example text are both caught. A glossed
example warns that the grid is Phase 3 rather than laying it out wrong —
the edge is stated, not discovered.

One trap worth recording, because it cost eighteen red tests and will
recur. `RAW_FORMAT: str = ""` on a `@dataclass` is a **field**, not a class
attribute: every instance takes the base class's default, the subclass's
value never arrives, and every `RawBlock` goes out tagged `""`. It is a
`ClassVar` now, and a test pins the two values.

### Phase 3 — the grid — DONE

Gloss tiers, judgment and marker columns, bands, `\exannot`, sub-examples.
`BaseEmitter.plan_table()` now holds the arithmetic both targets shared —
lead widths, the bands, the annotation column, the filler — and returns a
`TablePlan` of measurements with no markup in it. `emit_odt` went from
computing that to rendering it; `emit_docx` renders the same plan as OOXML.

**Measured, not assumed**: every gloss word starts at exactly the x of the
object word above it, and the relative geometry matches the ODT target
column for column (`a.` at 40/41, the judged text at 64, `judged` at 78).

The merging idiom was the predicted difficulty and it was real. ODF spans a
cell and emits a `covered-table-cell` for each column swallowed, so a row
has one element per column; OOXML spans with `w:gridSpan` and emits nothing
for the columns taken, so a row is complete when its **spans** total the
grid. A test asserts exactly that, on a paradigm of unequal tiers — which
is what produces spans at all, since with equal tiers every span is 1 and
the test cannot fail.

Two defects the geometry found, neither visible in the markup:

- **Every long word wrapped inside its column.** The widths come from
  `_ADVANCE` (Liberation Serif, 12pt) and pandoc's `reference.docx` draws
  in neither, so a column correct for a font the document does not use is
  not a correct column. Fact 10, arriving early: each run now names the
  face and size the estimate targets. Phase 4 should replace that direct
  formatting with a reference document.
- **The judgment mark floated**, ten points from the text it judges,
  because its column was left-aligned. linguexx `\llap`s the mark and the
  ODT target gives it a right-aligned style; the OOXML cell now does too.

Inline content goes through `InlineRenderer.runs()` rather than `esc()`,
which had been putting `\lpzg{3sg}` in the document as eleven literal
characters. Small capitals are direct formatting for now — a named
character style is Phase 4 — but they had to be drawn in Phase 3 regardless,
because the estimator measured them.

### Phase 4 — styles, the font baseline, and polish (1 day)
Inject the styles so a Word user can restyle from the sidebar, as a Writer
user can. Small caps for `\lpzg`. **Settle the font baseline** (fact 10):
either measure a second `_ADVANCE` table, or ship a reference document that
sets the body font to the one `_ADVANCE` already describes. The second is
much less work and keeps one table honest instead of two.

The space above and below an example is a spacer row with a styled height in
ODT; check whether `w:spacing` on the table's paragraphs is the better idiom
in OOXML before porting the spacer rows.

### Phase 5 — say so (½ day)
README, `docs/guide-fr.md`, CLAUDE.md, and the "What it does not" table,
which now has two columns' worth of truth to tell.

**Total: 4–6 focused days**, against the two weeks the ODT target took,
because the IR, the geometry and the test method already exist.

## Risks, and what would settle each

- **Word itself is untested.** Everything above was measured with
  LibreOffice, which is what is installed here. `SEQ` and `REF` are Word's
  own mechanisms and are not in doubt, but Word updates fields on open,
  print or F9 depending on version and setting, where Writer updates on
  load — so a document may open showing the cached numbers. Settle it by
  opening one built document in real Word before Phase 3, and if the
  caches show, write them correct at build time rather than relying on the
  update. That is cheap insurance and worth doing anyway.
- **Validity.** LibreOffice is forgiving; Word shows a repair prompt for
  malformed OOXML, and a repair prompt is worse than a wrong width. No
  schema validator was used here. Settle with `python-docx` or an OOXML
  validator in CI, or at minimum one manual open in Word per phase.
- **Two targets, one "What it does not" table.** The tracking work of
  `plan-linguexx-1.3.md` is the warning: a second target doubles the
  surface on which a linguexx change can be silently ignored. Whatever the
  table becomes, `_scan_unsupported` must cover both.

## Out of scope — do not implement without asking

- **Dropping the ODT target, or making docx the default.** ODT is the one
  with a macro, a reference document and a French manual.
- **A shared "office XML" abstraction** over the two emitters. They share
  arithmetic, not markup; an abstraction over `table:table-cell` and
  `w:tc` would be a third thing to maintain and would make both harder to
  read. Two emitters over one IR is the design.
- **.doc, RTF, or Google Docs.** Different question, different answer.
