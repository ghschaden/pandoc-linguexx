# pandoc-linguexx — plan

## Goal

A converter `linguexx2odt` that takes a LaTeX document containing
**linguexx**-formatted examples (default "lazy" syntax) and produces a
LibreOffice Writer file (`.odt`) in which every example is rendered
according to the **table method** described in
<http://gerhard.schaden.free.fr/blog/libreoffice-writer-for-linguists-and-linguistics/index.html>:

- the example number is a live LibreOffice *Number Range* field
  (`text:sequence`, name `NumEx`), wrapped in literal parentheses — so
  inserting/deleting/reordering examples in Writer renumbers everything;
- object-language words sit in individual table cells, gloss words in
  the cells directly beneath them (column-aligned);
- the free translation occupies a final row of merged cells;
- `\label`/`\ref` become `text:sequence-ref` cross-reference fields that
  track renumbering.

The rest of the document (sections, prose, emphasis, footnotes,
citations…) is converted by pandoc as usual.

**Explicitly NOT the ruby method.** Tables only.

## Verified facts (do not re-litigate; re-verify only if pandoc version changes)

Tested 2026-08-03 on pandoc 3.1.3:

1. `RawBlock`/`RawInline` with format `opendocument` pass through
   `pandoc → odt` **verbatim** into `content.xml`. A hand-built
   `table:table` with `text:sequence`, `text:sequence-ref`, and
   `table:number-columns-spanned` + `table:covered-table-cell` all
   survive intact.
2. All required namespaces (`table:`, `text:`, `style:`, `fo:`) are
   already declared on pandoc's `office:document-content` root.
3. pandoc's `content.xml` contains **no** `<text:sequence-decls>`
   element. LibreOffice may or may not tolerate an undeclared sequence
   (Spike S2 must check); the safe path is to inject
   `<text:sequence-decls><text:sequence-decl text:display-outline-level="0" text:name="NumEx"/></text:sequence-decls>`
   as the first child of `office:text` in a post-processing pass.

Consequence: **we never build pandoc `Table` AST nodes for examples.**
Each example becomes one opaque raw-opendocument block that we control
completely (column widths, merged cells, fields, styles). This
sidesteps every limitation of pandoc's table model.

## Architecture (decided)

Python package + CLI wrapper, four stages:

```
linguexx2odt input.tex -o output.odt

  [1] extract.py     scan input.tex, find linguexx example blocks
                     (\ex. … / \exg. … up to the terminating blank line,
                     including sub-example runs \a. \b. …),
                     parse them into an IR (dataclasses),
                     replace each block in the source with a unique
                     placeholder paragraph  ⟨⟨LINGUEXX-0007⟩⟩
                     (surrounded by blank lines so pandoc keeps it as
                     its own Para).

  [2] pandoc         residue.tex → AST JSON   (pandoc -f latex -t json)

  [3] inject.py      walk the JSON:
                     · Para == placeholder  →  RawBlock "opendocument"
                       built from the IR by emit_odt.py
                     · rewrite \ref/Link nodes whose target is an
                       example label → RawInline "opendocument"
                       text:sequence-ref
                     then JSON → output.odt  (pandoc -f json -t odt)

  [4] postprocess.py unzip output.odt, patch content.xml:
                     · inject text:sequence-decls (NumEx)
                     · inject automatic table/column styles referenced
                       by the raw tables (column widths; a raw block in
                       the body cannot carry automatic styles itself)
                     · optionally inject named character styles
                       (small caps for Leipzig abbreviations) into
                       styles.xml so the user can restyle in Writer
                     rezip (mind: `mimetype` entry first, STORED).
```

### Why not the alternatives (recorded so nobody revisits them blindly)

- **Pure Lua custom reader** (`pandoc -f linguexx.lua`): elegant and
  dependency-free, but (a) it cannot patch the zip / inject automatic
  styles, so a wrapper script is needed anyway; (b) Gerhard maintains
  Python far more readily than Lua. Rejected.
- **Panflute/Lua filter over `-f latex+raw_tex`**: pandoc's LaTeX
  reader destroys the *line structure* of the example (soft-break
  normalisation), and gloss alignment is defined by lines. Unfixable at
  the filter stage. Rejected.
- **pandoc `Table` AST** instead of raw blocks: weaker control over
  widths/merging/fields; raw blocks are strictly more powerful and
  already verified. Rejected.

### Rendering inline content inside cells

Cell contents may contain inline LaTeX (`\textit`, `\lpzg{…}`, judgment
stars, `\label`). Strategy, in order:

