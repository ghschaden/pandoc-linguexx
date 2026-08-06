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

' Deliberately not shared:
'   text_width_cm — the macro reads the real page style instead
'   font_pt — the macro reads the real font instead
'   width_safety — the macro measures, so it needs no margin for error
' --- END GENERATED

Const JUDG_CHARS   As String = "*?#%!"

' Column boundaries closer together than this are the same boundary.
Const GRID_TOL_CM  As Double = 0.015


' Every message goes through LxSay, so a caller that must not be blocked by
' a modal dialog (a test harness, a batch run over many examples) can turn
' the dialogs off and read the last message back instead.
Public LxSilent As Boolean
Public LxLastMessage As String


' ---------------------------------------------------------------- entry ---

Sub GlossSelection
    Dim oDoc As Object, oSel As Object, oRange As Object
    Dim aLines As Variant
    Dim nLines As Integer
    Dim oUndo As Object

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
    oUndo.enterUndoContext("Typeset example")
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
Const IT_NTIERS As Integer = 4     ' 1 means unglossed
Const IT_SIZE   As Integer = 5


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
Function LxParseItems(aLines As Variant, nLines As Integer, ByRef sError As String) As Variant
    Dim aItems() As Variant
    Dim aBody() As String
    Dim i As Integer, n As Integer, nBody As Integer
    Dim bAny As Boolean
    Dim sMarker As String, sRest As String, sLine As String

    sError = ""

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
                n = n + 1
            End If
            sLine = Trim(aLines(i))
            sMarker = LxSplitWords(sLine)(0)
            sRest = Trim(Mid(sLine, Len(sMarker) + 1))
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


' One item from its own lines: object language, gloss tiers, translation.
'
' A quoted last line is the translation whenever the item has more than one
' line.  That leaves an item of a single line unglossed, which is exactly
' what an unglossed sub-example is — "a. Sentences like this are fine."
Function LxMakeItem(sMarker As String, aBody() As String, nBody As Integer) As Variant
    Dim aItem(IT_SIZE - 1) As Variant
    Dim aTiers() As Variant
    Dim aWords As Variant
    Dim sTrans As String, sMark As String, sFirst As String
    Dim i As Integer, nTiers As Integer

    sTrans = ""
    If nBody > 1 Then
        If LxIsTranslation(aBody(nBody - 1)) Then
            sTrans = aBody(nBody - 1)
            nBody = nBody - 1
        End If
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
                                oTable.getCellByName(LxCell(c, nRow)).setString(aWords(i))
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
            ' nothing to do with each other.
            Call LxHead(oDoc, oTable, nRow, aItem, bFirstOfAll, nLead)
            bFirstOfAll = False
            Call LxWideCell(oTable, nRow, nLead, nCols + nFill, _
                            LxJoinWords(aTiers(0)), CELL_PARA)
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
        oTable.getCellByName(LxCell(1, nRow)).setString(aItem(IT_MARKER))
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
    oTable.getCellByName(LxCell(nLead, nRow)).setString(sText)
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

' The lines of the selection, trimmed, blank ones dropped.
'
' Enumerating paragraphs over a cursor built from the selection looks like
' the tidy way to do this and does not work — it yields a single empty
' element.  The selection's own string already has the paragraphs in it,
' separated by newlines, so split that.  Chr(11) is a line break inside a
' paragraph (Shift+Enter), which a linguist typing a gloss is at least as
' likely to have used as a paragraph mark.
Function LxSelectedLines(oRange As Object) As Variant
    Dim s As String, sLine As String
    Dim aRaw As Variant, aOut() As String
    Dim i As Integer, n As Integer

    s = oRange.getString()
    s = Replace(s, Chr(13) & Chr(10), Chr(10))
    s = Replace(s, Chr(13), Chr(10))
    s = Replace(s, Chr(11), Chr(10))
    aRaw = Split(s, Chr(10))

    ReDim aOut(UBound(aRaw))
    n = 0
    For i = 0 To UBound(aRaw)
        sLine = Trim(aRaw(i))
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
    aWords = LxSplitWords(sLine)
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
    c = Left(Trim(s), 1)
    LxIsTranslation = (InStr(LxQuotes(), c) > 0)
End Function


' Whitespace splits words, except inside {braces} — linguexx's way of
' making several words share one column.  The braces are not kept.
Function LxSplitWords(sLine As String) As Variant
    Dim aOut() As String
    Dim n As Integer, i As Integer, nDepth As Integer
    Dim sCur As String, c As String

    ReDim aOut(LxMaxI(Len(sLine), 1))
    n = -1 : sCur = "" : nDepth = 0
    For i = 1 To Len(sLine)
        c = Mid(sLine, i, 1)
        If c = "{" Then
            nDepth = nDepth + 1
        ElseIf c = "}" Then
            If nDepth > 0 Then nDepth = nDepth - 1
        ElseIf (c = " " Or c = Chr(9)) And nDepth = 0 Then
            If Len(sCur) > 0 Then
                n = n + 1 : aOut(n) = sCur : sCur = ""
            End If
        Else
            sCur = sCur & c
        End If
    Next i
    If Len(sCur) > 0 Then n = n + 1 : aOut(n) = sCur

    If n < 0 Then
        LxSplitWords = Array()
    Else
        ReDim Preserve aOut(n)
        LxSplitWords = aOut()
    End If
End Function


Function LxPullJudgment(sWord As String, ByRef sMark As String) As String
    Dim i As Integer, c As String
    sMark = "" : i = 1
    Do While i <= Len(sWord)
        c = Mid(sWord, i, 1)
        If InStr(JUDG_CHARS, c) = 0 Then Exit Do
        sMark = sMark & c
        i = i + 1
    Loop
    LxPullJudgment = Mid(sWord, i)
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
End Function


Function LxWidth(oFont As Object, dPxPerCm As Double, s As String) As Double
    If Len(s) = 0 Then
        LxWidth = 0
    Else
        LxWidth = oFont.getStringWidth(s) / dPxPerCm
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
