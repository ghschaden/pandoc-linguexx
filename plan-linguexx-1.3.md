# pandoc-linguexx — work order: catch up with linguexx 1.3–1.3.2

Companion to `plan.md`, which built the converter against linguexx 1.2 and
is otherwise still accurate. Nothing here revisits its architecture: the
opaque raw-opendocument block, the field-based numbering and the band
layout all stand. What follows is the surface that moved underneath them.

## Why now

The converter's last commit is `d9b9014`, 2026-08-25. It was written
against linguexx **1.2** (2026-07-31). Three linguexx releases have landed
since and none is reflected here:

| release | date |
|---|---|
| 1.3 | 2026-09-09 |
| 1.3.1 | 2026-09-15 |
| 1.3.2 | 2026-09-21 |

Target **1.3.2**, not linguexx `main`. The commits on `main` past the tag
are housekeeping: the suite run against 1.3.2's `.sty` in a current tree
passes 2378/2381 (the three failures are a new option case), and the
example documents render byte-identical pages with identical structure
trees under both. Nothing there reaches a page, so there is nothing in it
for this tool.

## Verified facts (do not re-litigate; re-verify only if linguexx or pandoc changes)

Tested 2026-09-25, pandoc 3.10.2, linguexx at `b507a41`, converter at
`d9b9014`. Each was run, not read off a changelog.

1. **`\ExLBr`/`\ExRBr` are ignored, silently.** A document with
   `\renewcommand{\ExLBr}{[}` typesets `[1]` under linguexx and comes out
   `(1)` here, with **no warning**. linguexx 1.3 fixed `\ExLBr` being
   ignored and its changelog calls that class of bug "the one kind of
   incompatibility a drop-in replacement cannot have: the document still
   compiles and only the page is wrong." This reproduces it one layer out.
2. **`\GlossTransSide` is ignored, silently.** With it set, linguexx puts
   the free translation *beside* the gloss — measured: translation and
   object tier share `y=127.85`. The converter emits it as a row *below*,
   with **no warning**. This is in the tool's core competency.
3. **`\exannot{…}` warns but loses the content.** The run prints
   `unhandled command \exannot; fragment rendered by pandoc`, and the
   annotation is then dropped entirely — zero occurrences of its text in
   `content.xml`. README promises unhandled constructs "degrade to
   readable output rather than to nothing"; here it is nothing.
4. **The generic unknown-command warning does fire.** Facts 1 and 2 are
   not holes in that mechanism — they are *changed behaviour of commands
   the converter believes it already handles*, which no unknown-command
   check can catch. Worth stating because the obvious fix (widen the
   unknown-command table) addresses fact 3 and neither of the others.
5. **Absent from `src/`, `tests/` and `docs/` alike:** `exannot`,
   `GlossTransSide`, `ExLBr`, `ExRBr`, `langsci`, `SetLeipzig`,
   `lpzglist`, `phantomalign`, `DeclareJudgment`, `SetAltSpoken`. Not
   merely unimplemented — absent from the README's "What it does not, and
   says so" table, so a reader has no way to learn they are unsupported.
6. **`[langsci]` is undeclared.** That table puts gb4e `exe`/`xlist` and
   `[legacy]` out of scope and says nothing about the `\ea … \z`
   front-end that 1.3 added. A langsci document reaches the catch-all.

Consequence: **the README's "never fails silently" promise is currently
false**, and not at the margins. Facts 1 and 2 are wrong output with no
warning, in the two things this tool exists to get right — numbers and
glosses.

## Phase A — stop being silently wrong — DONE

The priority, because wrong-and-quiet is worse than absent-and-declared.

- Honour `\ExLBr`/`\ExRBr` (and the sub-example pairs `\SubExLBr`/
  `\SubExRBr`, `\SubSubExLBr`/`\SubSubExRBr`, which have the same
  problem and were not probed — check, do not guess). They are preamble
  `\renewcommand`s, so this is a preamble scan feeding the number
  template, not a parser change.
- Detect `\GlossTransSide` in the preamble. Supporting the side layout is
  Phase C; for now **warn and degrade** to the below-the-gloss layout
  already emitted, which is at least declared rather than silent.
- Hard rule, and the reason this phase exists: a linguexx command that
  changes the *appearance of something already supported* must be
  detected even when it will not be implemented. The unknown-command
  fallback cannot see these, because nothing unknown appears.
- Golden tests for both, in `tests/cases/`, following the existing
  `*.tex` → IR JSON pattern.

## Phase B — declare the gaps — DONE

Documentation only; no behaviour changes.

- Extend the README's "What it does not, and says so" table with:
  `\exannot` (dropped, not degraded — say so until Phase C), `[langsci]`
  / `\ea … \z`, `[phantomalign]`, `\DeclareJudgment`, `\SetLeipzig` and
  the `\lpzglist` family, and the spoken-form setters.
- Say which linguexx version the converter targets. Its absence is why
  this drift went a month unnoticed; a version line makes the next gap a
  diff rather than an investigation.
- Mirror it into `docs/guide-fr.md`, which carries the same table.

## Phase C — DONE, and narrowed to one feature

