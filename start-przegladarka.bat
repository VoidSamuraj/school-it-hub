@echo off
rem Wolne Sale — w przeglądarce (gdyby okno programu się nie otwierało)
cd /d "%~dp0aplikacja"
".venv\Scripts\python.exe" -m wolnesale --browser
