Option Explicit
Dim fso, shell, base, py, cmd
Set fso = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")
base = fso.GetParentFolderName(WScript.ScriptFullName)
py = "pythonw.exe"
If Not fso.FileExists(shell.ExpandEnvironmentStrings("%LocalAppData%\Programs\Python\Python314\pythonw.exe")) Then py = "pyw.exe"
cmd = Chr(34) & py & Chr(34) & " " & Chr(34) & base & "\server.py" & Chr(34)
shell.CurrentDirectory = base
shell.Run cmd, 0, False