**`\GlossTransSide` — NOT IMPLEMENTED, decided 2026-09-25.** A side
translation is the same material in a different place, so normalising it to
the ordinary layout loses nothing a reader needs. Reproducing it would have
meant answering what that column does when an example splits into bands --
repeat beside every band, sit beside the first, or suppress the split -- a
question linguexx never faces because it reflows and an ODT table does not.
Not worth acquiring a semantics for a placement. Phase A's warning is the
whole treatment and is worded as a decision; the README says why, and a
reader who wants the side layout drags one column in Writer.

**`\exannot[⟨spoken⟩]{⟨text⟩}` — DONE.** `Body.annot`, pulled in
`_pull_annot` (it steps over the optional argument, which is dropped: the
spoken form is for a PDF screen reader). `Layout.annot_column_ratio` (.75,
`\ExAnnotColumn`'s default) and `annot_sep_em` (1, `\ExAnnotSep`). The
emitter reserves a trailing column, gives the body only what is left before
it, and puts the label on the first row of each body -- level with the
object tier, as linguexx sets it, not under the free translation.

Two details worth keeping:

- The separation gap is emitted however narrow it is, unlike the ordinary
  filler column, which is dropped below `min_col_cm`. The gap IS
  `\ExAnnotSep`; dropping it moved the annotation column an em left of
  where every other example put it, which is the one thing a column of
  labels may not do. Caught by measuring, not by reading.
- The deliberate difference: linguexx keeps an example that reaches the
  column full width and drops its annotation to the next line. This
  converter bands instead, which is what it already does to anything too
  wide, so the rule does not change at one length. Recorded in the README.

**Verified against linguexx, not against intent.** On a 17 cm block
linguexx sets both labels of the test paradigm at **12.750 cm** from the
text block's left edge (`pdftotext -bbox` on the rendered PDF); the
converter's annotation column begins at **12.750 cm**. That number is what
`test_exannot_column_sits_where_linguexx_puts_it` pins.

Adding `Body.annot` regenerated all ten goldens, as this order predicted.
The diff was read rather than trusted: **41 insertions, every one
`"annot": ""`**, and nothing else moved.

## Check the width estimator — DONE, it was nothing

Checked, and there is nothing to do. `\lpzg{\textbf{m}.pl}` comes out of
the inline renderer as `[('m', True), ('.pl', True)]` — both runs already
flagged small-caps, which is exactly 1.3's "the modifier adds to the small
capitals" — and it renders as `LxBold` nested inside `LxLeipzig`, so the
weight survives too. The estimate and the markup were both already right.
Recorded so nobody re-opens it.

## Out of scope — do not implement without asking

- **Spoken forms** (`\SetAltSpoken`, `\SetAnnotSpoken`,
  `\SetJudgmentSpoken`). These exist for a PDF screen reader. Whether the
  ODT should carry an accessibility layer at all is a question for
  Gerhard, not a gap to be filled.
- **Supporting `[langsci]`**, as opposed to declaring it unsupported in
  Phase B. It is a whole second front-end; `plan.md` already puts gb4e
  out of scope for v1 and the same argument applies.
- **Chasing linguexx `main`.** Target the tag. See "Why now".

## Not a linguexx matter, but it will bite

`.venv/bin/linguexx2odt` has lost its executable bit — pCloud does not
preserve Unix permissions, and the same thing happened to four tracked
files in the linguexx repo. The venv is gitignored so the repo is clean;
recreate it, or invoke through the CLI entry point, which is how the
probes above were run.


---

## What Phase A actually changed (2026-09-25)

- `latexutil.Brackets` + `scan_brackets()`: the six `\ExLBr`-family names
  read out of the preamble, in `\renewcommand`/`\newcommand`/`\def` form,
  braced or not, comments skipped. A redefinition after `\begin{document}`
  warns and is ignored — an ODT number's brackets are literal text emitted
  once per example and cannot change partway through.
- Threaded to the emitter (the number, and the width its column gets) and
  to the injector (`\ref`, and `\pref`'s bare form).
- Sub-example markers are rebuilt from `SubExLBr`/`SubExRBr` once in
  `parse()`, where the brackets are known, rather than threaded through
  `_parse_items`. With linguexx's defaults the output is unchanged
  character for character, which is why the existing goldens never moved.
- A label now resolves to the bare letter via `_ordinal_text(level,
  ordinal)` instead of `marker.rstrip(".")`, which was right only while a
  marker ended in a period.
- `_scan_unsupported()`: the preamble settings and package options that
  change how linguexx renders something the converter already emits. This
  is the blind spot the unknown-command fallback cannot cover — nothing
  unknown appears in the body.

### A bug found while doing it, and fixed

`\pref` printed **nothing at all** — an empty gap between two commas — and
had done since before this work order. pandoc drops `\pref` and the
relative references because they are linguexx's, not LaTeX's, so the
inject pass's `REF_CMD` branch was waiting for a `RawInline` that never
arrived. `-f latex+raw_tex` makes pandoc keep them. Verified first that it
costs the prose nothing: `Emph`, `Strong`, `Note`, `Cite`, `Math` and
`Header` parse identically with and without the extension.

### Proof

192 tests pass, from a baseline of 184. The two new end-to-end tests were
run against the pre-change code and both fail there, so they test what
they claim. `tests/cases/brackets.tex` and `tests/cases/transside.tex`
carry the goldens, both read by hand: the first pins that a label resolves
to `b` and not `b)`, the second that the warning fires.
