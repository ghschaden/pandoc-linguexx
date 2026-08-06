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

## 2026-08-06 — table spacing cannot be a named style; spacer rows can (measured)

The space above and below an example was `fo:margin-top`/`fo:margin-bottom`
on the per-example automatic table style `LxExTable{N}` — the one place in
the output that was direct formatting rather than a named style, so it was
the one thing a Writer user could not restyle for the whole document.

**The obvious fix does not work.** A named table style in `office:styles`
with the automatic style inheriting from it is silently ignored:
LibreOffice does not resolve `style:parent-style-name` on
`style:family="table"`.

Measured on demo.odt (12 examples), rendered headlessly, page count:

| variant | pages |
|---|---|
| margins on the automatic style, 0.18cm (the old output) | 2 |
| margins on the automatic style, 1.60cm | 3 |
| margins moved to a named parent table style, 1.60cm | 1 |
| margins moved to a named parent table style, 0.18cm | 1 |
| no margins anywhere | 1 |

The last three are identical, so the named table style contributed
nothing. This is also why LibreOffice's own UI offers table spacing only
in Table Properties, per table: there is no style mechanism behind it.

**What does work:** an empty full-width spacer row at the top and bottom
of each example table, whose height is a *fixed* `fo:line-height` on a
named **paragraph** style. Fixed line spacing clamps the empty paragraph
with no font-size floor, so the height is exact and linear — measured
against a 0cm baseline:

| line-height | rendered | expected |
|---|---|---|
| 0.18cm | +5.1pt | 5.10pt |
| 0.36cm | +10.2pt | 10.20pt |
| 1.00cm | +28.3pt | 28.35pt |

Three styles are emitted. `LxExampleSpace` carries the height;
`LxExampleSpaceAbove` and `LxExampleSpaceBelow` declare nothing and
inherit it. Editing the parent therefore moves both gaps, and giving a
child a height of its own breaks that side away — which is exactly the
`--example-spacing` / `--space-above` / `--space-below` split, expressed
in styles instead of in flags.

Verified end to end on tests/e2e/demo.tex, measuring the gap above and
below example (1) in the rendered PDF:

```
                                          above   below
--example-spacing 0    (baseline)           6.5     4.8
--example-spacing 0.18                     11.6     9.9   (+5.1 / +5.1)
--example-spacing 0.60                     23.5    21.8  (+17.0 / +17.0)
--space-above 0.60 --space-below 0         23.5     4.8  (+17.0 /  +0.0)
--space-above 0 --space-below 0.60          6.5    21.8   (+0.0 / +17.0)
editing LxExampleSpace -> 0.60cm           23.5    21.8   (= --example-spacing 0.60)
editing LxExampleSpaceAbove -> 0.60cm      23.5     9.9   (only the top moved)
```

The table style now states `fo:margin-top="0cm" fo:margin-bottom="0cm"`
explicitly rather than omitting them, so a `--reference-doc` default
cannot creep back in and add to the spacer rows.

A LibreOffice open+save round-trip preserves all three styles, the parent
links, and the children's *unset* line-height — so the "edit the parent to
move both" behaviour survives being saved by the user.

## 2026-08-06 — a Writer macro can do this too, and can measure (built)

`macro/LinguExx.bas` builds a glossed example from selected lines inside
Writer. Everything needed turned out to be reachable from Basic: text
tables, the `NumEx` field master, `mergeRange`, column separators, named
styles, and `UndoManager.enterUndoContext` for a single undo step.

**The reason to have it at all.** A macro can measure the real font, which
the converter structurally cannot. Measured against `Emitter.text_width_cm`
at 12pt Liberation Serif:

| word | measured | estimated | error |
|---|---|---|---|
| Esto | 0.741cm | 0.855cm | +15.4% |
| ejemplo | 1.323cm | 1.499cm | +13.3% |
| AAA | 0.952cm | 0.889cm | -6.7% |
| iii | 0.317cm | 0.406cm | +28.0% |
| ungrammatical | 2.460cm | 2.786cm | +13.2% |

That is README limitation #1 gone, and the text width comes from the
document's own page style rather than `--text-width`.

### Five things that had to be found by running it

1. **Multi-argument `Sub` calls need `Call`.** Without it the module does
   not compile — and a compile error opens a modal dialog, which in a
   headless LibreOffice blocks for ever rather than failing.
