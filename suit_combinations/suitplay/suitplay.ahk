; Copyright 2026 Ilya Sherman (ishermandom@)
; SPDX-License-Identifier: MIT
;
; Analyzes holdings with SuitPlay by driving its window the way a person would,
; and writes SuitPlay's chance of making each trick target. Runs under Wine in
; the machine `lima.yaml` describes, from the folder that holds SuitPlay.exe.
;
; Usage: `AutoHotkey32.exe suitplay.ahk HOLDINGS RESULTS [--accept-license]
; [--minutes-per-holding MINUTES]`
;
; - HOLDINGS: one holding per line in the analyzer's notation, North and South
;   joined by a hyphen, such as `AQT-xx`.
; - RESULTS: appended to, one line per trick target SuitPlay lists, containing
;   the holding, the target, and SuitPlay's chance, separated by tabs, such as
;   `AQT-xx`, `2`, and `76.0000%`. When SuitPlay can't analyze a holding, the
;   line contains the holding, `error`, and the reason.
; - `--accept-license`: click "I Accept" if SuitPlay shows its license
;   agreement. Without it, the script stops there, so that accepting stays the
;   user's decision.
; - `--minutes-per-holding MINUTES`: how long SuitPlay may calculate a single
;   holding before the script records it as an error and restarts SuitPlay; 5
;   by default.

#Requires AutoHotkey v2.0
#SingleInstance Force

mainWindow := "ahk_class TMainForm"
holdingDialog := "ahk_class TComboOKHelpRightDlg"
licenseWindow := "Software License Agreement"
errorWindow := "Error ahk_class TMessageForm"
; SuitPlay warns when it finds more best lines than it can list, such as 16 for
; QT85 opposite A742, and waits for OK before listing the ones it picks. The
; message itself can't be read, so the script dismisses any warning; a warning
; that changed SuitPlay's chances would show up in the comparison.
warningWindow := "Warning ahk_class TMessageForm"
; SuitPlay shows this window while it calculates.
calculatingWindow := "calculating"
; The longest a single holding may calculate before it counts as failed, set by
; `--minutes-per-holding`. A few holdings, such as K963 opposite J, take
; SuitPlay far longer than the default.
calculationLimitMilliseconds := 5 * 60000

; Stop with `message` on standard error and a nonzero exit status.
Fail(message) {
    FileAppend "suitplay.ahk: " message "`n", "**"
    ExitApp 1
}

; Start SuitPlay unless it's already running, and wait for its main window.
EnsureSuitPlayRunning(acceptsLicense) {
    if !WinExist(mainWindow)
        Run A_ScriptDir "\SuitPlay.exe", A_ScriptDir
    ; Until its license is accepted, SuitPlay shows only the agreement.
    start := A_TickCount
    while !WinExist(mainWindow) && !WinExist(licenseWindow) {
        if A_TickCount - start > 60000
            Fail("SuitPlay's window never appeared")
        Sleep 200
    }
    if WinExist(licenseWindow) {
        if !acceptsLicense
            Fail("SuitPlay is showing its license agreement; rerun with "
                . "--accept-license to accept it")
        ControlClick "I Accept", licenseWindow
        if !WinWait(mainWindow, , 60)
            Fail("SuitPlay's window never appeared after accepting its license")
    }
}

; Open the dialog that takes a holding, unless it's already open. Wine won't
; let one program read another's menus, so this presses the menu's keys:
; Alt+S for "Suit Combination", then N for "New ...".
OpenHoldingDialog() {
    if WinExist(holdingDialog)
        return
    WinActivate mainWindow
    Send "!s"
    Sleep 300
    Send "n"
    if !WinWait(holdingDialog, , 10)
        Fail("the holding dialog didn't open")
}

; The dialog's North and South text fields, as control names. Their numbering
; doesn't follow the screen, so North's is the upper one.
NorthAndSouthFields() {
    ControlGetPos , &firstTop, , , "TEdit1", holdingDialog
    ControlGetPos , &secondTop, , , "TEdit2", holdingDialog
    return firstTop < secondTop ? ["TEdit1", "TEdit2"] : ["TEdit2", "TEdit1"]
}

; Whether SuitPlay looks finished: its calculating window is gone, and either
; an error message shows or the results list answers with at least one row.
; SuitPlay keeps working after the calculating window closes, 36 seconds for
; KQ974 opposite a void, and until it's done the results list stays empty or
; doesn't answer at all.
IsFinished() {
    if WinExist(calculatingWindow)
        return false
    if WinExist(errorWindow)
        return true
    try {
        ; LVM_GETITEMCOUNT, waiting at most 200 ms for an answer.
        rowCount := SendMessage(0x1004, 0, 0, "TListView1", mainWindow
            , , , , 200)
    } catch TimeoutError {
        return false
    }
    return rowCount > 0
}

; Wait until SuitPlay has looked finished for half a second, or restart it if
; the calculation runs past the limit. Returns whether the calculation
; finished.
WaitForCalculation() {
    start := A_TickCount
    finishedPolls := 0
    while finishedPolls < 5 {
        Sleep 100
        if WinExist(warningWindow)
            ControlClick "OK", warningWindow
        finishedPolls := IsFinished() ? finishedPolls + 1 : 0
        if A_TickCount - start > calculationLimitMilliseconds {
            RestartSuitPlay()
            return false
        }
    }
    return true
}

