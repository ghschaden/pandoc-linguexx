// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 Gerhard Schaden
//
// This file is part of pandoc-linguexx.

/*
 * The OnlyOffice plugin's panel: the buttons, and the round trips to the
 * editor.  Everything else is in linguexx.js (tools/build_onlyoffice.py):
 * job.js decides, commands.js runs inside the editor.
 *
 * Unlike Word on the web, OnlyOffice renumbers: commands.insertExample
 * ends with UpdateAllFields (S7 fact 2), so there is nothing stale to
 * report -- the one cost is that a user's other fields (a DATE, a table of
 * contents) are refreshed with ours, which S7 recorded.  What carries over
 * from the Word pane is the rule that a click is answered at once and a
 * second click finds the buttons disabled.
 */

/* global LinguExx */

(function (window) {
  "use strict";
  var plugin = window.Asc.plugin;
  var working = false;

  function $(id) { return document.getElementById(id); }
  function say(message, kind) {
    $("status").className = kind || "";
    $("status").textContent = message;
  }
  function note(lines) {
    $("notes").textContent = (lines || []).filter(Boolean).join("\n\n");
  }

  /** Disable every button while the editor works; re-enable when done. */
  function busy(message) {
    if (working) return false;
    working = true;
    Array.prototype.forEach.call(document.querySelectorAll("button"), function (b) { b.disabled = true; });
    say(message);
    return true;
  }
  function idle() {
    working = false;
    Array.prototype.forEach.call(document.querySelectorAll("button"), function (b) { b.disabled = false; });
  }

  function typeset() {
    if (!busy("Typesetting…")) return;
    note([]);
    plugin.callCommand(LinguExx.readSelection, false, false, function (read) {
      var prep;
      try {
        prep = LinguExx.prepareJob(read || { error: "The editor returned nothing for the selection." });
      } catch (e) {
        idle();
        return say(String(e.message || e), "error");
      }
      if (prep.refusal) { idle(); return say(prep.refusal, "error"); }
      window.Asc.scope.job = prep.job;
      plugin.callCommand(LinguExx.insertExample, false, true, function (res) {
        idle();
        if (!res || res.error) return say((res && res.error) || "The example was not inserted.", "error");
        say("Done: example (" + res.number + ").", "ok");
        note(prep.notes);
      });
    });
  }

  function listExamples() {
    if (!busy("Reading the document's examples…")) return;
    var list = $("examples");
    list.textContent = "";
    plugin.callCommand(LinguExx.listExamples, false, false, function (examples) {
      idle();
      examples = examples || [];
      examples.forEach(function (ex) {
        var li = document.createElement("li");
        var b = document.createElement("button");
        b.className = "btn-text-default";
        b.textContent = "(" + ex.number + ") " + ex.preview;
        b.onclick = function () { insertReference(ex.bookmark); };
        li.appendChild(b);
        list.appendChild(li);
      });
      say(examples.length ? "Choose the example to refer to." : "There are no examples in this document yet.");
    });
  }

  function insertReference(bookmark) {
    if (!busy("Inserting the reference…")) return;
    // Pasting is how a plugin writes at the cursor; the placeholder is then
    // made a REF field inside the editor (commands.completeReference).
    var placeholder = "LXREF" + Date.now().toString(36);
    var text = $("bare").checked ? placeholder : "(" + placeholder + ")";
    plugin.executeMethod("PasteText", [text], function () {
      window.Asc.scope.ref = { placeholder: placeholder, bookmark: bookmark };
      plugin.callCommand(LinguExx.completeReference, false, true, function (res) {
        idle();
        if (!res || res.error) return say((res && res.error) || "The reference was not inserted.", "error");
        say("Reference inserted.", "ok");
      });
    });
  }

  /**
   * The example the cursor is in, back as its typed lines, the number --
   * the same field -- at the head of the first; typesetting them again
   * takes that number over, so references to it survive.
   */
  function untypeset() {
    if (!busy("Untypesetting…")) return;
    note([]);
    plugin.callCommand(LinguExx.readExampleTable, false, false, function (read) {
      var u;
      try {
        u = LinguExx.untypesetJob(read);
      } catch (e) {
        idle();
        return say(String(e.message || e), "error");
      }
      if (u.refusal) { idle(); return say(u.refusal, "error"); }
      window.Asc.scope.back = u.back;
      plugin.callCommand(LinguExx.writeLines, false, true, function (res) {
        idle();
        if (!res || res.error) return say((res && res.error) || "The example was not taken apart.", "error");
        say("Back as text. Edit it, select the lines, and typeset them again: the number stays the same.", "ok");
      });
    });
  }

  var FIELDS = ["indentCm", "numberCm", "markerCm", "aboveCm", "belowCm"];

  /** Fill the layout fields from the document. */
  function loadLayout() {
    plugin.callCommand(LinguExx.readLayout, false, false, function (read) {
      var s = LinguExx.settingsFromRead(read || {});
      FIELDS.forEach(function (k) { $(k).value = (Math.round(s[k] * 100) / 100).toString(); });
    });
  }

  /** Store the fields' settings in the document, or say why not. */
  function applyLayout() {
    var s = {};
    FIELDS.forEach(function (k) { s[k] = parseFloat(String($(k).value).replace(",", ".")); });
    var j = LinguExx.layoutJob(s);
    if (j.refusal) return say(j.refusal, "error");
    if (!busy("Applying the layout…")) return;
    window.Asc.scope.layout = j.layout;
    plugin.callCommand(LinguExx.writeLayout, false, true, function (res) {
      idle();
      if (!res || res.error) return say((res && res.error) || "The layout was not applied.", "error");
      say("Layout applied: the spacing now, the indents from the next example on.", "ok");
    });
  }

  plugin.init = function () {
    $("typeset").onclick = typeset;
    $("refs").onclick = listExamples;
    $("untypeset").onclick = untypeset;
    $("applyLayout").onclick = applyLayout;
    loadLayout();
    say("Select the lines of an example, then Typeset.");
  };

  plugin.button = function () {
    this.executeCommand("close", "");
  };
})(window);
