' SPDX-License-Identifier: GPL-3.0-or-later
' Copyright (C) 2026 Gerhard Schaden
'
' This file is part of pandoc-linguexx.
'
' pandoc-linguexx is free software: you can redistribute it and/or modify
' it under the terms of the GNU General Public License as published by the
' Free Software Foundation, either version 3 of the License, or (at your
' option) any later version.
'
' pandoc-linguexx is distributed in the hope that it will be useful, but
' WITHOUT ANY WARRANTY; without even the implied warranty of
' MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
' General Public License for more details.
'
' You should have received a copy of the GNU General Public License along
' with this program.  If not, see <https://www.gnu.org/licenses/>.

' GlossSelection — turn selected lines into an aligned linguistic example.
'
' Select the lines and run this.  The first line is the object language, the
' last is the free translation if it opens with a quote, and everything
' between is a gloss tier:
'
'     Esto es un ejemplo glosado
'     this is a example glossed
'     'This is a glossed example.'
'
' A single line is an unglossed example, numbered like any other:
'
'     A simple example.
'
' What this can do that linguexx2odt cannot is *measure*.  The converter
' estimates column widths from per-character advance widths because it has
' no font metrics; here the real font is on hand, so columns are exactly
' as wide as their contents (the estimate is off by -2% to +9% in
' practice).  The available text width likewise comes from the actual page
' style rather than from a --text-width flag.
'
' Character formatting the linguist already applied survives: small caps on
' a Leipzig gloss, italics on the object language, bold, superscripts.  It
' has to.  A gloss tier is very often typed as small caps, and reading the
' selection as a plain string threw that away.
'
' Keeping it is half the job; the other half is measuring it.  Small caps
' are capitals at SC_RATIO of the size, which is *wider* than the lowercase
' letters they stand in for — 10% to 20% wider, measured.  A column measured
' on the lowercase and then set in small caps is too narrow, and the words
' wrap inside their cells; a band packed on the lowercase holds one word too
' many and runs off the text block.  Bold, italic and superscript are the
' same story, so every run is measured in the font it will be drawn in.
'
' Style names are deliberately the ones linguexx2odt emits, so a converted
' example and a macro-built one are the same object and answer to the same
' styles.

Option Explicit

' --- BEGIN GENERATED — see tools/sync_macro.py; do not edit by hand
'
' Style names and layout lengths shared with the converter, so that a
' converted example and a macro-built one are the same object and
' answer to the same styles.  Regenerate with:
'
'     python3 tools/sync_macro.py --write
'
Const CELL_PARA   As String = "LxExampleCell"
Const TRANS_PARA  As String = "LxTranslation"
Const JUDG_PARA   As String = "LxJudgmentCell"
Const BAND_PARA   As String = "LxExampleBand"
Const SPACE_PARA  As String = "LxExampleSpace"
Const SPACE_ABOVE As String = "LxExampleSpaceAbove"
Const SPACE_BELOW As String = "LxExampleSpaceBelow"
Const SEQ_NAME    As String = "NumEx"

' In centimetres, from linguexx2odt.styles.Layout.
Const PAD_CM      As Double = 0.16
Const MIN_COL_CM  As Double = 0.55
Const MAX_COL_CM  As Double = 6.0
Const NUMBER_CM   As Double = 1.1
Const MARKER_CM   As Double = 0.7
Const JUDG_GAP_CM As Double = 0.12
Const SPACE_CM    As Double = 0.18
Const SC_RATIO    As Double = 0.8

' Deliberately not shared:
'   text_width_cm — the macro reads the real page style instead
'   font_pt — the macro reads the real font instead
'   width_safety — the macro measures, so it needs no margin for error
' --- END GENERATED

Const JUDG_CHARS   As String = "*?#%!"

' The document properties the three configurable indents are kept in, and
' the largest length any of the five will take.  Up here with the other
' constants because Basic resolves a Const in source order: one declared
' beside the code that owns it, down in the layout section, is "Variable
' not defined" to every procedure above it.  See that section for what each
' one means.
Const OPT_INDENT   As String = "LinguExxIndentCm"
Const OPT_NUMBER   As String = "LinguExxNumberCm"
Const OPT_MARKER   As String = "LinguExxMarkerCm"
Const OPT_MAX_CM   As Double = 10.0

' Column boundaries closer together than this are the same boundary.
Const GRID_TOL_CM  As Double = 0.015

' Run formats.  The selection is read as text with a one-character mark in
' front of every run of like-formatted characters; the marks are private-use
' codepoints, so nothing a linguist can type collides with them, and they
' ride along through splitting, banding and column assignment untouched.
' The format itself is kept here, out of the string, and looked up by the
' mark's offset from FMT_BASE.
'
' A mark is emitted again after every space, so that every *word* carries
' its own format and none of the code between here and LxPut has to track
' what was in force.  LxStrip takes them all back out for the places that
' want the text a linguist would recognise.
Const FMT_BASE     As Long = 57344        ' U+E000, the private use area
Const FMT_MAX      As Integer = 250

Dim LxFmtN         As Integer
Dim LxFmtCase(FMT_MAX)   As Integer       ' CharCaseMap
Dim LxFmtWeight(FMT_MAX) As Double        ' CharWeight
Dim LxFmtItalic(FMT_MAX) As Boolean       ' CharPosture <> NONE
Dim LxFmtStyle(FMT_MAX)  As String        ' CharStyleName
Dim LxFmtEsc(FMT_MAX)    As Integer       ' CharEscapement
Dim LxFmtEscH(FMT_MAX)   As Integer       ' CharEscapementHeight, per cent
Dim LxFmtUnder(FMT_MAX)  As Integer       ' CharUnderline
Dim LxFmtFont(FMT_MAX)   As Object        ' measuring font for this format
Dim LxFmtFontSC(FMT_MAX) As Object        ' and the reduced one for small caps


' Trees.  A node is five parallel arrays and two links, because Basic has
' no record type and an array of arrays is worse.  Children hang off
' LxNdKid/LxNdSib — first child, next sibling — which is the shape a
' bracket parser produces anyway and needs no second pass to build.
Const TREE_MAX     As Integer = 300       ' nodes in one tree
Const TREE_DEPTH   As Integer = 40        ' tiers in one tree
Const NODE_PAD_CM  As Double = 0.06       ' slack each side of a label
Const NODE_GAP_CM  As Double = 0.22       ' least space between subtrees
Const TIER_FACTOR  As Double = 2.0        ' tier spacing / line height
Const BRANCH_WIDTH As Integer = 8         ' branch thickness, 1/100 mm

Dim LxNdLabel(TREE_MAX) As String
Dim LxNdRoof(TREE_MAX)  As Boolean        ' drawn under a triangle
Dim LxNdKid(TREE_MAX)   As Integer        ' first child, -1 for a leaf
Dim LxNdSib(TREE_MAX)   As Integer        ' next sibling, -1 for the last
Dim LxNdDepth(TREE_MAX) As Integer
Dim LxNdX(TREE_MAX)     As Double         ' centre of the label, 1/100 mm
Dim LxNdW(TREE_MAX)     As Double
Dim LxNdN               As Integer
Dim LxFree(TREE_DEPTH)  As Double         ' leftmost free x on each tier

' The body font, kept for anything that has to be *drawn* rather than
' typed.  A tree in a sub-example is built long after the range it came
' from was absorbed by the table, so the font cannot be read off it there.
Dim LxBodyFont As String
Dim LxBodyPt   As Double

Dim LxTSrc As String                      ' the parser's input and cursor
Dim LxTPos As Integer
Dim LxTErr As String
Dim LxTTag As String                      ' the format mark in force

' Movement arrows.  Drawn in a gutter below the tree, one lane each, so an
' arrow never crosses a branch and two arrows never share a line.
Const ARROW_MAX     As Integer = 40
Const GUTTER_GAP_CM As Double = 0.30      ' from the deepest node to lane 0
Const LANE_STEP_CM  As Double = 0.34      ' from one lane to the next
Const HEAD_LEN_CM   As Double = 0.18
Const HEAD_HALF_CM  As Double = 0.07

Dim LxNdName(TREE_MAX)  As String         ' from the "name=" node option
Dim LxArFrom(ARROW_MAX) As Integer        ' node moved from
Dim LxArTo(ARROW_MAX)   As Integer        ' node moved to
Dim LxArLane(ARROW_MAX) As Integer
Dim LxArN               As Integer
Dim LxMoveSrc(ARROW_MAX) As String        ' the "move a -> b" lines, unparsed
Dim LxMoveN             As Integer


' Every message goes through LxSay, so a caller that must not be blocked by
' a modal dialog (a test harness, a batch run over many examples) can turn
' the dialogs off and read the last message back instead.
Public LxSilent As Boolean
Public LxLastMessage As String


' ---------------------------------------------------------------- entry ---

' An example: glossed, unglossed, or a paradigm of either.  Never a tree,
' whatever brackets are in it — see LxTreeOnly.
Sub GlossSelection
    Call LxExampleCommand(False, "Typeset example")
End Sub


' A numbered tree, or a paradigm of them:
'
'     a. [DP [D the] [NP [N tree]]]
'     b. [DP [D a] [NP [N cat]]]
'
' The same table an example gets, so it numbers and aligns with them; each
' item is a tree because the command says so, and nothing is inferred from
' the brackets.  One tree with no letter is just the one-item case.
Sub TreeSelection
    Call LxExampleCommand(True, "Typeset tree")
End Sub


' The lengths of an example that are a matter of house style rather than of
' measurement: the three indents and the space above and below.  See the
' layout section for where each is kept and why.
Sub LayoutSettings
    Call LxLayoutCommand()
End Sub


Sub LxExampleCommand(bTreeOnly As Boolean, sUndo As String)
    Dim oDoc As Object, oSel As Object, oRange As Object
    Dim aLines As Variant
    Dim nLines As Integer
    Dim oUndo As Object

    LxTreeOnly = bTreeOnly
    oDoc = ThisComponent
    If IsNull(oDoc) Then
        Call LxSay("Run this in a Writer document.")
        Exit Sub
    End If
    If Not oDoc.supportsService("com.sun.star.text.TextDocument") Then
        Call LxSay("Run this in a Writer document.")
        Exit Sub
    End If

    oSel = oDoc.getCurrentController().getSelection()
    If oSel.getCount() < 1 Then
        Call LxSay("Select the lines of the example first.")
        Exit Sub
    End If
    oRange = oSel.getByIndex(0)

    aLines = LxSelectedLines(oRange)
    ' Trouble with a number the selection carries is reported before
    ' anything is built: the alternative is an example that took a number
    ' off another one, which is exactly the breakage this is here to stop.
    If Len(LxNumErr) > 0 Then
        Call LxSay(LxNumErr)
        Exit Sub
    End If
    nLines = UBound(aLines) + 1
    ' One line is a perfectly good example — an unglossed one, which is the
    ' commonest kind there is.  Requiring two was a leftover from when this
    ' only knew how to build glossed examples; unglossed items became
    ' representable when sub-examples arrived.
    If nLines < 1 Then
        Call LxSay("Select the line or lines of the example first.")
        Exit Sub
    End If

    ' One undo context, so Ctrl+Z takes the whole example back in one go
    ' rather than unwinding it row by row.
    oUndo = oDoc.getUndoManager()
    oUndo.enterUndoContext(sUndo)
    On Error Goto Cleanup
    Call LxBuildExample(oDoc, oRange, aLines, nLines)
Cleanup:
    oUndo.leaveUndoContext()
    If Err <> 0 Then Call LxSay(Error$ & " (line " & Erl & ")")
End Sub


Sub LxSay(sMsg As String)
    LxLastMessage = sMsg
    If Not LxSilent Then MsgBox sMsg, 48, "Typeset example"
End Sub

' For non-interactive callers — a test harness, or a script running over
' many examples: does the work with the dialogs off and hands the message
' back instead.  "" means it succeeded.  Doing it in one call matters: a
' caller that set a flag in one invocation and read it in another could not
' rely on the flag still being set, and a modal dialog in a headless
' LibreOffice blocks for ever.
Function GlossSelectionQuiet() As String
    LxSilent = True
    LxLastMessage = ""
    Call GlossSelection
    LxSilent = False
    GlossSelectionQuiet = LxLastMessage
    LxLastMessage = ""
End Function


' ------------------------------------------------------------- the work ---

' An example is a list of *items*.  A plain example is one item with no
' marker; "a. ... b. ..." is one item per letter, all sharing one number and
' one column grid.  Each item is a Variant array indexed by the constants
' below — Basic has no record type, and threading five parallel arrays
' through six procedures would be worse than this.
Const IT_MARKER As Integer = 0     ' "a.", "(b)", "iii." — "" for a plain example
Const IT_JUDG   As Integer = 1     ' judgment mark pulled off the object line
Const IT_TRANS  As Integer = 2     ' free translation, or ""
Const IT_TIERS  As Integer = 3     ' array of word-arrays; tier 0 is the object
Const IT_NTIERS As Integer = 4     ' 1 means unglossed, 0 means a tree
Const IT_TREE   As Integer = 5     ' the item's own lines, when it is a tree
Const IT_SIZE   As Integer = 6


Sub LxBuildExample(oDoc As Object, oRange As Object, aLines As Variant, nLines As Integer)
    Dim aItems As Variant
    Dim sError As String

    aItems = LxParseItems(aLines, nLines, sError)
    If Len(sError) > 0 Then
        Call LxSay(sError)
        Exit Sub
    End If

    Call LxEnsureStyles(oDoc)
    Call LxLayOut(oDoc, oRange, aItems)
End Sub


' Split the selection into items.  A line whose first token is a
' sub-example marker starts a new one; everything up to the next marker
' belongs to it.  A marker may stand alone on its line or lead the object
' language, which is how people actually type them.
' A tree item reports its trouble through LxTErr, which is checked once
' here rather than threaded back out of LxMakeItem.
Function LxParseItems(aLines As Variant, nLines As Integer, ByRef sError As String) As Variant
    Dim aItems() As Variant
    Dim aBody() As String
    Dim i As Integer, n As Integer, nBody As Integer
    Dim bAny As Boolean
    Dim sMarker As String, sRest As String, sLine As String

    sError = ""
    LxTErr = ""

    bAny = False
    For i = 0 To nLines - 1
        If LxLooksLikeMarker(aLines(i)) Then bAny = True
    Next i

    If Not bAny Then                          ' one plain example
        ReDim aItems(0)
        ReDim aBody(nLines - 1)
        For i = 0 To nLines - 1
            aBody(i) = aLines(i)
        Next i
        aItems(0) = LxMakeItem("", aBody(), nLines)
        If Len(LxTErr) > 0 Then sError = LxTErr
        LxParseItems = aItems()
        Exit Function
    End If

    If Not LxLooksLikeMarker(aLines(0)) Then
        sError = "A sub-example letter appears part-way through the selection, " & _
                 "but the selection does not start with one." & Chr(10) & Chr(10) & _
                 "Start at the first sub-example, or leave the letters out " & _
                 "and gloss one example at a time."
        LxParseItems = Array()
        Exit Function
    End If

    ReDim aItems(nLines - 1)
    ReDim aBody(nLines - 1)
    n = 0 : nBody = 0 : sMarker = ""
    For i = 0 To nLines - 1
        If LxLooksLikeMarker(aLines(i)) Then
            If nBody > 0 Then
                aItems(n) = LxMakeItem(sMarker, aBody(), nBody)
                If Len(LxTErr) > 0 Then       ' taken now: the next item's
                    sError = LxTErr           ' LxSplitMoves would clear it
                    LxParseItems = Array()
                    Exit Function
                End If
                n = n + 1
            End If
            sLine = LxTrimTagged(aLines(i))
            sMarker = LxSplitWords(sLine)(0)
            sRest = LxCarryTag(sMarker, LxTrimTagged(Mid(sLine, Len(sMarker) + 1)))
            nBody = 0
            If Len(sRest) > 0 Then             ' "a. Esto es ..." on one line
                aBody(nBody) = sRest
                nBody = nBody + 1
            End If
        Else
            aBody(nBody) = aLines(i)
            nBody = nBody + 1
        End If
    Next i
    If nBody > 0 Then
        aItems(n) = LxMakeItem(sMarker, aBody(), nBody)
        If Len(LxTErr) > 0 Then
            sError = LxTErr
            LxParseItems = Array()
            Exit Function
        End If
        n = n + 1
    End If

    If n = 0 Then
        sError = "Every selected line is a sub-example letter with nothing after it."
        LxParseItems = Array()
        Exit Function
    End If

    ReDim Preserve aItems(n - 1)
    LxParseItems = aItems()
End Function


' Every item of this selection is a tree.
'
' Set by the tree commands and never inferred.  Bracket notation cannot be
' recognised from the text: labelled bracketing is how constituent
' structure is shown inside an ordinary example — [TP [DP John] [VP left]]
' — and nothing in the string separates "draw this" from "show this".  So
' the command the user chose is the whole of the signal, and Typeset
' example never draws a tree.
Dim LxTreeOnly As Boolean

' The width left for content beside the number, so a tree can say when it
' will not fit.  Set in LxLayOut, where the page is still in view.
Dim LxWideCm As Double


' The item's own lines, as an array the tree reader can take.
Function LxBodyLines(aBody() As String, nBody As Integer) As Variant
    Dim aOut() As String
    Dim i As Integer
    If nBody < 1 Then
        LxBodyLines = Array()
        Exit Function
    End If
    ReDim aOut(nBody - 1)
    For i = 0 To nBody - 1
        aOut(i) = aBody(i)
    Next i
    LxBodyLines = aOut()
End Function


' One item from its own lines: object language, gloss tiers, translation.
'
' A quoted last line is the translation whenever the item has more than one
' line.  That leaves an item of a single line unglossed, which is exactly
' what an unglossed sub-example is — "a. Sentences like this are fine."
Function LxMakeItem(sMarker As String, aBody() As String, nBody As Integer) As Variant
    Dim aItem(IT_SIZE - 1) As Variant
    Dim aTiers() As Variant
    Dim aWords As Variant, aLines As Variant
    Dim sTrans As String, sMark As String, sFirst As String, sSrc As String
    Dim i As Integer, nTiers As Integer

    sTrans = ""
    If nBody > 1 Then
        If LxIsTranslation(aBody(nBody - 1)) Then
            sTrans = aBody(nBody - 1)
            nBody = nBody - 1
        End If
    End If

    ' A tree is an item like any other: one row, one merged cell, its own
    ' letter and its own judgment mark.  Only what goes in the cell differs.
    aLines = LxBodyLines(aBody(), nBody)
    If LxTreeOnly Then
        ' The command said trees, so a body that will not parse is an error
        ' rather than a quiet fall back to text.  LxParseItems passes
        ' LxTErr on to the caller before anything is built.
        sMark = ""
        sSrc = LxSplitMoves(aLines)
        sSrc = LxPullJudgment(sSrc, sMark)
        If LxTreeParse(sSrc) >= 0 Then
            Call LxResolveMoves()
        ElseIf Len(sMarker) > 0 Then
            ' Say which item.  In a paradigm "a tree has to start with a
            ' bracket" on its own leaves the reader counting brackets.
            LxTErr = "Sub-example " & LxStrip(sMarker) & " is not a tree." & _
                     Chr(10) & Chr(10) & LxTErr & Chr(10) & Chr(10) & _
                     "Every item of a numbered tree is a tree.  To put a " & _
                     "tree beside a glossed example, make them two examples."
        End If
        aItem(IT_MARKER) = sMarker
        aItem(IT_JUDG) = sMark
        aItem(IT_TRANS) = sTrans
        aItem(IT_TIERS) = Array()
        aItem(IT_NTIERS) = 0
        aItem(IT_TREE) = aLines
        LxMakeItem = aItem()
        Exit Function
    End If

    ReDim aTiers(LxMaxI(nBody - 1, 0))
    nTiers = 0
    For i = 0 To nBody - 1
        aTiers(nTiers) = LxSplitWords(aBody(i))
        nTiers = nTiers + 1
    Next i

    ' A judgment mark leads the object line and belongs in its own hanging
    ' column, never glued to the first word — otherwise it shifts the text
    ' block right and a judged item no longer lines up with an unjudged one.
    sMark = ""
    If nTiers > 0 Then
        aWords = aTiers(0)
        If UBound(aWords) >= 0 Then
            sFirst = LxPullJudgment(aWords(0), sMark)
            If Len(sMark) > 0 Then
                If Len(sFirst) > 0 Then
                    aWords(0) = sFirst
                    aTiers(0) = aWords
                Else
                    aTiers(0) = LxDropFirst(aWords)   ' the mark stood alone
                End If
            End If
        End If
    End If

    aItem(IT_MARKER) = sMarker
    aItem(IT_JUDG) = sMark
    aItem(IT_TRANS) = sTrans
    aItem(IT_TIERS) = aTiers()
    aItem(IT_NTIERS) = nTiers
    LxMakeItem = aItem()
End Function