; Close SuitPlay and start it afresh. That's the way out of a calculation past
; the limit: SuitPlay's Interrupt button asks for confirmation and then can
; keep calculating for minutes.
RestartSuitPlay() {
    ProcessClose "SuitPlay.exe"
    ProcessWaitClose "SuitPlay.exe", 30
    EnsureSuitPlayRunning(false)
}

; Whether SuitPlay's displayed hand `shown` is the analyzer's `hand`: the same
; length, with every card the analyzer names. SuitPlay picks its own small cards
; for the x's, and may pick differently from the analyzer, which changes
; nothing because the x's are the lowest cards either way.
IsSameHand(hand, shown) {
    if StrLen(hand) != StrLen(shown)
        return false
    loop parse hand {
        if A_LoopField != "x" && !InStr(shown, A_LoopField, true)
            return false
    }
    return true
}

; Close an error message and the holding dialog behind it, if they're open.
DismissError() {
    if WinExist(errorWindow) {
        ControlClick "OK", errorWindow
        WinWaitClose errorWindow, , 10
    }
    if WinExist(holdingDialog) {
        ControlClick "Cancel", holdingDialog
        WinWaitClose holdingDialog, , 10
    }
}

; SuitPlay's results for `holding`, as lines for the RESULTS file.
AnalyzeHolding(holding) {
    ; SuitPlay takes a void as an empty field, where the analyzer may spell it
    ; out.
    hands := StrSplit(StrReplace(holding, "(void)"), "-")
    if hands.Length != 2
        return holding "`terror`tnot a North-South holding`n"
    OpenHoldingDialog()
    fields := NorthAndSouthFields()
    ControlSetText hands[1], fields[1], holdingDialog
    ControlSetText hands[2], fields[2], holdingDialog
    ControlClick "OK", holdingDialog
    if !WaitForCalculation()
        return holding "`terror`tSuitPlay ran past the time limit`n"
    if WinExist(errorWindow) {
        DismissError()
        return holding "`terror`tSuitPlay rejected the holding`n"
    }
    ; SuitPlay's card diagram shows the hands it analyzed, except when the best
    ; line differs between trick targets, which leaves the diagram blank.
    shownNorth := ControlGetText("TRichEdit4", mainWindow)
    shownSouth := ControlGetText("TRichEdit3", mainWindow)
    isShown := shownNorth != "" || shownSouth != ""
    isOtherHolding := !IsSameHand(hands[1], shownNorth)
        || !IsSameHand(hands[2], shownSouth)
    if isShown && isOtherHolding
        return Format("{}`terror`tSuitPlay shows {}-{} instead`n"
            , holding, shownNorth, shownSouth)
    lines := ""
    ; Each row is a goal, its chance, and a line's letter, separated by tabs.
    loop parse ListViewGetContent("", "TListView1", mainWindow), "`n" {
        columns := StrSplit(A_LoopField, "`t", " ")
        ; The matchpoint row has a line but no chance.
        if columns[2] != ""
            lines .= Format("{}`t{}`t{}`n", holding, columns[1], columns[2])
    }
    return lines
}

; How `thrown` reads in a message, such as "OSError from ListViewGetContent:
; (1460) Timeout."
DescribeError(thrown) {
    return Format("{} from {}: {}", Type(thrown), thrown.What, thrown.Message)
}

; An unattended run must never wait on AutoHotkey's error dialog, so an error
; that nothing else catches ends the run, naming the error on standard error.
OnError((thrown, mode) => Fail(DescribeError(thrown)))

usage := "usage: suitplay.ahk HOLDINGS RESULTS [--accept-license] "
    . "[--minutes-per-holding MINUTES]"
if A_Args.Length < 2
    Fail(usage)
holdingsPath := A_Args[1]
resultsPath := A_Args[2]
acceptsLicense := false
optionIndex := 3
while optionIndex <= A_Args.Length {
    switch A_Args[optionIndex] {
        case "--accept-license":
            acceptsLicense := true
        case "--minutes-per-holding":
            optionIndex += 1
            isWholeNumber := optionIndex <= A_Args.Length
                && IsInteger(A_Args[optionIndex])
                && A_Args[optionIndex] > 0
            if !isWholeNumber
                Fail("--minutes-per-holding takes a whole number of minutes; "
                    . usage)
            calculationLimitMilliseconds := A_Args[optionIndex] * 60000
        default:
            Fail("unknown option " A_Args[optionIndex] "; " usage)
    }
    optionIndex += 1
}
EnsureSuitPlayRunning(acceptsLicense)
loop read holdingsPath {
    holding := Trim(A_LoopReadLine)
    if holding = ""
        continue
    ; An unexpected failure on one holding, such as SuitPlay not answering,
    ; becomes that holding's error, and the run goes on with a fresh SuitPlay.
    try {
        lines := AnalyzeHolding(holding)
    } catch Error as thrown {
        lines := Format("{}`terror`t{}`n", holding, DescribeError(thrown))
        RestartSuitPlay()
    }
    FileAppend lines, resultsPath
}
ExitApp 0
