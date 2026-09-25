# What still needs a real Word

Two readers have now seen the sample and agree: LibreOffice and OnlyOffice
9.4 both read it correctly and neither refuses it. What is left needs
Microsoft Word specifically, and it is less than it was — the schema check
and OnlyOffice between them have retired most of the repair-prompt risk, and
the cache fix has removed the dependency on a reader recalculating anything.

What remains is below. None takes more than five minutes once Word is in
front of you.

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

Every field in it carries its **correct** cached value. The `--stale`
variant carries deliberately wrong ones, for probing whether a given
reader recalculates at all.

---

## Test 1 — does it read correctly, and does editing renumber?

**This test changed on 2026-09-25, and the reason is worth reading.** It
used to ask whether the reader recalculates stale fields. OnlyOffice 9.4
answered no — it showed (1) (1) with both references still at 99, where
LibreOffice showed (1) (2). Two real readers, opposite behaviour. So the
emitter cannot depend on recalculation for the document to be *correct*, and
the sample now ships with its cached values already right.

What is left to ask of Word is therefore two things, not one.

**1a. Does it read correctly on open?** The examples should be **(1)** and
**(2)** and the cross-references should agree. Since the caches are correct,
this should hold whether or not Word recalculates — so anything else is a
surprise worth reporting exactly.

**1b. Does editing renumber?** Paste a copy of the first example above the
original, select all, press **F9**. The numbers and the references should
follow the new order. *This* is the feature: a number that never changes is
a number the user could have typed.

**Passed in OnlyOffice 9.4 (2026-09-25).** Three examples read (1) (2) (3),
and the cross-references read (2) and (3) — the bookmarks stayed on the
original examples instead of being duplicated onto the pasted copy, so each
reference still pointed at the example it names. That is the failure this
test was written to catch, and it did not happen. Word is still worth
asking, but it is now a confirmation rather than a discovery.

If 1b fails, the target is in real trouble and nothing else in this file
matters much. If 1a fails while 1b works, Word disagrees with both other
readers about caches, which would be strange and very much worth knowing.

To probe a reader's recalculation behaviour deliberately, build the stale
variant: `python3 spikes/s5_docx_sample.py /tmp --stale`.

## Test 2 — does Word offer to repair the file? (partly answered already)

Watch the moment it opens. A repair prompt means the OOXML is malformed
somewhere LibreOffice tolerates and Word does not.

Answer **yes/no**, and if yes, whether the document still opens afterwards
and what it looks like. A repair prompt is worse than a wrong column width:
it teaches the user not to trust the tool.

**Most of this risk is now retired without Word.** The sample validates
clean against the official ECMA-376 transitional schemas:

```
make schemas                                  # once, into .ooxml-schemas/
python3 tools/validate_docx.py /tmp/linguexx-docx-sample.docx
```

reports every XML part well-formed and schema-valid. So the markup
conforms, which is the bulk of what makes Word refuse a file.

What is left for Word is the part a schema cannot describe: relationships,
content types, part-level rules, and Word's own opinions. A clean validation
makes a repair prompt unlikely; only Word makes it impossible. If Word *does*
prompt despite this, that is worth knowing precisely — it would mean the gap
between "conforms" and "Word accepts" is wider than assumed, and Phase 1
needs more than a validator.

## Test 3 — does inserting an example renumber the rest?

The point of the whole tool. **Already passed in OnlyOffice** (see 1b);
this is the same procedure in Word, and now a confirmation rather than an
open question.

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

- **Schema validation — done.** `make schemas` fetches the ECMA-376
  transitional schemas into a gitignored `.ooxml-schemas/`, and
  `tools/validate_docx.py` checks every XML part of a `.docx` for
  well-formedness and schema conformance. The sample passes. Both checks
  were mutation-tested — a cell placed outside a row, and a truncated
  part — and each is reported with its line.

  Wire it into CI in Phase 1, once there is emitter output worth
  validating; validating only the sample on every push would cost an 8 MB
  download to check a file nobody is editing.
- **Open the sample in OnlyOffice — done, 2026-09-25, and it passes.**
  Reads (1) and (2) with matching references, prints the same, and does not
  offer to repair the file. That is a second independent OOXML
  implementation *accepting* the markup, which is evidence of a different
  kind from the schema check: conformance says the file is well-formed
  against a standard, acceptance says a real reader will have it.

  It is also the reader that found the cache bug, by disagreeing with
  LibreOffice. Worth reaching for early whenever the emitter changes.

None of these can answer Test 1. Field recalculation is behaviour, not
markup, and only an implementation can tell you.

---

## When you have answers

Put them in `plan-docx.md`'s "Verified facts", with the date and which Word
— version and platform — said so. The whole point of that section is that a
later reader can tell a measurement from an assumption, and "Word does it"
without a version is an assumption wearing a measurement's clothes.

If Test 1 came back needing F9, edit Phase 2 to say the caches are written
correct at build time. If Test 2 came back with a repair prompt *despite*
the file validating, say so loudly — the validator exists now, so that
result would mean conformance is not enough and Phase 1 needs more than it.
