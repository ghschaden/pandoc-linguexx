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
r"""The names a reference and a caption print, in the document's language.

"section 1", "Abschnitt 1", "Table 1:", "Cuadro 1:" -- and three packages
supply them, each with its own idea of the language (measured,
tools/measure_names.py, which also checks this table):

- \cref's names are cleveref's, in the language given to cleveref or to
  the class as an option.  babel's option alone does NOT reach it: a
  German document with \usepackage[ngerman]{babel} and a bare
  \usepackage{cleveref} prints "section 1".
- \autoref's are hyperref's, which follows babel -- and stays English
  under polyglossia, which it does not know.
- A caption's "Table 1:" is babel's or polyglossia's, which do not always
  agree: "Table 1 – " in French under babel, "Tab. 1 : " under
  polyglossia.  Spanish captions say "Cuadro" while \autoref says "Tabla".

A language not measured prints English, and the run says so.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

#: Measured: python3 tools/measure_names.py --print
LANGUAGES = {
    "english": {
        "cref": {
            "section": [
                "section",
                "sections",
                "Section",
                "Sections"
            ],
            "table": [
                "table",
                "tables",
                "Table",
                "Tables"
            ],
            "figure": [
                "fig.",
                "figs.",
                "Figure",
                "Figures"
            ],
            "equation": [
                "eq.",
                "eqs.",
                "Equation",
                "Equations"
            ],
            "footnote": [
                "footnote",
                "footnotes",
                "Footnote",
                "Footnotes"
            ],
            "item": [
                "item",
                "items",
                "Item",
                "Items"
            ]
        },
        "page": [
            "page",
            "pages",
            "Page",
            "Pages"
        ],
        "pair": " and ",
        "list": [
            ", ",
            " and "
        ],
        "range": [
            "",
            " to "
        ],
        "groups_pair": " and ",
        "groups_list": [
            ", ",
            ", and "
        ],
        "autoref": {
            "section": "section",
            "subsection": "subsection",
            "subsubsection": "subsubsection",
            "table": "Table",
            "figure": "Figure",
            "equation": "Equation",
            "footnote": "footnote",
            "item": "item",
            "appendix": "Appendix"
        },
        "caption": {
            "table": [
                "Table",
                ": "
            ],
            "figure": [
                "Figure",
                ": "
            ]
        },
        "polyglossia_caption": {
            "table": [
                "Table",
                ": "
            ],
            "figure": [
                "Figure",
                ": "
            ]
        },
        "polyglossia_autoref": {
            "section": "section",
            "subsection": "subsection",
            "subsubsection": "subsubsection",
            "table": "Table",
            "figure": "Figure",
            "equation": "Equation",
            "footnote": "footnote",
            "item": "item",
            "appendix": "Appendix"
        }
    },
    "french": {
        "cref": {
            "section": [
                "section",
                "sections",
                "Section",
                "Sections"
            ],
            "table": [
                "tableau",
                "tableaux",
                "Tableau",
                "Tableaux"
            ],
            "figure": [
                "figure",
                "figures",
                "Figure",
                "Figures"
            ],
            "equation": [
                "équation",
                "équations",
                "Équation",
                "Équations"
            ],
            "footnote": [
                "note",
                "notes",
                "Note",
                "Notes"
            ],
            "item": [
                "point",
                "points",
                "Point",
                "Points"
            ]
        },
        "page": [
            "page",
            "pages",
            "Page",
            "Pages"
        ],
        "pair": " et ",
        "list": [
            ", ",
            " et "
        ],
        "range": [
            "",
            " à "
        ],
        "groups_pair": " et ",
        "groups_list": [
            ", ",
            ", et "
        ],
        "autoref": {
            "section": "section",
            "subsection": "sous-section",
            "subsubsection": "sous-sous-section",
            "table": "tableau",
            "figure": "figure",
            "equation": "équation",
            "footnote": "note",
            "item": "item",
            "appendix": "annexe"
        },
        "caption": {
            "table": [
                "Table",
                " – "
            ],
            "figure": [
                "Figure",
                " – "
            ]
        },
        "polyglossia_caption": {
            "table": [
                "Tab.",
                " : "
            ],
            "figure": [
                "Fig.",
                " : "
            ]
        },
        "polyglossia_autoref": {
            "section": "section",
            "subsection": "subsection",
            "subsubsection": "subsubsection",
            "table": "Table",
            "figure": "Figure",
            "equation": "Equation",
            "footnote": "footnote",
            "item": "item",
            "appendix": "Appendix"
        }
    },
    "german": {
        "cref": {
            "section": [
                "Abschnitt",
                "Abschnitte",
                "Abschnitt",
                "Abschnitte"
            ],
            "table": [
                "Tabelle",
                "Tabellen",
                "Tabelle",
                "Tabellen"
            ],
            "figure": [
                "Abb.",
                "Abb.",
                "Abbildung",
                "Abbildungen"
            ],
            "equation": [
                "Gleichung",
                "Gleichungen",
                "Gleichung",
                "Gleichungen"
            ],
            "footnote": [
                "Fußnote",
                "Fußnoten",
                "Fußnote",
                "Fußnoten"
            ],
            "item": [
                "Punkt",
                "Punkte",
                "Punkt",
                "Punkte"
            ]
        },
        "page": [
            "Seite",
            "Seiten",
            "Seite",
            "Seiten"
        ],
        "pair": " und ",
        "list": [
            ", ",
            " und "
        ],
        "range": [
            "",
            " bis "
        ],
        "groups_pair": " und ",
        "groups_list": [
            ", ",
            " und "
        ],
        "autoref": {
            "section": "Abschnitt",
            "subsection": "Unterabschnitt",
            "subsubsection": "Unterunterabschnitt",
            "table": "Tabelle",
            "figure": "Abbildung",
            "equation": "Gleichung",
            "footnote": "Fußnote",
            "item": "Punkt",
            "appendix": "Anhang"
        },
        "caption": {
            "table": [
                "Tabelle",
                ": "
            ],
            "figure": [
                "Abbildung",
                ": "
            ]
        },
        "polyglossia_caption": {
            "table": [
                "Tabelle",
                ": "
            ],
            "figure": [
                "Abbildung",
                ": "
            ]
        },
        "polyglossia_autoref": {
            "section": "section",
            "subsection": "subsection",
            "subsubsection": "subsubsection",
            "table": "Table",
            "figure": "Figure",
            "equation": "Equation",
            "footnote": "footnote",
            "item": "item",
            "appendix": "Appendix"
        }
    },
    "spanish": {
        "cref": {
            "section": [
                "apartado",
                "apartados",
                "Apartado",
                "Apartados"
            ],
            "table": [
                "cuadro",
                "cuadros",
                "Cuadro",
                "Cuadros"
            ],
            "figure": [
                "figura",
                "figuras",
                "Figura",
                "Figuras"
            ],
            "equation": [
                "ecuación",
                "ecuaciones",
                "Ecuación",
                "Ecuaciones"
            ],
            "footnote": [
                "nota",
                "notas",
                "Nota",
                "Notas"
            ],
            "item": [
                "punto",
                "puntos",
                "Punto",
                "Puntos"
            ]
        },
        "page": [
            "página",
            "páginas",
            "Página",
            "Páginas"
        ],
        "pair": " y ",
        "list": [
            ", ",
            " y "
        ],
        "range": [
            "",
            " a "
        ],
        "groups_pair": " y ",
        "groups_list": [
            ", ",
            " y "
        ],
        "autoref": {
            "section": "Sección",
            "subsection": "Subsección",
            "subsubsection": "Subsubsección",
            "table": "Tabla",
            "figure": "Figura",
            "equation": "Ecuación",
            "footnote": "Nota a pie de página",
            "item": "Elemento",
            "appendix": "Apéndice"
        },
        "caption": {
            "table": [
                "Cuadro",
                ": "
            ],
            "figure": [
                "Figura",
                ": "
            ]
        },
        "polyglossia_caption": {
            "table": [
                "Cuadro",
                ": "
            ],
            "figure": [
                "Figura",
                ": "
            ]
        },
        "polyglossia_autoref": {
            "section": "section",
            "subsection": "subsection",
            "subsubsection": "subsubsection",
            "table": "Table",
            "figure": "Figure",
            "equation": "Equation",
            "footnote": "footnote",
            "item": "item",
            "appendix": "Appendix"
        }
    },
    "italian": {
        "cref": {
            "section": [
                "sezione",
                "sezioni",
                "Sezione",
                "Sezioni"
            ],
            "table": [
                "tabella",
                "tabelle",
                "Tabella",
                "Tabelle"
            ],
            "figure": [
                "fig.",
                "fig.",
                "Figura",
                "Figure"
            ],
            "equation": [
                "eq.",
                "eq.",
                "Equazione",
                "Equazioni"
            ],
            "footnote": [
                "nota",
                "note",
                "Nota",
                "Note"
            ],
            "item": [
                "voce",
                "voci",
                "Voce",
                "Voci"
            ]
        },
        "page": [
            "pagina",
            "pagine",
            "Pagina",
            "Pagine"
        ],
        "pair": " e ",
        "list": [
            ", ",
            " e "
        ],
        "range": [
            "da ",
            " a "
        ],
        "groups_pair": " e ",
        "groups_list": [
            ", ",
            " e "
        ],
        "autoref": {
            "section": "sezione",
            "subsection": "sottosezione",
            "subsubsection": "sottosottosezione",
            "table": "Tabella",
            "figure": "Figura",
            "equation": "Equazione",
            "footnote": "nota",
            "item": "punto",
            "appendix": "Appendice"
        },
        "caption": {
            "table": [
                "Tabella",
                ": "
            ],
            "figure": [
                "Figura",
                ": "
            ]
        },
        "polyglossia_caption": {
            "table": [
                "Tabella",
                ": "
            ],
            "figure": [
                "Figura",
                ": "
            ]
        },
        "polyglossia_autoref": {
            "section": "section",
            "subsection": "subsection",
            "subsubsection": "subsubsection",
            "table": "Table",
            "figure": "Figure",
            "equation": "Equation",
            "footnote": "footnote",
            "item": "item",
            "appendix": "Appendix"
        }
    },
    "portuguese": {
        "cref": {
            "section": [
                "seção",
                "seções",
                "Seção",
                "Seções"
            ],
            "table": [
                "tabela",
                "tabelas",
                "Tabela",
                "Tabelas"
            ],
            "figure": [
                "fig.",
                "figs.",
                "Figura",
                "Figuras"
            ],
            "equation": [
                "eq.",
                "eqs.",
                "Equação",
                "Equações"
            ],
            "footnote": [
                "nota de rodapé",
                "notas de rodapé",
                "Nota de rodapé",
                "Notas de rodapé"
            ],
            "item": [
                "item",
                "itens",
                "Item",
                "Itens"
            ]
        },
        "page": [
            "página",
            "páginas",
            "Página",
            "Páginas"
        ],
        "pair": " e ",
        "list": [
            ", ",
            " e "
        ],
        "range": [
            "",
            " a "
        ],
        "groups_pair": " e ",
        "groups_list": [
            ", ",
            ", e "
        ],
        "autoref": {
            "section": "Seção",
            "subsection": "Subseção",
            "subsubsection": "Subsubseção",
            "table": "Tabela",
            "figure": "Figura",
            "equation": "Equação",
            "footnote": "Nota de rodapé",
            "item": "Item",
            "appendix": "Apêndice"
        },
        "caption": {
            "table": [
                "Tabela",
                ": "
            ],
            "figure": [
                "Figura",
                ": "
            ]
        },
        "polyglossia_caption": {
            "table": [
                "Tabela",
                ": "
            ],
            "figure": [
                "Figura",
                ": "
            ]
        },
        "polyglossia_autoref": {
            "section": "section",
            "subsection": "subsection",
            "subsubsection": "subsubsection",
            "table": "Table",
            "figure": "Figure",
            "equation": "Equation",
            "footnote": "footnote",
            "item": "item",
            "appendix": "Appendix"
        }
    },
    "dutch": {
        "cref": {
            "section": [
                "paragraaf",
                "paragrafen",
                "Paragraaf",
                "Paragrafen"
            ],
            "table": [
                "tabel",
                "tabellen",
                "Tabel",
                "Tabellen"
            ],
            "figure": [
                "fig.",
                "fig.’s",
                "Figuur",
                "Figuren"
            ],
            "equation": [
                "verg.",
                "verg.’s",
                "Vergelĳking",
                "Vergelĳkingen"
            ],
            "footnote": [
                "voetnoot",
                "voetnoten",
                "Voetnoot",
                "Voetnoten"
            ],
            "item": [
                "punt",
                "punten",
                "Punt",
                "Punten"
            ]
        },
        "page": [
            "pagina",
            "pagina’s",
            "Pagina",
            "Pagina’s"
        ],
        "pair": " en ",
        "list": [
            ", ",
            " en "
        ],
        "range": [
            "",
            " tot "
        ],
        "groups_pair": " en ",
        "groups_list": [
            ", ",
            " en "
        ],
        "autoref": {
            "section": "paragraaf",
            "subsection": "deelparagraaf",
            "subsubsection": "deel-deelparagraaf",
            "table": "Tabel",
            "figure": "Figuur",
            "equation": "Vergelijking",
            "footnote": "voetnoot",
            "item": "punt",
            "appendix": "Bijlage"
        },
        "caption": {
            "table": [
                "Tabel",
                ": "
            ],
            "figure": [
                "Figuur",
                ": "
            ]
        },
        "polyglossia_caption": {
            "table": [
                "Tabel",
                ": "
            ],
            "figure": [
                "Figuur",
                ": "
            ]
        },
        "polyglossia_autoref": {
            "section": "section",
            "subsection": "subsection",
            "subsubsection": "subsubsection",
            "table": "Table",
            "figure": "Figure",
            "equation": "Equation",
            "footnote": "footnote",
            "item": "item",
            "appendix": "Appendix"
        }
    }
}


#: The names each package knows a language by, to the table's key.
ALIASES = {
    **dict.fromkeys(("english", "american", "british", "usenglish", "ukenglish",
                     "canadian", "australian", "newzealand"), "english"),
    **dict.fromkeys(("french", "francais", "frenchb", "acadian", "canadien"), "french"),
    **dict.fromkeys(("german", "ngerman", "austrian", "naustrian", "swissgerman",
                     "nswissgerman"), "german"),
    **dict.fromkeys(("spanish", "spanishmx"), "spanish"),
    **dict.fromkeys(("italian",), "italian"),
    **dict.fromkeys(("brazilian", "brazil", "portuguese", "portuges"), "portuguese"),
    **dict.fromkeys(("dutch",), "dutch"),
}

#: Language options a document may give that this has no table for: they
#: are languages all the same, so they still decide which one is last.
OTHER_LANGUAGES = frozenset("""
    afrikaans albanian arabic basque bulgarian catalan croatian czech danish
    esperanto estonian finnish galician greek hebrew hungarian icelandic
    indonesian irish latin latvian lithuanian magyar norsk nynorsk polish
    romanian russian serbian slovak slovene slovenian swedish turkish
    ukrainian welsh
