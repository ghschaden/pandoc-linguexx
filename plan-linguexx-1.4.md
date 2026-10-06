# pandoc-linguexx — work order: catch up with linguexx 1.4

Companion to `plan-linguexx-1.3.md`, which brought the converter to 1.3.2
and whose method this follows: each change of the release was run through
the converter and compared with what linguexx 1.4 prints, not read off its
changelog.

## Target

**1.4** (2026-10-04, tag `1.4`), not linguexx `main`. `main` has gone on
since: morpheme alignment (`\GlossMorphAlign`), right-to-left glosses
(`\GlossRTL`, `\glscript`), a translation's default language, and fixes to
tier languages. None is released, so none is targeted; a 1.4 document
cannot contain them.

## What 1.4 changed, and what the converter did with it

Tested 2026-10-06, pandoc 3.10.2, against an export of the `1.4` tag;
converter at `8dc70d5`. Each document was built with
`TEXINPUTS=<linguexx 1.4>: pdflatex` and read with `pdftotext -layout`.

| 1.4 change | converter at `8dc70d5` | now |
|---|---|---|
| Movement arrows, `\mvto{a}{text}` / `\mvfrom{a}{text}` | **lost the text**: the fragment went to pandoc, which deleted the commands with their arguments. "MVPLAIN `\mvto{a}{LANDA}` stays here `\mvfrom{a}{BASEA}` end." came out "MVPLAIN stays here end.", under a warning saying it had been rendered | the words stay, in prose and in a gloss tier; the arrows are not drawn, and the run says so once |
| Inline verbatim in a dot-syntax example, `\verb`, `\Verb`, `\lstinline` | `\verb` came out right, with an "unhandled command" warning each time. linguexx's own `tests/verb-dot.tex` **made the conversion fail**: the source scanner knew only `\verb`, so a `%` inside a `\Verb` was a comment and pandoc got an unbalanced document. `\Verb*[formatcom=…]` failed inside pandoc and printed its source; the `.docx` printed every one as source | the scanner reads all three by their own rules (`latexutil._inline_verbatim_end`): options with braces, a starred space, `\lstinline{…}` closed at the first `}`. Pandoc gets the plain `\verb` it reads; the `.docx` gets the payload as text. `verb-dot.tex`'s eleven lines match linguexx's in both formats, without a warning |
| `\ref` to a custom-labelled example, `\ex.[(7)]\label{x}` | printed the example's index as a number field, "(1)" | prints the label, "(7)", and "7" for `\pref`; text, not a field |
| A sub-example under a custom label, `\ex.[(5)] \a.\label{y}` | "(2a)" | "(5a)", and "5a" for `\pref` |
| An empty gloss cell `{}` | already right: the converter kept the column, which linguexx 1.3.2 dropped | unchanged |
| `\cref` to a `\label` in the prose after an example | see "Not done" | unchanged |
| hyperref anchors, the option interface, the CTAN package | nothing on the converter's side | — |

The full corpus against 1.4 (`LINGUEXX_FULL_CORPUS=1`, a tree with linguexx
1.4 beside it) failed one test before these changes, the round trip of
`verb-dot.tex`, and passes after them: 513 passed, 1 skipped (as before).
The last step of that was not about verbatim at all: the way back writes a
"^" as `\textasciicircum{}`, which the renderer did not know, so the cell
fell back to its source. It knows it now. `make check` locally, against
linguexx `main`: 456 passed.

## Not done

- **A `\ref` or `\cref` to a label that is not an example's** (a section, a
  `\label` in the prose) is deleted, with a warning: "REFS: `\ref{s}` and
  `\cref{s}`." comes out "REFS: and .", where linguexx prints "1 and
  section 1". This is older than 1.4 -- 1.4 only fixed which label `\cref`
  takes -- and it is a question of its own: the converter would need
  pandoc's section numbering, which the reference document decides.
- **Typewriter face in a `.docx`** for inline verbatim: the text is right,
  the face is the cell's. A code character style would have to exist in the
  three places the constants live (`make macro`), for one construct.
