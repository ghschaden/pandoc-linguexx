# pandoc-linguexx — work order: references to what is not an example

A `\ref` to a label that was not an example's was deleted, with a warning:
"REFS: `\ref{s}` and `\cref{s}`." came out "REFS: and .", where LaTeX
prints "1 and section 1" (`plan-linguexx-1.4.md`, "Not done"). Pandoc,
reading with `raw_tex`, keeps every such reference as raw LaTeX, and the
writer deletes raw LaTeX.

## Decided

- **Live fields**, as a reference to an example is: a reference follows
  when a section is moved or inserted. That needs headings with a number
  the word processor keeps, so the converter numbers them (an outline
  numbering, not a typed "1.1").
- **Order**: sections and pages first; then footnotes, tables and figures,
  list items, equations. Equations stay text when their turn comes.

## Step 1: sections and pages — done (f32bbea)

Tested 2026-10-06, pandoc 3.10.2, LibreOffice; the expected text is
LaTeX's (`article`, hyperref, cleveref), read off `pdflatex` and
`pdftotext`.

| LaTeX | prints | `.odt` | `.docx` |
|---|---|---|---|
| `\ref`, `\pref` | 1.1 | `text:bookmark-ref` format `chapter` | `REF bm \w \h` |
| `\cref` / `\Cref` | section 1.1 / Section 1.1 | the word, then the same field | same |
| `\autoref` | subsection 1.1 (hyperref's name for the level) | same | same |
| `\nameref` | the title | format `text` | `REF bm \h` |
| `\pageref`, `\cpageref`, `\Cpageref` | 1, page 1, Page 1 | format `page` | `PAGEREF bm \h` |

- The bookmark is the converter's own, around the title inside the
  heading (`_Reflxsec<n>`): pandoc's is the label, `sec:intro`, which Word
  refuses, and in a `.docx` it spans the whole section, not the title.
- An unnumbered heading's bookmark is `_Reflxnon<n>`, and that is how the
  postprocess finds it: `text:is-list-header` in ODF and `numId 0` in OOXML
  take it out of the numbering without stepping the counter, as
  `\section*` does. A `\ref` to it prints the last number set before it,
  as LaTeX does (`\@currentlabel`).
- Levels 1 to 3 are numbered, `article`'s `secnumdepth`.
- The `.docx` cache is what LaTeX prints, for a reader that never updates
  fields (OnlyOffice), except a page: nothing before layout knows it, so the
  cache is "?". LibreOffice and Word compute it.
- `\pageref` to an example is a page field on the example's number
  (`text:sequence-ref` format `page`, `PAGEREF NumEx<n>`).

Tests: `tests/test_section_refs.py`. The conversions fail on the code before
this step: the line came out without its references, under the "deleted
from the output" warning. The full corpus against linguexx 1.4 passes (521).

## Known limits of step 1

- `\appendix` numbering (A, B) is not reproduced: the outline keeps
  counting in arabic numerals.
- `\cref{a,b}` with several labels is deleted with a warning, as before.
- A `book` or `report` document: pandoc makes `\chapter` level 1, which
  numbers right ("1.1" for a section), but such classes number only to
  `\subsection`, and level 3 is numbered here regardless.
- A `--reference-doc`'s own heading numbering is replaced.
- An unnumbered heading's reference in the `.odt` is computed by LibreOffice
  from the outline, which has no number there; LaTeX's "last number set" is
  only the cache.

## Step 2: tables, figures and footnotes — done (756f86b)

Measured the same way (2026-10-06).

| LaTeX | table | figure | footnote |
|---|---|---|---|
| caption | "Table 1: A table." | "Figure 1: A figure." | — |
| `\ref` | 2 | 1 | 2 |
| `\cref` / `\Cref` | table 1 / Table 1 | fig. 1 / Figure 1 | footnote 1 / Footnote 1 |
| `\autoref` | Table 2 | Figure 1 | footnote 1 |
| `\nameref` | the caption without its full stop | same | nothing at all |

- Pandoc writes a caption without a number, so the injector numbers it:
  "Table", a sequence field (`text:sequence` named Table or Figure, `SEQ
  Table`), ": ", and the title in a bookmark of its own for `\nameref`.
  The sequences are declared beside NumEx. Only a captioned float is
  counted, as only `\caption` steps LaTeX's counter.
- A footnote's `\label` arrives as raw LaTeX inside the Note. The injector
  puts a bookmark there (`_Reflxfnl<n>`), and the postprocess finds the
  note by it: in ODF to name the note's `text:id` in `text:note-ref`, in
  OOXML to bookmark the run with the note's mark in the text
  (`_Reflxfn<n>`), which is what `NOTEREF` points at.
- Spiked by hand first, as step 1 was: LibreOffice computes every field in
  both formats.

Tests: `tests/test_float_refs.py`; the conversions fail on the code of step 1.

### Known limits of step 2

- The names are English ("Table", "Figure", "footnote"). A French
  document's LaTeX prints "Tableau"; the converter does not read babel's
  language for this.
- A footnote inside an example is not counted (the example is rendered on
  its own, its note is not in the document's AST), so the cached number of
  a reference to a later note is one short: "2" where LaTeX prints "3". The
  field resolves to the right note and LibreOffice shows "3"; a .docx
  reader that does not update fields shows "2". Older than this step, and
  found by it: that note gets pandoc's id `ftn0` a second time, which a
  note reference to the first note of the document would find twice.
- Subfigures and `\caption` outside a float are not handled.

## Step 3: list items — done (35c6656)

Decided with the user: the lists are made LaTeX's first, since a live
reference shows the item's number as the word processor displays it.

| | LaTeX | `.odt` before | `.docx` before |
|---|---|---|---|
| level 1 / 2 / 3 | 1. / (a) / i. | 1. / 1. / 1. | 1. / a. / i. |
| `\setcounter{enumi}{4}` | 5. | 1. | 5. |

- The injector gives each `enumerate` in pandoc's DefaultStyle the style
  and delimiter of its depth (`sections.ENUM_LEVELS`); a list with a style
  of its own keeps it. Pandoc writes a list's start on `text:list`, which
  has no such attribute; the postprocess moves it to the first item.
- Spiked: pandoc writes a nested list as a list of its own, so "number in
  context" (`number`, `number-all-superior`, Word's `\w`, `\r`) gives
  "(b)(b)" or "ii.ii.i". The item's own number (`number-no-superior`, `\n`)
  is right, "(b)" and "i" -- the final full stop dropped in both formats.
  So a reference is a field per level, on bookmarks in the item and in
  each parent: "2" "(b)" "i" is LaTeX's "2(b)i".
- **The one difference from LaTeX**: the second level's reference keeps its
  parentheses, "2(b)" for LaTeX's "2b". No field drops them; text would
  have printed "2b" and stopped following the list. Decided for the live
  field, as for everything else here.
- `\nameref` to an item prints the title of the section it is in, as LaTeX
  does; it is that section's title field.

Tests: `tests/test_list_refs.py`; they fail on the code of step 2.

### Known limits of step 3

- `enumitem` labels (`label=(\roman*)`) are not read (pandoc gives the list
  its default style): such a list is numbered as article's default.
- The `enumerate` package's `[(i)]` reaches pandoc as a style of its own,
  which is kept, and a reference's cache follows it. Its reference keeps
  the parentheses too: "(ii)" where LaTeX prints "ii".
- A list deeper than four levels is numbered as the fourth (LaTeX refuses
  it).

## Step 4: equations — done

Decided at the start: references to equations are text. Measured first:
pandoc writes a display equation **with no number**, so a reference as
text would have named a number the page does not show. The numbers came
first, as captions' did.

- `equations.number_rows` reads the number off the source as amsmath
  assigns it: `equation`, `multline` once; `align`, `gather`, `alignat`,
  `flalign`, `eqnarray` per row (`\\` at the top level only, not inside a
  `cases` or `aligned`), none for `\nonumber`/`\notag`; `\tag{x}` prints
  "(x)" and steps nothing, `\tag{$*$}` "(∗)"; starred, `\[ \]` and
  `displaymath` none.
- Set as Writer and Word number their own equations: a paragraph
  (`LxEquation`, centre tab at half the text width, right tab at its end)
  with tab, the equation inline with `\displaystyle`, tab, "(n)". Spiked
  first: text after display math drops to its own line at the left.
  pandoc also puts consecutive display equations in one paragraph; the
  injector splits it, the prose around them into paragraphs of their own.
- An `align` with several numbers is split into a row per paragraph, its
  `&` removed, so each number stands beside its row. One with a single
  number stays whole, alignment and all. An equation without a number is
  left as pandoc writes it.
- References: "1", `\eqref` "(1)", "eq. (1)", "Equation (1)", `\autoref`
  "Equation 1" -- text. `\nameref` prints the section's title, as for an
  item; `\pageref` is a page field on a bookmark around the number, since
  no text could know a page.
- In the `.docx` pandoc defines a custom style it is given as a bare child
  of BodyText; `styles_docx.inject_styles` now drops a definition the
  converter's own replaces, where it used to add a second (invalid).

Tests: `tests/test_equation_refs.py`; the conversions fail on the code of
step 3.

### Known limits of step 4

- The numbers and references are text: inserting an equation does not
  renumber the ones after it, nor the references.
- A split `align` loses its column alignment.
- `\numberwithin{equation}{section}` ("1.1") is not read: the numbering is
  article's default, one counter through the document.
- An equation inside an example is not numbered: the example is rendered on
  its own, outside the AST this reads.

## Next

Nothing planned. `\appendix` lettering, several labels in one `\cref`,
and non-English names are the limits that remain across the steps.
