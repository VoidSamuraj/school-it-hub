@echo off
rem Wolne Sale — okno programu
cd /d "%~dp0aplikacja"
start "" ".venv\Scripts\pythonw.exe" -m wolnesale
