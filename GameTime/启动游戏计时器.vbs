Option Explicit
Dim fso, sh, base, url, profile, edge, p1, p2, launch

Set fso = CreateObject("Scripting.FileSystemObject")
Set sh  = CreateObject("WScript.Shell")

base = fso.GetParentFolderName(WScript.ScriptFullName)
url  = "file:///" & Replace(base, "\", "/") & "/index.html"
profile = base & "\profile"

p1 = sh.ExpandEnvironmentStrings("%ProgramFiles(x86)%") & "\Microsoft\Edge\Application\msedge.exe"
p2 = sh.ExpandEnvironmentStrings("%ProgramFiles%") & "\Microsoft\Edge\Application\msedge.exe"

If fso.FileExists(p1) Then
  edge = p1
ElseIf fso.FileExists(p2) Then
  edge = p2
Else
  edge = ""
End If

If edge <> "" Then
  launch = """" & edge & """" & " --app=""" & url & """ --user-data-dir=""" & profile & """"
  launch = launch & " --no-first-run --no-default-browser-check --no-service-autorun"
  launch = launch & " --disable-component-update --disable-background-networking --disable-sync"
  launch = launch & " --disk-cache-size=52428800 --window-size=1300,900"
  sh.Run launch, 1, False
Else
  sh.Run """" & base & "\index.html""", 1, False
End If
