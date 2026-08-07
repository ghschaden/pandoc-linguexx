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
' as wide as their contents (the estimate is off by -7% to +28% in
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
    dAvail = LxTextWidthCm(oDoc)

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

    dNumber = LxMax(NUMBER_CM, LxWidth(oFont, dPxPerCm, "(00)") + PAD_CM) + dJudg

    ' The marker column is carved out of in the same way, and the number
    ' column keeps its full width.  That is what puts a sub-example letter
    ' exactly where a main example's text begins — linguexx's own geometry.
    dMarker = 0
    If bSub Then
        For k = 0 To nItems - 1
            aItem = aItems(k)
            dMarker = LxMax(dMarker, LxWidth(oFont, dPxPerCm, aItem(IT_MARKER)))
        Next k
        dMarker = LxMax(MARKER_CM, dMarker + PAD_CM) + dJudg
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
                     dNumber, dMarker, dJudg, dFiller, nLead)
End Sub


Sub LxEmitTable(oDoc As Object, oRange As Object, aItems As Variant, _
                aBandStart() As Integer, nBands As Integer, _
                aColW() As Double, nCols As Integer, _
                aWordCol() As Integer, aWordSpan() As Integer, nWords As Integer, _
                dNumber As Double, dMarker As Double, dJudg As Double, _
                dFiller As Double, nLead As Integer)
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
    Call LxSetColumns(oTable, aWidths(), nTotalCols, dSum)

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

    LxFmtN = 0

    s = ""
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
                    Else
                        sLine = oPor.getString()
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
    Dim oMaster As Object, oField As Object, oText As Object
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

    ' Literal parentheses around a live number-range field: renumbering
    ' then costs nothing but F9, and \label/\ref written by linguexx2odt
    ' into the same NumEx sequence keep pointing at the right example.
    oText = oCell.getText()
    oText.setString("(")
    oText.insertTextContent(oText.createTextCursorByRange(oText.getEnd()), oField, False)
    oText.insertString(oText.getEnd(), ")", False)
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
    Dim i As Integer, nFmt As Integer
    Dim c As String, sRun As String

    oText = oCell.getText()
    oText.setString("")
    If Len(LxStrip(sText)) = 0 Then Exit Sub

    oCur = oText.createTextCursor()
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


Sub LxPutRun(oText As Object, oCur As Object, sRun As String, nFmt As Integer)
    If Len(sRun) = 0 Then Exit Sub
    oCur.gotoEnd(False)
    oText.insertString(oCur, sRun, False)
    oCur.goLeft(Len(sRun), True)              ' select what was just written
    Call LxApplyFmt(oCur, nFmt)
    oCur.gotoEnd(False)
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
Sub LxSetColumns(oTable As Object, aWidths() As Double, nCols As Integer, dSum As Double)
    Dim aSep() As Variant
    Dim i As Integer
    Dim dAcc As Double
    Dim nSum As Long

    oTable.HoriOrient = com.sun.star.text.HoriOrientation.FULL
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


Function LxColName(nCol As Integer) As String
    Dim s As String, n As Integer
    n = nCol : s = ""
    Do
        s = Chr(65 + (n Mod 26)) & s
        n = n \ 26 - 1
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
    Call LxEmitBareTree(oDoc, oRange, nRoot, sMark)
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
                   sMark As String)
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
