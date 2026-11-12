@echo off
rem School IT Hub — w przeglądarce (gdyby okno programu się nie otwierało)
cd /d "%~dp0aplikacja"
if not exist ".venv\Scripts\python.exe" (
  echo Najpierw uruchom instalacja-windows.bat
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -m wolnesale --browser %*