Sub LxLayOut(oDoc As Object, oRange As Object, aItems As Variant)
    Dim oFont As Object, dPxPerCm As Double
    Dim dAvail As Double, dNumber As Double, dJudg As Double, dMarker As Double
    Dim dIndent As Double, dTable As Double
    Dim aWordW() As Double, nWords As Integer
    Dim aBandStart() As Integer, nBands As Integer
    Dim aColW() As Double, nCols As Integer
    Dim aWordCol() As Integer, aWordSpan() As Integer
    Dim dTotal As Double, dFiller As Double, dW As Double
    Dim i As Integer, k As Integer, t As Integer, b As Integer, w As Integer
    Dim aItem As Variant, aTiers As Variant, aWords As Variant
    Dim nLead As Integer, nItems As Integer
    Dim bSub As Boolean, bGlossed As Boolean

    nItems = UBound(aItems) + 1
    If nItems < 1 Then Exit Sub

    oFont = LxFontForRange(oDoc, oRange, dPxPerCm)

    ' Read while the selection still exists: a tree item is drawn after the
    ' table has absorbed oRange, and cannot ask it anything by then.
    LxBodyFont = "" : LxBodyPt = 0
    On Error Resume Next
    LxBodyFont = oRange.CharFontName
    LxBodyPt = oRange.CharHeight
    On Error Goto 0
    If Len(LxBodyFont) = 0 Then LxBodyFont = "Liberation Serif"
    If LxBodyPt <= 0 Then LxBodyPt = 12

    ' The text block comes from the page in front of us, not from a flag.
    ' What the example may use of it is that less the indent the document
    ' asks for, and the table itself is that wide — every width below is
    ' measured inside it, so the indent has to come off before anything is
    ' packed rather than after.
    '
    ' Half the text block is as far in as an example will go, whatever it
    ' was asked for.  Not a house-style decision, and not reachable from
    ' the dialog either: it is the floor under a property typed by hand
    ' into File ▸ Properties on a narrow page, where the alternative is a
    ' table with no room left to put an example in.
    dAvail = LxTextWidthCm(oDoc)
    dIndent = LxOpt(oDoc, OPT_INDENT, 0)
    dIndent = LxMax(0, LxMin(dIndent, dAvail / 2))
    dAvail = dAvail - dIndent
    dTable = dAvail

    aItem = aItems(0)
    bSub = (Len(aItem(IT_MARKER)) > 0)

    ' The judgment column is reserved in *every* example, marked or not, and
    ' carved out of the column to its left rather than inserted after it.
    ' Both halves matter for the same invariant — a judged and an unjudged
    ' example must begin at the same x:
    '
    '   reserved always  ->  the text starts in the same place either way
    '   carved, not      ->  a mark consumes no horizontal space, it hangs
    '   inserted             into room the column before it gave up
    '
    ' linguexx2odt reserves it only when some example in the document is
    ' judged, because it can see the whole document first.  A macro sees one
    ' selection, so it always reserves; the cost is a few millimetres of
    ' indent in a document that never judges anything.
    dJudg = LxWidth(oFont, dPxPerCm, "*")
    For k = 0 To nItems - 1
        aItem = aItems(k)
        If Len(aItem(IT_JUDG)) > 0 Then
            dJudg = LxMax(dJudg, LxWidth(oFont, dPxPerCm, aItem(IT_JUDG)))
        End If
    Next k
    dJudg = dJudg + JUDG_GAP_CM

    ' The configured indents are floors, not exact distances: a column
    ' narrower than the number it has to hold would put "(100)" under the
    ' first word of the example.
    dNumber = LxMax(LxOpt(oDoc, OPT_NUMBER, NUMBER_CM), _
                    LxWidth(oFont, dPxPerCm, "(00)") + PAD_CM) + dJudg

    ' The marker column is carved out of in the same way, and the number
    ' column keeps its full width.  That is what puts a sub-example letter
    ' exactly where a main example's text begins — linguexx's own geometry.
    dMarker = 0
    If bSub Then
        For k = 0 To nItems - 1
            aItem = aItems(k)
            dMarker = LxMax(dMarker, LxWidth(oFont, dPxPerCm, aItem(IT_MARKER)))
        Next k
        dMarker = LxMax(LxOpt(oDoc, OPT_MARKER, MARKER_CM), dMarker + PAD_CM) + dJudg
    End If

    nLead = 2
    If bSub Then nLead = 3
    dAvail = dAvail - dNumber - dMarker
    LxWideCm = dAvail                         ' what a drawn item has to fit

    ' Column widths come from the glossed items only.  An unglossed item is
    ' one merged cell of running text, so its words must not drag a column
    ' wide enough to hold them.
    bGlossed = False
    nWords = 0
    For k = 0 To nItems - 1
        aItem = aItems(k)
        If aItem(IT_NTIERS) > 1 Then
            bGlossed = True
            If LxItemWords(aItem) > nWords Then nWords = LxItemWords(aItem)
        End If
    Next k

    If Not bGlossed Then                      ' nothing glossed: one wide column
        nWords = 1
        ReDim aWordW(0)
        aWordW(0) = dAvail
    Else
        ReDim aWordW(nWords - 1)
        For i = 0 To nWords - 1
            dW = 0
            For k = 0 To nItems - 1
                aItem = aItems(k)
                If aItem(IT_NTIERS) > 1 Then
                    aTiers = aItem(IT_TIERS)
                    For t = 0 To aItem(IT_NTIERS) - 1
                        aWords = aTiers(t)
                        If i <= UBound(aWords) Then
                            dW = LxMax(dW, LxWidth(oFont, dPxPerCm, aWords(i)))
                        End If
                    Next t
                End If
            Next k
            ' Capped like the converter: one very long word must not eat the
            ' whole line.  Past the cap it wraps inside its cell instead.
            aWordW(i) = LxMin(MAX_COL_CM, LxMax(MIN_COL_CM, dW + PAD_CM))
        Next i
    End If

    ' Bands: an example too wide for the text block is broken into stacked
    ' slices, each starting back at the left edge, the way linguexx2odt does
    ' it.  The band boundaries are shared by every item, as in the converter;
    ' an item with fewer words simply contributes no rows to a later band.
    ' Unlike the converter this can be redone at any time against the current
    ' page, because nothing here was frozen at conversion time.
    nBands = LxPackBands(aWordW(), nWords, dAvail, aBandStart())

    nCols = LxBuildGrid(aWordW(), nWords, aBandStart(), nBands, _
                        aColW(), aWordCol(), aWordSpan())

    dTotal = 0
    For i = 0 To nCols - 1
        dTotal = dTotal + aColW(i)
    Next i
    If dTotal > dAvail Then                   ' a single word wider than the page
        For i = 0 To nCols - 1
            aColW(i) = aColW(i) * dAvail / dTotal
        Next i
        dTotal = dAvail
    End If

    dFiller = 0
    If dTotal <= dAvail - MIN_COL_CM Then dFiller = dAvail - dTotal

    Call LxEmitTable(oDoc, oRange, aItems, aBandStart(), nBands, aColW(), nCols, _
                     aWordCol(), aWordSpan(), nWords, _
                     dNumber, dMarker, dJudg, dFiller, nLead, dIndent, dTable)
End Sub


Sub LxEmitTable(oDoc As Object, oRange As Object, aItems As Variant, _
                aBandStart() As Integer, nBands As Integer, _
                aColW() As Double, nCols As Integer, _
                aWordCol() As Integer, aWordSpan() As Integer, nWords As Integer, _
                dNumber As Double, dMarker As Double, dJudg As Double, _
                dFiller As Double, nLead As Integer, _
                dIndent As Double, dTable As Double)
    Dim oTable As Object
    Dim nRows As Integer, nTotalCols As Integer, nFill As Integer
    Dim b As Integer, t As Integer, i As Integer, c As Integer, k As Integer
    Dim nRow As Integer, nEnd As Integer, nItems As Integer, nMax As Integer
    Dim nShift As Integer
    Dim oCur As Object
    Dim aItem As Variant, aTiers As Variant, aWords As Variant, aNames As Variant
    Dim aWidths() As Double, dSum As Double
    Dim bFirstOfAll As Boolean, bFirstOfItem As Boolean

    nItems = UBound(aItems) + 1
    nFill = 0
    If dFiller > 0 Then nFill = 1
    nTotalCols = nLead + nCols + nFill

    nRows = 2                                 ' the two spacer rows
    For k = 0 To nItems - 1
        nRows = nRows + LxItemRows(aItems(k), aBandStart(), nBands)
    Next k

    oTable = oDoc.createInstance("com.sun.star.text.TextTable")
    oTable.initialize(nRows, nTotalCols)
    oDoc.getText().insertTextContent(oRange, oTable, True)
    Call LxPlainTable(oTable)

    ' Every cell gets a named style before anything else.  Writer gives a
    ' new table's first row the centred "Table Heading" style, which pulls
    ' the object language out of line with its own glosses.
    aNames = oTable.getCellNames()
    For i = 0 To UBound(aNames)
        oTable.getCellByName(aNames(i)).getText().createTextCursor().ParaStyleName = CELL_PARA
    Next i

    ' The spacer rows are styled across their whole width and left unmerged.
    ' Merging them would be tidier to look at in the XML and would break the
    ' widths below: a table whose first row is a single merged cell has no
    ' column separators left to set, so every column silently comes out the
    ' same width.
    For i = 0 To nTotalCols - 1
        Call LxSetCellStyle(oTable, LxCell(i, 1), SPACE_ABOVE)
        Call LxSetCellStyle(oTable, LxCell(i, nRows), SPACE_BELOW)
    Next i

    ' Widths, before any merging, for the same reason.  The table spans the
    ' text block (so it rescales rather than running off the page) and the
    ' columns hold their measured widths, with the slack parked in a
    ' trailing filler column.
    ReDim aWidths(nTotalCols - 1)
    If nLead = 3 Then
        aWidths(0) = dNumber
        aWidths(1) = dMarker - dJudg
        aWidths(2) = dJudg
    Else
        aWidths(0) = dNumber - dJudg
        aWidths(1) = dJudg
    End If
    For i = 0 To nCols - 1
        aWidths(nLead + i) = aColW(i)
    Next i
    If nFill = 1 Then aWidths(nTotalCols - 1) = dFiller

    dSum = 0
    For i = 0 To nTotalCols - 1
        dSum = dSum + aWidths(i)
    Next i
    Call LxSetColumns(oTable, aWidths(), nTotalCols, dSum, dIndent, dTable)

    nRow = 2
    bFirstOfAll = True
    For k = 0 To nItems - 1
        aItem = aItems(k)
        aTiers = aItem(IT_TIERS)
        bFirstOfItem = True

        If aItem(IT_NTIERS) > 1 Then
            nMax = LxItemWords(aItem)
            For b = 0 To nBands - 1
                If aBandStart(b) < nMax Then
                    For t = 0 To aItem(IT_NTIERS) - 1
                        aWords = aTiers(t)
                        If bFirstOfItem Then
                            Call LxHead(oDoc, oTable, nRow, aItem, bFirstOfAll, nLead)
                            bFirstOfItem = False
                            bFirstOfAll = False
                        End If
                        ' The first row of a continuation band says so.
                        ' Nothing else in the finished table can: this row
                        ' is built exactly like a tier row and starts in the
                        ' same column, so a reader counting rows cannot tell
                        ' three tiers of one band from one tier of three.
                        If b > 0 And t = 0 Then _
                            Call LxMarkBand(oTable, nRow, nLead, nCols + nFill)
                        ' Walk the band's whole word range, not just this
                        ' tier's: every tier row must end up with the same
                        ' cell structure, or the rows stop lining up.
                        nEnd = LxBandEnd(aBandStart(), nBands, nWords, b)
                        nShift = 0
                        For i = aBandStart(b) To nEnd - 1
                            c = nLead + aWordCol(i) - nShift
                            If i <= UBound(aWords) Then
                                Call LxPut(oTable.getCellByName(LxCell(c, nRow)), aWords(i))
                            End If
                            If aWordSpan(i) > 1 Then
                                ' Merging removes cells, so everything to the
                                ' right of it shifts left by span-1; the words
                                ' after this one have to be addressed by their
                                ' shifted name, not their grid column.
                                oCur = oTable.createCursorByCellName(LxCell(c, nRow))
                                oCur.goRight(aWordSpan(i) - 1, True)
                                oCur.mergeRange()
                                nShift = nShift + aWordSpan(i) - 1
                            End If
                        Next i
                        nRow = nRow + 1
                    Next t
                End If
            Next b
        Else
            ' Unglossed: running text in one merged cell, not one word per
            ' column.  Splitting it into columns would align words that have
            ' nothing to do with each other.  A tree takes the same row and
            ' the same merged cell; only its contents are drawn.
            Call LxHead(oDoc, oTable, nRow, aItem, bFirstOfAll, nLead)
            bFirstOfAll = False
            If aItem(IT_NTIERS) = 0 Then
                Call LxWideCellTree(oDoc, oTable, nRow, nLead, nCols + nFill, _
                                    aItem(IT_TREE))
            Else
                Call LxWideCell(oTable, nRow, nLead, nCols + nFill, _
                                LxJoinWords(aTiers(0)), CELL_PARA)
            End If
            nRow = nRow + 1
        End If

        If Len(aItem(IT_TRANS)) > 0 Then
            Call LxWideCell(oTable, nRow, nLead, nCols + nFill, _
                            aItem(IT_TRANS), TRANS_PARA)
            nRow = nRow + 1
        End If
    Next k
End Sub


' Number, sub-example letter and judgment mark — only on an item's first row,
' and the number only on the first item's.
Sub LxHead(oDoc As Object, oTable As Object, nRow As Integer, _
           aItem As Variant, bFirstOfAll As Boolean, nLead As Integer)
    If bFirstOfAll Then
        Call LxInsertNumber(oDoc, oTable.getCellByName(LxCell(0, nRow)))
    End If
    If nLead = 3 Then
        Call LxPut(oTable.getCellByName(LxCell(1, nRow)), aItem(IT_MARKER))
    End If
    Call LxSetCellStyle(oTable, LxCell(nLead - 1, nRow), JUDG_PARA)
    If Len(aItem(IT_JUDG)) > 0 Then
        oTable.getCellByName(LxCell(nLead - 1, nRow)).setString(aItem(IT_JUDG))
    End If
End Sub


' Mark a whole row as beginning a band — padding cells included, so the
' mark can be looked for on any cell of the row rather than on the one a
' short tier happened to leave empty.  Called before the row's words are
' written and its cells merged, while every cell of it still exists.
Sub LxMarkBand(oTable As Object, nRow As Integer, nLead As Integer, nSpan As Integer)
    Dim oCell As Object
    Dim i As Integer
    For i = nLead To nLead + nSpan - 1
        oCell = Nothing
        On Error Resume Next
        oCell = oTable.getCellByName(LxCell(i, nRow))
        On Error Goto 0
        ' A merge earlier in the table can leave a name with no cell behind
        ' it; the mark only has to land somewhere on the row.
        If Not IsNull(oCell) Then _
            oCell.getText().createTextCursor().ParaStyleName = BAND_PARA
    Next i
End Sub


Sub LxWideCell(oTable As Object, nRow As Integer, nLead As Integer, _
               nSpan As Integer, sText As String, sStyle As String)
    Dim oCur As Object
    Call LxSetCellStyle(oTable, LxCell(nLead, nRow), sStyle)
    If nSpan > 1 Then
        oCur = oTable.createCursorByCellName(LxCell(nLead, nRow))
        oCur.goRight(nSpan - 1, True)
        oCur.mergeRange()
    End If
    Call LxPut(oTable.getCellByName(LxCell(nLead, nRow)), sText)
End Sub


' A tree in a sub-example: the merged cell an unglossed item would get,
' with a drawing anchored in it instead of text.
'
' Parsed again here rather than carried over from LxMakeItem, because the
' node store is one tree wide and a paradigm has several.  Parsing is
' string work, and the item was only accepted as a tree because it parsed,
' so this cannot start failing at build time.
Sub LxWideCellTree(oDoc As Object, oTable As Object, nRow As Integer, _
                   nLead As Integer, nSpan As Integer, aLines As Variant)
    Dim oCur As Object, oCell As Object, oText As Object, oGroup As Object
    Dim sSrc As String, sMark As String
    Dim nRoot As Integer
    Dim dWidth As Double

    Call LxSetCellStyle(oTable, LxCell(nLead, nRow), CELL_PARA)
    If nSpan > 1 Then
        oCur = oTable.createCursorByCellName(LxCell(nLead, nRow))
        oCur.goRight(nSpan - 1, True)
        oCur.mergeRange()
    End If

    sSrc = LxSplitMoves(aLines)
    sSrc = LxPullJudgment(sSrc, sMark)
    nRoot = LxTreeParse(sSrc)
    If nRoot < 0 Then Exit Sub
    If Not LxResolveMoves() Then Exit Sub

    oCell = oTable.getCellByName(LxCell(nLead, nRow))
    oText = oCell.getText()
    oText.setString("")
    oCur = oText.createTextCursor()
    oCur.gotoEnd(False)
    oGroup = LxTreeDraw(oDoc, oText, oCur, nRoot, LxBodyFont, LxBodyPt)
    ' The lines as the linguist typed them — judgment mark, move lines and
    ' all — so that Untypeset can give the tree back as what made it.  The
    ' sub-example letter is not among them: it was taken off before the
    ' item was made, and Untypeset puts it back from its own column.
    Call LxTreeSource(oGroup, aLines)

    ' Said, not silently produced: a tree wider than its cell hangs off the
    ' page, and shortening a label is the user's call.
    dWidth = LxTreeWidth(nRoot) / 1000.0
    If dWidth > LxWideCm Then
        Call LxSay("A tree is " & Format(dWidth, "0.0") & " cm wide but " & _
                   "only " & Format(LxWideCm, "0.0") & " cm is left beside " & _
                   "the number, so it will stick out." & Chr(10) & Chr(10) & _
                   "Shorten a label, or group words with {braces} so they " & _
                   "share one node.")
    End If
End Sub


Function LxItemWords(aItem As Variant) As Integer
    Dim aTiers As Variant, aWords As Variant
    Dim t As Integer, n As Integer
    n = 0
    aTiers = aItem(IT_TIERS)
    For t = 0 To aItem(IT_NTIERS) - 1
        aWords = aTiers(t)
        If UBound(aWords) + 1 > n Then n = UBound(aWords) + 1
    Next t
    LxItemWords = n
End Function


' How many table rows this item will occupy — must agree exactly with what
' LxEmitTable goes on to write, or the table is the wrong height.
Function LxItemRows(aItem As Variant, aBandStart() As Integer, nBands As Integer) As Integer
    Dim n As Integer, b As Integer, nMax As Integer
    n = 0
    If aItem(IT_NTIERS) > 1 Then
        nMax = LxItemWords(aItem)
        For b = 0 To nBands - 1
            If aBandStart(b) < nMax Then n = n + aItem(IT_NTIERS)
        Next b
    Else
        n = 1
    End If
    If Len(aItem(IT_TRANS)) > 0 Then n = n + 1
    LxItemRows = n
End Function


Function LxJoinWords(aWords As Variant) As String
    Dim s As String
    Dim i As Integer
    s = ""
    For i = 0 To UBound(aWords)
        If i > 0 Then s = s & " "
        s = s & aWords(i)
    Next i
    LxJoinWords = s
End Function


' --------------------------------------------------------------- pieces ---

' The lines of the selection, trimmed, blank ones dropped, every run of
' character formatting marked (see FMT_BASE).
'
' Enumerating paragraphs over a *cursor* built from the selection looks like
' the tidy way to do this and does not work — it yields a single empty
' element, which is why this used to read oRange.getString() and throw all
' the formatting away.  Enumerating the selection range itself does work,
' and does the one hard part for free: the text portions it hands back are
' already clipped to the selection, so a half-selected paragraph yields
' exactly the half that was selected.
'
' Chr(11) is a line break inside a paragraph (Shift+Enter), which a linguist
' typing a gloss is at least as likely to have used as a paragraph mark; it
' arrives here as a portion of its own rather than as a character.
Function LxSelectedLines(oRange As Object) As Variant
    Dim oParEnum As Object, oPorEnum As Object
    Dim oPar As Object, oPor As Object
    Dim s As String, sLine As String, sType As String
    Dim aRaw As Variant, aOut() As String
    Dim i As Integer, n As Integer
    Dim bCloser As Boolean

    LxFmtN = 0
    LxNumHas = False
    LxNumId = 0
    LxNumErr = ""

    s = ""
    bCloser = False
    oParEnum = Nothing
    On Error Resume Next
    oParEnum = oRange.createEnumeration()
    On Error Goto 0
    If Not IsNull(oParEnum) Then
        Do While oParEnum.hasMoreElements()
            oPar = oParEnum.nextElement()
            If oPar.supportsService("com.sun.star.text.Paragraph") Then
                oPorEnum = oPar.createEnumeration()
                Do While oPorEnum.hasMoreElements()
                    oPor = oPorEnum.nextElement()
                    sType = ""
                    On Error Resume Next
                    sType = oPor.TextPortionType
                    On Error Goto 0
                    If sType = "LineBreak" Then
                        s = s & Chr(10)
                        bCloser = False
                    ElseIf sType = "TextField" And LxIsNumberField(oPor) Then
                        ' An example number: taken over rather than read as
                        ' a word.  Its own presentation ("7") would
                        ' otherwise lead the object language.
                        Call LxTakeNumber(oPor, s)
                        bCloser = True
                    Else
                        sLine = oPor.getString()
                        If bCloser Then
                            If Left(sLine, 1) = ")" Then sLine = Mid(sLine, 2)
                            bCloser = False
                        End If
                        If Len(sLine) > 0 Then _
                            s = s & LxTagged(sLine, LxFormatIndex(oPor))
                    End If
                Loop
            End If
            s = s & Chr(10)
        Loop
    End If

    ' Anything the enumeration could not read — a selection that is not a
    ' text range at all — still has a string, and a plain example is better
    ' than none.
    If Len(LxStrip(s)) = 0 Then
        LxFmtN = 0
        s = oRange.getString()
    End If

    s = Replace(s, Chr(13) & Chr(10), Chr(10))
    s = Replace(s, Chr(13), Chr(10))
    s = Replace(s, Chr(11), Chr(10))
    aRaw = Split(s, Chr(10))

    ReDim aOut(UBound(aRaw))
    n = 0
    For i = 0 To UBound(aRaw)
        sLine = LxTrimTagged(aRaw(i))
        If Len(sLine) > 0 Then
            aOut(n) = sLine
            n = n + 1
        End If
    Next i

    If n = 0 Then
        LxSelectedLines = Array()
    Else
        ReDim Preserve aOut(n - 1)
        LxSelectedLines = aOut()
    End If