""".split())


@dataclass(frozen=True)
class Names:
    cleveref: dict
    """The table entry \\cref's names come from."""
    babel: dict
    """The one captions and \\autoref's names come from."""
    polyglossia: bool = False

    def cref(self, kind: str, plural: bool = False, capital: bool = False) -> str:
        if kind == "page":
            return self.cleveref["page"][2 * capital + plural]
        return self.cleveref["cref"][kind][2 * capital + plural]

    def autoref(self, name: str) -> str:
        table = (LANGUAGES["english"]["autoref"] if self.polyglossia
                 else self.babel["autoref"])
        return table[name]

    def caption(self, kind: str) -> tuple[str, str]:
        """("Table", ": "): the name, and what goes between number and text."""
        name, sep = self.babel["polyglossia_caption" if self.polyglossia
                               else "caption"][kind]
        return name, sep

    @property
    def pair(self) -> str:
        return self.cleveref["pair"]

    @property
    def list(self) -> list[str]:
        return self.cleveref["list"]

    @property
    def range(self) -> list[str]:
        return self.cleveref["range"]

    @property
    def groups_pair(self) -> str:
        return self.cleveref["groups_pair"]

    @property
    def groups_list(self) -> list[str]:
        return self.cleveref["groups_list"]


ENGLISH = Names(LANGUAGES["english"], LANGUAGES["english"])


