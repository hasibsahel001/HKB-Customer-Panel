
Set WshShell = CreateObject("WScript.Shell")

WshShell.CurrentDirectory = "C:\Users\Cyber Phantom\Documents\Caddy"
WshShell.Run """C:\Users\Cyber Phantom\Documents\Caddy\caddy.exe"" run --config ""C:\Users\Cyber Phantom\Documents\Caddy\Caddyfile"" --adapter caddyfile", 0, False

WScript.Sleep 3000

WshShell.CurrentDirectory = "C:\Users\Cyber Phantom\Documents\hkb-panel"
WshShell.Run "cmd.exe /c ""C:\Users\Cyber Phantom\Documents\hkb-panel\run-panel.bat""", 0, False
