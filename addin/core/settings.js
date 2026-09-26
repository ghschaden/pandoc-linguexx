// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 Gerhard Schaden
//
// This file is part of pandoc-linguexx.

/**
 * The five lengths that are house style rather than measurement -- the
 * Writer macro's Example layout, for the add-ins.
 *
 *     |<- indent ->|(1)|<- number ->|a.|<- marker ->|Esto es un ejemplo
 *
 * plus the space above and below an example.  Kept where the macro keeps
 * them, so one document carries its settings between Writer, Word and
 * OnlyOffice: the three indents as user-defined document properties under
 * the macro's own names -- a .docx's custom properties, which LibreOffice
 * reads as user-defined ones (measured) -- and the two spacings as the
 * LxExampleSpace styles themselves.  tests/test_addin_core.py holds the
 * names and the limit to the macro's Const declarations.
 *
 * The indents apply to examples built afterwards; changing a spacing
 * restyles every example at once, because it is a style.
 */

import { LAYOUT, NAMES } from "./constants.js";

/** The macro's OPT_INDENT, OPT_NUMBER and OPT_MARKER. */
export const OPT = Object.freeze({
  indent: "LinguExxIndentCm",
  number: "LinguExxNumberCm",
  marker: "LinguExxMarkerCm",
});

/** The macro's OPT_MAX_CM: the largest any of the five will take. */
export const OPT_MAX_CM = 10.0;

export const DEFAULTS = Object.freeze({
  indentCm: 0,
  numberCm: LAYOUT.number_cm,
  markerCm: LAYOUT.marker_cm,
  aboveCm: LAYOUT.space_cm,
  belowCm: LAYOUT.space_cm,
});

/** One property's value, or the default -- LxOpt: prose or out of range is ignored. */
function opt(value, fallback) {
  const n = typeof value === "number" ? value : Number(value);
  return Number.isFinite(n) && n >= 0 && n <= OPT_MAX_CM ? n : fallback;
}

/**
 * The document's settings.  *props* maps property names to their values
 * (absent ones are defaults); *spacing* is {aboveCm, belowCm} as the
 * styles say, either absent for "not set".
 */
export function readSettings(props = {}, spacing = {}) {
  return {
    indentCm: opt(props[OPT.indent], DEFAULTS.indentCm),
    numberCm: opt(props[OPT.number], DEFAULTS.numberCm),
    markerCm: opt(props[OPT.marker], DEFAULTS.markerCm),
    aboveCm: opt(spacing.aboveCm, DEFAULTS.aboveCm),
    belowCm: opt(spacing.belowCm, DEFAULTS.belowCm),
  };
}

/**
 * "" when every length will do, else what the user is told -- the macro's
 * words.  Refused rather than clamped: a value silently made something else
 * is worse than one the user is asked to type again (LxWriteLayout).
 */
export function checkSettings(s) {
  for (const k of ["indentCm", "numberCm", "markerCm", "aboveCm", "belowCm"]) {
    const v = s[k];
    if (typeof v !== "number" || !Number.isFinite(v) || v < 0 || v > OPT_MAX_CM) {
      return `Every length has to be between 0 and ${OPT_MAX_CM.toFixed(0)} cm.`;
    }
  }
  return "";
}

/**
 * How the two spacings go into the styles -- LxApplySpacing.  Equal, they
 * live on the parent and both children inherit, so one edit of
 * LxExampleSpace in the Styles pane still moves both sides; unequal, each
 * child breaks away with its own.  [{style, cm}] or [{style, inherit}].
 */
export function spacingPlan(aboveCm, belowCm) {
  if (Math.abs(aboveCm - belowCm) < 0.001) {
    return [
      { style: NAMES.SPACE_PARA, cm: aboveCm },
      { style: NAMES.SPACE_ABOVE, inherit: true },
      { style: NAMES.SPACE_BELOW, inherit: true },
    ];
  }
  return [{ style: NAMES.SPACE_ABOVE, cm: aboveCm }, { style: NAMES.SPACE_BELOW, cm: belowCm }];
}

/**
 * The indent an example actually gets on a text block *widthCm* wide:
 * at most half of it -- the floor under a property typed by hand on a
 * narrow page, where the alternative is no room for the example (LxLayOut).
 */
export function effectiveIndent(indentCm, widthCm) {
  return Math.max(0, Math.min(indentCm, widthCm / 2));
}
