@echo off
rem Starts the receiver in this console window; after a moment it opens the page in the browser.
rem Normally RADIMCOM.exe is used (own app window, tray icon); start.bat stays for troubleshooting.
cd /d "%~dp0"
set "PY=python"
if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"
if exist "python\python.exe" set "PY=python\python.exe"
start "" /min cmd /c "timeout /t 10 /nobreak >nul & start http://localhost:8434"
"%PY%" app.py
pause
