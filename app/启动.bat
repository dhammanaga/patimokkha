@echo off
chcp 65001 >nul 2>&1
cd /d "%~dp0"
echo Starting server...
start "" http://127.0.0.1:8151/index.html
C:\Users\dhamm\.workbuddy\binaries\python\versions\3.13.12\python.exe _redraw_server.py 8151
pause