2. **Enumerating paragraphs over a cursor built from the selection does
   not work** — `createTextCursorByRange(sel).createEnumeration()` yields
   one empty element. The selection's own `getString()` already contains
   the paragraphs, so split that on Chr(10)/Chr(11)/Chr(13).
3. **`TableColumnSeparators` cannot be read back and modified.** On a
   table whose columns are still evenly spaced it yields nothing, and
   assigning that fails with "Object variable not set". Build the array
   with `createUnoStruct` instead.
4. **Merging a whole row destroys the column separators.** A table whose
   first row is a single merged cell has none left to set, and every
   column silently comes out the same width. The spacer rows are therefore
   styled across their width and left unmerged, and widths are set before
   any merge.
5. **Writer's default cell padding is 0.097cm and its borders are on.**
   The padding is wider than the 0.16cm gap between columns, so measured
   columns came out too narrow and words wrapped inside their cells.
   `TableBorder.Distance = 0` with zero-width lines fixes both.

Also: Writer gives a new table's first row the centred *Table Heading*
style, which pulls the object language out of line with its own glosses by
12-39pt until every cell is given an explicit `ParaStyleName`.

### What cannot be done

There is no "autoformat as you type" hook. `XModifyListener` fires on
every keystroke with no notion of an example being finished, so this is
command-driven — a shortcut the user presses, not a formatter guessing.

### Verification

`macro/run_macro_test.py` installs the .bas into a throwaway profile,
drives it over UNO, renders, and measures the PDF. Six cases pass: plain,
judged, `{braces}`, three tiers, an overlong example, and a judged/unjudged
pair in one document — the last pinning the same invariant as
`test_sub_example_letters_align_with_main_example_text`, with both text
blocks landing at x=120.6 and the second example numbering itself (2).

## 2026-08-06 — sub-examples in the Writer macro

`GlossSelection` now builds `a. … b. …` paradigms. The selection is parsed
into *items* — a line whose first token is a marker starts a new one — and
a plain example is simply one item with no marker, so there is a single
code path.

**Geometry, matching `Emitter._lead_widths` exactly.** Lead columns are
`[number][marker - judgment][judgment]` for a paradigm and
`[number - judgment][judgment]` for a plain example, where `number_cm` and
`marker_cm` each already include the judgment width. The consequence is the
invariant: a sub-example letter sits at `number_cm`, which is precisely
where a main example's *text* begins. Measured in the rendered PDF, both
at x=97.3.

**Unglossed items are running text in one merged cell**, not one word per
column. Only glossed items contribute to the column widths — otherwise an
unglossed item's words drag columns wide enough to hold them and the
glossed items' alignment goes slack. A paradigm with nothing glossed at
all collapses to a single wide column, as `Emitter._table` does.

**Band boundaries are shared by every item**, as in the converter: an item
with fewer words contributes no rows to a later band
(`if aBandStart(b) < nMax`). `LxItemRows` must agree exactly with what
`LxEmitTable` then writes, or the table is created at the wrong height.

**Translation detection changed.** It used to require more than two lines,
so a two-line selection could not lose its only gloss tier to a quoted
line. With unglossed items now representable that guard is wrong: a quoted
last line is a translation whenever the item has more than one line, which
is what makes `a. Otro ejemplo / 'Another example.'` an unglossed item with
a translation rather than a nonsense one-tier gloss.

**Refusal kept for one case**: a marker part-way through a selection that
does not start with one. Guessing there is worse than asking.

### Verification

Six sub-example cases in `macro/run_macro_test.py` — glossed, unglossed,
mixed, judged, roman numerals, marker alone on its line — all with markers
at one x and exactly one number, plus `check_sub_alignment`, which puts a
main example and a paradigm in one document and compares the letter with
the main example's text. Confirmed the last one bites: forcing the marker
column 0.5cm right fails it (97.3 vs 110.0).

Note what it does *not* catch — carving the judgment out of the marker
column versus inserting it after. Because the macro always reserves the
judgment column, that choice moves every sub-example's text by the same
0.33cm and is invisible to any alignment test. It matters against the
converter's geometry, not within a document, so it is pinned by review and
by matching `_lead_widths`, not by a test.

## 2026-08-06 — one repository, an explicit contract, and a real packaging bug