def _options(src: str, package: str) -> list[str]:
    opts: list[str] = []
    for m in re.finditer(r"\\usepackage\s*\[([^\]]*)\]\s*\{([^}]*)\}", src):
        if package in [p.strip() for p in m.group(2).split(",")]:
            opts += [o.strip() for o in m.group(1).split(",")]
    return opts


def _languages(options: list[str]) -> list[str]:
    out = []
    for o in options:
        o = o.strip().lower()
        if o.startswith("main="):
            out.append(o[5:])
        elif o in ALIASES or o in OTHER_LANGUAGES:
            out.append(o)
    return out


def detect(src: str, warn=lambda _m: None) -> Names:
    """The names *src*'s preamble asks for."""
    preamble = src.split("\\begin{document}", 1)[0]
    preamble = re.sub(r"(?<!\\)%.*", "", preamble)
    cls = re.search(r"\\documentclass\s*\[([^\]]*)\]", preamble)
    class_langs = _languages(cls.group(1).split(",") if cls else [])
    babel_opts = _options(preamble, "babel")
    main = [o.split("=", 1)[1].strip().lower() for o in babel_opts
            if o.strip().lower().startswith("main=")]
    babel_langs = main or class_langs + _languages(babel_opts)
    poly = re.search(r"\\set(?:main|default)language\s*(?:\[[^\]]*\])?\s*\{([^}]*)\}",
                     preamble)
    cref_langs = _languages(_options(preamble, "cleveref")) or class_langs

    def entry(lang: str | None, what: str) -> dict:
        if lang is None:
            return LANGUAGES["english"]
        key = ALIASES.get(lang)
        if key is None:
            warn(f"{what} in {lang}, which the converter has no names for: "
                 "printed in English")
            return LANGUAGES["english"]
        return LANGUAGES[key]

    uses_babel = bool(re.search(r"\\usepackage\s*(?:\[[^\]]*\])?\s*\{[^}]*\bbabel\b", preamble))
    if poly:
        caption_lang = poly.group(1).strip().lower()
    elif uses_babel and babel_langs:
        caption_lang = babel_langs[-1]
    else:
        caption_lang = None
    return Names(entry(cref_langs[-1] if cref_langs else None, "\\cref's names"),
                 entry(caption_lang, "captions and \\autoref's names"),
                 polyglossia=bool(poly))