1. A small hand-rolled renderer for the common cases:
   `\lpzg{x}` → `<text:span text:style-name="LxLeipzig">x</text:span>`
   (small-caps character style; compound labels like `3sg.pst` are just
   printed as-is — no /E-expansion machinery here, that is a PDF
   accessibility concern, irrelevant to ODT),
   `\textit`/`\emph`, `\textbf`, `\textsc`, judgment prefix (`*`, `??`,
   `#`, `%`) kept as literal text glued to the first word cell,
   `\label{…}` swallowed (recorded in IR).
2. Fallback for anything else: shell out
   `pandoc -f latex -t opendocument` on the fragment and unwrap the
   outer `<text:p>`. Log a warning naming the construct.

### Layout (per example type)

**Policy: a table is emitted only where a gloss tier exists** (decided
per sub-example). Unglossed material becomes ordinary paragraphs —
matching the blog post, which uses tables only for glosses. Rationale:
paragraphs reflow, survive page-width changes, and are trivially
editable; every table carries the width-freezing cost, so pay it only
where column alignment buys something.

Plain example (`\ex. Sentence.`): a single paragraph, style
`LxExample` (hanging indent so wrapped lines align under the text
start): `(⟨NumEx field⟩)⟨tab⟩Sentence.` — reflows like normal prose.

Unglossed sub-examples: paragraphs, style `LxSubExample` (two-level
hanging indent): first sub-example paragraph carries the number field,
i.e. `(⟨NumEx⟩)⟨tab⟩a.⟨tab⟩text`, subsequent ones `⟨tab⟩b.⟨tab⟩text`.

Glossed example (`\exg.` / gloss tiers) — table:

| (N) | w1 | w2 | … |
|     | g1 | g2 | … |
|     | 'translation' — merged across word columns |

(Three-tier glosses: one extra row.)

Glossed sub-examples: table with extra letter column:

| (N) | a. | w1 | w2 | … |
|     |    | g1 | g2 | … |
|     |    | 'translation' merged |
|     | b. | … |

Mixed examples (some sub-examples glossed, some not): each sub-example
is emitted in its own mode (paragraph or table band); the number
field goes on the first sub-example whatever its mode. Indent and
letter-column geometry are kept visually consistent between the two
modes via the styles (same effective left edges). The e2e demo must
contain a mixed example.

Letters are literal text in v1 (LibreOffice number-range fields have no
sub-counters; the blog method has the same property). A `\ref` to a
sub-example label renders as field + literal letter: `(⟨seq-ref⟩a)`.
Conditional alternative — auto-numbered letters via list numbering in
the letter cells (`text:list` num-format "a", `text:continue-list`
across cells) with refs through the "Numbered Paragraphs" reference
type, so "(3a)" = sequence-ref + number-ref: only if Spike S5 passes.
Rationale: sub-letter churn after conversion is rare (the .tex is the
source of truth; reconversion renumbers everything), so this is
nice-to-have, gated on the UI-constructibility principle below.

Column widths and text width: all width computation is relative to a
single converter parameter `--text-width` (default 16 cm = A4 with
default margins; a later version may parse `geometry` from the
preamble). Object-word columns sized "optimal-ish" — approximation from
string lengths (font metrics unavailable;
`0.55em × max(len(word), len(gloss))` heuristic, clamped), number
column fixed (~1.1 cm). **Prefer relative widths** in the emitted XML
(`table:rel-width` in %, column widths as proportions, table ≤ 100 %):
if the user later changes page geometry in Writer, a relative-width
table rescales and, when squeezed, cells wrap *internally* — ugly but
alignment-preserving — whereas absolute-cm tables overflow the margin.
S3 tests both variants. Inherent limitation of the table method (as
opposed to the ruby method): tables do not reflow, so band split
points of long examples are frozen at conversion time; page-width
changes are handled by *reconverting* from the .tex with a new
`--text-width`. Post-conversion width changes on a document that has
diverged from the .tex require manual re-splitting (same as the blog's
manual procedure) — state this plainly in the README. Perfect widths
are impossible without font metrics; the user can drag columns
afterwards — document this too. All widths go into injected automatic
styles.

## Ground truth & references

- **linguexx syntax**: `../linguexx/` — `linguexx.sty`, `tests/`,
  the manual, `examples/`. Read-only. The *lazy* syntax is the target;
  `gb4e` and `legacy` syntax options are out of scope v1.
- **Blog post** (the spec for the output): URL above. Key points: NumEx
  number-range Arabic field; text-to-table with unequal columns; merged
  translation cells; cross-references via *Insert reference to →
  value/Category and Number*.
