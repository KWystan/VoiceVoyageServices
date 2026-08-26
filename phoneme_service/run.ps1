$env:PYTHONUTF8 = "1"
Set-Location "$PSScriptRoot\.."
py -3.10 -X utf8 run.py