End Function


' ----------------------------------------------------------- the number ---

' An example number the selection already carries, waiting to be taken over.
'
' A cross-reference binds to the *identity* of a NumEx field — its
' ref-name, which UNO calls SequenceValue — and not to the number it
' happens to show.  So an example that is rebuilt must not be handed a new
' field: every reference to it would resolve to "Error: Reference source
' not found", and there is no way to point them back.  A number found in
' the selection is therefore taken over rather than remade, and
' LxInsertNumber transplants its identity into the field it creates.
'
' That is the whole of the rule: the number an example is built with is
' the one it was given, if it was given one.
Dim LxNumId  As Long          ' SequenceValue of the number to take over
Dim LxNumHas As Boolean
Dim LxNumErr As String        ' read by the commands, as LxTErr is


' The drawings found in the example being untypesetted: which cell each
' sits in, and the bracket notation it was drawn from.  Read once, before
' the rows are walked, because a shape knows its cell but a cell does not
' know its shapes.
Const SHAPE_MAX As Integer = 60           ' trees in one example
Dim LxShCell(SHAPE_MAX) As String
Dim LxShSrc(SHAPE_MAX)  As String
Dim LxShN               As Integer


' Is this portion an example number — a NumEx field of the kind
' LxInsertNumber makes?
'
' A cross-reference *to* an example is a GetReference field and answers
' False, so a selection that refers to other examples is untouched; so is
' every other field a document may have in it.
Function LxIsNumberField(oPor As Object) As Boolean
    Dim oFld As Object
    Dim sName As String

    LxIsNumberField = False
    oFld = Nothing
    On Error Resume Next
    oFld = oPor.TextField
    On Error Goto 0
    If IsNull(oFld) Then Exit Function
    If Not oFld.supportsService("com.sun.star.text.TextField.SetExpression") _
        Then Exit Function

    sName = ""
    On Error Resume Next
    sName = oFld.TextFieldMaster.Name
    On Error Goto 0
    LxIsNumberField = (sName = SEQ_NAME)
End Function


' Take the number over, and take it out of the text.
'
' The literal "(" in front of it goes with it — LxInsertNumber writes the
' parentheses itself, and left in they would become the first word of the
' example.  The ")" after it is dropped by the caller, which is holding the
' portion it leads.
Sub LxTakeNumber(oPor As Object, ByRef s As String)
    Dim oFld As Object

    If LxNumHas Then
        LxNumErr = "The selection carries two example numbers." & _
                   Chr(10) & Chr(10) & _
                   "An example has one.  Typeset one example at a time."
        Exit Sub
    End If

    ' The number leads the example it belongs to.  One found after the text
    ' has started belongs to something else — most likely a second example
    ' further down the selection — and taking it over would move a number
    ' from one example to another silently.
    If Not LxOnlyOpener(s) Then
        LxNumErr = "An example number appears part-way through the " & _
                   "selection." & Chr(10) & Chr(10) & _
                   "The number an example takes over has to lead it.  " & _
                   "Start the selection at the number, or leave the number " & _
                   "out and a new one is made."
        Exit Sub
    End If

    oFld = oPor.TextField
    LxNumId = oFld.SequenceValue
    LxNumHas = True
    If Right(s, 1) = "(" Then s = Left(s, Len(s) - 1)
End Sub


' Is there nothing in the text so far but the opening parenthesis of the
' number about to be read?  Format marks do not count as text, and neither
' does a blank line above the example.
Function LxOnlyOpener(s As String) As Boolean
    Dim t As String
    t = LxStrip(s)
    t = Replace(t, "(", "")
    t = Replace(t, Chr(9), "")
    t = Replace(t, Chr(10), "")
    LxOnlyOpener = (Len(Trim(t)) = 0)
End Function


' ------------------------------------------------------------ run marks ---

' The format of one text portion, as an index into the LxFmt* arrays.
'
' Font name and size are deliberately not part of it.  Carrying them would
' mean writing them back as direct formatting on every cell, and then
' editing LxExampleCell would no longer change the example — the whole point
' of the styles.  What is carried is what a linguist marks *within* a line
' and would notice the loss of.
Function LxFormatIndex(oPor As Object) As Integer
    Dim i As Integer
    Dim nCase As Integer, nEsc As Integer, nEscH As Integer, nUnder As Integer
    Dim dWeight As Double
    Dim bItalic As Boolean
    Dim sStyle As String

    nCase = com.sun.star.style.CaseMap.NONE
    dWeight = com.sun.star.awt.FontWeight.NORMAL
    bItalic = False
    sStyle = ""
    nEsc = 0 : nEscH = 100 : nUnder = com.sun.star.awt.FontUnderline.NONE

    On Error Resume Next
    nCase = oPor.CharCaseMap
    dWeight = oPor.CharWeight
    bItalic = (oPor.CharPosture <> com.sun.star.awt.FontSlant.NONE)
    sStyle = oPor.CharStyleName
    nEsc = oPor.CharEscapement
    nEscH = oPor.CharEscapementHeight
    nUnder = oPor.CharUnderline
    On Error Goto 0

    For i = 0 To LxFmtN - 1
        If LxFmtCase(i) = nCase And LxFmtWeight(i) = dWeight And _
           LxFmtItalic(i) = bItalic And LxFmtStyle(i) = sStyle And _
           LxFmtEsc(i) = nEsc And LxFmtEscH(i) = nEscH And _
           LxFmtUnder(i) = nUnder Then
            LxFormatIndex = i
            Exit Function
        End If
    Next i

    ' More distinct formats than there are marks to name them with: the rest
    ' of the example is still built, just without its formatting.
    If LxFmtN > FMT_MAX Then
        LxFormatIndex = -1
        Exit Function
    End If

    i = LxFmtN
    LxFmtCase(i) = nCase
    LxFmtWeight(i) = dWeight
    LxFmtItalic(i) = bItalic
    LxFmtStyle(i) = sStyle
    LxFmtEsc(i) = nEsc
    LxFmtEscH(i) = nEscH
    LxFmtUnder(i) = nUnder
    LxFmtFont(i) = Nothing
    LxFmtFontSC(i) = Nothing
    LxFmtN = LxFmtN + 1
    LxFormatIndex = i
End Function


Function LxTag(nFmt As Integer) As String
    If nFmt < 0 Then LxTag = "" Else LxTag = Chr(FMT_BASE + nFmt)
End Function


' The format a mark stands for, or -1 if this is an ordinary character.
Function LxTagIndex(c As String) As Integer
    Dim n As Long
    LxTagIndex = -1
    If Len(c) <> 1 Then Exit Function
    n = Asc(c) - FMT_BASE
    If n >= 0 And n < LxFmtN Then LxTagIndex = CInt(n)
End Function


' Mark the text, and mark it again after every space — so that whatever
' splits it into words, every word comes away knowing its own format.
Function LxTagged(s As String, nFmt As Integer) As String
    Dim sTag As String, sOut As String, c As String
    Dim i As Integer
    Dim bSpace As Boolean

    sTag = LxTag(nFmt)
    If Len(sTag) = 0 Then
        LxTagged = s
        Exit Function
    End If

    sOut = sTag
    bSpace = False
    For i = 1 To Len(s)
        c = Mid(s, i, 1)
        If c = " " Or c = Chr(9) Then
            sOut = sOut & c
            bSpace = True
        Else
            If bSpace Then sOut = sOut & sTag
            sOut = sOut & c
            bSpace = False
        End If
    Next i
    LxTagged = sOut
End Function


' The text without its marks — what the line "really says", for every test
' that asks a question about the characters a linguist typed.
Function LxStrip(s As String) As String
    Dim i As Integer
    Dim c As String, sOut As String
    For i = 1 To Len(s)
        c = Mid(s, i, 1)
        If LxTagIndex(c) < 0 Then sOut = sOut & c
    Next i
    LxStrip = sOut
End Function


' Trim, keeping the mark that the first surviving character is under: plain
' Trim() would not even see the spaces, because a mark stands in front of
' them.
Function LxTrimTagged(s As String) As String
    Dim i As Integer, n As Integer
    Dim c As String, sTag As String

    n = Len(s)
    Do While n > 0
        c = Mid(s, n, 1)
        If c <> " " And c <> Chr(9) Then Exit Do
        n = n - 1
    Loop

    i = 1
    sTag = ""
    Do While i <= n
        c = Mid(s, i, 1)
        If LxTagIndex(c) >= 0 Then
            sTag = c
        ElseIf c <> " " And c <> Chr(9) Then
            Exit Do
        End If
        i = i + 1
    Loop

    If i > n Then
        LxTrimTagged = ""
    Else
        LxTrimTagged = sTag & Mid(s, i, n - i + 1)
    End If
End Function


Function LxLastTag(s As String) As String
    Dim i As Integer
    Dim c As String
    LxLastTag = ""
    For i = Len(s) To 1 Step -1
        c = Mid(s, i, 1)
        If LxTagIndex(c) >= 0 Then
            LxLastTag = c
            Exit Function
        End If
    Next i
End Function


' Text cut out of the middle of a line has lost the mark that was in force
' where the cut was made; give it back the one the part before it ended on.
Function LxCarryTag(sFrom As String, s As String) As String
    Dim sTag As String
    LxCarryTag = s
    If Len(s) = 0 Then Exit Function
    If LxTagIndex(Left(s, 1)) >= 0 Then Exit Function
    sTag = LxLastTag(sFrom)
    If Len(sTag) > 0 Then LxCarryTag = sTag & s
End Function


' Does this line open with a sub-example marker — "a.", "(b)", "iii."?
'
' Deliberately narrow, because a false positive refuses to gloss a perfectly
' good example: the token must be a single letter or a roman numeral, so
' "Dr." and "no." are not markers while "a." and "ii." are.
Function LxLooksLikeMarker(sLine As String) As Boolean
    Dim aWords As Variant
    Dim s As String, c As String
    Dim i As Integer

    LxLooksLikeMarker = False
    aWords = LxSplitWords(LxStrip(sLine))
    If UBound(aWords) < 0 Then Exit Function

    s = aWords(0)
    If Len(s) < 2 Or Len(s) > 6 Then Exit Function
    c = Right(s, 1)
    If c <> "." And c <> ")" Then Exit Function
    s = Left(s, Len(s) - 1)
    If Left(s, 1) = "(" Then s = Mid(s, 2)
    If Len(s) = 0 Then Exit Function

    If Len(s) = 1 Then
        c = LCase(s)
        LxLooksLikeMarker = (c >= "a" And c <= "z")
        Exit Function
    End If

    For i = 1 To Len(s)                       ' roman numeral?
        If InStr("ivxlcdm", LCase(Mid(s, i, 1))) = 0 Then Exit Function
    Next i
    LxLooksLikeMarker = True
End Function


' Does this line open like a free translation?
'
' The opening quote is the only signal available — linguexx has \glt, we
' have the character the linguist typed — so the list has to cover what
' they actually type.  Chr(96), the backtick, is the one that matters most:
' `like this' is the LaTeX convention, so it is exactly what someone coming
' from linguexx reaches for, and autocorrect turns only the closing half
' into a curly quote.  Missing it made the translation a third gloss tier,
' which put it inside the first band of a long example instead of at the
' end of the table, split one word per column.
' Characters a free translation may open with.  A Function, not a Const:
' Basic's Const takes a compile-time constant expression only, and Chr() is
' a call — declaring it as a Const makes the whole module fail to compile,
' which in headless LibreOffice shows up as the macro quietly doing nothing.
Function LxQuotes() As String
    LxQuotes = "'" & Chr(34) & Chr(96) & Chr(171) & Chr(8216) & Chr(8217) & _
               Chr(8218) & Chr(8220) & Chr(8222) & Chr(8249)
End Function


Function LxIsTranslation(s As String) As Boolean
    Dim c As String
    c = Left(Trim(LxStrip(s)), 1)
    LxIsTranslation = (InStr(LxQuotes(), c) > 0)
End Function


' Whitespace splits words, except inside {braces} — linguexx's way of
' making several words share one column.  The braces are not kept.
'
' Format marks are not characters of the word: one in the middle of a word
' stays where it is, and the last one seen opens the *next* word, so a
' format that spans a space is not lost at the space.  A word that would be
' nothing but marks is no word at all.
Function LxSplitWords(sLine As String) As Variant
    Dim aOut() As String
    Dim n As Integer, i As Integer, nDepth As Integer
    Dim sCur As String, c As String, sTag As String

    ReDim aOut(LxMaxI(Len(sLine), 1))
    n = -1 : sCur = "" : nDepth = 0 : sTag = ""
    For i = 1 To Len(sLine)
        c = Mid(sLine, i, 1)
        If LxTagIndex(c) >= 0 Then
            sTag = c
            If Len(sCur) > 0 Then sCur = sCur & c
        ElseIf c = "{" Then
            nDepth = nDepth + 1
        ElseIf c = "}" Then
            If nDepth > 0 Then nDepth = nDepth - 1
        ElseIf (c = " " Or c = Chr(9)) And nDepth = 0 Then
            If Len(sCur) > 0 Then
                n = n + 1 : aOut(n) = LxTrimTags(sCur) : sCur = ""
            End If
        Else
            If Len(sCur) = 0 Then sCur = sTag
            sCur = sCur & c
        End If
    Next i
    If Len(sCur) > 0 Then n = n + 1 : aOut(n) = LxTrimTags(sCur)

    If n < 0 Then
        LxSplitWords = Array()
    Else
        ReDim Preserve aOut(n)
        LxSplitWords = aOut()
    End If
End Function


' Drop marks left dangling at the end of a word, where they can only open a
' run with nothing in it.
Function LxTrimTags(s As String) As String
    Dim n As Integer
    n = Len(s)
    Do While n > 0
        If LxTagIndex(Mid(s, n, 1)) < 0 Then Exit Do
        n = n - 1
    Loop
    LxTrimTags = Left(s, n)
End Function


' The mark comes away as plain text — it is set in its own cell, in that
' cell's style — but whatever formatting was in force has to stay with the
' word behind it.
Function LxPullJudgment(sWord As String, ByRef sMark As String) As String
    Dim i As Integer
    Dim c As String, sTag As String

    sMark = "" : sTag = "" : i = 1
    Do While i <= Len(sWord)
        c = Mid(sWord, i, 1)
        If LxTagIndex(c) >= 0 Then
            sTag = c
        ElseIf InStr(JUDG_CHARS, c) = 0 Then
            Exit Do
        Else
            sMark = sMark & c
        End If
        i = i + 1
    Loop
    LxPullJudgment = LxCarryTag(sTag, Mid(sWord, i))
End Function


Function LxDropFirst(aWords As Variant) As Variant
    Dim aOut() As String, i As Integer
    If UBound(aWords) < 1 Then
        LxDropFirst = Array()
        Exit Function
    End If
    ReDim aOut(UBound(aWords) - 1)
    For i = 1 To UBound(aWords)
        aOut(i - 1) = aWords(i)
    Next i
    LxDropFirst = aOut()
End Function


' Greedy packing, identical in spirit to Emitter._bands.
Function LxPackBands(aWordW() As Double, nWords As Integer, dAvail As Double, _
                     aBandStart() As Integer) As Integer
    Dim i As Integer, n As Integer
    Dim dAcc As Double
    ReDim aBandStart(nWords)
    aBandStart(0) = 0 : n = 1 : dAcc = 0
    For i = 0 To nWords - 1
        If dAcc + aWordW(i) > dAvail And i > aBandStart(n - 1) Then
            aBandStart(n) = i : n = n + 1 : dAcc = 0
        End If
        dAcc = dAcc + aWordW(i)
    Next i
    LxPackBands = n
End Function


' The shared column grid of one example's table.
'
' Bands each start at the left edge, so their word boundaries fall in
' different places.  A table has one column grid, so the grid is the
' *union* of every band's boundaries, and each word spans the columns it
' covers.  Anything simpler couples the bands together: with one
' rectangular grid, the fifth column of band 2 has to be as wide as the
' fifth column of band 1, so one long word stretches an unrelated column
' in another line.  This is what linguexx2odt's Grid class builds, and what
' merging cells by hand in Writer produces.
Function LxBuildGrid(aWordW() As Double, nWords As Integer, _
                     aBandStart() As Integer, nBands As Integer, _
                     ByRef aColW() As Double, ByRef aWordCol() As Integer, _
                     ByRef aWordSpan() As Integer) As Integer
    Dim aEdge() As Double, aUniq() As Double
    Dim nEdges As Integer, nU As Integer
    Dim b As Integer, i As Integer, j As Integer, k As Integer
    Dim nEnd As Integer, lo As Integer, hi As Integer
    Dim x As Double, dPrev As Double, dTmp As Double

    ReDim aWordCol(LxMaxI(nWords - 1, 0))
    ReDim aWordSpan(LxMaxI(nWords - 1, 0))

    ' every band's cumulative boundaries, measured from the left edge
    ReDim aEdge(LxMaxI(nWords, 1) * LxMaxI(nBands, 1))
    nEdges = 0
    For b = 0 To nBands - 1
        x = 0
        nEnd = LxBandEnd(aBandStart(), nBands, nWords, b)
        For j = aBandStart(b) To nEnd - 1
            x = x + aWordW(j)
            aEdge(nEdges) = x
            nEdges = nEdges + 1
        Next j
    Next b
    If nEdges = 0 Then
        ReDim aColW(0)
        aColW(0) = 0
        LxBuildGrid = 0
        Exit Function
    End If

    For i = 1 To nEdges - 1                   ' insertion sort; a few dozen at most
        dTmp = aEdge(i)
        k = i - 1
        Do While k >= 0
            If aEdge(k) <= dTmp Then Exit Do
            aEdge(k + 1) = aEdge(k)
            k = k - 1
        Loop
        aEdge(k + 1) = dTmp
    Next i

    ReDim aUniq(nEdges - 1)                   ' boundaries closer than the
    nU = 0                                    ' tolerance are one boundary
    For i = 0 To nEdges - 1
        If nU = 0 Then
            aUniq(0) = aEdge(0)
            nU = 1
        ElseIf aEdge(i) - aUniq(nU - 1) > GRID_TOL_CM Then
            aUniq(nU) = aEdge(i)
            nU = nU + 1
        End If
    Next i

    ReDim aColW(nU - 1)
    dPrev = 0
    For i = 0 To nU - 1
        aColW(i) = aUniq(i) - dPrev
        dPrev = aUniq(i)
    Next i

    For b = 0 To nBands - 1
        x = 0
        nEnd = LxBandEnd(aBandStart(), nBands, nWords, b)
        For j = aBandStart(b) To nEnd - 1
            lo = LxEdgeIndex(aUniq(), nU, x)
            x = x + aWordW(j)
            hi = LxEdgeIndex(aUniq(), nU, x)
            aWordCol(j) = lo
            aWordSpan(j) = LxMaxI(1, hi - lo)
        Next j
    Next b

    LxBuildGrid = nU
End Function


' How many grid columns lie left of x.
Function LxEdgeIndex(aUniq() As Double, nU As Integer, x As Double) As Integer
    Dim i As Integer, n As Integer
    For i = 0 To nU - 1
        If Abs(aUniq(i) - x) <= GRID_TOL_CM Then
            LxEdgeIndex = i + 1
            Exit Function
        End If
    Next i
    n = 0
    For i = 0 To nU - 1
        If aUniq(i) < x Then n = n + 1
    Next i
    LxEdgeIndex = n
End Function


Function LxBandEnd(aBandStart() As Integer, nBands As Integer, _
                   nWords As Integer, b As Integer) As Integer
    If b + 1 < nBands Then
        LxBandEnd = LxMinI(aBandStart(b + 1), nWords)
    Else
        LxBandEnd = nWords
    End If
End Function


' --------------------------------------------------------- measurement ---

