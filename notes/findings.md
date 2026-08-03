# findings

Dated, append-only. Each entry records what was *measured*, not what was
expected. Spike scripts live in `spikes/`; re-run them with
`python3 spikes/sN_*.py` from the project root.

---

## 2026-08-03 — Phase 0 environment

| tool | version |
|---|---|
| pandoc | 3.6.1 (plan's "verified facts" were taken on 3.1.3 → S1 re-run) |
| LibreOffice | 26.2.4.2 |
| Python | 3.14.6 |
| pytest | 9.0.3 |

---

## 2026-08-03 — S1 raw-opendocument passthrough (PASS, re-verified on 3.6.1)

`spikes/s1_passthrough.py`

- Via the **JSON reader** (`pandoc -f json -t odt`) — the path the real
  pipeline uses — a `RawBlock ("opendocument", …)` reaches `content.xml`
  **byte-for-byte**. Verified for `text:sequence`, `text:sequence-ref`,
  and `table:table` with `table:number-columns-spanned` +
  `table:covered-table-cell`.
- Via the **markdown reader** the raw block is *not* byte-exact: literal
  TAB characters inside the raw string are expanded to spaces
  (`--tab-stop`). Harmless for us (we never go through markdown), but it
  means spikes must test the JSON path, not a convenient `.md`.
  Emitter rule anyway: never put a literal TAB in emitted XML, use
  `<text:tab/>`.
- All namespaces the emitter needs (`table:`, `text:`, `style:`, `fo:`,
  `office:`) are declared on pandoc's `office:document-content` root.
- pandoc's `content.xml` still contains **no** `<text:sequence-decls>`.

**Consequence:** plan's stage [3] (JSON → odt with raw blocks) is sound
on 3.6.1. No change.

---

## 2026-08-03 — S2 NumEx fields evaluate (PASS, both variants)

`spikes/s2_fields.py`

Built two ODTs whose fields carry a deliberately **wrong cached value**
(`99`), so a correct PDF can only come from real evaluation.

| variant | fields survive LO round-trip | PDF shows 1 / 2 / refs |
|---|---|---|
| with injected `<text:sequence-decls>` | yes | yes |
| without any sequence-decls | yes | yes |

- LibreOffice **recomputes** `text:formula="ooow:NumEx+1"` on load: the
  `99`s are gone from the PDF, replaced by 1 and 2.
- `text:sequence-ref text:reference-format="value"` resolves, **including
  a forward reference** (ref to an example later in the document).
- LibreOffice tolerates a missing `sequence-decls` and re-adds it on
  save. We inject it anyway — it costs nothing and matches what
  LibreOffice itself writes.

**Risk "LibreOffice rejects fields without sequence-decls" (~30 %) is
closed: it does not.**

---

## 2026-08-03 — S3 table widths (PASS; the plan's abs-vs-rel question was the wrong question)

`spikes/s3_table.py`. A 12-word glossed table built to 16.34 cm, then the
page squeezed from A4/2 cm margins (17 cm text) to A4/5 cm (11 cm text).
Rightmost ink measured with `pdftotext -bbox`.

| mode | table props | 2 cm margins | 5 cm margins |
|---|---|---|---|
| `abs` | `style:width` + `table:align="margins"` | inside (18.58 ≤ 19.00) | **inside** (15.94 ≤ 16.00) |
| `absleft` | `style:width` + `table:align="left"` | inside (17.98) | **OVERFLOWS** (20.98 vs 16.00 — off the paper) |
| `rel` | `style:rel-width="100%"` + `rel-column-width` | inside | inside |

**The deciding attribute is `table:align="margins"`, not the choice of
absolute vs relative column widths.** With it, even an absolute-cm table
rescales to the current text width; without it, the table runs off the
page.

When squeezed, cells wrap **internally** and column alignment is
preserved — no clipping, no lost content:

```
(1) est es un ejemp glosa bastant larg par llena la line enter
    o             lo    do     e      o a r             a a
    this is a exam glosse rather longto fill the who line
                  ple d                                 le
```

Ugly, exactly as the plan predicted, but never wrong.

**Decision (emitter):** mirror what LibreOffice itself writes in
`reference.odt` — `table:align="margins"` on the table style, and **both**
`style:column-width` (cm) and `style:rel-column-width` (`N*`) on every
column style. Absolute widths give the intended look on the build
geometry; the relative ones plus `align="margins"` make it degrade
gracefully. Cell style `fo:padding="0cm" fo:border="none"`.

---

## 2026-08-03 — S4 placeholder round-trip (PASS, with a rule for extract.py)

`spikes/s4_placeholder.py`. Nine placeholders in deliberately awkward
positions, both a Unicode (`⟨⟨LINGUEXX-0007⟩⟩`) and an ASCII
(`LINGUEXXPLACEHOLDER0007ENDLINGUEXX`) spelling.

- **9/9 survive the LaTeX reader intact** in both spellings; the Unicode
  form is not mangled, and an unknown `\usepackage{linguexx}` is ignored
  without complaint. Unicode form adopted (unmistakable in a `.tex`, and
  cannot collide with real text).
- **5/9 came back as their own `Para`.** The four that did not are
  exactly the four constructed to fail, and they split into two classes:
  - *self-inflicted* — placeholder written without a surrounding blank
    line, or mid-sentence. **Rule: extract.py must always emit the
    placeholder as its own paragraph, inserting blank lines on both
    sides.** Then it is always its own `Para`.
  - *genuinely nested* — inside `itemize` (block depth 1) and inside a
    `\footnote`. These are the plan's Phase-4 edge cases: detect, warn,
    and leave the LaTeX untouched rather than corrupt it.

### `\ref` representation on pandoc 3.6.1

`\ref{ex:first}` becomes a **`Link`**, never a `RawInline`:

```json
{"t":"Link","c":[["",[],[["reference-type","ref"],["reference","ex:first"]]],
                 [{"t":"Str","c":"[ex:first]"}],["#ex:first",""]]}
```

Clean rewrite target: match on the `reference` attribute. inject.py will
still handle a `RawInline "latex" "\\ref{…}"` defensively, since older
pandocs and `+raw_tex` can produce it.

---

## 2026-08-03 — reference.odt read out (the output spec)

`tests/reference/reference.fodt` (from Gerhard's hand-built file). This
is the oracle; where it and `plan.md` disagree, **it wins**.

### Field XML — confirmed exactly as planned

```xml
(<text:sequence text:ref-name="refNumEx0" text:name="NumEx"
   text:formula="ooow:NumEx+1" style:num-format="1">1</text:sequence>)
(<text:sequence-ref text:reference-format="value"
   text:ref-name="refNumEx0">1</text:sequence-ref>)
```

Parentheses are **literal text outside the field**; the field carries the
bare number. Sub-example refs are `(` + field + literal `b` + `)`.

### Correction 1 — plain examples are NOT tables

`plan.md` "Table layout" shows a plain `\ex.` as a two-cell table.
Gerhard's file uses a **paragraph with tabs**:

```
(1)<tab><tab>This is a first example.
```

and the sub-example paradigm likewise, one paragraph per sub-example:

```
(2)<tab><tab>a.<tab>*First subexample – ungrammatical.
   <tab><tab>b.<tab> Second subexample.
```

**Rule adopted here, then SUPERSEDED** — see the 2026-08-03 entry "ODF tab
stops cannot address the outdented region" at the end of this file. It was
implemented as written (no gloss tier → paragraphs with named styles
`LxExample`/`LxExampleSub` carrying a hanging indent and explicit tab
stops), measured, and found unable to hold R-JUDG. Every example is now a
table. This section is kept because it is still an accurate *description
of the reference document*; it is simply not what the converter does.

### Correction 2 — judgment marks must hang left

Gerhard's own prose in the reference: *"Notice that in (2b), alignment
should not be with the judgment."* He faked it by hand, padding the
unjudged line with two spaces (`<text:s/>`). Confirmed as a real package
invariant by `../linguexx/tests/judgment-align.tex`: *"the sentinel that
follows [the leading word] must land at exactly the same x — unless the
judgment mark wrongly consumed horizontal space in the text block."*

**Requirement R-JUDG:** the judgment mark occupies no horizontal space in
the text block. Table mode: its own narrow column left of the first word
column. Paragraph mode: a right-aligned tab stop immediately before the
text tab stop, so the mark hangs into the gap.

### Correction 3 — the long-example band pattern

Reference item 4 is **one table with a fine 22-column grid**, not stacked
tables. Bands are row *pairs* (object row, gloss row) sharing one column
grid; each word occupies 1–5 grid columns via
`table:number-columns-spanned` + `table:covered-table-cell`. The number
cell appears only in the first band; continuation bands leave it empty.
Column 2 is a narrow empty spacer (the indent) present in every band. The
translation is the **last row**, spanning all 20 word columns.

Per the plan this specifies the *future* auto-split feature only; **v1
still just warns on overwidth**. Recorded so the shape is not
re-litigated. Note the fine grid is what makes bands with different word
counts co-exist in one table.

### Other facts read off the reference

- Table style: `style:width="17cm"` + `table:align="margins"`; page is
  A4, 2 cm margins → text width **17 cm**. `plan.md`'s default
  `--text-width 16cm` comes from pandoc's Letter/1in default, not from
  Gerhard's geometry. **Default changed to 17cm** (A4, 2 cm margins).
- Leipzig glosses are `fo:font-variant="small-caps"` character styles
  (`T4` in the reference) → our named style `LxLeipzig`.
- Cell style: `fo:padding="0cm" fo:border="none"`.
- Column styles carry **both** `style:column-width` and
  `style:rel-column-width` — LibreOffice always writes both.

### S5 — CLOSED, negative

Reference item 5 (sub-example letters as automatic list numbering with a
working cross-reference) **is absent** from the file Gerhard built; the
letters are literal text. By the plan's own design principle — *"if
Gerhard cannot build item 5 by hand, the converter does not fabricate it
either"* — **sub-example letters are literal text. Decision closed.**

---

## 2026-08-03 — linguexx lazy syntax, read from source (corrects plan Phase 1)

Read from `../linguexx/tests/linguexx-test.tex`, `gloss.tex`,
`judgment-align.tex`, `termination.tex`, `straysub.tex`.

`plan.md` Phase 1 lists the v1 surface as "`\ex.` … `\exg.` two- and
three-tier glosses". That is incomplete and partly mis-stated. The actual
lazy surface:

| construct | meaning | v1 |
|---|---|---|
| `\ex.` | plain example | yes |
| `\a.` `\b.` `\c.` … | sub-examples; a *repeated* `\a.` opens a deeper (roman) level | yes, one level; deeper → warn |
| `\gll … \\ … \\` | two-tier gloss | yes |
| `\glll … \\ … \\ … \\` | three-tier gloss | yes |
| `\gl … \endgl` | n-tier gloss | yes |
| `\glt ‘…’` | free translation | yes |
| `\exg.` / `\ag.` / `\bg.` | shorthand: example + `\gll` in one | yes |
| `{braced group}` in a tier | several words = **one** column | yes |
| unequal tiers | shorter tier → empty cells | yes |
| `*` `??` `?*` `\#` `\%` prefix, `\jdg{…}` | judgments | yes (R-JUDG) |
| `\label` / `\sublabel` | targets | yes |
| `\ref` `\pref` | reference | yes |
| `\lpzg{…}` | Leipzig abbreviation | yes |
| `\z.` (and `\z.\z.`) | early termination / level pop | yes — affects where the example *ends* |
| `\refrange` `\prefrange` | ranged refs | warn + degrade |
| `\Last` `\pLast` `\LLast` `\Next` | relative refs | warn + degrade |
| `\exsource{…}` | flush-right source | warn + degrade (render inline at end) |
| `\ex.[(4′)]` | custom label, counter **not** stepped | warn + degrade, per plan |
| `\altn` `\altg`, `exe`/`xlist`, footnote examples | — | out of scope (plan) |

**Termination is not just "blank line".** An example ends at: a blank
line, `\z.`, an environment boundary (`\end{minipage}`), or a closing
brace of the enclosing group. The parser must implement all four or it
will swallow following prose. `tests/termination.tex` is the ready-made
golden case.

A stray `\a.` with no open example is a *package error* by design
(`straysub.tex`) — the parser should warn, not crash, and leave it alone.

---

## 2026-08-03 — ODF tab stops cannot address the outdented region (reverses part of Correction 1)

Measured, not reasoned: a paragraph with
`fo:margin-left="1.8cm" fo:text-indent="-1.8cm"` and
`<style:tab-stop style:position="1.1cm"/>` puts the tabbed content at
**2.9 cm** from the page margin, not 1.1 cm.

**`style:tab-stop style:position` is measured from the paragraph's own
left indent, not from the page margin.** With a hanging indent the whole
outdented region — exactly where the example number and the sub-example
letter live — is therefore unreachable: it would need a stop at a
negative position, which ODF does not allow.

Consequences, in the order they bite:

1. A sub-example paradigm cannot be laid out as paragraphs: the letters
   `b.`, `c.` (whose lines carry no number) have no stop to land on and
   collapse onto the text position.
2. A judgment mark cannot be hung to the left of the text, because that
   also needs a stop inside the outdented region. Measured on the first
   paragraph-based build: `*First` and `Second` started 0.65 cm apart —
   a direct violation of R-JUDG.

The alternative that does work in paragraphs is the one Gerhard used by
hand in `reference.odt`: no indent at all, plain tab stops from the page
margin — at the cost that a wrapped example returns to the left margin,
running underneath its own number, and that judgment alignment has to be
faked with padding spaces (which is what he did).

**Decision: every example is a table**, i.e. back to plan.md's original
"Table layout" section. Correction 1 stands as a description of what the
reference document does, but is *not* adopted:

- number, sub-example letter and judgment each get their own column, so
  alignment is structural rather than a function of tab arithmetic;
- long examples wrap inside their text cell, correctly indented;
- one code path instead of two.

The judgment column is decided **per document, not per example**: it is
emitted for every example or for none. `judgment-align.tex` pins the
alignment of a judged example against an unjudged one — i.e. *across*
examples — and a per-example column made `(1)` and `(2)` start 0.45 cm
apart. Both directions are now pinned by
`tests/test_e2e.py::test_judgment_marks_do_not_shift_the_text`, which was
mutation-checked: reverting the column decision to per-example makes it
fail.

### Filler column

With `table:align="margins"` LibreOffice stretches the table across the
whole text block, spreading the words of a short gloss right across the
page. A trailing **filler column** absorbing the slack fixes it — which
is what the reference document effectively has in its 12.5 cm last
column. Word columns then keep their content-based widths.

### The cached field value is not evidence

`test_numbers_are_evaluated_not_echoed` passed even with
`text:formula` deleted, because we emit a *correct* cached value inside
each `text:sequence`. It therefore proved nothing about the field being
live. `test_numbers_come_from_the_formula_not_the_cached_value` corrupts
every cached value to 99 before rendering; deleting the formula now fails
it. (We still emit the correct cached value: a consumer that does not
evaluate fields should show sensible numbers.)

---

## 2026-08-03 — auto-split of overlong examples (was out of scope in v1; built on request)

Manual acceptance passed first: inserting an example in Writer renumbers
the document and updates the cross-references, so the field construction
is confirmed end to end. Auto-split then went in.

### The grid is the union of the bands' boundaries

A band is one horizontal slice of an example — its tier rows emitted
together, the next band starting again at the left edge. All bands live in
**one** table, so they share one column grid, and bands of different word
counts have their boundaries in different places. The grid must therefore
be the **union of every band's cumulative word boundaries**, with each
word spanning the columns it covers.

`reference.odt` corroborates this independently: item 4 is a 13-word band
over a 9-word band and comes out with a **22-column grid** full of
`table:number-columns-spanned` + `table:covered-table-cell`. That is what
merging cells by hand yields, and it is what the union rule produces. The
fine grid is not an artefact of hand-building — it is the only way two
differently-broken bands can co-exist in one table.

Implemented as `emit_odt.Grid`. Bands are chosen greedily against
`--text-width`; a word wider than the whole text block gets a band to
itself and a warning, rather than being merged into a neighbour.

### Decisions

- Word widths are computed **once for the whole example** and shared by
  every body, so a sub-example paradigm keeps its columns aligned across
  `a.`/`b.`; banding then partitions that shared width vector by word
  index, which is what lets bodies of different lengths sit in one grid.
- The number cell is filled on the **first row of the first band** only;
  continuation bands leave number, letter and judgment empty — as in the
  reference.
- The translation is one row at the end, after every band.
- `--no-split` restores the previous behaviour (squeeze into one band).
  Either way the *declared* table width is clamped to the text block, so
  `table:align="margins"` never has to rescue us.

### Verification

Measured on the rendered PDF, not asserted from the XML: in demo.tex's
17-word example, all 14 words of band 1 and all 3 of band 2 sit at exactly
the same x as their glosses, and band 2 restarts at the band-1 left edge
(3.55 cm).

Four mutations were checked, each killed by a test:

| mutation | killed by |
|---|---|
| grid built from the first band only | `test_two_bands_share_a_union_grid` |
| every word spans exactly one column | `test_overlong_example_is_split_into_aligned_bands` |
| number repeated on every band | same |
| splitting never happens | same |

---

## 2026-08-03 — the judgment column is carved out, not inserted (measured against linguexx)

Compiled `../linguexx/tests/_preamble` with pdflatex on a probe of a main
example, a judged main example and a judged/unjudged sub-example pair, and
measured the PDF:

```
(1)    ALPHA           main text  3.72
(2)  * ALPHA           mark 3.48, text still 3.72
(3)    a. * ALPHA      letter 3.72, mark 4.32, sub text 4.57
       b.   ALPHA      letter 3.72,            sub text 4.57
```

Two facts, neither of them guessable:

1. **A sub-example letter sits at exactly the x where a main example's
   text begins** (both 3.72 cm). The letter column and the main text
   column share a left edge.
2. The judgment mark consumes no horizontal space in the text block — it
   hangs to the *left* of the text, in the gap belonging to the column
   before it.

Our first judgment column satisfied (2) within an example but broke (1):
inserting a column between the number and the text pushed a main
example's text right (3.55 cm) while leaving the letters where they were
(3.10 cm).

**Fix:** the judgment column is *carved out of the column to its left*
rather than inserted after it — out of the number column for a main
example, out of the letter column for a sub-example. The total width
before the text is therefore unchanged by the presence of judgments:

```
main:  [number - judgment][judgment][text …]   text at number_cm
sub:   [number][letter - judgment][judgment][text …]   letter at number_cm
```

Measured after the fix: main text and both letters at 3.43 cm, mark at
3.22 cm, sub text at 4.47 cm — linguexx's structure exactly.

Column widths for number, letter and judgment are now computed in
`Emitter.prepare` from what the document actually contains, so `(100)` and
`viii.` fit and a lone `*` does not reserve room for `\%\#`.

Pinned by `test_sub_example_letters_align_with_main_example_text`; both
inserting the column instead of carving it, and left-aligning the mark
inside its column, fail it.