> Paths in the two entries above predate this one: `macro/LinguExx.bas` is
> now `src/linguexx2odt/writermacro/LinguExx.bas`, and
> `macro/run_macro_test.py` is `tools/run_macro_test.py`.

Asked whether the converter and the Writer macro should be split into
separate packages. They should not, and the reason is worth writing down:
what the two share is a **specification, not code** — six style names,
seven layout lengths, the `NumEx` sequence, and the geometry rules. The
whole point is that a converted example and a macro-built one are the same
object. Separate repositories would make that contract implicit and it had
already begun to drift.

**Drift found.** `max_col_cm = 6.0` existed in the converter and had no
counterpart in the macro, which let a single very long word take a column
as wide as it liked. `width_safety = 1.06` is also absent, but that one is
deliberate — the macro measures. Nothing distinguished the accident from
the decision. Now `styles.py` carries three tables: `MACRO_NAMES`,
`MACRO_LENGTHS`, and `MACRO_NOT_SHARED`, the last with a reason per entry,
so an absence is on the record.

`tools/sync_macro.py` writes a generated block into `LinguExx.bas` and
`tests/test_macro_sync.py` fails on drift — no LibreOffice needed, so it
runs in the ordinary suite. It also asserts every shared constant is
*used*, not merely declared: `MAX_COL_CM` sitting unreferenced would be
drift with a fig leaf, which is exactly the state the macro was in.
Verified both directions fail: changing `pad_cm` in styles.py, and
un-wiring `MAX_COL_CM` in the macro.

**The packaging bug.** `[tool.setuptools.packages.find] where = ["src"]`
with no package-data meant `pip install pandoc-linguexx` shipped the
converter and **no macro at all** — the `.bas` was a loose top-level
directory, and wheels ship packages. Moved to
`src/linguexx2odt/writermacro/` as package data, with
`linguexx2odt --print-macro` to get it out again.

**The `.oxt`.** `tools/build_oxt.py` packages the macro as a LibreOffice
extension: `description.xml`, `Addons.xcu` for the menu entry, and the
Basic library as `script.xlb` + a `.xba` module wrapping the source in
CDATA (the build refuses if the source ever contains `]]>`). Verified by
installing it with `unopkg add` into a throwaway profile — one where
*nothing* had been pasted into Basic — and invoking
`vnd.sun.star.script:LinguExx.Gloss.GlossSelectionQuiet?...&location=application`
over UNO: the paradigm came out with markers at x=97.3 and glosses under
their words, identical to the pasted-in build.

The menu URL in `Addons.xcu` is the same script URL the harness invokes,
so what a user clicks is what the tests exercise.

### 2026-08-06 — the .oxt needed a dialog.xlb it has no dialogs for

Installed in the desktop, the first build gave on every start:

    Error loading BASIC of document .../LinguExx/dialog.xlb:
    General Error. General input/output error.

LibreOffice registers a Basic library folder as **both** a script library
and a dialog library, and then reads `dialog.xlb` whether or not the
extension has any dialogs.  The package shipped only `script.xlb`.

Measured on the broken package over UNO:

```
ApplicationDialogLibraryContainer.getLibraryLinkURL("LinguExx")
  -> file:///.../linguexx-0.1.0.oxt/LinguExx/dialog.xlb   (does not exist)
  getByName        -> ok, elements = []
  isLibraryLoaded  -> True
```

— the exact path from the error message.  Note what this cost: headless
LibreOffice resolves that link lazily and reports success, so the harness
was perfectly happy with a package the desktop rejected on every launch.
`loadLibrary` returning OK is not evidence that the library file exists;
only `getLibraryLinkURL` plus a filesystem check is.  Any future check of
an extension's contents should assert on the resolved paths, not on a
call that succeeds.

**Fix:** ship an empty `dialog.xlb` declaring the library and no elements.
Verified on a fresh install: the link resolves to a real 296-byte file,
`script.xlb` resolves, the `Gloss` module is present, and the macro still
builds a paradigm through the menu's own script URL.

### 2026-08-06 — a translation the macro did not recognise, and a Const that broke the module

Reported from a real document (`tests/longex.odt`): in a long, banded
example the translation came out in the *third* row, split one word per
column, with two gloss bands after it.

Not the banding.  The translation line began with **U+0060, a backtick** —
LaTeX's `` `quoted' `` convention, which is exactly what someone coming from
linguexx types, and autocorrect only curls the closing half.  `LxIsTranslation`
did not list it, so the line became a third gloss *tier*; tiers are emitted
per band, which put it inside band 1 and left an empty tier row in band 2.

