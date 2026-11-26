@echo off
rem Downloads what the ATC speech to text needs: faster-whisper into lib\whisper and the Whisper model (see install_atc.py).
cd /d "%~dp0"
set "PY=python"
if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"
if exist "python\python.exe" set "PY=python\python.exe"
"%PY%" install_atc.py %*
pause
