#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Gerhard Schaden
#
# Regenerate the manual's figures: each source in src/ is converted with
# this checkout's linguexx2odt, laid out by LibreOffice, and cropped to its
# ink.  The PDFs are committed, so the manual builds without LibreOffice;
# run this after a change that alters what the converter writes.
#
#   sh docs/manual/figures/make-figures.sh
#
# Needs pandoc, soffice and pdfcrop (TeX Live).
set -eu
here=$(cd "$(dirname "$0")" && pwd)
root=$(cd "$here/../../.." && pwd)
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT

for src in "$here"/src/*.tex; do
    name=$(basename "$src" .tex)
    for to in odt docx; do
        PYTHONPATH="$root/src" python3 -m linguexx2odt "$src" \
            -o "$work/$name-$to.$to" --to "$to" -q
        soffice --headless --convert-to pdf --outdir "$work" \
            "$work/$name-$to.$to" >/dev/null 2>&1
        # the page number in the footer is ink too: cut the bottom of the
        # page away first, then crop what is left to its ink
        pdfcrop --bbox "0 90 612 842" "$work/$name-$to.pdf" "$work/$name-$to-body.pdf" >/dev/null
        pdfcrop --margins 4 "$work/$name-$to-body.pdf" "$work/$name-$to-crop.pdf" >/dev/null
        cp "$work/$name-$to-crop.pdf" "$here/$name-$to.pdf"
    done
done
echo "figures written to $here"
