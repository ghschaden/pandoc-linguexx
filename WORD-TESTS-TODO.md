# What still needs a real Word

Everything in `plan-docx.md`'s verified facts was measured in LibreOffice,
because that is what is installed here. Three questions remain that only
Microsoft Word can answer, and the whole `.docx` plan rests on the first of
them. None takes more than five minutes once Word is in front of you.

## The file

```
python3 spikes/s5_docx_sample.py /tmp
```

writes `/tmp/linguexx-docx-sample.docx`. It is not converter output — the
converter cannot emit `.docx`, which is the point of the plan. It is the
OOXML a `--to docx` emitter *would* write, hand-assembled, so that opening
it tests **the plan** rather than LibreOffice's `.docx` exporter. (Re-saving
a converted `.odt` as `.docx` tests the exporter, which is a different and
much less interesting question.)

Every number in it caches `1` and every reference caches `99`, on purpose.

---

## Test 1 — do the fields recalculate? (the one that matters)

Open the file and read the two examples and the last line.

| what you see | what it means |
|---|---|
| **(1)** and **(2)**, references agreeing | Fields are live. The premise holds, no plan change. |
| **(1)** and **(1)**, references `99` | Fields are not recalculating on open. See below — not fatal. |
| anything else | Write down exactly what, it is more interesting than either. |

If you see the second, press **F9** (or Ctrl+A then F9) and look again. If
the numbers correct themselves, Word recalculates on demand rather than on
open, and the emitter must write the caches **already correct at build
time** — the field stays live for later edits, but the document reads right
before anyone presses anything. That is an afternoon in Phase 2, not a
redesign, and it is worth doing regardless.

This is the test the target lives or dies by: a number that does not
renumber is a number the user could have typed.

## Test 2 — does Word offer to repair the file?

Watch the moment it opens. A repair prompt means the OOXML is malformed
somewhere LibreOffice tolerates and Word does not.

Answer **yes/no**, and if yes, whether the document still opens afterwards
and what it looks like. A repair prompt is worse than a wrong column width:
it teaches the user not to trust the tool.

If this fails, Phase 1 grows an OOXML schema validator in CI. See "Without
Word" below for how far that can be taken here.

## Test 3 — does inserting an example renumber the rest?

The point of the whole tool, and the one thing a static render cannot show.

1. Click just before the **(1)** example.
2. Type a line of ordinary text, press Enter.
3. Copy the whole first example table and paste it above the original.
4. Ctrl+A, F9.

The two examples should now read (1) and (2) **in their new order**, and the
cross-references at the bottom should follow them. If the references now
point at the wrong examples, say so — that is about bookmarks surviving a
copy, and it would change how `inject.py` names them.

---

## Getting Word, on Linux, for free

Ranked by how much they actually answer, not by convenience.

**1. Somebody else's Word.** For three five-minute tests, a colleague with
Word and this file answers everything. Genuinely the best option and the one
to try first.

**2. A Windows evaluation VM plus an Office trial.** Microsoft publishes
free time-limited Windows evaluation images, and Microsoft 365 has a
one-month trial. This is the only route that gives *real, current* Word on
this machine. No VM tooling is installed here (`virt-manager` and
`qemu-system-x86_64` are both absent), so it is an afternoon of setup.
Definitive, and the answer stays valid.

**3. Word for the web** (free with a Microsoft account, works in any
browser). Fast, and **be careful reading the result**: Word for the web has
limited field support and may display cached values without recalculating.
So it is asymmetric evidence —

- shows **(1) (2)** with matching references → fields are live, believe it;
- shows **99** → tells you nothing, because you cannot distinguish "Word
  does not recalculate" from "Word for the web does not recalculate".

Worth two minutes precisely because a positive result is conclusive.

**4. Wine.** `wine` is installed here. It runs real Word binaries, so field
behaviour would be genuine — but you still need a licensed Word to install,
and Wine is fiddly with recent Office. Only sensible if you already have an
installer.

**Not Word, but still useful: OnlyOffice or WPS** (both free, both on
Flathub, and `flatpak` is installed). Neither is Word and neither answers
Test 1 authoritatively. What they *do* give is a second independent OOXML
implementation: if the file opens clean in LibreOffice **and** OnlyOffice,
malformed markup is much less likely, which is most of Test 2's value for
ten minutes' work.

---

## What can be done here, without Word

Worth doing anyway, and it shrinks what Word has to answer:

- **Schema-validate the OOXML.** `lxml` is installed; the ECMA-376
  schemas are a download away. Validating `word/document.xml` against
  `wml.xsd` would catch most of what makes Word offer to repair a file,
  and it belongs in CI once the emitter exists. This is the single highest
  -value thing that does not need Word.
- **Check every part is well-formed and the zip is sane** — cheap, catches
  gross breakage, and proves nothing about schema conformance.
- **Open the sample in OnlyOffice**, per above.

None of these can answer Test 1. Field recalculation is behaviour, not
markup, and only an implementation can tell you.

---

## When you have answers

Put them in `plan-docx.md`'s "Verified facts", with the date and which Word
— version and platform — said so. The whole point of that section is that a
later reader can tell a measurement from an assumption, and "Word does it"
without a version is an assumption wearing a measurement's clothes.

If Test 1 came back needing F9, edit Phase 2 to say the caches are written
correct at build time. If Test 2 came back with a repair prompt, add the
schema validator to Phase 1 before any more OOXML is written.
