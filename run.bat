@echo off
set PYTHONUTF8=1
cd /d "%~dp0"
py -3.10 -X utf8 run_services.py
pause
