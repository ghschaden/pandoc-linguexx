# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Gerhard Schaden
"""linguexx 1.5: shared rows, morpheme boundaries, language scope and rendering."""
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

from linguexx2odt.cli import main
from linguexx2odt.emit_base import emitter_for
from linguexx2odt.extract import parse
from linguexx2odt.gloss import morphemes
from linguexx2odt import reverse, postprocess
from linguexx2odt.styles import Layout

COMMON = r"""\documentclass{article}
\usepackage{linguexx}
\begin{document}
\ex.\label{shared} VARIANTS
\ag.\label{rowa} * Alpha {} Cappa \exannot{ANNA}\\
\bg. Beta Longer Delta \exannot{ANNB}\\
\CommonGloss FIRST SECOND THIRD\\
\CommonGloss ONE TWO THREE\\
\glt TRANSLATION.

References: \ref{shared}, \ref{rowa}.
\end{document}
"""

MORPH = r"""\documentclass{article}
\usepackage{linguexx}
\begin{document}
\GlossMorphAlign
\ex. \glll Aaaaaaaaa-ab-ac \\
           ba-Bbbbbbbbb-bc \\
           ca-cb-Ccccccccc \\
\glt MORPHTRANS.

\end{document}
"""


def emitted(source, target, width=16):
    parsed = parse(source)
    emitter = emitter_for(target, layout=Layout(text_width_cm=width), labels=parsed.labels)
    emitter.prepare(parsed.examples)
    xml = emitter.example(parsed.examples[0])
    return parsed, emitter, xml


@pytest.mark.parametrize(('word', 'parts'), [
    ('ev-ler-de', ('ev', '-ler', '-de')),
    ('ev=ler', ('ev', '=ler')),
    ('{in-law}-mother', ('{in-law}', '-mother')),
    ('{ev-ler}', ('{ev-ler}',)),
    ('-t', ('-t',)), ('stem-', ('stem-',)),
    ('a--b', ('a--b',)), ('a–b', ('a–b',)),
    (r'\lpzg{a-b}=c', (r'\lpzg{a-b}', '=c')),
    (r'a-\mvto{x}{b}', (r'a-\mvto{x}{b}',)),
])
def test_morpheme_boundaries(word, parts):
    assert morphemes(word) == parts


def test_settings_are_scoped_to_groups_environments_examples_and_items():
    src = r"""\GlossTierLang{1}{de}\GlossTierLang{2}{es}
{\GlossMorphAlign
\ex. \gll Hund \\ perro \\ \glt uno

\begin{quote}\GlossMorphAlignOff
\ex. \gll Katze \\ gato \\ \glt dos

\end{quote}
\ex. \GlossTierLang{2}{}\GlossTransLang{fr}\gll Kuh \\ cow \\ \glt trois

}
\ex. \a. \GlossTransLang{it}\gll Maus \\ ratón \\ \glt quattro
\b. \gll Vogel \\ pájaro \\ \glt cinco

\ex. \GlossTierLang{2}{}\gll Fisch \\ fish \\ \glt six

\ex. \glll Hund \\ perro \\ dog \\ \glt seven

"""
    r = parse(src)
    bodies = [b for ex in r.examples for b in ex.bodies]
    assert [b.morph_align for b in bodies] == [True, False, True, False, False, False, False]
    assert [b.translation_language for b in bodies] == ['es', 'es', 'fr', 'it', 'es', '', '']
    assert bodies[2].tiers[1].language == ''
    assert bodies[4].tiers[1].language == 'es'
    assert r'\Gloss' not in r.residue


def test_common_gloss_keeps_rows_gaps_marks_and_shared_translation():
    r = parse(COMMON)
    ex = r.examples[0]
    assert ex.head == 'VARIANTS'
    assert ex.items[0].body.tiers[0].cells == ('Alpha', '', 'Cappa')
    assert ex.items[0].body.judgment == '*'
    assert ex.items[0].body.annot == 'ANNA'
    assert ex.items[1].body.annot == 'ANNB'
    assert len(ex.shared.tiers) == 2
    assert ex.shared.translation == 'TRANSLATION.'
    assert r.labels['rowa'] == (0, 'a')
    assert not r.warnings