' The point of the whole exercise: a real font, really measured.
Function LxFontForRange(oDoc As Object, oRange As Object, ByRef dPxPerCm As Double) As Object
    Dim oDev As Object, oInfo As Object
    Dim sName As String
    Dim dPt As Double
    Dim aFD As New com.sun.star.awt.FontDescriptor

    ' Writer's own layout device where available — it is what the page is
    ' measured against — falling back to a screen-compatible one.
    oDev = Nothing
    On Error Resume Next
    oDev = oDoc.ReferenceDevice
    On Error Goto 0
    If IsNull(oDev) Then
        oDev = createUnoService("com.sun.star.awt.Toolkit").createScreenCompatibleDevice(200, 200)
    End If
    oInfo = oDev.getInfo()
    dPxPerCm = oInfo.PixelPerMeterX / 100.0

    sName = "" : dPt = 0
    On Error Resume Next
    sName = oRange.CharFontName
    dPt = oRange.CharHeight
    On Error Goto 0
    If Len(sName) = 0 Then sName = "Liberation Serif"
    If dPt <= 0 Then dPt = 12

    aFD.Name = sName
    aFD.Height = CLng(dPt / 72.0 * 2.54 * dPxPerCm)
    LxFontForRange = oDev.getFont(aFD)

    Call LxBuildFmtFonts(oDev, sName, dPt, dPxPerCm)
End Function


' One measuring font per run format.  Bold and italic are wider than roman,
' a superscript is smaller, and small caps need a second font at SC_RATIO to
' draw their lowercase with — measure any of them with the body font and the
' column comes out the wrong width.
'
' Only weight, slant and size vary: the family is the one the example is
' being set in, because that is the one the table will be set in too.
Sub LxBuildFmtFonts(oDev As Object, sName As String, dPt As Double, dPxPerCm As Double)
    Dim aFD As New com.sun.star.awt.FontDescriptor
    Dim i As Integer
    Dim dSize As Double

    For i = 0 To LxFmtN - 1
        dSize = dPt
        If LxFmtEscH(i) > 0 And LxFmtEscH(i) < 100 Then _
            dSize = dPt * LxFmtEscH(i) / 100.0

        aFD.Name = sName
        aFD.Weight = LxFmtWeight(i)
        If LxFmtItalic(i) Then
            aFD.Slant = com.sun.star.awt.FontSlant.ITALIC
        Else
            aFD.Slant = com.sun.star.awt.FontSlant.NONE
        End If
        aFD.Height = CLng(dSize / 72.0 * 2.54 * dPxPerCm)
        LxFmtFont(i) = oDev.getFont(aFD)

        If LxFmtCase(i) = com.sun.star.style.CaseMap.SMALLCAPS Then
            aFD.Height = CLng(dSize * SC_RATIO / 72.0 * 2.54 * dPxPerCm)
            LxFmtFontSC(i) = oDev.getFont(aFD)
        Else
            LxFmtFontSC(i) = Nothing
        End If
    Next i
End Sub


' The width of a marked string: each run measured in its own font, in what
' it will actually be drawn as.
Function LxWidth(oFont As Object, dPxPerCm As Double, s As String) As Double
    Dim i As Integer, nFmt As Integer
    Dim c As String, sRun As String
    Dim d As Double

    d = 0 : sRun = "" : nFmt = -1
    For i = 1 To Len(s)
        c = Mid(s, i, 1)
        If LxTagIndex(c) >= 0 Then
            d = d + LxRunWidth(oFont, dPxPerCm, sRun, nFmt)
            sRun = ""
            nFmt = LxTagIndex(c)
        Else
            sRun = sRun & c
        End If
    Next i
    LxWidth = d + LxRunWidth(oFont, dPxPerCm, sRun, nFmt)
End Function


Function LxRunWidth(oFont As Object, dPxPerCm As Double, _
                    s As String, nFmt As Integer) As Double
    Dim oF As Object

    LxRunWidth = 0
    If Len(s) = 0 Then Exit Function
    If nFmt < 0 Then
        LxRunWidth = oFont.getStringWidth(s) / dPxPerCm
        Exit Function
    End If

    oF = LxFmtFont(nFmt)
    If IsNull(oF) Then oF = oFont

    ' A case map changes what is drawn, not what the text says, so the
    ' string has to be measured as it will appear.
    Select Case LxFmtCase(nFmt)
    Case com.sun.star.style.CaseMap.UPPERCASE
        LxRunWidth = oF.getStringWidth(UCase(s)) / dPxPerCm
    Case com.sun.star.style.CaseMap.LOWERCASE
        LxRunWidth = oF.getStringWidth(LCase(s)) / dPxPerCm
    Case com.sun.star.style.CaseMap.SMALLCAPS
        LxRunWidth = LxSmallCapsWidth(oF, LxFmtFontSC(nFmt), dPxPerCm, s)
    Case Else
        LxRunWidth = oF.getStringWidth(s) / dPxPerCm
    End Select
End Function


' Small caps: every lowercase letter is drawn as its capital at SC_RATIO of
' the size, everything else at full size.  Measured in runs of like
' characters rather than one at a time, so that kerning inside a run of
' capitals still counts.
Function LxSmallCapsWidth(oF As Object, oSC As Object, dPxPerCm As Double, _
                          s As String) As Double
    Dim i As Integer
    Dim c As String, sSeg As String
    Dim bLower As Boolean, bThis As Boolean
    Dim d As Double

    d = 0 : sSeg = "" : bLower = False
    For i = 1 To Len(s)
        c = Mid(s, i, 1)
        bThis = (UCase(c) <> c)               ' a letter with a capital form
        If Len(sSeg) > 0 And bThis <> bLower Then
            d = d + LxSegWidth(oF, oSC, dPxPerCm, sSeg, bLower)
            sSeg = ""
        End If
        bLower = bThis
        sSeg = sSeg & c
    Next i
    LxSmallCapsWidth = d + LxSegWidth(oF, oSC, dPxPerCm, sSeg, bLower)
End Function


Function LxSegWidth(oF As Object, oSC As Object, dPxPerCm As Double, _
                    s As String, bLower As Boolean) As Double
    LxSegWidth = 0
    If Len(s) = 0 Then Exit Function
    If bLower And Not IsNull(oSC) Then
        LxSegWidth = oSC.getStringWidth(UCase(s)) / dPxPerCm
    Else
        LxSegWidth = oF.getStringWidth(s) / dPxPerCm
    End If
End Function


' The text block of the page the cursor is on, in cm.
Function LxTextWidthCm(oDoc As Object) As Double
    Dim oPS As Object, sStyle As String
    sStyle = oDoc.getCurrentController().getViewCursor().PageStyleName
    oPS = oDoc.getStyleFamilies().getByName("PageStyles").getByName(sStyle)
    LxTextWidthCm = (oPS.Width - oPS.LeftMargin - oPS.RightMargin) / 1000.0
End Function


' ------------------------------------------------------------ ODF bits ---

Sub LxInsertNumber(oDoc As Object, oCell As Object)
    Dim oText As Object, oCur As Object
    oText = oCell.getText()
    oText.setString("")
    oCur = oText.createTextCursor()
    Call LxPutNumber(oDoc, oText, oCur)
End Sub


' The number itself, written at a cursor: in the cell of a table being
' built, or — when an example is untypeset — into the line of text the
' example comes back as, where it goes on standing for that example until
' the example is built again.
Sub LxPutNumber(oDoc As Object, oText As Object, oCur As Object)
    Dim oMaster As Object, oField As Object
    Dim sMaster As String

    sMaster = "com.sun.star.text.FieldMaster.SetExpression." & SEQ_NAME
    If oDoc.getTextFieldMasters().hasByName(sMaster) Then
        oMaster = oDoc.getTextFieldMasters().getByName(sMaster)
    Else
        oMaster = oDoc.createInstance("com.sun.star.text.FieldMaster.SetExpression")
        oMaster.Name = SEQ_NAME
    End If
    oMaster.SubType = com.sun.star.text.SetVariableType.SEQUENCE

    oField = oDoc.createInstance("com.sun.star.text.TextField.SetExpression")
    oField.Content = SEQ_NAME & "+1"
    oField.NumberingType = com.sun.star.style.NumberingType.ARABIC
    oField.attachTextFieldMaster(oMaster)

    ' The identity of the number the selection carried, if it carried one:
    ' this field becomes the one the cross-references were already pointing
    ' at, and they keep resolving.  Set after the master is attached and
    ' before the field is inserted, which is the order that was measured to
    ' work; LibreOffice does hand out the freed identity by itself when the
    ' old field is the only one gone, but that is luck rather than a
    ' promise, and two examples in flight would break it.
    If LxNumHas Then oField.SequenceValue = LxNumId

    ' Literal parentheses around a live number-range field: renumbering
    ' then costs nothing but F9, and \label/\ref written by linguexx2odt
    ' into the same NumEx sequence keep pointing at the right example.
    oCur.collapseToEnd()
    oText.insertString(oCur, "(", False)
    oText.insertTextContent(oCur, oField, False)
    oCur.collapseToEnd()
    oText.insertString(oCur, ")", False)
End Sub


' No borders, no cell padding — a glossed example has to read as aligned
' text, not as a spreadsheet.  The padding matters twice over: Writer's
' default is 0.097cm on every side, which is wider than the gap we put
' between columns, so leaving it makes every measured column too narrow and
' the words wrap inside their cells.
Sub LxPlainTable(oTable As Object)
    Dim aBorder As New com.sun.star.table.TableBorder
    Dim aLine As New com.sun.star.table.BorderLine

    aLine.Color = 0
    aLine.InnerLineWidth = 0
    aLine.OuterLineWidth = 0
    aLine.LineDistance = 0

    aBorder.TopLine = aLine
    aBorder.BottomLine = aLine
    aBorder.LeftLine = aLine
    aBorder.RightLine = aLine
    aBorder.HorizontalLine = aLine
    aBorder.VerticalLine = aLine
    aBorder.IsTopLineValid = True
    aBorder.IsBottomLineValid = True
    aBorder.IsLeftLineValid = True
    aBorder.IsRightLineValid = True
    aBorder.IsHorizontalLineValid = True
    aBorder.IsVerticalLineValid = True
    aBorder.Distance = 0
    aBorder.IsDistanceValid = True

    oTable.TableBorder = aBorder
End Sub


Sub LxSetCellStyle(oTable As Object, sCell As String, sStyle As String)
    oTable.getCellByName(sCell).getText().createTextCursor().ParaStyleName = sStyle
End Sub


' setString for marked text: one insertion per run, each in the formatting
' it was read with.  Everything in the table that came from the linguist's
' own text goes through here; text this macro made up itself (the number,
' the sub-example brackets) does not, and is left to the cell style.
Sub LxPut(oCell As Object, sText As String)
    Dim oText As Object, oCur As Object

    oText = oCell.getText()
    oText.setString("")
    If Len(LxStrip(sText)) = 0 Then Exit Sub

    oCur = oText.createTextCursor()
    Call LxPutTagged(oText, oCur, sText)
End Sub


' The same, written at a cursor in any text rather than into a cell of its
' own — which is what Untypeset needs, putting an example back into the
' body text it came from.
Sub LxPutTagged(oText As Object, oCur As Object, sText As String)
    Dim i As Integer, nFmt As Integer
    Dim c As String, sRun As String

    sRun = "" : nFmt = -1
    For i = 1 To Len(sText)
        c = Mid(sText, i, 1)
        If LxTagIndex(c) >= 0 Then
            Call LxPutRun(oText, oCur, sRun, nFmt)
            sRun = ""
            nFmt = LxTagIndex(c)
        Else
            sRun = sRun & c
        End If
    Next i
    Call LxPutRun(oText, oCur, sRun, nFmt)
End Sub


' collapseToEnd, not gotoEnd: in a cell of its own the two are the same,
' but written into body text gotoEnd would jump to the end of the document
' and put the rest of the example there.
Sub LxPutRun(oText As Object, oCur As Object, sRun As String, nFmt As Integer)
    If Len(sRun) = 0 Then Exit Sub
    oCur.collapseToEnd()
    oText.insertString(oCur, sRun, False)
    oCur.goLeft(Len(sRun), True)              ' select what was just written
    Call LxApplyFmt(oCur, nFmt)
    oCur.collapseToEnd()
End Sub


' Put the run's formatting back.
'
' The character style goes on first, and then each property only if it is
' not already what the style gave — so text that was never formatted by hand
' comes out with no direct formatting at all, and a run that carried
' LxLeipzig still answers to LxLeipzig afterwards instead of being frozen
' into hard small caps.
Sub LxApplyFmt(oCur As Object, nFmt As Integer)
    If nFmt < 0 Then Exit Sub
    On Error Resume Next
    If Len(LxFmtStyle(nFmt)) > 0 Then oCur.CharStyleName = LxFmtStyle(nFmt)
    If oCur.CharCaseMap <> LxFmtCase(nFmt) Then oCur.CharCaseMap = LxFmtCase(nFmt)
    If oCur.CharWeight <> LxFmtWeight(nFmt) Then oCur.CharWeight = LxFmtWeight(nFmt)
    If (oCur.CharPosture <> com.sun.star.awt.FontSlant.NONE) <> LxFmtItalic(nFmt) Then
        If LxFmtItalic(nFmt) Then
            oCur.CharPosture = com.sun.star.awt.FontSlant.ITALIC
        Else
            oCur.CharPosture = com.sun.star.awt.FontSlant.NONE
        End If
    End If
    If oCur.CharEscapement <> LxFmtEsc(nFmt) Then
        oCur.CharEscapement = LxFmtEsc(nFmt)
        oCur.CharEscapementHeight = LxFmtEscH(nFmt)
    End If
    If oCur.CharUnderline <> LxFmtUnder(nFmt) Then oCur.CharUnderline = LxFmtUnder(nFmt)
    On Error Goto 0
End Sub


Sub LxMergeRow(oTable As Object, nRow As Integer, nCols As Integer)
    Dim oCur As Object
    If nCols < 2 Then Exit Sub
    oCur = oTable.createCursorByCellName(LxCell(0, nRow))
    oCur.goRight(nCols - 1, True)
    oCur.mergeRange()
End Sub


' Column widths, as relative positions of the n-1 separators between them.
'
' The separator array has to be *built*, never read back and modified:
' reading TableColumnSeparators off a table whose columns are still evenly
' spaced yields nothing at all, and assigning that to a variable fails with
' "Object variable not set".
'
' Unindented, the table spans the text block (HoriOrient FULL) so that it
' rescales with the page rather than running off it.  An indented one
' cannot: FULL means "the whole text block" and there is no margin to give
' it, so the table is placed and sized outright instead.  That is the one
' thing an indent costs — such an example holds its width when the page
' changes, where an unindented one follows it.
Sub LxSetColumns(oTable As Object, aWidths() As Double, nCols As Integer, _
                 dSum As Double, dIndent As Double, dTable As Double)
    Dim aSep() As Variant
    Dim i As Integer
    Dim dAcc As Double
    Dim nSum As Long

    If dIndent > 0 Then
        oTable.HoriOrient = com.sun.star.text.HoriOrientation.LEFT_AND_WIDTH
        oTable.LeftMargin = CLng(dIndent * 1000)
        oTable.Width = CLng(dTable * 1000)
    Else
        oTable.HoriOrient = com.sun.star.text.HoriOrientation.FULL
    End If
    If nCols < 2 Or dSum <= 0 Then Exit Sub

    nSum = oTable.TableColumnRelativeSum
    ReDim aSep(nCols - 2)
    dAcc = 0
    For i = 0 To nCols - 2
        dAcc = dAcc + aWidths(i)
        aSep(i) = createUnoStruct("com.sun.star.text.TableColumnSeparator")
        aSep(i).Position = CLng(dAcc / dSum * nSum)
        aSep(i).IsVisible = True
    Next i
    oTable.TableColumnSeparators = aSep()
End Sub


Function LxCell(nCol As Integer, nRow As Integer) As String
    LxCell = LxColName(nCol) & nRow
End Function


' The name Writer gives the nth column, counting from 0.
'
' Not base 26.  Writer runs A..Z and then *lowercase* a..z before it uses
' two letters at all — A, …, Z, a, …, z, AA, …, AZ, Aa, …, Az, BA — so the
' 27th column is "a" and not "AA".  Measured, on a table of 120 columns.
'
' This was base 26, and every example wider than 26 columns died on the
' first cell past Z with "Object variable not set": the name it asked for
' belonged to no cell.  A long glossed example reaches 26 columns easily —
' one column per word — so it was not an exotic case.
Function LxColName(nCol As Integer) As String
    Dim s As String, n As Integer, r As Integer
    n = nCol : s = ""
    Do
        r = n Mod 52
        If r < 26 Then
            s = Chr(65 + r) & s
        Else
            s = Chr(97 + r - 26) & s
        End If
        n = n \ 52 - 1
    Loop While n >= 0
    LxColName = s
End Function


' ---------------------------------------------------------------- styles ---

' Created only when missing, so a document converted by linguexx2odt keeps
' the styles it arrived with and the user's edits to them are never undone.
Sub LxEnsureStyles(oDoc As Object)
    Dim oFam As Object, oStyle As Object
    Dim aSpacing As New com.sun.star.style.LineSpacing

    oFam = oDoc.getStyleFamilies().getByName("ParagraphStyles")

    If Not oFam.hasByName(CELL_PARA) Then
        oStyle = oDoc.createInstance("com.sun.star.style.ParagraphStyle")
        oStyle.ParentStyle = "Table Contents"
        oFam.insertByName(CELL_PARA, oStyle)
        oStyle.ParaTopMargin = 0
        oStyle.ParaBottomMargin = 0
        oStyle.ParaFirstLineIndent = 0
    End If

    If Not oFam.hasByName(TRANS_PARA) Then
        oStyle = oDoc.createInstance("com.sun.star.style.ParagraphStyle")
        oStyle.ParentStyle = CELL_PARA
        oFam.insertByName(TRANS_PARA, oStyle)
        oStyle.ParaTopMargin = 100                      ' 0.1 cm
    End If

    If Not oFam.hasByName(JUDG_PARA) Then
        oStyle = oDoc.createInstance("com.sun.star.style.ParagraphStyle")
        oStyle.ParentStyle = CELL_PARA
        oFam.insertByName(JUDG_PARA, oStyle)
        oStyle.ParaAdjust = com.sun.star.style.ParagraphAdjust.RIGHT
    End If

    ' Declares nothing, so it is CELL_PARA in every visible respect.  It is
    ' a mark rather than a look: it says "this row starts a new band", which
    ' a finished table cannot otherwise tell anyone — see LxRowIsBand.
    If Not oFam.hasByName(BAND_PARA) Then
        oStyle = oDoc.createInstance("com.sun.star.style.ParagraphStyle")
        oStyle.ParentStyle = CELL_PARA
        oFam.insertByName(BAND_PARA, oStyle)
    End If

    ' The space around an example: a fixed line height on an empty spacer
    ' row.  A table margin would work too, but LibreOffice ignores
    ' style:parent-style-name on table styles, so it could never be a style
    ' the user can edit.  See notes/findings.md.
    If Not oFam.hasByName(SPACE_PARA) Then
        oStyle = oDoc.createInstance("com.sun.star.style.ParagraphStyle")
        oStyle.ParentStyle = CELL_PARA
        oFam.insertByName(SPACE_PARA, oStyle)
        aSpacing.Mode = com.sun.star.style.LineSpacingMode.FIX
        aSpacing.Height = CInt(SPACE_CM * 1000)
        oStyle.ParaLineSpacing = aSpacing
        oStyle.CharHeight = 1
    End If
    Call LxEnsureChildStyle(oDoc, oFam, SPACE_ABOVE)
    Call LxEnsureChildStyle(oDoc, oFam, SPACE_BELOW)
End Sub


' Declares nothing of its own, so it tracks SPACE_PARA: editing the parent
' moves both gaps, giving a child a height of its own moves only that side.
Sub LxEnsureChildStyle(oDoc As Object, oFam As Object, sName As String)
    Dim oStyle As Object
    If oFam.hasByName(sName) Then Exit Sub
    oStyle = oDoc.createInstance("com.sun.star.style.ParagraphStyle")
    oStyle.ParentStyle = SPACE_PARA
    oFam.insertByName(sName, oStyle)
End Sub


' ============================================================ untypeset ===
'
' An example, back as the lines it was built from.
'
' This is what makes a typeset example changeable.  A built example is a
' table whose columns are already set: editing it in place means editing
' cell by cell, and a word added or removed needs a column the table has
' not got.  Building a replacement was worse — a new example takes a new
' number, and every cross-reference to the old one dies with it.
'
' So the example comes back as text, with its number still at the head of
' the first line, and the number is taken over again when it is built
' afresh (see LxTakeNumber).  Edit the text as text, select it, typeset it:
' the same example, the same number, the same references — and any of the
' building commands will take it, so a glossed example can come back as a
' tree or a paradigm.
'
' What it reads is the table, and only the table.  Nothing was written down
' at build time to be read back here, because a second copy of the example
' would start drifting from the first the moment anyone edited a cell.  The
' one thing the table cannot say for itself is where a band begins — its
' rows are built exactly like tier rows — and that is recorded as a *style*
' on the row, which is structure rather than a copy of anything.  See
' BAND_PARA.
'
' Deliberately not handled: an example holding a drawn tree.  The drawing
' is shapes, and the bracket notation it was drawn from is not in them; the
' command says so rather than handing back an example with the tree quietly
' missing from it.

