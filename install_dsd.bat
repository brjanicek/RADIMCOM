@echo off
rem Downloads the DSD-FME decoder for the DSD mode (not part of the RADIMCOM package, see install_dsd.py).
cd /d "%~dp0"
set "PY=python"
if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"
if exist "python\python.exe" set "PY=python\python.exe"
"%PY%" install_dsd.py
pause
