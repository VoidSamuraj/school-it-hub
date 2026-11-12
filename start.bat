@echo off
rem School IT Hub — uruchomienie (okno programu). Opcje: --browser, --siec, --demo
cd /d "%~dp0aplikacja"
if not exist ".venv\Scripts\pythonw.exe" (
  echo Najpierw uruchom instalacja-windows.bat
  pause
  exit /b 1
)
start "" ".venv\Scripts\pythonw.exe" -m wolnesale %*