@pytest.mark.parametrize('target', ['odt', 'docx'])
def test_common_gloss_columns_are_shared_and_bands_interleave(target):
    _, e, xml = emitted(COMMON, target, width=5)
    ex = parse(COMMON).examples[0]
    plan = e.plan_table(ex)
    assert len(plan.grid.bands_of(0)) > 1
    assert all(p == plan.grid.plans[0] for p in plan.grid.plans)
    # Column one in all rows must precede column two in any row.
    assert xml.index('Alpha') < xml.index('Beta') < xml.index('FIRST') < xml.index('SECOND')
    assert xml.count('TRANSLATION.') == 1


@pytest.mark.parametrize('target', ['odt', 'docx'])
def test_morpheme_tabs_are_identical_across_tiers(target):
    r, e, xml = emitted(MORPH, target)
    body = r.examples[0].body
    tabs = [e.morph_parts(body, t, 0)[1] for t in body.tiers]
    assert len(tabs[0]) == 2 and tabs[0] == tabs[1] == tabs[2]
    assert ('<text:tab/>' if target == 'odt' else '<w:tab/>') in xml


@pytest.mark.parametrize('source', [
    r'\glll a-b \\ x-y-z \\ c-d \\',
    r'\glll a-\mvto{x}{b} \\ c-d \\ e-f \\',
    r'\gll {a-b} \\ c-d \\',
])
def test_mismatches_protection_and_moves_do_not_align(source):
    r, e, _ = emitted('\\GlossMorphAlign\n\\ex. ' + source, 'docx')
    b = r.examples[0].body
    assert all(not e.morph_parts(b, t, 0)[1] for t in b.tiers)
    if 'x-y-z' in source:
        assert any('morpheme count mismatch in column 1' in w for w in e.warnings)


def test_judgment_does_not_remove_morpheme_protection():
    r = parse(r'\GlossMorphAlign \ex. \gll * {a-b} c-d \\ x-y z-w \\')
    assert r.examples[0].body.tiers[0].segments == (('{a-b}',), ('c', '-d'))


@pytest.mark.parametrize('target', ['odt', 'docx'])
def test_language_is_written_to_tiers_and_translation(tmp_path, target):
    source = (r'\documentclass{article}\usepackage{linguexx}'
              r'\GlossTierLang{1}{de}\GlossTierLang{2}{es-MX}\begin{document}'
              r'\ex. \gll Hund \\ perro \\ \glt Traducción.' '\n\n'
              r'\end{document}')
    tex = tmp_path / 'lang.tex'
    tex.write_text(source)
    out = tmp_path / f'lang.{target}'
    assert main([str(tex), '--to', target, '-o', str(out), '-q']) == 0
    xml = postprocess.read(out, 'content.xml' if target == 'odt' else 'word/document.xml')
    ET.fromstring(xml)
    assert ('style:rfc-language-tag="es-MX"' if target == 'odt' else 'w:val="es-MX"') in xml


@pytest.mark.parametrize('source', [COMMON, MORPH])
def test_new_layouts_round_trip_through_docx(tmp_path: Path, source):
    tex, out, back = (tmp_path / name for name in ('doc.tex', 'doc.docx', 'back.tex'))
    tex.write_text(source)
    assert main([str(tex), '--to', 'docx', '-o', str(out), '-q']) == 0
    reverse.convert(out, back, lambda _: None)
    before, after = parse(source).examples[0], parse(back.read_text()).examples[0]
    assert before.head == after.head
    assert [t.cells for b in before.bodies for t in b.tiers] == [
        t.cells for b in after.bodies for t in b.tiers]
    assert [b.translation for b in before.bodies] == [b.translation for b in after.bodies]