Sub UntypesetSelection
    Call LxUntypesetCommand()
End Sub


Function UntypesetSelectionQuiet() As String
    LxSilent = True
    LxLastMessage = ""
    Call UntypesetSelection
    LxSilent = False
    UntypesetSelectionQuiet = LxLastMessage
    LxLastMessage = ""
End Function


Sub LxUntypesetCommand()
    Dim oDoc As Object, oTable As Object, oText As Object
    Dim oCur As Object, oUndo As Object
    Dim aLines As Variant
    Dim nLines As Integer
    Dim sErr As String
    Dim bLead As Boolean

    oDoc = ThisComponent
    If IsNull(oDoc) Then
        Call LxSay("Run this in a Writer document.")
        Exit Sub
    End If
    If Not oDoc.supportsService("com.sun.star.text.TextDocument") Then
        Call LxSay("Run this in a Writer document.")
        Exit Sub
    End If

    oTable = Nothing
    On Error Resume Next
    oTable = oDoc.getCurrentController().getViewCursor().TextTable
    On Error Goto 0
    If IsNull(oTable) Then
        Call LxSay("Put the cursor in the example you want back as text.")
        Exit Sub
    End If

    If Not LxIsExampleTable(oTable) Then
        Call LxSay("That table is not an example." & Chr(10) & Chr(10) & _
                   "An example is topped and tailed by the spacer rows " & _
                   "that carry the space around it, and this one is not — " & _
                   "so taking it apart would be taking apart a table you " & _
                   "built yourself.")
        Exit Sub
    End If

    ' A tree comes back as the brackets it was drawn from, which the
    ' drawing carries.  One that carries none cannot: refusing keeps it,
    ' where going ahead would hand back an example with the drawing
    ' silently gone out of it.
    If Not LxReadShapes(oDoc, oTable) Then
        Call LxSay("That example holds a drawing this cannot read back." & _
                   Chr(10) & Chr(10) & _
                   "A tree keeps the bracket notation it was drawn from, " & _
                   "and this drawing has none: a picture put into the " & _
                   "example, or a tree drawn before trees kept theirs.  " & _
                   "Untypesetting it would lose it.")
        Exit Sub
    End If

    aLines = LxReadTable(oTable, sErr)
    If Len(sErr) > 0 Then
        Call LxSay(sErr)
        Exit Sub
    End If
    nLines = UBound(aLines) + 1
    If nLines < 1 Then
        Call LxSay("There is nothing in that example to give back.")
        Exit Sub
    End If

    oText = LxHostText(oDoc, oTable)
    oUndo = oDoc.getUndoManager()
    oUndo.enterUndoContext("Untypeset example")
    On Error Goto Cleanup

    ' Room for the text, in front of the table and inside the undo context
    ' — it is part of the same one step.  A cursor made here goes on
    ' pointing at the same place after the table is removed (measured).
    oCur = LxPlaceBefore(oDoc, oText, oTable, bLead)
    If IsNull(oCur) Then
        oUndo.leaveUndoContext()
        Call LxSay("There is nowhere to put the text: Writer would not " & _
                   "make a paragraph in front of that example.")
        Exit Sub
    End If
    ' The table goes first, so that at no moment do two fields claim the
    ' same identity: the number written back takes the old one's, and the
    ' old one has to be gone before it does.
    oText.removeTextContent(oTable)
    Call LxWriteLines(oDoc, oText, oCur, aLines, nLines, bLead)
Cleanup:
    oUndo.leaveUndoContext()
    If Err <> 0 Then Call LxSay(Error$ & " (line " & Erl & ")")
End Sub


' ------------------------------------------------------ reading it back ---

' Every line of the example: one per tier, one per translation, the
' sub-example letter and judgment mark back at the head of their item's
' first line, and the bands joined back onto the tiers they were split off.
Function LxReadTable(oTable As Object, ByRef sErr As String) As Variant
    Dim aOut() As String
    Dim aCells As Variant
    Dim aTree As Variant
    Dim nRows As Integer, nLead As Integer, nRow As Integer
    Dim nOut As Integer, nBase As Integer, nTier As Integer
    Dim n As Integer, j As Integer, nMax As Integer
    Dim bJudg As Boolean, bMarker As Boolean, bBand0 As Boolean, bStart As Boolean
    Dim sLine As String, sMark As String, sJudg As String, sPre As String
    Dim sTree As String

    sErr = ""
    LxFmtN = 0                                ' formats are read afresh
    LxNumHas = False
    LxNumId = 0

    nRows = oTable.getRows().getCount()
    nLead = LxLeadColumns(oTable, nRows, bJudg, bMarker)
    If nLead < 1 Then
        sErr = "That example does not say where its text begins." & _
               Chr(10) & Chr(10) & _
               "It has neither a judgment column nor a translation, which " & _
               "are the two things that give it away.  A converted " & _
               "document whose examples are never judged can look like " & _
               "this; typeset one example by hand and this will read it."
        LxReadTable = Array()
        Exit Function
    End If

    ' One line per row, and a row holding a tree gives back as many lines
    ' as its brackets were typed over.
    nMax = nRows
    For n = 0 To LxShN - 1
        nMax = nMax + UBound(Split(LxShSrc(n), Chr(10))) + 1
    Next n
    ReDim aOut(nMax)
    nOut = 0 : nBase = 0 : nTier = 0 : bBand0 = True

    For nRow = 1 To nRows
        aCells = LxRowCells(oTable, nRow)
        If UBound(aCells) < 0 Then
            ' nothing in this row to read
        ElseIf LxRowHasStyle(oTable, aCells, SPACE_ABOVE) _
            Or LxRowHasStyle(oTable, aCells, SPACE_BELOW) Then
            ' a spacer row: height, and nothing else
        ElseIf LxRowHasStyle(oTable, aCells, TRANS_PARA) Then
            ' The translation is running text in a cell of its own, so it
            ' comes back as it stands — no columns to rejoin, no braces.
            sLine = LxRowText(oTable, aCells, nLead, False)
            If Len(LxStrip(sLine)) > 0 Then
                aOut(nOut) = sLine
                nOut = nOut + 1
            End If
        Else
            ' The item's head cells.  A letter in the marker column starts a
            ' new item; so does the first content row, which has the number.
            sMark = ""
            If bMarker Then sMark = LxStrip(LxCellText(oTable, 1, nRow))
            sJudg = ""
            If bJudg Then sJudg = LxStrip(LxCellText(oTable, nLead - 1, nRow))
            bStart = (nOut = 0) Or (Len(sMark) > 0)
            If nOut = 0 Then Call LxTakeCellNumber(oTable, nRow)

            If bStart Then
                nBase = nOut : nTier = 0 : bBand0 = True
            ElseIf LxRowHasStyle(oTable, aCells, BAND_PARA) Then
                nTier = 0 : bBand0 = False    ' a band, not another tier
            End If

            sTree = LxRowTree(aCells, nLead)
            If Len(sTree) > 0 Then
                ' A drawn tree gives back the lines it was drawn from, which
                ' may be several: the brackets, and a "move a -> b" under
                ' them.  The judgment mark is *not* put back in front of
                ' them — it led those lines when they were read and leads
                ' them still — but the letter is, because that was taken off
                ' before the item was made.
                aTree = Split(sTree, Chr(10))
                For j = 0 To UBound(aTree)
                    sLine = Trim(aTree(j))
                    If j = 0 And Len(sMark) > 0 Then sLine = sMark & " " & sLine
                    If Len(sLine) > 0 Then
                        aOut(nOut) = sLine
                        nOut = nOut + 1
                    End If
                Next j
            Else
                sLine = LxRowText(oTable, aCells, nLead, True)
                If bStart Then
                    ' The letter leads its item's first line and the mark is
                    ' glued to the first word, which is how they were typed
                    ' and how LxParseItems reads them again.
                    sPre = ""
                    If Len(sMark) > 0 Then sPre = sMark & " "
                    sPre = sPre & sJudg
                    sLine = sPre & sLine
                End If

                If bBand0 Then
                    aOut(nOut) = sLine
                    nOut = nOut + 1
                ElseIf Len(LxStrip(sLine)) > 0 Then
                    ' This band's share of a tier already written: it belongs
                    ' on the end of that line, not on a line of its own.
                    n = nBase + nTier
                    If n < nOut Then
                        aOut(n) = aOut(n) & " " & sLine
                    Else
                        aOut(nOut) = sLine    ' more tiers than the first
                        nOut = nOut + 1       ' band had: not ours, keep it
                    End If
                End If
            End If
            nTier = nTier + 1
        End If
    Next nRow

    LxReadTable = LxNonEmpty(aOut(), nOut)
End Function


' The lines that have something in them, in order.
Function LxNonEmpty(aLines() As String, nLines As Integer) As Variant
    Dim aOut() As String
    Dim i As Integer, n As Integer
    ReDim aOut(LxMaxI(nLines - 1, 0))
    n = 0
    For i = 0 To nLines - 1
        If Len(LxStrip(LxTrimTagged(aLines(i)))) > 0 Then
            aOut(n) = LxTrimTagged(aLines(i))
            n = n + 1
        End If
    Next i
    If n = 0 Then
        LxNonEmpty = Array()
    Else
        ReDim Preserve aOut(n - 1)
        LxNonEmpty = aOut()
    End If
End Function


' How many columns come before the example's own text, and which of them
' are what.
'
' The judgment column answers it outright wherever there is one, and this
' macro reserves one in every example it builds.  Where there is none — a
' converted document that judges nothing has no judgment column at all —
' the wide cell of a translation row starts exactly where the text does,
' which is the same answer from the other side.  Nothing is inferred from
' what a cell happens to *contain*: a first word that reads like "a." would
' otherwise turn an example into a paradigm.
Function LxLeadColumns(oTable As Object, nRows As Integer, _
                       ByRef bJudg As Boolean, ByRef bMarker As Boolean) As Integer
    Dim aCells As Variant
    Dim nRow As Integer, i As Integer, nLead As Integer, nHead As Integer
    Dim sStyle As String

    bJudg = False : bMarker = False
    nLead = -1
    For nRow = 1 To nRows
        aCells = LxRowCells(oTable, nRow)
        For i = 0 To UBound(aCells)
            sStyle = LxCellStyle(oTable.getCellByName(aCells(i)))
            If sStyle = JUDG_PARA Then
                bJudg = True
                nLead = LxCellColOf(aCells(i)) + 1
                Exit For
            ElseIf sStyle = TRANS_PARA And nLead < 0 Then
                nLead = LxCellColOf(aCells(i))
            End If
        Next i
        If bJudg Then Exit For
    Next nRow

    If nLead >= 1 Then
        nHead = nLead                         ' the columns before the text,
        If bJudg Then nHead = nHead - 1       ' less the judgment column:
        bMarker = (nHead >= 2)                ' number alone, or number and
    End If                                    ' letter
    LxLeadColumns = nLead
End Function


' One row of the example, as text.
'
' A cell holding two words in a row of many is a {braced group} — it was
' one column because the braces said so, and it has to say so again or it
' comes back as two columns.  A row of *one* cell is the merged wide cell
' of an unglossed item or a translation, which is running text and must not
' be braced: hence bBrace, which the caller knows and this cannot.
Function LxRowText(oTable As Object, aCells As Variant, nLead As Integer, _
                   bBrace As Boolean) As String
    Dim i As Integer, nCount As Integer
    Dim s As String, sCell As String, sPlain As String

    nCount = 0
    For i = 0 To UBound(aCells)
        If LxCellColOf(aCells(i)) >= nLead Then nCount = nCount + 1
    Next i

    s = ""
    For i = 0 To UBound(aCells)
        If LxCellColOf(aCells(i)) >= nLead Then
            sCell = LxTrimTagged(LxReadText(oTable.getCellByName(aCells(i)).getText()))
            sPlain = LxStrip(sCell)
            If Len(sPlain) > 0 Then
                If bBrace And nCount > 1 And InStr(sPlain, " ") > 0 Then _
                    sCell = "{" & sCell & "}"
                If Len(s) > 0 Then s = s & " "
                s = s & sCell
            End If
        End If
    Next i
    LxRowText = s
End Function


' Text with its formatting marked, the way LxSelectedLines reads a
' selection — so what comes out of a cell can go straight back through the
' same splitting, banding and measuring as text a linguist typed.
'
' The number field is skipped: it is read for its identity, by
' LxTakeCellNumber, and would otherwise arrive as a word saying "7".
Function LxReadText(oText As Object) As String
    Dim oParEnum As Object, oPorEnum As Object
    Dim oPar As Object, oPor As Object
    Dim s As String, sTxt As String, sType As String

    s = ""
    oParEnum = oText.createEnumeration()
    Do While oParEnum.hasMoreElements()
        oPar = oParEnum.nextElement()
        If oPar.supportsService("com.sun.star.text.Paragraph") Then
            If Len(s) > 0 Then s = s & " "
            oPorEnum = oPar.createEnumeration()
            Do While oPorEnum.hasMoreElements()
                oPor = oPorEnum.nextElement()
                sType = ""
                On Error Resume Next
                sType = oPor.TextPortionType
                On Error Goto 0
                If sType = "LineBreak" Then
                    s = s & " "
                ElseIf sType = "TextField" And LxIsNumberField(oPor) Then
                    ' its identity is taken elsewhere; its text is not text
                Else
                    sTxt = oPor.getString()
                    If Len(sTxt) > 0 Then s = s & LxTagged(sTxt, LxFormatIndex(oPor))
                End If
            Loop
        End If
    Loop
    LxReadText = s
End Function


' The example's number, taken out of the first cell of its first row: not
' the digit, which is a field's presentation and means nothing, but the
' identity every cross-reference to this example points at.
Sub LxTakeCellNumber(oTable As Object, nRow As Integer)
    Dim oCell As Object, oParEnum As Object, oPorEnum As Object
    Dim oPar As Object, oPor As Object
    Dim s As String

    oCell = Nothing
    On Error Resume Next
    oCell = oTable.getCellByName(LxCell(0, nRow))
    On Error Goto 0
    If IsNull(oCell) Then Exit Sub

    oParEnum = oCell.getText().createEnumeration()
    Do While oParEnum.hasMoreElements()
        oPar = oParEnum.nextElement()
        If oPar.supportsService("com.sun.star.text.Paragraph") Then
            oPorEnum = oPar.createEnumeration()
            Do While oPorEnum.hasMoreElements()
                oPor = oPorEnum.nextElement()
                If LxIsNumberField(oPor) Then
                    s = ""                    ' LxTakeNumber wants the text
                    Call LxTakeNumber(oPor, s)  ' before it, and there is none
                    Exit Sub
                End If
            Loop
        End If
    Loop
End Sub


' --------------------------------------------------------- table pieces ---

' An example, or a table the linguist built?  The spacer rows say which:
' this macro and the converter both top and tail an example with a row
' whose only job is to be the space above or below it, and nothing else
' makes a row like that.  Getting this wrong would take a real table apart.
Function LxIsExampleTable(oTable As Object) As Boolean
    Dim nRows As Integer
    LxIsExampleTable = False
    nRows = oTable.getRows().getCount()
    If nRows < 3 Then Exit Function
    If Not LxRowHasStyle(oTable, LxRowCells(oTable, 1), SPACE_ABOVE) Then Exit Function
    LxIsExampleTable = LxRowHasStyle(oTable, LxRowCells(oTable, nRows), SPACE_BELOW)
End Function


' The drawings in this table, each with the cell it sits in and the bracket
' notation it was drawn from.  False means one of them carries no source —
' a picture somebody put in an example, or a tree drawn before trees kept
' their brackets — and the caller refuses rather than lose it.
'
' A tree is a group of shapes anchored in a cell, and the anchor knows both
' which table and which cell.
Function LxReadShapes(oDoc As Object, oTable As Object) As Boolean
    Dim oPage As Object, oShape As Object
    Dim i As Integer
    Dim sName As String, sCell As String, sSrc As String

    LxShN = 0
    LxReadShapes = True
    oPage = oDoc.getDrawPage()
    For i = 0 To oPage.getCount() - 1
        oShape = oPage.getByIndex(i)
        sName = "" : sCell = ""
        On Error Resume Next
        sName = oShape.getAnchor().TextTable.Name
        sCell = oShape.getAnchor().Cell.CellName
        On Error Goto 0
        If Len(sName) > 0 And sName = oTable.Name Then
            sSrc = LxShapeSource(oShape)
            If Len(sSrc) = 0 Or LxShN > SHAPE_MAX Then
                LxReadShapes = False
                Exit Function
            End If
            LxShCell(LxShN) = sCell
            LxShSrc(LxShN) = sSrc
            LxShN = LxShN + 1
        End If
    Next i
End Function


' What was drawn in this cell, or "" for a cell with nothing drawn in it.
Function LxCellTree(sCell As String) As String
    Dim i As Integer
    LxCellTree = ""
    If Len(sCell) = 0 Then Exit Function
    For i = 0 To LxShN - 1
        If LxShCell(i) = sCell Then
            LxCellTree = LxShSrc(i)
            Exit Function
        End If
    Next i
End Function


' The tree drawn in this row, if one is.
Function LxRowTree(aCells As Variant, nLead As Integer) As String
    Dim i As Integer
    Dim s As String
    LxRowTree = ""
    For i = 0 To UBound(aCells)
        If LxCellColOf(aCells(i)) >= nLead Then
            s = LxCellTree(aCells(i))
            If Len(s) > 0 Then
                LxRowTree = s
                Exit Function
            End If
        End If
    Next i
End Function


' The cells of one row, in column order.  The names a table hands out are
' already in that order, and a merged-away cell is simply not among them —
' which is exactly what "this row has one wide cell" looks like here.
Function LxRowCells(oTable As Object, nRow As Integer) As Variant
    Dim aNames As Variant, aOut() As String
    Dim i As Integer, n As Integer

    aNames = oTable.getCellNames()
    ReDim aOut(UBound(aNames))
    n = 0
    For i = 0 To UBound(aNames)
        If LxCellRowOf(aNames(i)) = nRow Then
            aOut(n) = aNames(i)
            n = n + 1
        End If
    Next i
    If n = 0 Then
        LxRowCells = Array()
    Else
        ReDim Preserve aOut(n - 1)
        LxRowCells = aOut()
    End If
End Function


Function LxRowHasStyle(oTable As Object, aCells As Variant, sStyle As String) As Boolean
    Dim i As Integer
    LxRowHasStyle = False
    For i = 0 To UBound(aCells)
        If LxCellStyle(oTable.getCellByName(aCells(i))) = sStyle Then
            LxRowHasStyle = True
            Exit Function
        End If
    Next i
End Function


Function LxCellStyle(oCell As Object) As String
    Dim oEnum As Object
    LxCellStyle = ""
    If IsNull(oCell) Then Exit Function
    oEnum = oCell.getText().createEnumeration()
    If oEnum.hasMoreElements() Then LxCellStyle = oEnum.nextElement().ParaStyleName
End Function


' The plain text of one cell by position, or "" where a merge has left no
' cell at all.
Function LxCellText(oTable As Object, nCol As Integer, nRow As Integer) As String
    Dim oCell As Object
    oCell = Nothing
    On Error Resume Next
    oCell = oTable.getCellByName(LxCell(nCol, nRow))
    On Error Goto 0
    If IsNull(oCell) Then
        LxCellText = ""
    Else
        LxCellText = oCell.getString()
    End If
End Function


Function LxCellRowOf(sName As String) As Integer
    Dim i As Integer
    Dim c As String, s As String
    s = ""
    For i = 1 To Len(sName)
        c = Mid(sName, i, 1)
        If c >= "0" And c <= "9" Then s = s & c
    Next i
    If Len(s) = 0 Then LxCellRowOf = -1 Else LxCellRowOf = CInt(s)
End Function


' The inverse of LxColName: "A" is 0, "Z" is 25, "a" is 26, "AA" is 52.
Function LxCellColOf(sName As String) As Integer
    Dim i As Integer, v As Integer
    Dim n As Long
    Dim c As String

    n = 0
    For i = 1 To Len(sName)
        c = Mid(sName, i, 1)
        If c >= "A" And c <= "Z" Then
            v = Asc(c) - 64                   ' A is 1
        ElseIf c >= "a" And c <= "z" Then
            v = Asc(c) - 96 + 26              ' a is 27
        Else
            Exit For                          ' the row number
        End If
        n = n * 52 + v
    Next i
    LxCellColOf = CInt(n - 1)
End Function


' ------------------------------------------------------ writing it back ---

' The text the table sits in — the body, or whatever else it was built in.
Function LxHostText(oDoc As Object, oTable As Object) As Object
    Dim o As Object
    o = Nothing
    On Error Resume Next
    o = oTable.getAnchor().getText()
    On Error Goto 0
    If IsNull(o) Then o = oDoc.getText()
    LxHostText = o
End Function


