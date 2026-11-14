# linguexx 1.5 compatibility review

Target: the upstream `1.5` tag, checked on 2026-11-14. The adjacent checkout's
package and tests match that tag; its later changes are to the manual only.
Right-to-left glosses are excluded at the user's request.

## Changes

| Upstream change | Converter behavior |
|---|---|
| `\CommonGloss` | Dot-syntax variant rows and shared tiers form one table. Widths are measured across all rows; gaps, judgments, labels and annotations stay in place. Each continuation band contains the variants followed by their shared tiers, with letters and annotations repeated. The translation occurs once, at the example indent. Beamer pauses are flattened to the final slide's rows. |
| `\GlossMorphAlign`, `\GlossMorphAlignOff` | Morphemes at unbraced `-` and `=` align using measured tab stops inside word cells. Braced units, citation forms and TeX dashes stay whole. Unsegmented tiers do not participate. Conflicting counts warn and fall back to word alignment; movement and alternative columns remain word-aligned. Morpheme columns reserve their full width; a squeezed table warns and falls back to words to avoid overflowing tab stops. |
| Tier and translation languages | Both formats carry language metadata. Empty declarations clear the setting. Without an explicit translation language, only the last gloss tier's declaration is inherited. Group/environment declarations are scoped, and local example/sub-example declarations do not leak into the next item. |
| Judgment detection in every gloss spelling | Already supported. Marks still hang in their own column, including `*(`, whose parenthesis remains part of the word. The change to its PDF spoken description has no converter counterpart. |
| `\exrefcheck[words=n]` | Reports relative references and both range ends to stderr, with target numbers, source lines and opening words. Source locations replace PDF page numbers. Nothing is typeset; `--quiet` suppresses the report. |
| References mentioned in the report | Added `\TextNext`, `\pTextNext` and `\Refrange` to the existing reference conversion path. `\Refrange` keeps both full numbers and their example brackets. |
| `\Exalph`, `\Exroman` documentation | Existing counter-style support remains; `\let\Exalph\ExLatinAlph` is now recognized too. |
| PDF tagging, kernel labels, French punctuation | TeX/PDF implementation changes, with no new converter layout required. Existing reference and judgment tests still apply. |
| RTL grids, `\glscript`, RTL mirroring | Excluded. Explicit `\GlossRTL` and `\glscript` uses warn. |

The existing limitations remain: phantom alignment is warned about rather
than reproduced, tier fonts use the document styles, and the `exe`/`xlist`
interface is outside supported syntax. Invalid shared-gloss input with no
variant rows, or a variant after shared lines, warns and becomes plain text
rather than losing the words or producing a broken table.

## Reverse conversion and editor tools

`docx2linguexx` and `odt2linguexx` recognize variant/shared-row styles, recover
shared glosses, and remove morpheme-padding tabs without adding word spaces.
Language declarations and the alignment switch are not reconstructed.
The round-trip oracle now compares shared tiers and translations too.

The interactive Writer macro and add-in input syntax are unchanged. Their
Untypeset implementations do not read these new layouts; use the command-line
reverse converters for them. The generated Word style definitions include the
new styles (`make macro`), and the unshared Writer styles are explicitly
recorded in `MACRO_STYLES_NOT_SHARED`.

## Validation

The unmodified baseline: **578 passed, 2 failed**, both failures being
round trips of new shared-gloss corpus documents. LibreOffice requires running
outside the workspace sandbox on this machine.

Focused tests cover settings scope and clearing, protected morphemes and
mismatch fallback, shared column widths and band order, language markup,
reference reports, Latin labels, and round trips. Actual LibreOffice PDF
coordinates verify shared-column alignment, annotation positions, translation
indent, and morpheme starts in both ODT and DOCX. The same example sources
were compiled with the `1.5` release's `linguexx.sty`; local comparison files
are in `build/linguexx-1.5/`.

The complete checks use `LINGUEXX_FULL_CORPUS=1 make check`; the upstream
corpus includes valid examples, Beamer documents and deliberate syntax-error
fixtures. The JavaScript checks use `make js-test`. The PDF manual is rebuilt
with `make manual`.

Final results:

- The full run completed **723 passing tests**, including the entire upstream
  corpus. Its only failure was the CI target-version assertion: the workflow
  still pinned 1.4 and the README's version line had changed punctuation.
  Both are corrected, with CI now cloning tag `1.5`.
- After that correction and the final squeezed-table safeguard, **69 focused
  tests passed**: all 1.5 tests, tooling checks, width tests and banding tests,
  including PDF rendering and reverse conversion.
- `ruff check .`, `git diff --check`, and `make js-test` passed (11 JavaScript
  test files). Shared-gloss, morpheme and language-metadata DOCX documents
  passed ECMA-376 XML schema validation.
- `make manual` succeeded; the rebuilt PDF is included.
