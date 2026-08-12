#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Gerhard Schaden
#
# This file is part of pandoc-linguexx.
#
# pandoc-linguexx is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by the
# Free Software Foundation, either version 3 of the License, or (at your
# option) any later version.
#
# pandoc-linguexx is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# General Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program.  If not, see <https://www.gnu.org/licenses/>.

"""Package the Writer macro as a LibreOffice extension.

    python3 tools/build_oxt.py [-o dist/linguexx-0.1.0.oxt]

An installed extension is the right way to hand this to someone who is not
going to paste Basic into an IDE: it lands in the menu, it can carry a
keyboard shortcut, and — unlike macros embedded in a document — it raises
no macro-security warning every time a file is opened.

Install and remove with:

    unopkg add   linguexx-0.1.0.oxt
    unopkg remove net.schaden.linguexx
"""

from __future__ import annotations

import argparse
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from linguexx2odt import writermacro  # noqa: E402

IDENTIFIER = "net.schaden.linguexx"
LIBRARY = "LinguExx"
MODULE = "Gloss"

DESCRIPTION = """<?xml version="1.0" encoding="UTF-8"?>
<description xmlns="http://openoffice.org/extensions/description/2006"
             xmlns:dep="http://openoffice.org/extensions/description/2006"
             xmlns:xlink="http://www.w3.org/1999/xlink">
  <identifier value="{identifier}"/>
  <version value="{version}"/>
  <display-name>
    <name lang="en">LinguExx — glossed linguistic examples</name>
    <name lang="fr">LinguExx — exemples linguistiques glosés</name>
  </display-name>
  <extension-description>
    <src lang="en" xlink:href="description-en.txt"/>
  </extension-description>
  <publisher>
    <name lang="en">Gerhard Schaden</name>
  </publisher>
  <dependencies>
    <OpenOffice.org-minimal-version value="4.1" dep:name="LibreOffice 4.1"/>
  </dependencies>
</description>
"""

DESCRIPTION_TXT = (
    "Turns selected lines into an aligned linguistic example: object "
    "language over glosses, a free translation, hanging judgment marks, and "
    "sub-example paradigms. Column widths are measured against the real "
    "font. Example numbers are live fields, so inserting an example "
    "renumbers the rest. The indents and the space above and below are "
    "set from the menu; everything else is a named style.\n"
)

MANIFEST = """<?xml version="1.0" encoding="UTF-8"?>
<manifest:manifest xmlns:manifest="http://openoffice.org/2001/manifest">
  <manifest:file-entry
      manifest:media-type="application/vnd.sun.star.basic-library"
      manifest:full-path="{library}/"/>
  <manifest:file-entry
      manifest:media-type="application/vnd.sun.star.configuration-data"
      manifest:full-path="Addons.xcu"/>
</manifest:manifest>
"""

# LibreOffice registers a Basic library folder as *both* a script and a
# dialog library, then reads dialog.xlb whether or not the extension has any
# dialogs.  Omitting it gives every GUI start
#     Error loading BASIC of document .../LinguExx/dialog.xlb: General Error.
# so ship an empty one.  Headless does not read it, which is why the harness
# was happy with a package the desktop rejected.
DIALOG_XLB = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE library:library PUBLIC "-//OpenOffice.org//DTD OfficeDocument 1.0//EN" "library.dtd">
<library:library xmlns:library="http://openoffice.org/2000/library"
    library:name="{library}" library:readonly="false"
    library:passwordprotected="false"/>
"""

SCRIPT_XLB = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE library:library PUBLIC "-//OpenOffice.org//DTD OfficeDocument 1.0//EN" "library.dtd">
<library:library xmlns:library="http://openoffice.org/2000/library"
    library:name="{library}" library:readonly="false"
    library:passwordprotected="false">
  <library:element library:name="{module}"/>
</library:library>
"""

MODULE_XBA = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE script:module PUBLIC "-//OpenOffice.org//DTD OfficeDocument 1.0//EN" "module.dtd">
<script:module xmlns:script="http://openoffice.org/2000/script"
    script:name="{module}" script:language="StarBasic"><![CDATA[{source}]]></script:module>
