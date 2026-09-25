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

### Phase 1 — the seam (½ day)
Split `Emitter` into what is shared and what is ODF. Introduce the target
as a parameter, with ODT as the only value, and change nothing else. The
suite must report the same 203 tests, because nothing has happened yet.
Doing this first keeps the diff of Phase 2 readable as "a new backend"
rather than "a refactor with a backend inside it".

### Phase 2 — numbers and references (1 day)
`emit_docx.py` emitting one example as a `w:tbl`, with `SEQ` fields and
bookmarks, and `inject.py` writing `REF` fields inline. No bands, no
judgments, no glosses — a plain `\ex.` and a `\ref` to it. The end-to-end
test is the one that matters and it exists already in the ODT form: render
to PDF, read the numbers back, and check they renumber when an example is
inserted.

### Phase 3 — the grid (1–2 days)
Gloss tiers, merged cells, judgment and marker columns, bands, `\exannot`.
All the decisions are made; this is transcription into different element
names, checked against the same rendered-geometry assertions the ODT target
already has. Expect the merging idiom to be the only real thinking:
`w:gridSpan` and `w:vMerge` do not behave like covered cells.

### Phase 4 — styles and polish (½–1 day)
Inject the styles so a Word user can restyle from the sidebar, as a Writer
user can. Small caps for `\lpzg`. The space above and below an example,
which in ODT is a spacer row with a styled height — check whether
`w:spacing` on the table's paragraphs is the better idiom in OOXML rather
than porting the spacer rows.

### Phase 5 — say so (½ day)
README, `docs/guide-fr.md`, CLAUDE.md, and the "What it does not" table,
which now has two columns' worth of truth to tell.

**Total: 3–5 focused days**, against the two weeks the ODT target took,
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
- **The Writer macro has no docx counterpart**, and should not get one:
  `LinguExx.bas` is Basic in a Writer document. An open question worth an
  experiment rather than an assumption — if the docx carries the same style
  names, *Untypeset* may already work on a .docx opened in Writer, since
  the macro reads styles and cells, not the file format. Try it before
  deciding anything.
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