' A cursor at the end of the paragraph immediately in front of the table,
' and whether the first line needs a paragraph break in front of it.
'
' Write there and take the table away, and the text has landed exactly
' where the table stood.  The paragraph before it is used when there is
' one — appended to, so the prose above the example keeps its own line —
' and when there is not, Writer is asked for one the way a linguist would
' ask: the cursor at the very start of the first cell, then Enter, which is
' what .uno:InsertPara does.  That is exactly the case Writer makes a
' paragraph in; with one already there it does nothing, which is why this
' does not simply always ask.
'
' Nothing simpler works.  A table's own anchor is not a range that can be
' inserted at — insertString there silently does nothing, measured — and
' reaching for the paragraph *after* the table fails on the commonest
' arrangement in a linguistics paper: two examples one after the other,
' with no paragraph between them at all.
Function LxPlaceBefore(oDoc As Object, oText As Object, oTable As Object, _
                       ByRef bLead As Boolean) As Object
    Dim oVC As Object, oDisp As Object, oPar As Object
    Dim aNames As Variant

    LxPlaceBefore = Nothing
    bLead = False

    oPar = LxParagraphBefore(oText, oTable)
    If IsNull(oPar) Then
        aNames = oTable.getCellNames()
        If UBound(aNames) < 0 Then Exit Function
        oVC = oDoc.getCurrentController().getViewCursor()
        oVC.gotoRange(oTable.getCellByName(aNames(0)).getText().getStart(), False)
        oDisp = createUnoService("com.sun.star.frame.DispatchHelper")
        oDisp.executeDispatch(oDoc.getCurrentController().getFrame(), _
                              ".uno:InsertPara", "", 0, Array())
        oPar = LxParagraphBefore(oText, oTable)
        If IsNull(oPar) Then Exit Function
        ' Whatever came back has to be empty: a paragraph with something in
        ' it was already there, and writing into it would put the example
        ' in the middle of somebody's sentence.
        If Len(oPar.getString()) > 0 Then Exit Function
    Else
        bLead = (Len(oPar.getString()) > 0)
    End If

    LxPlaceBefore = oText.createTextCursorByRange(oPar.getEnd())
End Function


' The paragraph immediately before the table, or Nothing if what comes
' before it is another table or the start of the text.
Function LxParagraphBefore(oText As Object, oTable As Object) As Object
    Dim oEnum As Object, oEl As Object, oPrev As Object

    LxParagraphBefore = Nothing
    oPrev = Nothing
    oEnum = oText.createEnumeration()
    Do While oEnum.hasMoreElements()
        oEl = oEnum.nextElement()
        If oEl.supportsService("com.sun.star.text.TextTable") Then
            If oEl.Name = oTable.Name Then
                LxParagraphBefore = oPrev
                Exit Function
            End If
            oPrev = Nothing
        ElseIf oEl.supportsService("com.sun.star.text.Paragraph") Then
            oPrev = oEl
        End If
    Loop
End Function


' The lines, one paragraph each, the number at the head of the first.
'
' They take the paragraph style of the text they are written into, as
' typing there would.  Imposing one would be worse: a document whose body
' style is not "Standard" would get an example back in a style it uses
' nowhere else.
Sub LxWriteLines(oDoc As Object, oText As Object, oCur As Object, _
                 aLines As Variant, nLines As Integer, bLead As Boolean)
    Dim i As Integer

    For i = 0 To nLines - 1
        ' Breaks go *between* the lines, and one in front of the first only
        ' when the paragraph written into has text in it already: the last
        ' line belongs in the paragraph the example was given, so a
        ' trailing break would leave an empty one behind.
        If i > 0 Or bLead Then
            oCur.collapseToEnd()
            oText.insertControlCharacter(oCur, _
                com.sun.star.text.ControlCharacter.PARAGRAPH_BREAK, False)
        End If
        If i = 0 And LxNumHas Then
            Call LxPutNumber(oDoc, oText, oCur)
            oCur.collapseToEnd()
            oText.insertString(oCur, Chr(9), False)
        End If
        Call LxPutTagged(oText, oCur, aLines(i))
    Next i
End Sub


' =============================================================== layout ===
'
' The lengths that are a matter of house style rather than of measurement,
' and where each of them is kept.
'
' Three are horizontal, and each is measured from the one before it:
'
'     |<- indent ->|(1)|<- number ->|a.|<- marker ->|Esto es un ejemplo
'
' so `indent` moves the whole example in from the margin, `number` says how
' far the sub-example letter — and therefore a main example's own text —
' sits from the number, and `marker` how far a sub-example's text sits from
' its letter.  They are kept as user-defined document properties (File ▸
' Properties ▸ Custom Properties), because there is nowhere better: a
' column width is worked out afresh for every example and no style holds
' one.
'
' The two vertical ones are not kept here at all.  The space above and
' below an example already *is* a paragraph style — LxExampleSpace and its
' two children — so writing the height down a second time would give the
' document two answers and let them drift the moment someone edited the
' style in the sidebar.  The dialog reads and writes the style itself.
'
' Which is the one asymmetry worth knowing about, and the dialog says so:
' changing the spacing restyles every example in the document at once,
' because it is a style; changing an indent shows up only in examples built
' afterwards, because the ones already built are tables whose columns are
' already set.
'
' All of it is per document, deliberately.  The styles are per document and
' a paper has one geometry; a linguist who wants the same in every paper
' should set it in the template they start from.
'
' OPT_INDENT, OPT_NUMBER, OPT_MARKER and OPT_MAX_CM are declared at the top
' of the module rather than here, because Basic resolves constants in
' source order.

Sub LxLayoutCommand()
    Dim oDoc As Object, oUndo As Object
    Dim dIndent As Double, dNumber As Double, dMarker As Double
    Dim dAbove As Double, dBelow As Double

    oDoc = ThisComponent
    If IsNull(oDoc) Then
        Call LxSay("Run this in a Writer document.")
        Exit Sub
    End If
    If Not oDoc.supportsService("com.sun.star.text.TextDocument") Then
        Call LxSay("Run this in a Writer document.")
        Exit Sub
    End If

    Call LxReadLayout(oDoc, dIndent, dNumber, dMarker, dAbove, dBelow)
    If Not LxAskLayout(dIndent, dNumber, dMarker, dAbove, dBelow) Then Exit Sub

    oUndo = oDoc.getUndoManager()
    oUndo.enterUndoContext("LinguExx layout")
    On Error Goto Cleanup
    Call LxWriteLayout(oDoc, dIndent, dNumber, dMarker, dAbove, dBelow)
Cleanup:
    oUndo.leaveUndoContext()
    If Err <> 0 Then Call LxSay(Error$ & " (line " & Erl & ")")
End Sub


' What this document is set to now — its own values where it has them, the
' defaults everywhere else.  A document that has never had an example built
' in it has neither property nor style, and answers with the defaults.
Sub LxReadLayout(oDoc As Object, ByRef dIndent As Double, _
                 ByRef dNumber As Double, ByRef dMarker As Double, _
                 ByRef dAbove As Double, ByRef dBelow As Double)
    dIndent = LxOpt(oDoc, OPT_INDENT, 0)
    dNumber = LxOpt(oDoc, OPT_NUMBER, NUMBER_CM)
    dMarker = LxOpt(oDoc, OPT_MARKER, MARKER_CM)
    dAbove = LxSpaceOf(oDoc, SPACE_ABOVE)
    dBelow = LxSpaceOf(oDoc, SPACE_BELOW)
End Sub


' Refuses out of range rather than clamping: a value silently made
' something else is worse than one the user is asked to type again.
Sub LxWriteLayout(oDoc As Object, dIndent As Double, dNumber As Double, _
                  dMarker As Double, dAbove As Double, dBelow As Double)
    Dim i As Integer
    Dim aValue(4) As Double

    aValue(0) = dIndent : aValue(1) = dNumber : aValue(2) = dMarker
    aValue(3) = dAbove  : aValue(4) = dBelow
    For i = 0 To 4
        If aValue(i) < 0 Or aValue(i) > OPT_MAX_CM Then
            Call LxSay("Every length has to be between 0 and " & _
                       Format(OPT_MAX_CM, "0") & " cm.")
            Exit Sub
        End If
    Next i

    Call LxOptSet(oDoc, OPT_INDENT, dIndent)
    Call LxOptSet(oDoc, OPT_NUMBER, dNumber)
    Call LxOptSet(oDoc, OPT_MARKER, dMarker)
    Call LxApplySpacing(oDoc, dAbove, dBelow)
End Sub


' ------------------------------------------------------------- the store ---

Function LxOpt(oDoc As Object, sName As String, dDefault As Double) As Double
    Dim oProps As Object
    Dim dValue As Double

    LxOpt = dDefault
    On Error Resume Next
    oProps = oDoc.getDocumentProperties().getUserDefinedProperties()
    If IsNull(oProps) Then Exit Function
    If Not oProps.getPropertySetInfo().hasPropertyByName(sName) Then Exit Function
    dValue = CDbl(oProps.getPropertyValue(sName))
    If Err <> 0 Then Exit Function            ' someone typed prose into it
    If dValue >= 0 And dValue <= OPT_MAX_CM Then LxOpt = dValue
End Function


' Two things here are not optional, and both were found the hard way.
'
' REMOVEABLE: LibreOffice refuses to add a user-defined property without it.
'
' CreateUnoValue: a user-defined property may hold a string, a boolean, a
' date, a duration or a *double*, and nothing else.  Basic hands a Double
' whose value happens to be integral across as a Long, so storing 2 cm
' raised IllegalTypeException where storing 0.9 cm had just worked —
' 1.1 and 0.7, the defaults, hid it perfectly.  The value object says
' "double" and means it.
Sub LxOptSet(oDoc As Object, sName As String, dValue As Double)
    Dim oProps As Object
    Dim aVal As Variant

    oProps = oDoc.getDocumentProperties().getUserDefinedProperties()
    aVal = CreateUnoValue("double", dValue)
    If oProps.getPropertySetInfo().hasPropertyByName(sName) Then
        oProps.setPropertyValue(sName, aVal)
    Else
        oProps.addProperty(sName, _
                           com.sun.star.beans.PropertyAttribute.REMOVEABLE, aVal)
    End If
End Sub


' The fixed line height of a spacing style, in cm.  A child that declares
' nothing of its own reports what it inherits, which is exactly the answer
' wanted: what this side of an example currently measures.
Function LxSpaceOf(oDoc As Object, sStyle As String) As Double
    Dim oFam As Object, oStyle As Object
    Dim aSp As Variant

    LxSpaceOf = SPACE_CM
    On Error Resume Next
    oFam = oDoc.getStyleFamilies().getByName("ParagraphStyles")
    If IsNull(oFam) Then Exit Function
    If Not oFam.hasByName(sStyle) Then Exit Function
    oStyle = oFam.getByName(sStyle)
    aSp = oStyle.ParaLineSpacing
    If Err <> 0 Then Exit Function
    If aSp.Mode = com.sun.star.style.LineSpacingMode.FIX Then
        LxSpaceOf = aSp.Height / 1000.0
    End If
End Function


' The two sides, kept the way styles.py writes them for the converter: equal
' heights live on the parent with both children inheriting, so one sidebar
' edit of LxExampleSpace still moves both sides; unequal ones break each
' child away on its own.
Sub LxApplySpacing(oDoc As Object, dAbove As Double, dBelow As Double)
    Call LxEnsureStyles(oDoc)
    If Abs(dAbove - dBelow) < 0.001 Then
        Call LxSetSpace(oDoc, SPACE_PARA, dAbove, False)
        Call LxSetSpace(oDoc, SPACE_ABOVE, 0, True)
        Call LxSetSpace(oDoc, SPACE_BELOW, 0, True)
    Else
        Call LxSetSpace(oDoc, SPACE_ABOVE, dAbove, False)
        Call LxSetSpace(oDoc, SPACE_BELOW, dBelow, False)
    End If
End Sub


Sub LxSetSpace(oDoc As Object, sStyle As String, dCm As Double, bInherit As Boolean)
    Dim oFam As Object, oStyle As Object
    Dim aSp As New com.sun.star.style.LineSpacing

    oFam = oDoc.getStyleFamilies().getByName("ParagraphStyles")
    If Not oFam.hasByName(sStyle) Then Exit Sub
    oStyle = oFam.getByName(sStyle)
    If bInherit Then
        oStyle.setPropertyToDefault("ParaLineSpacing")
    Else
        aSp.Mode = com.sun.star.style.LineSpacingMode.FIX
        aSp.Height = CInt(dCm * 1000)
        oStyle.ParaLineSpacing = aSp
    End If
End Sub


' ------------------------------------------------------------ the dialog ---

' Built here rather than shipped as a .xdl, so that the one file that ships
' is still the one file the tests drive: a dialog in the extension's dialog
' library would not exist when LinguExx.bas is pasted into an IDE or loaded
' straight into a Basic library, which is how everything else here is run.
'
' The model is built apart from being shown, so that the building can be
' tested: everything that can go wrong here — a mistyped control property,
' a field left holding another field's value — goes wrong while the model
' is assembled, and a headless test can assemble one and read it back
' without a window server to execute() in.
Function LxLayoutModel(dIndent As Double, dNumber As Double, _
                       dMarker As Double, dAbove As Double, _
                       dBelow As Double) As Object
    Dim oModel As Object, oNote As Object

    oModel = createUnoService("com.sun.star.awt.UnoControlDialogModel")
    oModel.Title = "LinguExx — example layout"
    oModel.Width = 214
    oModel.Height = 172

    Call LxDlgRow(oModel, "indent", "Indent to the example number (cm)", _
                  "From the left margin to the ""(1)"".", 8, dIndent)
    Call LxDlgRow(oModel, "number", "Indent to the sub-example letter (cm)", _
                  "From the number to the ""a."" — and so to where a main " & _
                  "example's own text begins.  A floor: a number too wide " & _
                  "for it still gets its room.", 26, dNumber)
    Call LxDlgRow(oModel, "marker", "Indent to the sub-example text (cm)", _
                  "From the ""a."" to the text beside it.  A floor, as above.", _
                  44, dMarker)
    Call LxDlgRow(oModel, "above", "Space above an example (cm)", _
                  "The height of the LxExampleSpaceAbove style.", 70, dAbove)
    Call LxDlgRow(oModel, "below", "Space below an example (cm)", _
                  "The height of the LxExampleSpaceBelow style.", 88, dBelow)

    oNote = oModel.createInstance("com.sun.star.awt.UnoControlFixedTextModel")
    oModel.insertByName("note", oNote)
    oNote.PositionX = 8
    oNote.PositionY = 112
    oNote.Width = 198
    oNote.Height = 32
    oNote.MultiLine = True
    oNote.Label = "The indents apply to examples built from now on.  The " & _
                  "spacings are styles, so they restyle every example in " & _
                  "this document at once." & Chr(10) & _
                  "Defaults: 0, 1.1, 0.7, 0.18, 0.18 cm."

    Call LxDlgButton(oModel, "ok", "OK", com.sun.star.awt.PushButtonType.OK, 106)
    Call LxDlgButton(oModel, "cancel", "Cancel", _
                     com.sun.star.awt.PushButtonType.CANCEL, 158)
    LxLayoutModel = oModel
End Function


Function LxAskLayout(ByRef dIndent As Double, ByRef dNumber As Double, _
                     ByRef dMarker As Double, ByRef dAbove As Double, _
                     ByRef dBelow As Double) As Boolean
    Dim oModel As Object, oDlg As Object
    Dim bOK As Boolean

    LxAskLayout = False
    oModel = LxLayoutModel(dIndent, dNumber, dMarker, dAbove, dBelow)

    oDlg = createUnoService("com.sun.star.awt.UnoControlDialog")
    oDlg.setModel(oModel)
    oDlg.setVisible(False)
    oDlg.createPeer(createUnoService("com.sun.star.awt.Toolkit"), Null)
    bOK = (oDlg.execute() = 1)
    If bOK Then
        dIndent = oDlg.getControl("indent").getModel().Value
        dNumber = oDlg.getControl("number").getModel().Value
        dMarker = oDlg.getControl("marker").getModel().Value
        dAbove = oDlg.getControl("above").getModel().Value
        dBelow = oDlg.getControl("below").getModel().Value
    End If
    oDlg.dispose()
    LxAskLayout = bOK
End Function


' One labelled length.  A numeric field rather than a text box on purpose:
' it takes no parsing, and so no view about whether this user's decimal
' separator is a point or a comma.
Sub LxDlgRow(oModel As Object, sName As String, sLabel As String, _
             sHelp As String, nY As Integer, dValue As Double)
    Dim oLabel As Object, oField As Object

    oLabel = oModel.createInstance("com.sun.star.awt.UnoControlFixedTextModel")
    oModel.insertByName("lbl_" & sName, oLabel)
    oLabel.PositionX = 8
    oLabel.PositionY = nY + 2
    oLabel.Width = 130
    oLabel.Height = 10
    oLabel.Label = sLabel
    oLabel.HelpText = sHelp

    oField = oModel.createInstance("com.sun.star.awt.UnoControlNumericFieldModel")
    oModel.insertByName(sName, oField)
    oField.PositionX = 144
    oField.PositionY = nY
    oField.Width = 62
    oField.Height = 13
    oField.DecimalAccuracy = 2
    oField.ValueMin = 0
    oField.ValueMax = OPT_MAX_CM
    oField.ValueStep = 0.05
    oField.Spin = True
    oField.Value = dValue
    oField.HelpText = sHelp
End Sub


' nType is left untyped so the PushButtonType constant reaches the property
' as whatever it is, rather than being narrowed on the way in.
Sub LxDlgButton(oModel As Object, sName As String, sLabel As String, _
                nType, nX As Integer)
    Dim oBtn As Object
    oBtn = oModel.createInstance("com.sun.star.awt.UnoControlButtonModel")
    oModel.insertByName(sName, oBtn)
    oBtn.PositionX = nX
    oBtn.PositionY = 150
    oBtn.Width = 48
    oBtn.Height = 14
    oBtn.Label = sLabel
    oBtn.PushButtonType = nType
    oBtn.DefaultButton = (sName = "ok")
End Sub


' ----------------------------------------------------------- the quiet door ---

' For non-interactive callers, as GlossSelectionQuiet is for examples: the
' same settings without the dialog, the message back instead of a box.
Function LayoutSettingsQuiet(dIndent As Double, dNumber As Double, _
                             dMarker As Double, dAbove As Double, _
                             dBelow As Double) As String
    Dim oDoc As Object

    LxSilent = True
    LxLastMessage = ""
    oDoc = ThisComponent
    If IsNull(oDoc) Then
        Call LxSay("Run this in a Writer document.")
    Else
        ' Trapped, as the interactive command traps it: a caller that cannot
        ' see a dialog cannot see an untrapped runtime error either, and
        ' would be told the settings took when they had not.
        On Error Goto Trouble
        Call LxWriteLayout(oDoc, dIndent, dNumber, dMarker, dAbove, dBelow)
        Goto Done
Trouble:
        Call LxSay(Error$ & " (line " & Erl & ")")
Done:
        On Error Goto 0
    End If
    LxSilent = False
    LayoutSettingsQuiet = LxLastMessage
    LxLastMessage = ""
End Function


' The five lengths as the dialog would offer them, read back out of the
' controls it would offer them in.  Builds the whole model and shows none
' of it, so a headless caller can check that the dialog assembles and that
' each field is holding this document's own value.
Function LayoutDialogQuiet() As String
    Dim oDoc As Object, oModel As Object
    Dim dIndent As Double, dNumber As Double, dMarker As Double
    Dim dAbove As Double, dBelow As Double
    Dim i As Integer, s As String
    Dim aName As Variant

    oDoc = ThisComponent
    If IsNull(oDoc) Then
        LayoutDialogQuiet = ""
        Exit Function
    End If
    Call LxReadLayout(oDoc, dIndent, dNumber, dMarker, dAbove, dBelow)
    oModel = LxLayoutModel(dIndent, dNumber, dMarker, dAbove, dBelow)

    aName = Array("indent", "number", "marker", "above", "below")
    s = ""
    For i = 0 To UBound(aName)
        If i > 0 Then s = s & ";"
        s = s & Trim(Str(oModel.getByName(aName(i)).Value))
    Next i
    LayoutDialogQuiet = s
End Function


' The five lengths of the current document, in the order the dialog shows
' them.  Str() rather than Format(), so the caller reading them back is not
' handed a decimal comma.
Function LayoutQuiet() As String
    Dim oDoc As Object
    Dim dIndent As Double, dNumber As Double, dMarker As Double
    Dim dAbove As Double, dBelow As Double

    oDoc = ThisComponent
    If IsNull(oDoc) Then
        LayoutQuiet = ""
        Exit Function
    End If
    Call LxReadLayout(oDoc, dIndent, dNumber, dMarker, dAbove, dBelow)
    LayoutQuiet = Trim(Str(dIndent)) & ";" & Trim(Str(dNumber)) & ";" & _
                  Trim(Str(dMarker)) & ";" & Trim(Str(dAbove)) & ";" & _
                  Trim(Str(dBelow))
End Function


' ----------------------------------------------------------------- util ---

Function LxMax(a As Double, b As Double) As Double
    If a > b Then LxMax = a Else LxMax = b
End Function