"""

# One menu, one entry per command.  The URL is the same script URL the
# harness invokes, so what the menu runs is what the tests exercise.
ADDONS_XCU = """<?xml version="1.0" encoding="UTF-8"?>
<oor:component-data xmlns:oor="http://openoffice.org/2001/registry"
                    xmlns:xs="http://www.w3.org/2001/XMLSchema"
                    oor:name="Addons" oor:package="org.openoffice.Office">
  <node oor:name="AddonUI">
    <node oor:name="OfficeMenuBar">
      <node oor:name="{identifier}" oor:op="replace">
        <prop oor:name="Title" oor:type="xs:string">
          <value xml:lang="en-US">LinguExx</value>
          <value xml:lang="fr">LinguExx</value>
        </prop>
        <prop oor:name="Target" oor:type="xs:string">
          <value>_self</value>
        </prop>
        <node oor:name="Submenu">
          <node oor:name="m01" oor:op="replace">
            <prop oor:name="URL" oor:type="xs:string">
              <value>vnd.sun.star.script:{library}.{module}.GlossSelection?language=Basic&amp;location=application</value>
            </prop>
            <prop oor:name="Title" oor:type="xs:string">
              <value xml:lang="en-US">Typeset example</value>
              <value xml:lang="fr">Composer l'exemple</value>
            </prop>
            <prop oor:name="Target" oor:type="xs:string">
              <value>_self</value>
            </prop>
            <prop oor:name="Context" oor:type="xs:string">
              <value>com.sun.star.text.TextDocument</value>
            </prop>
          </node>
          <node oor:name="m02" oor:op="replace">
            <prop oor:name="URL" oor:type="xs:string">
              <value>vnd.sun.star.script:{library}.{module}.TreeSelection?language=Basic&amp;location=application</value>
            </prop>
            <prop oor:name="Title" oor:type="xs:string">
              <value xml:lang="en-US">Typeset numbered tree</value>
              <value xml:lang="fr">Composer l'arbre numéroté</value>
            </prop>
            <prop oor:name="Target" oor:type="xs:string">
              <value>_self</value>
            </prop>
            <prop oor:name="Context" oor:type="xs:string">
              <value>com.sun.star.text.TextDocument</value>
            </prop>
          </node>
          <node oor:name="m03" oor:op="replace">
            <prop oor:name="URL" oor:type="xs:string">
              <value>vnd.sun.star.script:{library}.{module}.TreeSelectionBare?language=Basic&amp;location=application</value>
            </prop>
            <prop oor:name="Title" oor:type="xs:string">
              <value xml:lang="en-US">Typeset unnumbered tree</value>
              <value xml:lang="fr">Composer l'arbre sans numéro</value>
            </prop>
            <prop oor:name="Target" oor:type="xs:string">
              <value>_self</value>
            </prop>
            <prop oor:name="Context" oor:type="xs:string">
              <value>com.sun.star.text.TextDocument</value>
            </prop>
          </node>
          <node oor:name="m04" oor:op="replace">
            <prop oor:name="URL" oor:type="xs:string">
              <value>vnd.sun.star.script:{library}.{module}.UntypesetSelection?language=Basic&amp;location=application</value>
            </prop>
            <prop oor:name="Title" oor:type="xs:string">
              <value xml:lang="en-US">Untypeset example</value>
              <value xml:lang="fr">Décomposer l'exemple</value>
            </prop>
            <prop oor:name="Target" oor:type="xs:string">
              <value>_self</value>
            </prop>
            <prop oor:name="Context" oor:type="xs:string">
              <value>com.sun.star.text.TextDocument</value>
            </prop>
          </node>
          <node oor:name="m05" oor:op="replace">
            <prop oor:name="URL" oor:type="xs:string">
              <value>private:separator</value>
            </prop>
          </node>
          <node oor:name="m06" oor:op="replace">
            <prop oor:name="URL" oor:type="xs:string">
              <value>vnd.sun.star.script:{library}.{module}.LayoutSettings?language=Basic&amp;location=application</value>
            </prop>
            <prop oor:name="Title" oor:type="xs:string">
              <value xml:lang="en-US">Example layout…</value>
              <value xml:lang="fr">Mise en page des exemples…</value>
            </prop>
            <prop oor:name="Target" oor:type="xs:string">
              <value>_self</value>
            </prop>
            <prop oor:name="Context" oor:type="xs:string">
              <value>com.sun.star.text.TextDocument</value>
            </prop>
          </node>
        </node>
      </node>
    </node>
  </node>
</oor:component-data>
"""


def version() -> str:
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    for line in text.splitlines():
        if line.startswith("version"):
            return line.split("=", 1)[1].strip().strip('"')
    return "0.0.0"


def build(out: Path) -> Path:
    source = writermacro.source()
    if "]]>" in source:
        sys.exit("the macro contains ']]>', which cannot go inside a CDATA section")

    fields = dict(identifier=IDENTIFIER, library=LIBRARY, module=MODULE,
                  version=version(), source=source)
    members = {
        "description.xml": DESCRIPTION.format(**fields),
        "description-en.txt": DESCRIPTION_TXT,
        "META-INF/manifest.xml": MANIFEST.format(**fields),
        "Addons.xcu": ADDONS_XCU.format(**fields),
        f"{LIBRARY}/script.xlb": SCRIPT_XLB.format(**fields),
        f"{LIBRARY}/dialog.xlb": DIALOG_XLB.format(**fields),
        f"{LIBRARY}/{MODULE}.xba": MODULE_XBA.format(**fields),
    }

    out.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for name, text in members.items():
            z.writestr(name, text)
    return out


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("-o", "--output", type=Path,
                   default=ROOT / "dist" / f"linguexx-{version()}.oxt")
    args = p.parse_args(argv)
    out = build(args.output)
    print(f"{out}  ({out.stat().st_size} bytes)")
    print(f"install with:  unopkg add {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