def test_exrefcheck_does_not_print_its_options():
    r = parse(r'\exrefcheck[words=12]\ex. Text.' + '\n\n')
    assert 'words=12' not in r.residue
    assert not r.warnings


def test_rtl_is_explicitly_out_of_scope():
    r = parse(r'\GlossRTL\ex. \gll א ב \\ a b \\')
    assert any('right-to-left gloss layout is not supported' in w for w in r.warnings)


def test_reference_report_includes_both_range_ends_and_relative_targets():
    r = parse(r'''\exrefcheck[words=2]
See \Next.
\ex.\label{a} Alpha beta gamma.

\ex.\label{b} Delta epsilon zeta. Previous \Last.

Range \Refrange{a}{b}. % \Next is not a reference here
''')
    assert len(r.reference_report) == 4
    assert 'Alpha beta' in r.reference_report[0] and 'gamma' not in r.reference_report[0]
    assert 'Delta epsilon' in r.reference_report[1]
    assert r'\Refrange{a} -> 1' in r.reference_report[2]
    assert r'\Refrange{b} -> 2' in r.reference_report[3]
    assert r'(\pref{a})–(\pref{b})' in r.residue


@pytest.mark.parametrize('target', ['odt', 'docx'])
@pytest.mark.parametrize('source', [COMMON, MORPH], ids=['shared', 'morph'])
def test_rendered_alignment_and_odt_round_trip(tmp_path, target, source):
    import subprocess
    import pdfwords
    tex = tmp_path / 'proof.tex'
    tex.write_text(source)
    out = tmp_path / f'proof.{target}'
    assert main([str(tex), '--to', target, '-o', str(out), '-q']) == 0
    subprocess.run(['soffice', '--headless', f'-env:UserInstallation=file://{tmp_path}/lo',
                    '--convert-to', 'pdf', '--outdir', str(tmp_path), str(out)],
                   check=True, capture_output=True, timeout=120)
    x = pdfwords.first_x(out.with_suffix('.pdf'))
    if source == COMMON:
        for a, b in [('Beta', 'FIRST'), ('Longer', 'SECOND'),
                     ('Cappa', 'Delta'), ('Cappa', 'THIRD'), ('ANNA', 'ANNB'),
                     ('VARIANTS', 'TRANSLATION.')]:
            assert abs(x[a] - x[b]) < 0.5, (a, b, x)
    else:
        # In the widest tier the adjoining parts form one PDF token.
        assert abs(x[next(w for w in x if w.startswith('-Bbbbbbbbb'))] - x['-cb']) < 0.5, x
        assert abs(x['-ac'] - x['-Ccccccccc']) < 0.5, x
    if target == 'odt':
        docx = reverse.odt_to_docx(out, tmp_path / 'roundtrip')
        back = tmp_path / 'back.tex'
        reverse.convert(docx, back, lambda _: None)
        before, after = parse(source).examples[0], parse(back.read_text()).examples[0]
        assert [t.cells for b in before.bodies for t in b.tiers] == [
            t.cells for b in after.bodies for t in b.tiers]


def test_explicit_latin_alphabet_is_recognized():
    r = parse(r"\let\Exalph\ExLatinAlph\begin{document}\ex. \a. First.\b. Second.")
    assert [i.marker for i in r.examples[0].items] == ['a.', 'b.']
    assert not r.warnings


@pytest.mark.parametrize('target', ['odt', 'docx'])
def test_squeezed_morphemes_fall_back_without_overflowing_tabs(target):
    r = parse(MORPH)
    e = emitter_for(target, layout=Layout(text_width_cm=2), split=False)
    e.prepare(r.examples)
    xml = e.example(r.examples[0])
    assert ('<text:tab/>' if target == 'odt' else '<w:tab/>') not in xml
    assert any('morpheme alignment disabled' in w for w in e.warnings)