Function LxMin(a As Double, b As Double) As Double
    If a < b Then LxMin = a Else LxMin = b
End Function

Function LxMaxI(a As Integer, b As Integer) As Integer
    If a > b Then LxMaxI = a Else LxMaxI = b
End Function

Function LxMinI(a As Integer, b As Integer) As Integer
    If a < b Then LxMinI = a Else LxMinI = b
End Function


' ================================================================ trees ===
'
' TreeSelection — turn bracket notation into a drawn syntax tree.
'
' Select the brackets and run it:
'
'     [DP [D the] [NP [N tree]]]
'
' The label is the first token after a '[', everything after it is a child,
' and a bare word is a leaf — the notation qtree and forest share.  A
' {braced group} is one label even with spaces in it, and a leaf marked
' ", roof" is drawn under a triangle, as in forest.
'
' The tree is a group of draw shapes anchored as a character in the wide
' cell of the same kind of table GlossSelection builds, so it carries a
' NumEx field and the LxExampleSpace styles and lines up with every other
' example in the document.  It is a real Writer object: selectable,
' printable, and editable afterwards by dragging — though nothing re-runs
' the layout if you do, exactly as a built example does not re-align itself.
'
' Node labels keep whatever formatting they were typed in, and they are
' measured by *being set*: a scratch text shape with TextAutoGrowWidth is
' given the label and asked how wide it came out.  That is exact where
' getStringWidth is 2-5% out — and it costs nothing to be formatting-aware,
' because the shape measures italics and small caps by rendering them.
'
' Deliberately not supported: movement arrows, edge labels, and every node
' option but "roof".  Arrows need node identity and routing, which is a
' different program; the parser refuses them by name rather than dropping
' them silently.


' ---------------------------------------------------------------- entry ---

' A numbered tree: an example whose content happens to be a tree.
' A bare tree: the same drawing, anchored where the brackets were, with no
' table, no number and no example styles.  For a tree in a footnote, a
' figure or a slide — anywhere it should not spend an example number.
'
' One tree only: a paradigm needs letters, and letters need the table that
' the numbered command builds.
Sub TreeSelectionBare
    Call LxBareTreeCommand()
End Sub


Sub LxBareTreeCommand()
    Dim oDoc As Object, oSel As Object, oRange As Object
    Dim oUndo As Object
    Dim aLines As Variant
    Dim sSrc As String, sMark As String
    Dim nRoot As Integer

    oDoc = ThisComponent
    If IsNull(oDoc) Then
        Call LxSay("Run this in a Writer document.")
        Exit Sub
    End If
    If Not oDoc.supportsService("com.sun.star.text.TextDocument") Then
        Call LxSay("Run this in a Writer document.")
        Exit Sub
    End If

    oSel = oDoc.getCurrentController().getSelection()
    If oSel.getCount() < 1 Then
        Call LxSay("Select the bracket notation of the tree first.")
        Exit Sub
    End If
    oRange = oSel.getByIndex(0)

    ' A tree is one expression however many lines it was typed over, so the
    ' selected lines are joined rather than treated as tiers.  The exception
    ' is a "move a -> b" line, which is about the tree rather than part of
    ' it and is set aside here.
    aLines = LxSelectedLines(oRange)
    If Len(LxNumErr) > 0 Then
        Call LxSay(LxNumErr)
        Exit Sub
    End If
    ' A bare tree has no number, so there is nowhere for one it was handed
    ' to go.  Drawing it anyway would destroy the field and every
    ' cross-reference to it, silently — the one thing this must not do.
    If LxNumHas Then
        Call LxSay("The selection carries an example number, and a tree " & _
                   "without a number has nowhere to put it." & _
                   Chr(10) & Chr(10) & _
                   "Drawing it would break every cross-reference to that " & _
                   "example.  Use Typeset numbered tree, or delete the " & _
                   "number first and lose the references deliberately.")
        Exit Sub
    End If
    If UBound(aLines) < 0 Then
        Call LxSay("Select the bracket notation of the tree first.")
        Exit Sub
    End If
    sSrc = LxSplitMoves(aLines)
    If Len(LxTErr) > 0 Then
        Call LxSay(LxTErr)
        Exit Sub
    End If

    ' A judgment mark leads the tree the way it leads an example, and lands
    ' in the same hanging column.
    sSrc = LxPullJudgment(sSrc, sMark)

    nRoot = LxTreeParse(sSrc)
    If nRoot < 0 Then
        If LxLooksLikeMarker(aLines(0)) Then
            Call LxSay("That looks like a paradigm.  A tree without a " & _
                       "number cannot carry a letter, because the letters " & _
                       "live in the table only the numbered command builds." & _
                       Chr(10) & Chr(10) & "Use Typeset numbered tree.")
        Else
            Call LxSay(LxTErr)
        End If
        Exit Sub
    End If

    If Not LxResolveMoves() Then
        Call LxSay(LxTErr)
        Exit Sub
    End If

    ' No LxEnsureStyles: a bare tree has no business creating example
    ' styles in a document that never asked for one.
    oUndo = oDoc.getUndoManager()
    oUndo.enterUndoContext("Typeset tree")
    On Error Goto Cleanup
    Call LxEmitBareTree(oDoc, oRange, nRoot, sMark, aLines)
Cleanup:
    oUndo.leaveUndoContext()
    If Err <> 0 Then Call LxSay(Error$ & " (line " & Erl & ")")
End Sub


' The non-interactive doors, as GlossSelectionQuiet is for examples.
Function TreeSelectionQuiet() As String
    LxSilent = True
    LxLastMessage = ""
    Call TreeSelection
    LxSilent = False
    TreeSelectionQuiet = LxLastMessage
    LxLastMessage = ""
End Function


Function TreeSelectionBareQuiet() As String
    LxSilent = True
    LxLastMessage = ""
    Call TreeSelectionBare
    LxSilent = False
    TreeSelectionBareQuiet = LxLastMessage
    LxLastMessage = ""
End Function


' --------------------------------------------------------------- parsing ---

Function LxTreeParse(s As String) As Integer
    Dim nRoot As Integer

    LxTErr = ""
    LxNdN = 0
    LxTSrc = s
    LxTPos = 1
    LxTTag = ""

    ' Refused by name, not dropped in silence: a tree that quietly lost its
    ' movement arrows looks finished and is not.
    If InStr(LxStrip(s), "\") > 0 Then
        LxTErr = "This does not read LaTeX (anything with a backslash)." & _
                 Chr(10) & Chr(10) & _
                 "For movement, name the two nodes and put a move line " & _
                 "under the tree:" & Chr(10) & _
                 "    [CP [DP,name=wh what] [TP [V saw] [DP,name=t __]]]" & _
                 Chr(10) & "    move t -> wh"
        LxTreeParse = -1
        Exit Function
    End If

    Call LxTSkip()
    If LxTPos > Len(LxTSrc) Or Mid(LxTSrc, LxTPos, 1) <> "[" Then
        LxTErr = "A tree has to start with a bracket, like " & _
                 "[DP [D the] [NP [N tree]]]."
        LxTreeParse = -1
        Exit Function
    End If

    nRoot = LxTNode()
    If Len(LxTErr) > 0 Then
        LxTreeParse = -1
        Exit Function
    End If

    Call LxTSkip()
    If LxTPos <= Len(LxTSrc) Then
        LxTErr = "The tree ends before the selection does; there is still " & _
                 """" & LxStrip(Mid(LxTSrc, LxTPos)) & """ after it."
        LxTreeParse = -1
        Exit Function
    End If

    LxTreeParse = nRoot
End Function


Function LxTNode() As Integer
    Dim n As Integer, nKid As Integer, nPrev As Integer
    Dim c As String

    n = LxNewNode()
    If n < 0 Then
        LxTNode = -1
        Exit Function
    End If

    LxTPos = LxTPos + 1                       ' the '['
    Call LxTSkip()
    LxNdLabel(n) = LxTToken()

    nPrev = -1
    Do
        Call LxTSkip()
        If LxTPos > Len(LxTSrc) Then
            LxTErr = "A bracket is never closed."
            LxTNode = -1
            Exit Function
        End If
        c = Mid(LxTSrc, LxTPos, 1)
        If c = "]" Then
            LxTPos = LxTPos + 1
            Exit Do
        End If
        If c = "[" Then
            nKid = LxTNode()
        Else                                  ' a bare word is a leaf
            nKid = LxNewNode()
            If nKid >= 0 Then
                LxNdLabel(nKid) = LxTToken()
                Call LxTOptions(nKid)         ' ", roof" lives on leaves too
            End If
        End If
        If nKid < 0 Or Len(LxTErr) > 0 Then
            LxTNode = -1
            Exit Function
        End If
        If nPrev < 0 Then
            LxNdKid(n) = nKid
        Else
            LxNdSib(nPrev) = nKid
        End If
        nPrev = nKid
    Loop

    Call LxTOptions(n)
    If Len(LxTErr) > 0 Then
        LxTNode = -1
        Exit Function
    End If
    LxTNode = n
End Function


Function LxNewNode() As Integer
    Dim n As Integer
    If LxNdN > TREE_MAX Then
        LxTErr = "That tree has more nodes than this can draw."
        LxNewNode = -1
        Exit Function
    End If
    n = LxNdN
    LxNdLabel(n) = ""
    LxNdName(n) = ""
    LxNdRoof(n) = False
    LxNdKid(n) = -1
    LxNdSib(n) = -1
    LxNdDepth(n) = 0
    LxNdX(n) = 0
    LxNdW(n) = 0
    LxNdN = LxNdN + 1
    LxNewNode = n
End Function


' A label: bare, or {braced} so that it may hold spaces.  Format marks are
' ordinary characters here — they are none of the delimiters, so they ride
' along inside the label and LxPut puts the formatting back at the end.
Function LxTToken() As String
    Dim c As String, s As String
    Dim nDepth As Integer, nStart As Integer

    LxTToken = ""
    If LxTPos > Len(LxTSrc) Then Exit Function

    If Mid(LxTSrc, LxTPos, 1) = "{" Then
        nDepth = 0
        nStart = LxTPos + 1
        Do While LxTPos <= Len(LxTSrc)
            c = Mid(LxTSrc, LxTPos, 1)
            If c = "{" Then
                nDepth = nDepth + 1
            ElseIf c = "}" Then
                nDepth = nDepth - 1
                If nDepth = 0 Then
                    s = Mid(LxTSrc, nStart, LxTPos - nStart)
                    LxTPos = LxTPos + 1
                    LxTToken = LxTCarry(s)
                    Exit Function
                End If
            End If
            LxTPos = LxTPos + 1
        Loop
        LxTErr = "A { is never closed."
        Exit Function
    End If

    nStart = LxTPos
    Do While LxTPos <= Len(LxTSrc)
        If LxTIsDelim(Mid(LxTSrc, LxTPos, 1)) Then Exit Do
        LxTPos = LxTPos + 1
    Loop
    LxTToken = LxTCarry(Mid(LxTSrc, nStart, LxTPos - nStart))
End Function


' Give a label the mark that was in force where it *began*, not the one it
' ended on.  A label runs up to the next bracket, and a mark is not a
' delimiter, so "sg" written in small caps before a plain "]" comes out of
' the scanner as "<small caps>sg<plain>" — wear the last of those and the
' label is set in the formatting of the bracket after it.
'
' The trailing mark is still worth keeping: it is what the *next* label
' inherits.  So it is noted here and then trimmed off, because on the end
' of a label it can only open a run with nothing in it.
Function LxTCarry(s As String) As String
    Dim sIn As String, sLast As String
    sIn = LxTTag
    sLast = LxLastTag(s)
    If Len(sLast) > 0 Then LxTTag = sLast
    LxTCarry = LxCarryTag(sIn, LxTrimTags(s))
End Function


Function LxTIsDelim(c As String) As Boolean
    LxTIsDelim = (InStr("[]{} ", c) > 0 Or c = Chr(9))
End Function


' Skip what separates one piece of structure from the next: whitespace, and
' the format marks that sit in front of it.  A mark is remembered rather
' than thrown away — it is the formatting the *next* label is written in,
' and LxTToken puts it back on the front.  Everything upstream of here can
' therefore go on treating brackets as brackets.
Sub LxTSkip()
    Dim c As String
    Do While LxTPos <= Len(LxTSrc)
        c = Mid(LxTSrc, LxTPos, 1)
        If LxTagIndex(c) >= 0 Then
            LxTTag = c
        ElseIf c <> " " And c <> Chr(9) Then
            Exit Do
        End If
        LxTPos = LxTPos + 1
    Loop
End Sub


' forest writes node options after a comma: "the big tree, roof".  Only
' roof is understood, and anything else is refused by name.
Sub LxTOptions(n As Integer)
    Dim sHead As String, sRest As String, sOpt As String, sKey As String
    Dim p As Integer

    p = InStr(LxNdLabel(n), ",")
    If p = 0 Then Exit Sub
    sHead = Left(LxNdLabel(n), p - 1)
    sRest = Mid(LxNdLabel(n), p + 1)

    Do
        p = InStr(sRest, ",")
        If p > 0 Then
            sOpt = Left(sRest, p - 1)
            sRest = Mid(sRest, p + 1)
        Else
            sOpt = sRest
            sRest = ""
        End If
        sOpt = Trim(LxStrip(sOpt))
        sKey = LCase(sOpt)
        If sKey = "roof" Then
            LxNdRoof(n) = True
        ElseIf Left(sKey, 5) = "name=" Then
            ' the value keeps its case: it is what a move line refers to
            LxNdName(n) = Trim(Mid(sOpt, 6))
        ElseIf Len(sOpt) > 0 Then
            LxTErr = "This does not know the node option """ & sOpt & """.  " & _
                     "Only ""roof"" and ""name=..."" are supported."
            Exit Sub
        End If
    Loop While Len(sRest) > 0

    LxNdLabel(n) = LxTrimTagged(sHead)
End Sub


' -------------------------------------------------------------- movement ---

' Movement is written as its own line under the tree, not as TikZ:
'
'     [CP [DP,name=wh what] [C\' [C did] [TP [V see] [DP,name=t __]]]]
'     move t -> wh
'
' forest says this with \draw[->] (t) to[out=south west,in=south] (wh), and
' a subset of TikZ is a trap: the moment `move` looked like \draw people
' would reach for bend angles, edge labels and node anchors, and wherever
' the subset ended would look like a bug rather than a boundary.  A line
' that is plainly not TikZ promises only what it delivers.
Function LxIsMoveLine(sLine As String) As Boolean
    Dim s As String
    s = LCase(Trim(LxStrip(sLine)))
    LxIsMoveLine = (Left(s, 5) = "move " Or Left(s, 5) = "move" & Chr(9))
End Function


' The tree source, with the move lines taken out and kept for later — their
' names cannot be resolved until every node exists.
Function LxSplitMoves(aLines As Variant) As String
    Dim i As Integer
    Dim s As String

    LxTErr = ""
    LxMoveN = 0
    s = ""
    For i = 0 To UBound(aLines)
        If LxIsMoveLine(aLines(i)) Then
            If LxMoveN > ARROW_MAX Then
                LxTErr = "That is more movement arrows than this can draw."
                LxSplitMoves = ""
                Exit Function
            End If
            LxMoveSrc(LxMoveN) = LxStrip(aLines(i))
            LxMoveN = LxMoveN + 1
        Else
            If Len(s) > 0 Then s = s & " "
            s = s & aLines(i)
        End If
    Next i

    If Len(Trim(s)) = 0 And LxMoveN > 0 Then
        LxTErr = "There are movement lines but no tree above them."
    End If
    LxSplitMoves = s
End Function


' Turn the move lines into node pairs, now that the tree has been parsed.
Function LxResolveMoves() As Boolean
    Dim i As Integer, p As Integer
    Dim s As String, sFrom As String, sTo As String

    LxArN = 0
    LxResolveMoves = False

    For i = 0 To LxMoveN - 1
        s = Trim(Mid(Trim(LxMoveSrc(i)), 5))       ' drop the leading "move"
        p = InStr(s, "->")
        If p = 0 Then
            LxTErr = "A movement line reads ""move <from> -> <to>""; this " & _
                     "one has no arrow:" & Chr(10) & Chr(10) & "    " & _
                     Trim(LxMoveSrc(i))
            Exit Function
        End If
        sFrom = Trim(Left(s, p - 1))
        sTo = Trim(Mid(s, p + 2))

        LxArFrom(LxArN) = LxNodeNamed(sFrom)
        LxArTo(LxArN) = LxNodeNamed(sTo)
        If LxArFrom(LxArN) < 0 Or LxArTo(LxArN) < 0 Then
            If LxArFrom(LxArN) < 0 Then s = sFrom Else s = sTo
            LxTErr = "No node is named """ & s & """." & Chr(10) & Chr(10) & _
                     "Name one by adding "", name=" & s & """ inside its " & _
                     "brackets, as in [DP,name=" & s & " what]."
            Exit Function
        End If
        If LxArFrom(LxArN) = LxArTo(LxArN) Then
            LxTErr = "A movement line points """ & sFrom & """ at itself."
            Exit Function
        End If
        LxArN = LxArN + 1
    Next i

    LxResolveMoves = True
End Function


Function LxNodeNamed(sName As String) As Integer
    Dim i As Integer
    LxNodeNamed = -1
    If Len(sName) = 0 Then Exit Function
    For i = 0 To LxNdN - 1
        If LxNdName(i) = sName Then
            LxNodeNamed = i
            Exit Function
        End If
    Next i
End Function


' Which lane each arrow runs in.
'
' Two arrows may share a lane only if their spans do not overlap, so this is
' greedy colouring of an interval graph — narrowest span first, so that a
' movement nested inside another sits above it rather than below, which is
' how the same configuration is drawn by hand.
Sub LxArrowLanes()
    Dim aOrder(ARROW_MAX) As Integer
    Dim i As Integer, j As Integer, k As Integer, m As Integer
    Dim nTmp As Integer
    Dim bFree As Boolean

    For i = 0 To LxArN - 1
        aOrder(i) = i
        LxArLane(i) = -1
    Next i

    For i = 1 To LxArN - 1                       ' insertion sort by span
        nTmp = aOrder(i)
        j = i - 1
        Do While j >= 0
            If LxArSpan(aOrder(j)) <= LxArSpan(nTmp) Then Exit Do
            aOrder(j + 1) = aOrder(j)
            j = j - 1
        Loop
        aOrder(j + 1) = nTmp
    Next i

    For i = 0 To LxArN - 1
        k = 0
        Do
            bFree = True
            For j = 0 To i - 1
                m = aOrder(j)
                If LxArLane(m) = k And LxArOverlap(aOrder(i), m) Then
                    bFree = False
                    Exit For
                End If
            Next j
            If bFree Then Exit Do
            k = k + 1
        Loop
        LxArLane(aOrder(i)) = k
    Next i
End Sub


Function LxArLo(i As Integer) As Double
    LxArLo = LxMin(LxNdX(LxArFrom(i)), LxNdX(LxArTo(i)))
End Function

Function LxArHi(i As Integer) As Double
    LxArHi = LxMax(LxNdX(LxArFrom(i)), LxNdX(LxArTo(i)))
End Function

Function LxArSpan(i As Integer) As Double
    LxArSpan = LxArHi(i) - LxArLo(i)
End Function

Function LxArOverlap(i As Integer, j As Integer) As Boolean
    LxArOverlap = (LxArLo(i) <= LxArHi(j) And LxArLo(j) <= LxArHi(i))
End Function


' ---------------------------------------------------------------- layout ---

' Every parent centred over its children, and no two subtrees overlapping.
'
' Not Reingold-Tilford: instead of contours and threads it keeps one
' leftmost-free-x per tier, places bottom up, and shifts a whole subtree
' right when its parent would collide at its own tier.  Non-overlap then
' holds by construction, which is the property that matters, and for a
' syntax tree — tens of nodes, not thousands — the quadratic worst case
' costs nothing.  The linear algorithm packs marginally tighter and is
' much harder to be sure of.
Function LxTreeLayout(oProbe As Object, nRoot As Integer, _
                      dPad As Double, dGap As Double) As Boolean
    Dim i As Integer
    Dim dLeft As Double

    For i = 0 To TREE_DEPTH
        LxFree(i) = 0
    Next i

    If Not LxTDepth(nRoot, 0) Then
        LxTErr = "That tree is nested deeper than this can draw."
        LxTreeLayout = False
        Exit Function
    End If

    Call LxTPlace(nRoot, oProbe, dPad, dGap)

    dLeft = LxTMinLeft(nRoot)                 ' start the tree at x = 0
    If dLeft <> 0 Then Call LxTShift(nRoot, -dLeft)
    LxTreeLayout = True
End Function


Function LxTDepth(n As Integer, d As Integer) As Boolean
    Dim k As Integer
    LxTDepth = False
    If d > TREE_DEPTH Then Exit Function
    LxNdDepth(n) = d
    k = LxNdKid(n)
    Do While k >= 0
        If Not LxTDepth(k, d + 1) Then Exit Function
        k = LxNdSib(k)
    Loop
    LxTDepth = True
End Function


Sub LxTPlace(n As Integer, oProbe As Object, dPad As Double, dGap As Double)
    Dim k As Integer, nLast As Integer
    Dim dWant As Double, dFloor As Double

    LxNdW(n) = LxTMeasure(oProbe, LxNdLabel(n)) + dPad

    k = LxNdKid(n)
    If k < 0 Then
        LxNdX(n) = LxFree(LxNdDepth(n)) + LxNdW(n) / 2
    Else
        nLast = -1
        Do While k >= 0
            Call LxTPlace(k, oProbe, dPad, dGap)
            nLast = k
            k = LxNdSib(k)
        Loop
        dWant = (LxNdX(LxNdKid(n)) + LxNdX(nLast)) / 2
        dFloor = LxFree(LxNdDepth(n)) + LxNdW(n) / 2
        If dWant < dFloor Then                ' the parent will not fit there
            Call LxTShift(n, dFloor - dWant)
            dWant = dFloor
        End If
        LxNdX(n) = dWant
    End If

    Call LxTClaim(n, dGap)
End Sub


Sub LxTShift(n As Integer, dx As Double)
    Dim k As Integer
    LxNdX(n) = LxNdX(n) + dx
    k = LxNdKid(n)
    Do While k >= 0
        Call LxTShift(k, dx)
        k = LxNdSib(k)
    Loop
End Sub


Sub LxTClaim(n As Integer, dGap As Double)
    Dim k As Integer
    Dim d As Double
    d = LxNdX(n) + LxNdW(n) / 2 + dGap
    If d > LxFree(LxNdDepth(n)) Then LxFree(LxNdDepth(n)) = d
    k = LxNdKid(n)
    Do While k >= 0
        Call LxTClaim(k, dGap)
        k = LxNdSib(k)
    Loop
End Sub


Function LxTMinLeft(n As Integer) As Double
    Dim k As Integer
    Dim d As Double
    d = LxNdX(n) - LxNdW(n) / 2
    k = LxNdKid(n)
    Do While k >= 0
        d = LxMin(d, LxTMinLeft(k))
        k = LxNdSib(k)
    Loop
    LxTMinLeft = d
End Function


Function LxTreeWidth(n As Integer) As Double
    Dim k As Integer
    Dim d As Double
    d = LxNdX(n) + LxNdW(n) / 2
    k = LxNdKid(n)
    Do While k >= 0
        d = LxMax(d, LxTreeWidth(k))
        k = LxNdSib(k)
    Loop
    LxTreeWidth = d
End Function


Function LxTreeTiers(n As Integer) As Integer
    Dim k As Integer
    Dim m As Integer
    m = LxNdDepth(n) + 1
    k = LxNdKid(n)
    Do While k >= 0
        m = LxMaxI(m, LxTreeTiers(k))
        k = LxNdSib(k)
    Loop
    LxTreeTiers = m
End Function


' ------------------------------------------------------------ measuring ---

' A label is measured by being set.  The probe grows to fit its own text,
' so what comes back is what Writer will actually draw — including the
' label's own italics or small caps, which no width model has to know
' about because the shape renders them.
Function LxTMeasure(oProbe As Object, sLabel As String) As Double
    If Len(LxStrip(sLabel)) = 0 Then
        LxTMeasure = 0
        Exit Function
    End If
    Call LxPut(oProbe, sLabel)
    LxTMeasure = oProbe.getSize().Width
End Function


Function LxTreeProbe(oDoc As Object, oText As Object, oWhere As Object, _
                     sFont As String, dPt As Double) As Object
    Dim oShape As Object
    oShape = oDoc.createInstance("com.sun.star.drawing.TextShape")
    oText.insertTextContent(oWhere, oShape, False)
    oShape.AnchorType = com.sun.star.text.TextContentAnchorType.AT_PARAGRAPH
    Call LxTPlainShape(oShape, sFont, dPt)
    oShape.TextAutoGrowWidth = True
    oShape.TextAutoGrowHeight = True
    LxTreeProbe = oShape
End Function


Sub LxTPlainShape(oShape As Object, sFont As String, dPt As Double)
    oShape.FillStyle = com.sun.star.drawing.FillStyle.NONE
    oShape.LineStyle = com.sun.star.drawing.LineStyle.NONE
    oShape.TextWordWrap = False
    oShape.TextLeftDistance = 0
    oShape.TextRightDistance = 0
    oShape.TextUpperDistance = 0
    oShape.TextLowerDistance = 0
    oShape.CharFontName = sFont
    oShape.CharHeight = dPt
End Sub


' ------------------------------------------------------------- the table ---

' Probe, measure, lay out, draw.  Everything the two forms of tree share;
' they differ only in what they anchor it into.  Nothing on failure, with
' LxTErr set.
Function LxTreeDraw(oDoc As Object, oText As Object, oWhere As Object, _
                    nRoot As Integer, sFont As String, dPt As Double) As Object
    Dim oProbe As Object
    Dim dLineH As Double

    LxTreeDraw = Nothing
    oProbe = LxTreeProbe(oDoc, oText, oWhere, sFont, dPt)
    Call LxTMeasure(oProbe, "Ag")             ' the width is discarded; the
    dLineH = oProbe.getSize().Height          ' line height is the point

    If Not LxTreeLayout(oProbe, nRoot, NODE_PAD_CM * 1000, NODE_GAP_CM * 1000) Then
        oDoc.getDrawPage().remove(oProbe)
        Exit Function
    End If
    oDoc.getDrawPage().remove(oProbe)

    LxTreeDraw = LxTreeShapes(oDoc, oText, oWhere, nRoot, dLineH, _
                              dLineH * TIER_FACTOR, sFont, dPt)
End Function


' ------------------------------------------------------- a tree on its own ---

' No table, no number, no example styles: the tree replaces the brackets
' where they stand and is anchored as a character in that same paragraph,
' so whatever was either side of the notation stays either side of the tree.
Sub LxEmitBareTree(oDoc As Object, oRange As Object, nRoot As Integer, _
                   sMark As String, aLines As Variant)
    Dim oText As Object, oCur As Object, oGroup As Object, oTail As Object
    Dim sFont As String
    Dim dPt As Double, dWidth As Double, dAvail As Double
    Dim bTail As Boolean

    ' Read the font off the selection before the tree replaces it.
    sFont = "" : dPt = 0
    On Error Resume Next
    sFont = oRange.CharFontName
    dPt = oRange.CharHeight
    On Error Goto 0
    If Len(sFont) = 0 Then sFont = "Liberation Serif"
    If dPt <= 0 Then dPt = 12

    dAvail = LxTextWidthCm(oDoc)
    oText = oRange.getText()

    ' An as-character group reserves vertical room in the line but not
    ' horizontal — measured: a 38pt-wide tree between two words leaves a
    ' 31pt gap, which is the width of the words alone.  So the tree is drawn
    ' where the line's text ends.  Text *before* it is fine, and is how the
    ' judgment mark below works; text after it would end up beside the tree
    ' rather than after it, so that is worth saying.
    bTail = False
    On Error Resume Next
    oTail = oText.createTextCursorByRange(oRange.getEnd())
    oTail.gotoEndOfParagraph(True)
    bTail = (Len(Trim(LxStrip(oTail.getString()))) > 0)
    On Error Goto 0

    ' There is no hanging column without a table, so a judgment mark becomes
    ' the text it would have been had you typed it there yourself.
    oRange.setString(sMark)
    oCur = oText.createTextCursorByRange(oRange.getEnd())

    oGroup = LxTreeDraw(oDoc, oText, oCur, nRoot, sFont, dPt)
    If IsNull(oGroup) Then
        Call LxSay(LxTErr)
        Exit Sub
    End If
    ' A bare tree keeps its source too.  Nothing reads it back yet — there
    ' is no table to untypeset — but a drawing that says what it is costs
    ' one line, and the two kinds of tree should not differ in what they
    ' carry.
    Call LxTreeSource(oGroup, aLines)

    dWidth = LxTreeWidth(nRoot) / 1000.0
    If dWidth > dAvail Then
        Call LxSay("The tree is " & Format(dWidth, "0.0") & " cm wide but " & _
                   "the text block is only " & Format(dAvail, "0.0") & _
                   " cm, so it will stick out." & Chr(10) & Chr(10) & _
                   "Shorten a label, or group words with {braces} so they " & _
                   "share one node.")
    ElseIf bTail Then
        Call LxSay("A tree without a number is drawn where the line's text " & _
                   "ends, so it should be the last thing on its line." & _
                   Chr(10) & Chr(10) & _
                   "There is still text after this one; move it to a " & _
                   "paragraph of its own, or use Typeset example instead " & _
                   "so the tree gets a table to sit in.")
    End If
End Sub


' ------------------------------------------------------------- the shapes ---

' One text shape per node, one line per branch, one triangle per roof, all
' grouped and anchored as a character.
'
' Two orderings matter, both found the hard way:
'
'   * a shape already anchored as a character cannot be grouped, so every
'     piece is anchored to the paragraph and only the finished group is
'     made a character;
'   * a polygon shape must be given its PolyPolygon *before* its position.
'     Setting position or size first puts the polygon in another coordinate
'     space — 2501 units out, on a page with 2cm margins — and the branches
'     land away from the nodes they belong to.
Function LxTreeShapes(oDoc As Object, oText As Object, oWhere As Object, _
                      nRoot As Integer, dLineH As Double, dTier As Double, _
                      sFont As String, dPt As Double) As Object
    Dim oShapes As Object, oGroup As Object

    oShapes = createUnoService("com.sun.star.drawing.ShapeCollection")
    Call LxTEmitNode(oDoc, oText, oWhere, oShapes, nRoot, dLineH, dTier, sFont, dPt)
    Call LxTEmitArrows(oDoc, oText, oWhere, oShapes, dLineH, dTier)

    oGroup = oDoc.getDrawPage().group(oShapes)
    oGroup.AnchorType = com.sun.star.text.TextContentAnchorType.AS_CHARACTER
    LxTreeShapes = oGroup
End Function


' The name every tree this macro draws answers to, and the one thing that
' tells one of our drawings from a picture somebody put in an example.
Const TREE_TITLE As String = "LinguExx tree"


' Keep the bracket notation the tree was drawn from, on the drawing.
'
' A group of shapes cannot be read back into brackets — shapes have
' positions, not structure — so without this a tree in an example could not
' be untypesetted at all, and its number was stuck inside it.  The source
' goes in the group's Description, which is Writer's alt text: the one
' field a drawing has for saying what it is, and this is what it is.  It
' doubles as the alt text a tagged PDF wants.
'
' It is a copy of something, which everything else here avoids — but the
' alternative is not "no copy", it is "no way back", and the drawing was
' already not the source: the docs have always said a tree is re-run from
' its brackets rather than from what was drawn last time.  Drag a node and
' the drawing changes while this does not, exactly as dragging one has
' always left the layout it came from behind.
'
' Formatting is not kept.  Alt text is plain text, and the marks that carry
' formatting through this macro are private-use codepoints that would show
' up as boxes in Format ▸ Description.  A label's italics survive in the
' drawing and are lost when the brackets come back.
Sub LxTreeSource(oGroup As Object, aLines As Variant)
    Dim s As String
    Dim i As Integer

    If IsNull(oGroup) Then Exit Sub
    s = ""
    For i = 0 To UBound(aLines)
        If i > 0 Then s = s & Chr(10)
        s = s & LxStrip(aLines(i))
    Next i

    On Error Resume Next
    oGroup.Title = TREE_TITLE
    oGroup.Description = s
    On Error Goto 0
End Sub


' The source a drawing carries, or "" for a drawing that is not one of
' ours.  The title is what says so: a picture with alt text on it must not
' be read as bracket notation.
Function LxShapeSource(oShape As Object) As String
    Dim sTitle As String, sDesc As String
    sTitle = "" : sDesc = ""
    On Error Resume Next
    sTitle = oShape.Title
    sDesc = oShape.Description
    On Error Goto 0
    If sTitle = TREE_TITLE Then LxShapeSource = sDesc Else LxShapeSource = ""
End Function


Sub LxTEmitNode(oDoc As Object, oText As Object, oWhere As Object, _
                oShapes As Object, n As Integer, dLineH As Double, _
                dTier As Double, sFont As String, dPt As Double)
    Dim oShape As Object
    Dim k As Integer
    Dim dY As Double, dBottom As Double, dTop As Double
    Dim aPos As New com.sun.star.awt.Point
    Dim aSize As New com.sun.star.awt.Size

    dY = LxNdDepth(n) * dTier

    If Len(LxStrip(LxNdLabel(n))) > 0 Then
        oShape = oDoc.createInstance("com.sun.star.drawing.TextShape")
        oText.insertTextContent(oWhere, oShape, False)
        oShape.AnchorType = com.sun.star.text.TextContentAnchorType.AT_PARAGRAPH
        aPos.X = CLng(LxNdX(n) - LxNdW(n) / 2)
        aPos.Y = CLng(dY)
        aSize.Width = CLng(LxNdW(n))
        aSize.Height = CLng(dLineH)
        oShape.setPosition(aPos)
        oShape.setSize(aSize)
        Call LxTPlainShape(oShape, sFont, dPt)
        oShape.TextAutoGrowWidth = False
        oShape.TextAutoGrowHeight = False
        oShape.TextHorizontalAdjust = com.sun.star.drawing.TextHorizontalAdjust.CENTER
        oShape.TextVerticalAdjust = com.sun.star.drawing.TextVerticalAdjust.CENTER
        Call LxPut(oShape, LxNdLabel(n))
        Call LxTShapeFont(oShape, sFont, dPt)
        oShapes.add(oShape)
    End If

    dBottom = dY + dLineH
    k = LxNdKid(n)
    Do While k >= 0
        dTop = LxNdDepth(k) * dTier
        If LxNdRoof(k) Then
            Call LxTRoof(oDoc, oText, oWhere, oShapes, LxNdX(n), dBottom, k, dTop)
        Else
            Call LxTBranch(oDoc, oText, oWhere, oShapes, LxNdX(n), dBottom, _
                           LxNdX(k), dTop)
        End If
        Call LxTEmitNode(oDoc, oText, oWhere, oShapes, k, dLineH, dTier, _
                         sFont, dPt)
        k = LxNdSib(k)
    Loop
End Sub


' The label keeps its own italics and small caps from LxPut; the family and
' size are the document's, applied afterwards because they are not part of
' what a run carries.
Sub LxTShapeFont(oShape As Object, sFont As String, dPt As Double)
    Dim oCur As Object
    oCur = oShape.getText().createTextCursor()
    oCur.gotoStart(False)
    oCur.gotoEnd(True)
    On Error Resume Next
    oCur.CharFontName = sFont
    oCur.CharHeight = dPt
    On Error Goto 0
End Sub


' Every polygon in a tree goes through here, so the ordering rule lives in
' one place: the PolyPolygon first, in the shape's own frame, and only then
' the position.  Points arrive already relative to (dLeft, dTop).
Function LxTPolyShape(oDoc As Object, oText As Object, oWhere As Object, _
                      sKind As String, aPts As Variant, _
                      dLeft As Double, dTop As Double, _
                      bFill As Boolean) As Object
    Dim oShape As Object
    Dim aPos As New com.sun.star.awt.Point

    oShape = oDoc.createInstance("com.sun.star.drawing." & sKind)
    oText.insertTextContent(oWhere, oShape, False)
    oShape.AnchorType = com.sun.star.text.TextContentAnchorType.AT_PARAGRAPH

    oShape.PolyPolygon = Array(aPts)
    aPos.X = CLng(dLeft) : aPos.Y = CLng(dTop)
    oShape.setPosition(aPos)

    oShape.LineStyle = com.sun.star.drawing.LineStyle.SOLID
    oShape.LineWidth = BRANCH_WIDTH
    oShape.LineColor = RGB(0, 0, 0)
    If bFill Then
        oShape.FillStyle = com.sun.star.drawing.FillStyle.SOLID
        oShape.FillColor = RGB(0, 0, 0)
    Else
        oShape.FillStyle = com.sun.star.drawing.FillStyle.NONE
    End If
    LxTPolyShape = oShape
End Function


Function LxPt(x As Double, y As Double) As Object
    Dim aP As New com.sun.star.awt.Point
    aP.X = CLng(x) : aP.Y = CLng(y)
    LxPt = aP
End Function


Sub LxTBranch(oDoc As Object, oText As Object, oWhere As Object, _
              oShapes As Object, x0 As Double, y0 As Double, _
              x1 As Double, y1 As Double)
    Dim dLeft As Double
    dLeft = LxMin(x0, x1)
    oShapes.add(LxTPolyShape(oDoc, oText, oWhere, "LineShape", _
        Array(LxPt(x0 - dLeft, 0), LxPt(x1 - dLeft, y1 - y0)), _
        dLeft, y0, False))
End Sub


' A movement arrow: down out of the node it moved from, along its own lane
' under the tree, and up into the node it moved to, with a filled head.
'
' Drawn as a polyline in a gutter rather than as a curve because a straight
' run under the tree crosses nothing, and because two of them in adjacent
' lanes stay legible where two arcs would not.
Sub LxTArrow(oDoc As Object, oText As Object, oWhere As Object, _
             oShapes As Object, x0 As Double, y0 As Double, _
             x1 As Double, y1 As Double, dLane As Double)
    Dim dLeft As Double, dHead As Double, dHalf As Double, dTop As Double

    dLeft = LxMin(x0, x1)
    dHead = HEAD_LEN_CM * 1000
    dHalf = HEAD_HALF_CM * 1000

    ' The top of the arrow is where it *ends*, not where it starts: movement
    ' goes up the tree, so y1 is above y0.  LxTPolyShape wants points
    ' measured from the bounding box, and getting that wrong does not fail —
    ' it silently sinks the whole arrow by however far the box was out.
    dTop = LxMin(y0, y1 + dHead)

    oShapes.add(LxTPolyShape(oDoc, oText, oWhere, "PolyLineShape", _
        Array(LxPt(x0 - dLeft, y0 - dTop), _
              LxPt(x0 - dLeft, dLane - dTop), _
              LxPt(x1 - dLeft, dLane - dTop), _
              LxPt(x1 - dLeft, y1 + dHead - dTop)), _
        dLeft, dTop, False))

    ' the head, apex on the underside of the node moved to
    oShapes.add(LxTPolyShape(oDoc, oText, oWhere, "PolyPolygonShape", _
        Array(LxPt(dHalf, 0), LxPt(0, dHead), LxPt(2 * dHalf, dHead), _
              LxPt(dHalf, 0)), _
        x1 - dHalf, y1, True))
End Sub


' The underside of everything a node dominates.
'
' An arrow leaves and arrives *here*, not at the node's own baseline.  A
' node almost always has something under it — a terminal, a whole subtree —
' and an arrow drawn to the node's baseline goes straight through it.  An
' arrow should point at a constituent, not cross it, and the bottom of the
' subtree is the one place on the node's own x where nothing is in the way.
Function LxSubtreeBottom(n As Integer, dLineH As Double, dTier As Double) As Double
    Dim k As Integer
    Dim d As Double
    d = LxNdDepth(n) * dTier + dLineH
    k = LxNdKid(n)
    Do While k >= 0
        d = LxMax(d, LxSubtreeBottom(k, dLineH, dTier))
        k = LxNdSib(k)
    Loop
    LxSubtreeBottom = d
End Function


' The gutter: every arrow below every node, each in the lane it was given.
Sub LxTEmitArrows(oDoc As Object, oText As Object, oWhere As Object, _
                  oShapes As Object, dLineH As Double, dTier As Double)
    Dim i As Integer
    Dim dDeep As Double, dLane As Double

    If LxArN < 1 Then Exit Sub

    dDeep = 0
    For i = 0 To LxNdN - 1
        dDeep = LxMax(dDeep, LxNdDepth(i) * dTier + dLineH)
    Next i

    Call LxArrowLanes()
    For i = 0 To LxArN - 1
        dLane = dDeep + GUTTER_GAP_CM * 1000 + LxArLane(i) * LANE_STEP_CM * 1000
        Call LxTArrow(oDoc, oText, oWhere, oShapes, _
                      LxNdX(LxArFrom(i)), _
                      LxSubtreeBottom(LxArFrom(i), dLineH, dTier), _
                      LxNdX(LxArTo(i)), _
                      LxSubtreeBottom(LxArTo(i), dLineH, dTier), dLane)
    Next i
End Sub


' A roof: the triangle from the parent down to the width of the child's own
' label, which is what "the big tree" under one NP is supposed to look like.
Sub LxTRoof(oDoc As Object, oText As Object, oWhere As Object, _
            oShapes As Object, xApex As Double, yApex As Double, _
            k As Integer, yBase As Double)
    Dim dLo As Double, dHi As Double, dLeft As Double

    dLo = LxNdX(k) - LxNdW(k) / 2
    dHi = LxNdX(k) + LxNdW(k) / 2
    dLeft = LxMin(dLo, xApex)

    oShapes.add(LxTPolyShape(oDoc, oText, oWhere, "PolyPolygonShape", _
        Array(LxPt(xApex - dLeft, 0), _
              LxPt(dLo - dLeft, yBase - yApex), _
              LxPt(dHi - dLeft, yBase - yApex), _
              LxPt(xApex - dLeft, 0)), _
        dLeft, yApex, False))
End Sub
