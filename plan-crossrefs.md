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

## Step 1: sections and pages — done

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

## Next

Footnotes, tables and figures (whether pandoc already numbers captions is
to be measured), list items, equations (text).