- **ODF spec** for `text:sequence` (`text:formula="ooow:NumEx+1"`,
  `style:num-format="1"`, `text:ref-name`), `text:sequence-ref`
  (`text:reference-format`: `value` prints the bare number — check
  whether "(3)"-style output should wrap literal parentheses around the
  field; decision: yes, literal parens, field carries only the number,
  matching the blog's manual procedure).
- **Oracle for field semantics**: generate a candidate ODT, open in
  LibreOffice. Headless checks below; final renumbering behaviour
  (insert an example in Writer, watch numbers shift) needs one manual
  test by Gerhard per milestone. If available, a hand-made
  `tests/reference/reference.odt` built manually per the blog post is
  the best oracle — diff our XML against it (`.odt` → `.fodt` via
  `soffice --convert-to fodt` makes diffing sane).

  Requested contents of `reference.odt` (Gerhard builds by hand in
  Writer):
  1. two plain numbered examples + one cross-reference in prose;
  2. one glossed example (table method, merged translation row);
  3. one sub-example paradigm (a./b.);
  4. **one very long glossed example**, split by hand the way overlong
     examples should be handled (stacked object/gloss row-pair bands:
     one table or two stacked tables? empty number cell or indent on
     the continuation band? where does the translation row go?). This
     *specifies* the future auto-split feature; v1 itself still only
     warns on overwidth. NB (Gerhard's point): the split *position* is
     relative to the page width used when building the file — treat
     the reference as specifying the **band pattern only**, never the
     break points. Break points are computed at conversion time from
     `--text-width`.
  5. *if constructible in the Writer UI*: sub-example letters as
     automatic list numbering (format "a.", continued across table
     cells) with one working cross-reference to a letter — see S5.

- **Design principle**: the converter only emits field constructs that
  a Writer user could have created through the UI. Anything more exotic
  makes the output unmaintainable for exactly the LibreOffice-using
  collaborators the conversion targets. Corollary: if Gerhard cannot
  build item 5 by hand, the converter does not fabricate it either.

## Phases

### Phase 0 — Spikes (½ day)

Each spike = a tiny script under `spikes/` + a dated finding appended
to `notes/findings.md`. Go/no-go gate.

- **S1 (done, see "Verified facts")**: raw opendocument passthrough.
  Re-run only if the pandoc version changes.
- **S2**: hand-assemble a minimal ODT (via the stage-3/4 mechanics)
  containing two NumEx fields and one sequence-ref.
  Check: `soffice --headless --convert-to pdf` succeeds; convert to
  `.fodt` and verify fields present; open the PDF and confirm "(1)",
  "(2)", ref "(1)" actually render (fields evaluate). Test **with and
  without** the injected `sequence-decls` to learn whether LibreOffice
  tolerates its absence.
- **S3**: same file + a 3-row table with merged translation row and
  injected automatic column-width styles. Confirm widths are honoured
  and the merge renders. Build both an absolute-cm and a relative-%
  variant; change the page margins on each (script the change in the
  .fodt) and confirm the relative variant rescales with internal cell
  wrapping while the absolute one overflows — this decides the
  emitter's default width mode.
- **S4**: pandoc JSON round-trip — confirm a placeholder Para is
  findable and replaceable in `-t json` output for a realistic .tex
  (placeholder must not get sucked into a neighbouring paragraph).
- **S5 (conditional — only if reference.odt item 5 exists)**:
  auto-numbered sub-example letters. Extract the list-numbering +
  cross-reference XML from Gerhard's hand-built version (`.fodt`),
  replicate it in generated output, verify: letters render a./b./c.,
  continue correctly across table cells and across sub-example blocks
  within one example (but restart at each new example), and the
  letter cross-reference survives headless render. If Gerhard could
  not build it in the UI, or replication is fragile: literal letters
  stand, decision closed.

### Phase 1 — Parser (`extract.py`) (1–2 days)

- IR as frozen dataclasses: `Example(number_label, judgments, subexamples | body)`,
  `SubExample(letter, body)`, `Body(tiers: list[list[Cell]], translation, label)` —
  exact shape to be settled during implementation, but keep it dumb and
  serialisable (JSON) for golden tests.
- Supported v1 surface (harvest canonical inputs from
  `../linguexx/tests/` and the manual):
  - `\ex.` plain examples, terminated by blank line
  - `\exg.` two- and three-tier glosses (`\\`-separated tiers,
    quoted translation line)
  - sub-examples `\a.` `\b.` … (one level; `\a.g.` glossed
    sub-examples if linguexx's lazy syntax has them — check the manual,
    do not guess)
  - judgments as body-initial tokens (`*`, `??`, `#`, `%`), including
    on sub-examples (`\b. *text`)
  - `\label{…}` anywhere in the example; `\lpzg{…}` in gloss tiers
  - optional-argument forms (`\ex[…]`): parse and **warn + degrade**
    (custom label printed literally), do not silently drop
- Hard rule: unknown constructs inside an example never crash the run —
  emit the fragment via the pandoc-fragment fallback and warn.
- pytest golden tests: `tests/cases/*.tex` → parsed IR JSON snapshots.

### Phase 2 — Emitter (`emit_odt.py`) (1–2 days)

- IR → opendocument XML per the layout policy above: styled
  *paragraphs* for unglossed examples/sub-examples, *tables* only for
  glossed material. Build XML
  with `xml.etree.ElementTree` or careful string templates — no third-
  party deps. Every generated table gets deterministic names
  (`LxEx1`, …) and style references (`LxExTable`, `LxExCol.A` …).
- Named paragraph styles `LxExample`, `LxSubExample` (hanging indents,
  tab stops aligned with the glossed tables' number/letter columns)
  injected into `styles.xml` alongside the character styles.
- Fields exactly as verified in S2.
- Named character styles: `LxLeipzig` (small caps), `LxTranslation`,
  `LxJudgment` — injected into `styles.xml` so they are user-visible
  styles, not one-off formatting.
- Golden tests: IR JSON → XML snapshots; plus a headless-render smoke
  test per case (skip gracefully if `soffice` absent).

### Phase 3 — Pipeline + CLI (1 day)

- `inject.py`: JSON walk; `\ref{…}`-to-example-label rewriting (pandoc
  parses `\ref` into a `Link` or leaves `RawInline` depending on
  version/extensions — handle both; check what 3.x actually emits for
  the input docs, record in notes).
- `postprocess.py`: zip surgery. Preserve `mimetype` as first, STORED
  entry; keep everything else byte-identical except `content.xml` /
  `styles.xml`.
- CLI `linguexx2odt in.tex [-o out.odt] [--text-width 16cm]
  [--keep-intermediates] [-v]`,
  `pyproject.toml`, entry point. stdlib + pandoc only; pytest as dev
  dep.
- End-to-end test: `tests/e2e/demo.tex` — ≥10 examples covering plain,
  glossed (2/3 tiers), sub-examples with judgments, `\lpzg`, labels,
  forward and backward `\ref` in prose, examples adjacent to sections,
  first and last position in document. Assert: pandoc exits 0, odt
  unzips, XML well-formed, expected number of `text:sequence` fields,
  headless PDF renders.

### Phase 4 — Polish

- Distribution: standard PyPI packaging (`pipx install linguexx2odt`),
  console entry point, pinned minimum pandoc version documented.
  Note (settled, do not revisit): the tool cannot be distributed as a
  pandoc-native extension (Lua reader/filter) **in any language** —
  filters run after the LaTeX reader has destroyed the line structure
  glosses depend on, and per-example column widths must be written
  into content.xml's automatic-styles section, which no reader,
  filter, template, or reference-doc can reach. The wrapper + zip
  post-processing is forced by the target, not by Python. Optional:
  request a listing on pandoc's third-party tools wiki page.

- README (usage; what to fix manually in Writer: column widths,
  overlong examples that exceed line width — the blog itself declares
  those a manual job; renumbering demo).
- Edge-case sweep: multiple consecutive examples; example immediately
  before/after an environment; `\ex.` inside `itemize`/footnotes →
  detect, warn, pass through untouched rather than corrupt.
- Manual acceptance by Gerhard: insert a new example in Writer between
  (1) and (2), confirm renumbering + refs update after F9/reload.

## Risks

| Risk | P | Mitigation |
|---|---|---|
| `text:sequence` attribute details wrong (formula syntax, ref format) | ~25 % | S2 oracle-driven; ask Gerhard for a hand-made reference.odt; diff via .fodt |
| LibreOffice rejects/ignores fields without sequence-decls | ~30 % (moot — we inject) | S2 tests both paths |
| Column-width heuristic looks bad | ~60 % cosmetically | Documented as user-adjustable; widths in one function, easy to tune |
| linguexx corner syntax not in v1 surface appears in real docs | ~50 % | warn-and-degrade policy; parser never crashes |
| pandoc `\ref` representation varies | ~20 % | handle Link and RawInline; pin minimum pandoc version in README |

Overall feasibility of the v1 scope: ~90 %. No identified blocker; the
one genuinely empirical question (field XML accepted and *evaluated* by
LibreOffice) is de-risked in S2 before any real investment.

## Out of scope (v1) — do not implement without asking

Ruby method; `\alt`/`\altg`; footnote examples; `gb4e`/`legacy` syntax
options; math inside examples; automatic line-breaking of overlong
examples; DOCX output; round-tripping ODT→LaTeX.