Added the backtick, plus `„`, `‹` and the guillemets, to the recognised
openers.

**And a self-inflicted second bug worth recording.**  The first fix declared
them as

    Private Const LX_QUOTES As String = "'" & Chr(34) & ...

Basic's `Const` takes a compile-time constant expression, and `Chr()` is a
call, so the module stopped compiling.  Headless LibreOffice reported
*nothing*: `GlossSelectionQuiet` returned `""` and simply did not build a
table, so the harness saw a document of plain paragraphs.  A macro that
silently does nothing is what a compile error looks like from the outside —
if the harness ever shows unstyled, unnumbered text where a table should be,
suspect the module, not the layout.  It is a Function now.

Pinned by three cases in the harness asserting on the *ODT*, not the PDF:
the translation must be the last content row, styled `LxTranslation`, whole,
in a single cell.  A translation mistaken for a gloss tier still renders —
it just renders in the wrong row — so the PDF is the wrong place to look.

### 2026-08-06 — a single unglossed line is an example too

`GlossSelection` refused a one-line selection: "Select at least two lines".
That guard dated from when the macro could only build glossed examples —
object language over at least one gloss tier.  Unglossed *items* became
representable when sub-examples arrived, which quietly made the guard wrong:
`a. this / b. that` worked while `A simple example.` did not, even though the
unglossed example is the commonest kind in a paper.

Relaxed to `nLines < 1`.  Nothing else needed changing — `LxMakeItem` already
produces a one-tier item, `LxLayOut` already collapses to a single wide column
when nothing is glossed, and `LxEmitTable` already emits an unglossed item as
running text in one merged cell.  The feature was there; only the door was
locked.

Pinned by four cases asserting on the ODT (one word per column would still
render, and at one word the difference is invisible in a PDF) plus
`check_unglossed_alignment`, which puts a glossed and an unglossed example in
one document and requires both to start at the same x — measured 97.3 and
97.3.  A paper that mixes the two must not have its examples marching in and
out from one to the next.

One test bug found on the way: the first version of the ODT check allowed at
most two filled cells in the first row, which a *judged* unglossed example
fails legitimately — number, mark, and text make three.  The check now
discounts the number and judgment cells and requires exactly one text cell.

### 2026-08-06 — the macro's bands were coupled; ported the converter's union grid

Reported from `tests/longex1.odt`: in a two-band example, band 2's glosses
sat in band 1's cells.  Checked both tools first — the **converter was
already right**.  Given the same long German example it builds 21 columns
with `ist[2]`, `extrem[3]`, `überschritten[4]`: the union of both bands'
boundaries, each word spanning what it covers.

The macro used the rectangular grid documented earlier as a deliberate
simplification — column *i* as wide as the widest word in position *i* of
any band.  That is precisely the coupling: with 16 shared columns,
`einer` sat in `Dies`'s column and `überschritten` stretched the column
`langes` lives in.  "Marginally wider packing" understated it; the real
cost is that an unrelated line changes your layout.

`LxBuildGrid` is now a port of `emit_odt.Grid`: collect every band's
cumulative boundaries, sort, merge within `GRID_TOL_CM`, and give each word
`(first column, span)`.  Same example through the macro afterwards: 23
columns, widest span 3, bands independent.

The one thing the converter does not have to deal with is that **merging
removes cells, so everything to the right shifts left by span-1**.  Words
after a merge must be addressed by their shifted name, not their grid
column, which is what `nShift` tracks in `LxEmitTable`.  Each tier row also
walks the band's *whole* word range rather than its own, so a short tier
still produces the same cell structure and the rows keep lining up.

Pinned by `check_bands`: at least two bands, at least one **tier** cell
spanning more than one column — a rectangular grid never produces one — and
glosses under their words in every band, not just the first.  Verified it
bites by forcing `aWordSpan(j) = 1`.

Also fixed here: `connect()` in the harness still passed `--invisible`.  An
earlier edit meant to change it to `--headless` had silently not matched,
and the unconditional "ok" print hid that.  Stray `--invisible` instances
outlived their runs and squatted on port 2084, which is what produced a
"Binary URP bridge disposed" mid-run.  The replacement now asserts.
