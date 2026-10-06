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

- ~~`\appendix` numbering~~ and ~~`\cref` with several labels~~: resolved,
  see "The remaining issues" below.
- A `book` or `report` document: pandoc makes `\chapter` level 1, which
  numbers right ("1.1" for a section), but such classes number only to
  `\subsection`, and level 3 is numbered here regardless.
- A `--reference-doc`'s own heading numbering is replaced.
- ~~An unnumbered heading's reference showed nothing once updated~~, in
  both formats (found while writing the manual): the field pointed at the
  heading, which has no number. It points at the last numbered heading
  before it now, whose number is what LaTeX prints.

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

- ~~English names~~ and ~~a footnote inside an example~~: resolved, see
  "The remaining issues" below.
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

## Step 4: equations — done (6e05d4e)

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
- ~~`\numberwithin{equation}{section}`~~: resolved, see below.
- An equation inside an example is not numbered: the example is rendered on
  its own, outside the AST this reads.

## The remaining issues — resolved

Asked for after step 4: "Resolve remaining issues". Each was measured
against LaTeX first, and each has its tests.

- **A footnote inside an example** (`tests/test_example_footnotes.py`).
  Worse than recorded: the `.odt` resolved a reference to the document's
  first note to the example's (two notes called `ftn0`), a `\label` in the
  note was taken for the example's ("(1)" for "2"), and the `.docx` printed
  `\footnote{...}` in the cell. The example renderer knows `\footnote` now:
  each such note is named `lxftn<n>` -- its `text:id`, and in OOXML a
  bookmark around its mark -- so a reference names it directly; the
  extractor leaves a `\label` inside a note to the note; footnote numbering
  counts them where their example stands. Found on the way: LibreOffice
  pairs a `.docx` note with its mark by the *order of the ids*, not by id
  (measured: an appended note with a high id showed the next note's text),
  so every note is renumbered in text order.
- **Several labels in `\cref`, `\crefrange`, and `\cref` to an example**
  (`cleveref.py`, `tests/test_cleveref.py`). Measured: grouped by kind in
  first-come order, sorted, repeats dropped, runs of three or more as a
  range, "a and b" / "a, b and c" within a group, "A, B, and C" between
  groups, plural names, `\Cref` capitalising the first group only. A
  single `\cref` to an example was deleted too; linguexx prints "(1)".
- **Pages in a `.docx` cache** (`pages.py`, `tests/test_pages.py`). When
  LibreOffice and pdfinfo are there, the finished file is exported to PDF
  with its bookmarks as named destinations, and each page field's "?"
  becomes the page its bookmark is on. Without them, "?" stays and the run
  says so. In the `.odt` a page reference to an *example* or a *footnote*
  stays "?" (a sequence and a note, not bookmarks); LibreOffice computes it
  on loading, and no other `.odt` reader was tried.
- **The document's language** (`names.py`, `tools/measure_names.py`,
  `tests/test_names.py`). Measured per language and per way of loading:
  cleveref's names follow a language given to cleveref or to the class,
  *not* babel's option alone (then they stay English, in LaTeX too);
  hyperref's `\autoref` names and the captions follow babel; under
  polyglossia `\autoref` stays English and the captions are polyglossia's
  own ("Tab. 1 : " in French, "Table 1 – " under babel). English, French,
  German, Spanish, Italian, Portuguese, Dutch; another language prints
  English, with a warning.
- **`\appendix`** (`tests/test_appendix.py`). Pandoc drops it without a
  trace, so the extractor leaves a marker paragraph; the sections after it
  are "A", "A.1", their headings take a lettered numbering of their own (a
  list in ODF, a second numbering in OOXML), and `\autoref` says "Appendix
  A" in the document's language. The references are fields on those
  numbers and followed them even before the converter knew (spiked).
- **`\numberwithin{equation}{section}`** (and `\counterwithin`): "(1.2)",
  "(A.1)", restarting at each section.
- Found and fixed on the way: `\autoref` to an unnumbered heading is
  "section", with the last number before it (it said "paragraph").

### What remains, and why

- **"2(b)" for LaTeX's "2b"**, and "(ii)" for "ii": a reference to a list
  item whose label has parentheses keeps them. Spiked in both formats: no
  reference format of either drops them. Hidden counter fields could, but
  would drift as soon as an item is added in the word processor.
- **`\cpageref` with several labels on one page** prints "pages 1 and 1"
  where cleveref merges them into "page 1": the pages are known only after
  layout, when the phrase is already written.
- **A `table` with no `tabular`** (an image in a table float): pandoc drops
  the environment, caption and label with it, before the converter sees it.
  Older than this work; a reference to it prints "??" and warns.
- French typography of the prose itself -- "REFS :" with a space before
  the colon, the footnote mark "1." -- is babel's on every line, not a
  reference's.

## Next

Nothing planned; see "What remains, and why".
